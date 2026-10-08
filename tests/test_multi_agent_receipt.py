from __future__ import annotations

import copy

import pytest

import cleanroomx.multi_agent as multi_agent
from cleanroomx.multi_agent import (
    AgentReply,
    ChatSessionStore,
    MultiAgentCoordinator,
    verify_agent_batch_result,
)


def _coordinator():
    store = ChatSessionStore()
    store.create_session("chat", "Receipt test")
    coordinator = MultiAgentCoordinator(store)
    return store, coordinator


def test_agent_batch_receipt_round_trip_detects_nested_tamper():
    _store, coordinator = _coordinator()
    coordinator.register_agent(
        "requirements",
        lambda request: AgentReply(
            "Requirements checked.",
            {"task": request.task_id, "value": 1},
        ),
    )

    batch = coordinator.run(
        "chat",
        "review",
        agent_ids=["requirements"],
        task_id="task-receipt",
    )

    document = batch.to_dict()
    assert document["schema"] == "cleanroomx.multi-agent-batch"
    assert document["schema_version"] == 1
    assert document["canonicalization"] == "json-sort-keys-compact-utf8-v1"
    assert document["integrity"]["algorithm"] == "sha256"
    assert len(document["integrity"]["sha256"]) == 64
    assert verify_agent_batch_result(document) == document

    tampered = copy.deepcopy(document)
    tampered["results"][0]["data"]["value"] = 2
    with pytest.raises(ValueError, match="integrity check failed"):
        verify_agent_batch_result(tampered)


def test_agent_batch_verifier_rejects_semantically_inconsistent_valid_digest():
    _store, coordinator = _coordinator()
    coordinator.register_agent(
        "requirements",
        lambda _request: "ok",
    )
    batch = coordinator.run(
        "chat",
        "review",
        agent_ids=["requirements"],
        task_id="task-semantic",
    )
    document = batch.to_dict()

    document["specialist_agent_ids"] = ["verification"]
    unsigned = copy.deepcopy(document)
    unsigned.pop("integrity")
    document["integrity"]["sha256"] = multi_agent._canonical_json_sha256(unsigned)

    with pytest.raises(ValueError, match="requested agent order"):
        verify_agent_batch_result(document)


def test_committed_transcript_carries_one_batch_receipt():
    store, coordinator = _coordinator()
    coordinator.register_agent(
        "requirements",
        lambda _request: AgentReply("Requirements checked.", {"ok": True}),
    )
    coordinator.register_agent(
        "verification",
        lambda _request: AgentReply("Verification checked.", {"ok": True}),
    )
    coordinator.register_agent(
        "coordinator",
        lambda request: AgentReply(
            "Synthesis complete.",
            {"peer_count": len(request.peer_results)},
        ),
    )

    batch = coordinator.run(
        "chat",
        "review",
        agent_ids=["requirements", "verification"],
        synthesizer_agent_id="coordinator",
        task_id="task-transcript-receipt",
    )

    session = store.get_session("chat")
    assistants = [
        message
        for message in session.messages
        if message.role == "assistant"
    ]
    assert len(assistants) == 3
    assert batch.output_revision == session.revision

    receipt = batch.receipt()
    assert receipt["task_id"] == "task-transcript-receipt"
    assert receipt["session_id"] == "chat"
    assert receipt["commit_state"] == "committed"
    assert receipt["input_revision"] == 1
    assert receipt["output_revision"] == session.revision
    assert receipt["sha256"] == batch.to_dict()["integrity"]["sha256"]
    for message in assistants:
        assert message.metadata["batch_receipt"] == receipt
        assert (
            message.metadata["multi_agent_task_id"]
            == "task-transcript-receipt"
        )


def test_conflicted_batch_receipt_is_not_written_to_transcript():
    store, coordinator = _coordinator()

    def conflicting_agent(request):
        store.append_message(
            "chat",
            role="user",
            content="concurrent change",
            expected_revision=request.session.revision,
            expected_instance_id=request.session.instance_id,
        )
        return "stale result"

    coordinator.register_agent("slow", conflicting_agent)

    batch = coordinator.run(
        "chat",
        "review",
        agent_ids=["slow"],
        task_id="task-conflict-receipt",
    )

    assert batch.commit_state == "conflict"
    assert batch.output_revision is None
    verify_agent_batch_result(batch.to_dict())

    session = store.get_session("chat")
    assert [message.role for message in session.messages] == ["user", "user"]
    assert all(
        "batch_receipt" not in message.metadata
        for message in session.messages
    )


@pytest.mark.parametrize("schema_version", (True, 1.0))
def test_batch_receipt_rejects_noninteger_schema_version_even_with_matching_digest(
    schema_version,
):
    _store, coordinator = _coordinator()
    coordinator.register_agent("requirements", lambda _request: "ok")
    batch = coordinator.run(
        "chat", "review", agent_ids=["requirements"], task_id="task-version"
    )
    document = batch.to_dict()
    document["schema_version"] = schema_version
    unsigned = copy.deepcopy(document)
    unsigned.pop("integrity")
    document["integrity"]["sha256"] = multi_agent._canonical_json_sha256(unsigned)

    with pytest.raises(ValueError, match="agent batch schema version"):
        verify_agent_batch_result(document)


@pytest.mark.parametrize("with_synthesis", (False, True))
@pytest.mark.parametrize("revision_delta", (-1, 1, 9))
def test_batch_verifier_rejects_rehashed_inconsistent_commit_revision(
    with_synthesis, revision_delta
):
    _store, coordinator = _coordinator()
    coordinator.register_agent("requirements", lambda _request: "ok")
    coordinator.register_agent("verification", lambda _request: "ok")
    if with_synthesis:
        coordinator.register_agent("reviewer", lambda _request: "reviewed")

    batch = coordinator.run(
        "chat",
        "check",
        agent_ids=["requirements", "verification"],
        synthesizer_agent_id="reviewer" if with_synthesis else None,
        task_id="task-revision-integrity",
    )
    assert batch.output_revision == batch.input_revision + 2 + int(with_synthesis)
    verify_agent_batch_result(batch.to_dict())

    forged = copy.deepcopy(batch.to_dict())
    forged["output_revision"] += revision_delta
    unsigned = copy.deepcopy(forged)
    unsigned.pop("integrity")
    forged["integrity"]["sha256"] = multi_agent._canonical_json_sha256(unsigned)

    with pytest.raises(
        ValueError, match="output_revision must equal input_revision"
    ):
        verify_agent_batch_result(forged)


def test_batch_revision_counts_failed_assistant_records():
    store, coordinator = _coordinator()

    def fail(_request):
        raise RuntimeError("deliberate failure")

    coordinator.register_agent("failed", fail)
    coordinator.register_agent("ok", lambda _request: "ready")
    coordinator.register_agent("failed-synthesis", fail)

    batch = coordinator.run(
        "chat",
        "check",
        agent_ids=["failed", "ok"],
        synthesizer_agent_id="failed-synthesis",
        task_id="task-error-count-revision",
    )

    assert batch.commit_state == "committed"
    assert batch.error_count == 2
    assert batch.output_revision == batch.input_revision + 3
    assert store.get_session("chat").revision == batch.output_revision
    assert verify_agent_batch_result(batch.to_dict()) == batch.to_dict()
