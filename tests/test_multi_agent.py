from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest

from cleanroomx.multi_agent import (
    AgentReply,
    ChatSessionStore,
    MultiAgentCoordinator,
    SessionIncarnationConflict,
    SessionRevisionConflict,
)


def test_chat_sessions_are_isolated_and_revision_checked():
    store = ChatSessionStore()
    a = store.create_session("chat-a", "A")
    b = store.create_session("chat-b", "B")

    store.append_message(
        "chat-a",
        role="user",
        content="alpha",
        expected_revision=a.revision,
    )

    assert [
        message.content
        for message in store.get_session("chat-a").messages
    ] == ["alpha"]
    assert store.get_session("chat-b").messages == ()
    assert store.get_session("chat-b").revision == b.revision

    with pytest.raises(SessionRevisionConflict):
        store.append_message(
            "chat-a",
            role="user",
            content="stale",
            expected_revision=0,
        )


def test_store_round_trip_preserves_multiple_chats(tmp_path):
    store = ChatSessionStore()
    store.create_session(
        "design",
        "Design",
        metadata={"project": "CR-01"},
    )
    store.create_session("verify", "Verify")
    store.append_message(
        "design",
        role="user",
        content="size airflow",
    )
    store.append_message(
        "verify",
        role="assistant",
        content="evidence ready",
        agent_id="evidence",
        metadata={"score": 1.0},
    )

    path = tmp_path / "workspace.json"
    store.save(path)
    loaded = ChatSessionStore.load(path)

    assert loaded.to_dict() == store.to_dict()


def test_parallel_agents_commit_in_requested_order_not_completion_order():
    store = ChatSessionStore()
    store.create_session("chat", "Parallel")
    coordinator = MultiAgentCoordinator(
        store,
        max_workers=2,
    )

    release_first = Event()
    second_finished = Event()

    def slow(_request):
        second_finished.wait(timeout=2)
        release_first.wait(timeout=2)
        return "first"

    def fast(_request):
        second_finished.set()
        release_first.set()
        return "second"

    coordinator.register_agent("slow", slow)
    coordinator.register_agent("fast", fast)

    batch = coordinator.run(
        "chat",
        "go",
        agent_ids=["slow", "fast"],
        task_id="task-order",
    )

    assert batch.commit_state == "committed"
    assert [
        result.agent_id
        for result in batch.results
    ] == ["slow", "fast"]
    session = store.get_session("chat")
    assert [
        (message.agent_id, message.content)
        for message in session.messages[1:]
    ] == [
        ("slow", "first"),
        ("fast", "second"),
    ]


def test_agent_failure_is_isolated_and_recorded():
    store = ChatSessionStore()
    store.create_session("chat", "Failure isolation")
    coordinator = MultiAgentCoordinator(store)

    coordinator.register_agent(
        "ok",
        lambda request: AgentReply(
            "done",
            {"phase": request.phase},
        ),
    )

    def broken(_request):
        raise RuntimeError("boom")

    coordinator.register_agent("broken", broken)

    batch = coordinator.run(
        "chat",
        "go",
        agent_ids=["ok", "broken"],
        task_id="task-fail",
    )

    assert batch.error_count == 1
    assert batch.results[0].state == "completed"
    assert batch.results[1].state == "error"
    assert batch.results[1].error_type == "RuntimeError"
    assert "boom" in store.get_session("chat").messages[-1].content


def test_synthesizer_receives_specialist_results():
    store = ChatSessionStore()
    store.create_session("chat", "Synthesis")
    coordinator = MultiAgentCoordinator(store)

    coordinator.register_agent(
        "requirements",
        lambda _request: "R",
    )
    coordinator.register_agent(
        "hvac",
        lambda _request: {"airflow": 1200},
    )

    def synth(request):
        assert request.phase == "synthesis"
        assert [
            result.agent_id
            for result in request.peer_results
        ] == ["requirements", "hvac"]
        assert request.peer_results[1].data["airflow"] == 1200
        return "merged"

    coordinator.register_agent(
        "coordinator",
        synth,
    )

    batch = coordinator.run(
        "chat",
        "review",
        agent_ids=["requirements", "hvac"],
        synthesizer_agent_id="coordinator",
        task_id="task-synth",
    )

    assert batch.synthesis is not None
    assert batch.synthesis.content == "merged"
    assert (
        store.get_session("chat").messages[-1].agent_id
        == "coordinator"
    )


def test_same_session_concurrent_change_prevents_stale_agent_output_commit():
    store = ChatSessionStore()
    store.create_session("chat", "Conflict")
    coordinator = MultiAgentCoordinator(store)

    started = Event()
    release = Event()

    def agent(_request):
        started.set()
        release.wait(timeout=2)
        return "stale output"

    coordinator.register_agent("worker", agent)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            coordinator.run,
            "chat",
            "long task",
            agent_ids=["worker"],
            task_id="task-conflict",
        )
        assert started.wait(timeout=2)
        current = store.get_session("chat")
        store.append_message(
            "chat",
            role="user",
            content="newer message",
            expected_revision=current.revision,
        )
        release.set()
        batch = future.result(timeout=2)

    assert batch.commit_state == "conflict"
    assert batch.output_revision is None
    assert all(
        message.content != "stale output"
        for message in store.get_session("chat").messages
    )


