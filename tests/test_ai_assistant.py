from __future__ import annotations

import hashlib
import json

import pytest

from cleanroomx.ai_assistant import (
    AssistantEvidenceError,
    EvidenceReviewAgent,
    LocalModelError,
    LocalOllamaClient,
    collect_review_evidence,
    register_local_ai_reviewer,
)
from cleanroomx.multi_agent import (
    AgentExecution,
    AgentReply,
    AgentRequest,
    ChatSessionStore,
    MultiAgentCoordinator,
)
from cleanroomx.multi_agent_project import (
    PROJECT_AGENT_RESULT_SCHEMA,
    PROJECT_AGENT_RESULT_SCHEMA_VERSION,
)


def _data(
    *,
    task_id="task-test",
    session_id="review",
    analysis_id="a1",
    sha="a" * 64,
    name="Facility A",
):
    return {
        "schema": PROJECT_AGENT_RESULT_SCHEMA,
        "schema_version": PROJECT_AGENT_RESULT_SCHEMA_VERSION,
        "task_id": task_id,
        "session_id": session_id,
        "project": {
            "name": name,
            "source_revision": {"size_bytes": 145, "sha256": sha},
        },
        "analysis": {"id": analysis_id, "name": "Airflow", "kind": "airflow"},
        "run": {"status": "completed", "outputs": {"airflow": 100}},
    }


def _request(*records, phase="synthesis", task_id="task-test"):
    store = ChatSessionStore()
    store.create_session("review", "Review")
    return AgentRequest(
        task_id=task_id,
        phase=phase,
        session=store.get_session("review"),
        prompt="Can this room be certified?",
        shared_input={},
        peer_results=tuple(records),
    )


def _record(agent_id, data=None, *, state="completed"):
    return AgentExecution(
        agent_id=agent_id,
        state=state,
        data=data or {},
        error_type="RuntimeError" if state == "error" else None,
        error_message="failed" if state == "error" else None,
    )


def test_evidence_packet_is_task_bound_and_content_hashed():
    evidence = collect_review_evidence(
        _request(_record("analysis-1", _data()))
    )
    assert evidence["project"]["source_sha256"] == "a" * 64
    assert evidence["analyses"][0]["analysis"]["id"] == "a1"
    unsigned = {k: v for k, v in evidence.items() if k != "evidence_sha256"}
    canonical = json.dumps(
        unsigned, sort_keys=True, ensure_ascii=False,
        allow_nan=False, separators=(",", ":"),
    ).encode("utf-8")
    assert evidence["evidence_sha256"] == hashlib.sha256(canonical).hexdigest()
    assert evidence["advisory_only"] is True


@pytest.mark.parametrize(
    "request",
    [
        _request(),
        _request(_record("analysis-1", _data()), phase="specialist"),
        _request(_record("analysis-1", _data(task_id="wrong"))),
        _request(_record("analysis-1", _data(session_id="other"))),
        _request(_record("analysis-1", _data(sha="not a hash"))),
        _request(_record("analysis-1", {"schema": "fabricated"})),
        _request(_record("analysis-1", _data(), state="error")),
        _request(
            _record("analysis-1", _data(analysis_id="a1")),
            _record("analysis-2", _data(analysis_id="a1")),
        ),
        _request(
            _record("analysis-1", _data(analysis_id="a1")),
            _record("analysis-2", _data(analysis_id="a2", sha="b" * 64)),
        ),
        _request(
            _record("analysis-1", _data(analysis_id="a1")),
            _record("analysis-2", _data(analysis_id="a2", name="Facility B")),
        ),
    ],
)
def test_review_rejects_unusable_evidence(request):
    with pytest.raises(AssistantEvidenceError):
        collect_review_evidence(request)


def test_model_is_not_called_when_evidence_is_missing():
    called = []
    agent = EvidenceReviewAgent(
        LocalOllamaClient("local-model"),
        reply_provider=lambda messages: called.append(messages) or "unverified",
    )
    with pytest.raises(AssistantEvidenceError):
        agent(_request(_record("other-agent", {"schema": "untrusted"})))
    assert called == []


