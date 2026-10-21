from __future__ import annotations

import json

import pytest

from cleanroomx.ai_assistant import (
    AIProviderError,
    OpenAIResponsesClient,
    ProjectAdviceAgent,
    load_project_context,
    register_project_advice_agent,
)
from cleanroomx.ai_assistant_cli import main as ai_main
from cleanroomx.multi_agent import ChatSessionStore, MultiAgentCoordinator
from cleanroomx.project import AnalysisDocument, ProjectDocument, save_project_document


def _project(tmp_path):
    path = tmp_path / "facility.cleanroomx.json"
    save_project_document(
        path,
        ProjectDocument(
            name="Test facility",
            description="Metadata only",
            metadata={"private_note": "DO_NOT_SEND_THIS_SECRET"},
            analyses=[
                AnalysisDocument(
                    id="air-review",
                    name="Air review",
                    kind="air_system_design",
                    input={"design": {"private": "DO_NOT_SEND_THIS_SECRET"}},
                )
            ],
        ),
    )
    return path


def _ask(path, *, client=None, question="What should I inspect?"):
    store = ChatSessionStore()
    store.create_session("project-review", "Project review")
    coordinator = MultiAgentCoordinator(store)
    register_project_advice_agent(
        coordinator,
        project_path=path,
        client=client,
    )
    return coordinator.run(
        "project-review",
        question,
        agent_ids=["project-advisor"],
        task_id="ai-test-task",
    )


def test_offline_review_reads_only_saved_metadata(tmp_path):
    path = _project(tmp_path)
    original = path.read_bytes()
    snapshot = load_project_context(path)
    assert snapshot.metadata["analysis_count"] == 1
    assert snapshot.metadata["analyses"][0]["id"] == "air-review"
    assert snapshot.metadata["evidence_status"] == "not_verified"
    assert "DO_NOT_SEND_THIS_SECRET" not in json.dumps(snapshot.metadata)
    batch = _ask(path)
    assert batch.commit_state == "committed"
    assert batch.error_count == 0
    assert "NOT VERIFIED" in batch.results[0].content
    assert batch.results[0].data["read_only"] is True
    assert path.read_bytes() == original


def test_opt_in_provider_only_receives_bounded_metadata(tmp_path):
    path = _project(tmp_path)
    sent = []

    class FakeClient:
        model = "test-model"

        def answer(self, *, question, context, history):
            sent.append((question, context, history))
            return "Check the configured analysis before interpreting any result."

    batch = _ask(path, client=FakeClient())
    assert batch.error_count == 0
    assert batch.results[0].data["provider"] == "openai"
    assert batch.results[0].data["engineering_evidence_status"] == "not_verified"
    assert len(sent) == 1
    assert sent[0][0] == "What should I inspect?"
    assert sent[0][1]["analyses"][0]["id"] == "air-review"
    assert "DO_NOT_SEND_THIS_SECRET" not in json.dumps(sent[0][1])


def test_source_modified_during_provider_call_never_commits_advice(tmp_path):
    path = _project(tmp_path)

    class MutatingClient:
        model = "test-model"

        def answer(self, *, question, context, history):
            path.write_bytes(path.read_bytes() + b" ")
            return "Stale, must not commit"

    batch = _ask(path, client=MutatingClient())
    assert batch.results[0].state == "error"
    assert batch.results[0].error_type == "ProjectChangedDuringAIReview"
    assert "Stale, must not commit" not in batch.results[0].content


def test_openai_provider_requires_explicit_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = OpenAIResponsesClient()
    with pytest.raises(AIProviderError, match="OPENAI_API_KEY"):
        client.answer(question="Review", context={"name": "Sample"})


def test_openai_provider_posts_no_storage_and_parses_completed_text(monkeypatch):
    from cleanroomx import ai_assistant

    monkeypatch.setenv("OPENAI_API_KEY", "test-private-api-key")
    requests = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return json.dumps({
                "status": "completed",
                "output": [{
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "No validated CFD evidence."}],
                }],
            }).encode("utf-8")

    def mock_urlopen(req, timeout):
        requests.append((req, timeout))
        return FakeResponse()

    monkeypatch.setattr(ai_assistant.urlrequest, "urlopen", mock_urlopen)
    answer = OpenAIResponsesClient(model="test-model").answer(
        question="What is verified?",
        context={"name": "Sample", "evidence_status": "not_verified"},
    )
    assert answer == "No validated CFD evidence."
    assert len(requests) == 1
    req = requests[0][0]
    assert req.full_url == "https://api.openai.com/v1/responses"
    payload = json.loads(req.data)
    assert payload["store"] is False
    assert payload["max_output_tokens"] == 800
    assert payload["model"] == "test-model"
    assert "What is verified?" in payload["input"][-1]["content"]
    assert "test-private-api-key" not in req.data.decode("utf-8")


def test_openai_provider_rejects_incomplete_response(monkeypatch):
    from cleanroomx import ai_assistant

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return b'{"status":"incomplete","output":[]}'

    monkeypatch.setattr(
        ai_assistant.urlrequest,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(),
    )
    with pytest.raises(AIProviderError, match="invalid or incomplete"):
        OpenAIResponsesClient().answer(question="Review", context={})


def test_cli_saves_isolated_workspace_and_never_overwrites_project(tmp_path, capsys):
    path = _project(tmp_path)
    workspace = tmp_path / "assistant-chats.json"
    original = path.read_bytes()
    assert ai_main([str(path), "List saved analyses", "--workspace", str(workspace)]) == 0
    assert "NOT VALIDATED ENGINEERING EVIDENCE" in capsys.readouterr().out
    assert workspace.is_file()
    assert path.read_bytes() == original
    assert ai_main([str(path), "Another question", "--workspace", str(workspace)]) == 0
    data = json.loads(workspace.read_text(encoding="utf-8"))
    assert len(data["sessions"]) == 1
    assert data["sessions"][0]["revision"] == 4


def test_cli_refuses_to_use_project_as_workspace(tmp_path):
    path = _project(tmp_path)
    with pytest.raises(SystemExit):
        ai_main([str(path), "Review", "--workspace", str(path)])
