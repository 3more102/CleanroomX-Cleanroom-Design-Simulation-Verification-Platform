from __future__ import annotations

import copy
import json
from urllib.error import HTTPError

import pytest

from cleanroomx.ai_assistant import (
    AssistantConfiguration,
    AssistantConfigurationError,
    AssistantProviderError,
    CLOUD_URL,
    LOCAL_URL,
    ask_model,
    build_assistant_context,
    format_offline_review,
    project_snapshot_sha256,
)
from cleanroomx.project import new_project


def test_read_only_context_is_bounded_and_does_not_change_project():
    project = new_project()
    before = copy.deepcopy(project.to_dict())

    context = build_assistant_context(project)
    review = format_offline_review(context)

    assert project.to_dict() == before
    assert context["schema"] == "cleanroomx.ai-assistant-context"
    assert context["project"]["in_memory_sha256"] == project_snapshot_sha256(project)
    assert context["diagnostics"]["summary"]["status"] in ("pass", "warning", "error")
    assert "LOCAL EVIDENCE REVIEW" in review
    assert "not an AI model" in review
    assert "certification" in review
    assert not any("input" in item for item in context["project"]["analyses"])


def test_bad_finding_limit_fails_closed():
    with pytest.raises(ValueError):
        build_assistant_context(new_project(), max_findings=0)
    with pytest.raises(ValueError):
        build_assistant_context(new_project(), max_findings=True)


def test_provider_defaults_to_local_only(monkeypatch):
    monkeypatch.delenv("CLEANROOMX_AI_PROVIDER", raising=False)
    monkeypatch.delenv("CLEANROOMX_AI_MODEL", raising=False)
    cfg = AssistantConfiguration.from_environment()
    assert cfg.endpoint == LOCAL_URL
    assert cfg.provider == "ollama"
    assert cfg.api_key is None


def test_cloud_requires_explicit_opt_in_and_secret(monkeypatch):
    monkeypatch.setenv("CLEANROOMX_AI_PROVIDER", "openai")
    monkeypatch.setenv("CLEANROOMX_AI_MODEL", "selected-model")
    monkeypatch.delenv("CLEANROOMX_AI_ALLOW_CLOUD", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "not-a-real-secret")
    with pytest.raises(AssistantConfigurationError, match="ALLOW_CLOUD"):
        AssistantConfiguration.from_environment()

    monkeypatch.setenv("CLEANROOMX_AI_ALLOW_CLOUD", "1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(AssistantConfigurationError, match="OPENAI_API_KEY"):
        AssistantConfiguration.from_environment()

    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    cfg = AssistantConfiguration.from_environment()
    assert cfg.endpoint == CLOUD_URL


def test_model_uses_bounded_project_snapshot_without_executing_work(monkeypatch):
    project = new_project()
    context = build_assistant_context(project)
    sent = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return json.dumps({
                "choices": [{"message": {"content": "Review the configuration first."}}]
            }).encode("utf-8")

    def fake_urlopen(request, timeout):
        sent["request"] = request
        sent["timeout"] = timeout
        return Response()

    monkeypatch.setattr("cleanroomx.ai_assistant.urlopen", fake_urlopen)
    answer = ask_model(
        "What needs checking?",
        context,
        configuration=AssistantConfiguration("ollama", "llama3.2", LOCAL_URL),
    )
    assert answer == "Review the configuration first."
    assert sent["request"].full_url == LOCAL_URL
    assert sent["timeout"] == 30
    body = json.loads(sent["request"].data)
    assert body["stream"] is False
    assert body["messages"][0]["role"] == "system"
    assert "Project diagnostic snapshot" in body["messages"][1]["content"]
    assert project_snapshot_sha256(project) == context["project"]["in_memory_sha256"]


def test_rejects_unapproved_endpoint_before_network(monkeypatch):
    context = build_assistant_context(new_project())
    def no_network(*_args, **_kwargs):
        raise AssertionError("No network should be called")
    monkeypatch.setattr("cleanroomx.ai_assistant.urlopen", no_network)
    with pytest.raises(AssistantConfigurationError, match="Invalid local"):
        ask_model(
            "Review",
            context,
            configuration=AssistantConfiguration(
                "ollama", "model", "http://evil.example/v1/chat/completions"
            ),
        )


def test_http_failure_does_not_expose_api_key(monkeypatch):
    context = build_assistant_context(new_project())
    secret = "highly-sensitive-test-key"
    def fails(*_args, **_kwargs):
        raise HTTPError(CLOUD_URL, 401, "Unauthorized", {}, None)
    monkeypatch.setattr("cleanroomx.ai_assistant.urlopen", fails)
    with pytest.raises(AssistantProviderError, match="HTTP 401") as exc:
        ask_model(
            "Review",
            context,
            configuration=AssistantConfiguration("openai", "model", CLOUD_URL, secret),
        )
    assert secret not in str(exc.value)


def test_empty_or_oversize_question_rejected():
    context = build_assistant_context(new_project())
    with pytest.raises(ValueError):
        ask_model(" ", context)
    with pytest.raises(ValueError):
        ask_model("x" * 4001, context)


def test_diagnostics_context_has_explicit_run_evidence_limits():
    context = build_assistant_context(new_project())
    assert "recent_runs" in context
    assert context["recent_runs"] == []
    assert context["recent_runs_truncated"] is False
    assert any("convergence" in limit for limit in context["limitations"])


def test_focus_is_explicit_and_model_system_guidance_is_restricted(monkeypatch):
    from cleanroomx.ai_assistant import REVIEW_FOCUS
    assert set(REVIEW_FOCUS) == {"general", "cfd", "hvac", "particles", "verification"}
    context = build_assistant_context(new_project())
    with pytest.raises(ValueError, match="Unsupported engineering review focus"):
        ask_model(
            "Review", context,
            configuration=AssistantConfiguration("ollama", "model", LOCAL_URL),
            focus="execute-shell",
        )

    import json
    requests = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self, _limit):
            return b'{"choices":[{"message":{"content":"Check recorded residuals first."}}]}'
    def fake_urlopen(request, timeout):
        requests.append(json.loads(request.data))
        return Response()
    monkeypatch.setattr("cleanroomx.ai_assistant.urlopen", fake_urlopen)
    response = ask_model(
        "What is CFD status?", context,
        configuration=AssistantConfiguration("ollama", "model", LOCAL_URL),
        focus="cfd",
    )
    assert response == "Check recorded residuals first."
    assert "mesh independence" in requests[0]["messages"][0]["content"]


def test_critical_findings_are_not_lost_before_context_truncation(monkeypatch):
    issue = lambda number, severity: {
        "sequence": number, "severity": severity,
        "rule": "rule." + str(number), "message": "message",
        "suggested_action": "Review the input.", "element": {"type": "project"},
    }
    synthetic = {
        "issues": [issue(n, "info") for n in range(1, 21)] + [
            issue(21, "error")
        ],
        "summary": {
            "status": "error", "complete": True, "issue_count": 21,
            "error_count": 1, "warning_count": 0, "info_count": 20,
        },
        "verification_history": {"latest_by_analysis": []},
    }
    monkeypatch.setattr(
        "cleanroomx.ai_assistant.analyze_project_diagnostics",
        lambda *_args, **_kwargs: synthetic,
    )
    context = build_assistant_context(new_project(), max_findings=5)
    assert context["diagnostics"]["findings"][0]["rule"] == "rule.21"
    assert context["diagnostics"]["findings_truncated"] is True