def test_different_chats_can_run_concurrently_without_cross_contamination():
    store = ChatSessionStore()
    store.create_session("chat-a", "A")
    store.create_session("chat-b", "B")
    coordinator = MultiAgentCoordinator(
        store,
        max_workers=2,
    )
    barrier = Barrier(2)

    def echo(request):
        barrier.wait(timeout=2)
        return f"{request.session.id}:{request.prompt}"

    coordinator.register_agent("worker", echo)

    with ThreadPoolExecutor(max_workers=2) as executor:
        a = executor.submit(
            coordinator.run,
            "chat-a",
            "alpha",
            agent_ids=["worker"],
            task_id="task-a",
        )
        b = executor.submit(
            coordinator.run,
            "chat-b",
            "beta",
            agent_ids=["worker"],
            task_id="task-b",
        )
        assert a.result(timeout=3).commit_state == "committed"
        assert b.result(timeout=3).commit_state == "committed"

    assert [
        message.content
        for message in store.get_session("chat-a").messages
    ] == [
        "alpha",
        "chat-a:alpha",
    ]
    assert [
        message.content
        for message in store.get_session("chat-b").messages
    ] == [
        "beta",
        "chat-b:beta",
    ]


def test_unknown_and_duplicate_agents_fail_before_chat_mutation():
    store = ChatSessionStore()
    store.create_session("chat", "Validation")
    coordinator = MultiAgentCoordinator(store)
    coordinator.register_agent(
        "worker",
        lambda _request: "ok",
    )

    with pytest.raises(ValueError, match="duplicates"):
        coordinator.run(
            "chat",
            "go",
            agent_ids=["worker", "worker"],
        )
    with pytest.raises(ValueError, match="unknown agent"):
        coordinator.run(
            "chat",
            "go",
            agent_ids=["missing"],
        )

    assert store.get_session("chat").revision == 0


def test_session_incarnation_guard_rejects_delete_recreate_aba():
    store = ChatSessionStore()
    original = store.create_session("chat", "Original")
    store.append_message(
        "chat",
        role="user",
        content="original",
        expected_revision=original.revision,
        expected_instance_id=original.instance_id,
    )

    store.delete_session("chat")
    replacement = store.create_session("chat", "Replacement")
    replacement = store.append_message(
        "chat",
        role="user",
        content="replacement",
        expected_revision=replacement.revision,
        expected_instance_id=replacement.instance_id,
    )

    with pytest.raises(SessionIncarnationConflict):
        store.append_message(
            "chat",
            role="assistant",
            content="stale",
            expected_revision=replacement.revision,
            expected_instance_id=original.instance_id,
        )

    assert [
        message.content
        for message in store.get_session("chat").messages
    ] == ["replacement"]


def test_stale_batch_after_delete_recreate_never_commits_to_replacement_chat():
    store = ChatSessionStore()
    store.create_session("chat", "Original")
    coordinator = MultiAgentCoordinator(store)

    started = Event()
    release = Event()

    def worker(_request):
        started.set()
        release.wait(timeout=2)
        return "stale output"

    coordinator.register_agent("worker", worker)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            coordinator.run,
            "chat",
            "long task",
            agent_ids=["worker"],
            task_id="task-aba",
        )
        assert started.wait(timeout=2)

        store.delete_session("chat")
        replacement = store.create_session(
            "chat",
            "Replacement",
        )
        store.append_message(
            "chat",
            role="user",
            content="replacement",
            expected_revision=replacement.revision,
            expected_instance_id=replacement.instance_id,
        )
        release.set()
        batch = future.result(timeout=2)

    assert batch.commit_state == "conflict"
    assert batch.output_revision is None
    assert [
        message.content
        for message in store.get_session("chat").messages
    ] == ["replacement"]


def test_stale_session_skips_synthesis_before_expensive_follow_up():
    store = ChatSessionStore()
    store.create_session("chat", "Stale synthesis")
    coordinator = MultiAgentCoordinator(store)

    started = Event()
    release = Event()
    synthesis_called = Event()

    def specialist(_request):
        started.set()
        release.wait(timeout=2)
        return "specialist"

    def synth(_request):
        synthesis_called.set()
        return "summary"

    coordinator.register_agent("worker", specialist)
    coordinator.register_agent("coordinator", synth)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            coordinator.run,
            "chat",
            "long task",
            agent_ids=["worker"],
            synthesizer_agent_id="coordinator",
            task_id="task-stale-synth",
        )
        assert started.wait(timeout=2)
        current = store.get_session("chat")
        store.append_message(
            "chat",
            role="user",
            content="newer message",
            expected_revision=current.revision,
            expected_instance_id=current.instance_id,
        )
        release.set()
        batch = future.result(timeout=2)

    assert batch.commit_state == "conflict"
    assert batch.synthesis is None
    assert not synthesis_called.is_set()