def test_review_uses_local_model_only_as_advisory():
    seen = []

    def respond(messages):
        seen.append(messages)
        return "Not demonstrated by these results."

    agent = EvidenceReviewAgent(
        LocalOllamaClient("local-model"),
        reply_provider=respond,
    )
    reply = agent(_request(_record("analysis-1", _data())))
    assert reply.content.startswith("AI ADVISORY (NOT ENGINEERING VERIFICATION)")
    assert reply.data["advisory_only"] is True
    assert reply.data["analysis_ids"] == ["a1"]
    assert len(seen) == 1
    assert seen[0][0]["role"] == "system"
    assert "never claim iso 14644 compliance" in seen[0][0]["content"].lower()
    sent = json.loads(seen[0][1]["content"])
    assert sent["question"] == "Can this room be certified?"
    assert sent["evidence"]["analyses"][0]["run"]["outputs"]["airflow"] == 100


def test_review_must_not_return_empty_answer():
    agent = EvidenceReviewAgent(
        LocalOllamaClient("local-model"),
        reply_provider=lambda messages: "  ",
    )
    with pytest.raises(LocalModelError):
        agent(_request(_record("analysis-1", _data())))


def test_coordinator_runs_specialists_then_opt_in_review_with_receipt():
    store = ChatSessionStore()
    store.create_session("review", "Review")
    coordinator = MultiAgentCoordinator(store)
    coordinator.register_agent(
        "analysis-1",
        lambda request: AgentReply(
            "completed",
            _data(task_id=request.task_id, session_id=request.session.id),
        ),
    )
    register_local_ai_reviewer(
        coordinator,
        model="local-model",
        reply_provider=lambda messages: "Engineering review is inconclusive.",
    )
    batch = coordinator.run(
        "review", "Examine results",
        agent_ids=["analysis-1"],
        synthesizer_agent_id="ai-reviewer",
        task_id="task-test",
    )
    assert batch.commit_state == "committed"
    assert batch.error_count == 0
    assert batch.synthesis is not None
    assert batch.synthesis.state == "completed"
    assert batch.synthesis.data["advisory_only"] is True
    assert store.get_session("review").revision == 3


def test_invalid_project_evidence_produces_explicit_agent_error():
    store = ChatSessionStore()
    store.create_session("review", "Review")
    coordinator = MultiAgentCoordinator(store)
    coordinator.register_agent("untrusted", lambda request: {"value": 1})
    register_local_ai_reviewer(
        coordinator, model="local-model",
        reply_provider=lambda messages: "Should not be called",
    )
    batch = coordinator.run(
        "review", "Examine results",
        agent_ids=["untrusted"], synthesizer_agent_id="ai-reviewer",
        task_id="task-test",
    )
    assert batch.synthesis is not None
    assert batch.synthesis.state == "error"
    assert batch.synthesis.error_type == "AssistantEvidenceError"
    assert batch.error_count == 1


@pytest.mark.parametrize("kwargs", [
    {"model": ""}, {"model": "x with spaces"},
    {"model": "x", "port": 0}, {"model": "x", "port": True},
    {"model": "x", "timeout": 0}, {"model": "x", "timeout": True},
])
def test_local_model_rejects_unsafe_configuration(kwargs):
    with pytest.raises(ValueError):
        LocalOllamaClient(**kwargs)


def test_local_model_handles_mocked_ollama_reply(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, size):
            assert size > 0
            return json.dumps({
                "message": {"role": "assistant", "content": "Insufficient evidence."}
            }).encode("utf-8")

    class Opener:
        def open(self, request, timeout):
            assert request.full_url == "http://127.0.0.1:11434/api/chat"
            assert json.loads(request.data)["stream"] is False
            return Response()

    monkeypatch.setattr(
        "cleanroomx.ai_assistant.build_opener",
        lambda *args: Opener(),
    )
    assert LocalOllamaClient("local-model").chat(
        [{"role": "user", "content": "review"}]
    ) == "Insufficient evidence."
