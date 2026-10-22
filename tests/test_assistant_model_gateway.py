"""Synthetic model gateway contracts: no actual external model or CFD evidence."""
from __future__ import annotations

import json
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import pytest

import cleanroomx.assistant_model_gateway as gateway
from cleanroomx.assistant_review import ASSISTANT_REVIEW_SCHEMA, AssistantSourceChangedError


def _review():
    return {
        "schema": ASSISTANT_REVIEW_SCHEMA,
        "source": {
            "sha256": "a" * 64, "stable_during_review": True, "size_bytes": 200,
        },
        "summary": {
            "error_count": 1, "warning_count": 0, "info_count": 0, "issue_count": 1,
        },
        "findings": [{
            "evidence_ref": "diagnostics.issue.1",
            "severity": "error", "rule": "test.missing_real_run",
            "finding": "Recorded solver output is missing.",
            "suggested_action": "Execute and verify the OpenFOAM case.",
            "element": {"sensitive_room_geometry": "do not transmit"},
        }],
        "project": {"name": "Do not transmit project name or geometry"},
        "limitations": ["No independent physical validation."],
        "decision": "review_required",
        "omitted_findings": 0,
    }


def _reply(value="Model suggestion"):
    return json.dumps({"choices": [{"message": {"content": value}}]}).encode()


def test_context_allowlist_excludes_noncanonical_project_data():
    report = _review()
    report["raw_geometry"] = {"secret": "do not send"}
    selected = gateway.bounded_review_context(report)
    encoded = json.dumps(selected)
    assert "do not send" not in encoded
    assert "project name" not in encoded
    assert "sensitive_room_geometry" not in encoded
    assert selected["engineering_release"] == "HOLD"
    assert selected["saved_project_sha256"] == "a" * 64


def test_local_request_is_explicit_bounded_and_read_only():
    calls = []
    def transport(request, timeout):
        calls.append((request, timeout))
        assert request.full_url == gateway.OLLAMA_ENDPOINT
        assert request.get_method() == "POST"
        assert request.get_header("Authorization") is None
        assert timeout == 30
        assert len(request.data) < gateway.MAX_REQUEST_BYTES
        payload = json.loads(request.data)
        assert payload["stream"] is False
        assert [m["role"] for m in payload["messages"]] == ["system", "user"]
        outbound = payload["messages"][-1]["content"]
        assert "test.missing_real_run" in outbound
        assert "diagnostics.issue.1" in outbound
        assert "do not transmit" not in outbound.lower()
        assert "Measured concentration 42" not in outbound
        return _reply()
    result = gateway.ask_model_about_review(
        "What is missing?", _review(),
        settings=gateway.ModelSettings(provider="ollama", model="llama3.2"),
        transport=transport,
    )
    assert result == "Model suggestion"
    assert len(calls) == 1


@pytest.mark.parametrize("env,match", [
    ({"CLEANROOMX_AI_PROVIDER": "openai", "CLEANROOMX_AI_MODEL": "test"},
     "disabled"),
    ({"CLEANROOMX_AI_PROVIDER": "openai", "CLEANROOMX_AI_ALLOW_CLOUD": "1",
      "OPENAI_API_KEY": "test-key"}, "CLEANROOMX_AI_MODEL"),
    ({"CLEANROOMX_AI_PROVIDER": "openai", "CLEANROOMX_AI_ALLOW_CLOUD": "1",
      "CLEANROOMX_AI_MODEL": "test"}, "OPENAI_API_KEY"),
    ({"CLEANROOMX_AI_PROVIDER": "unauthorized"}, "Provider"),
])
def test_cloud_configuration_fails_closed(env, match):
    with pytest.raises(gateway.ModelConfigurationError, match=match):
        gateway.ModelSettings.from_environment(env)


def test_cloud_requires_opt_in_and_only_uses_fixed_endpoint():
    settings = gateway.ModelSettings.from_environment({
        "CLEANROOMX_AI_PROVIDER": "openai",
        "CLEANROOMX_AI_ALLOW_CLOUD": "1",
        "CLEANROOMX_AI_MODEL": "configured-model",
        "OPENAI_API_KEY": "example-not-a-real-key",
    })
    assert settings.endpoint() == gateway.OPENAI_ENDPOINT
    def transport(request, timeout):
        assert request.full_url == gateway.OPENAI_ENDPOINT
        assert request.get_header("Authorization") == "Bearer example-not-a-real-key"
        return _reply()
    assert gateway.ask_model_about_review(
        "Which checks are missing?", _review(), settings=settings,
        transport=transport,
    ) == "Model suggestion"
    with pytest.raises(gateway.ModelConfigurationError):
        gateway.ModelSettings(
            provider="openai", model="configured-model", api_key="dummy"
        ).endpoint()


def test_no_arbitrary_url_or_redirect():
    with pytest.raises(gateway.ModelConfigurationError):
        gateway.ModelSettings(provider="private-provider", model="x").endpoint()
    assert gateway._NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.example") is None


@pytest.mark.parametrize("invalid", [
    "", " ", "x" * 1201, True, None,
])
def test_bad_question_causes_no_http_request(invalid):
    calls = []
    with pytest.raises(ValueError):
        gateway.ask_model_about_review(
            invalid, _review(),
            settings=gateway.ModelSettings(provider="ollama", model="llama3.2"),
            transport=lambda *args: calls.append(args),
        )
    assert calls == []


@pytest.mark.parametrize("content", [
    b'{"choices":[{"message":{"content":"first","content":"second"}}]}',
    b'{"choices":[{"message":{"content":NaN}}]}',
    b'{"choices":[]}',
    b'{"choices":[{"message":{"content":""}}]}',
    b'not-json',
    b'x' * (gateway.MAX_RESPONSE_BYTES + 1),
    b'{"choices":[{"message":{"content": 2}}]}',
])
def test_invalid_response_refused_without_publishing(content):
    with pytest.raises(gateway.ModelGatewayError):
        gateway.ask_model_about_review(
            "Give safe checks", _review(),
            settings=gateway.ModelSettings(provider="ollama", model="llama3.2"),
            transport=lambda *args: content,
        )


def test_transport_failure_message_does_not_echo_api_secrets():
    def transport(*args):
        raise HTTPError(gateway.OPENAI_ENDPOINT, 401, "key is secret", {}, None)
    with pytest.raises(gateway.ModelGatewayError, match="HTTP 401") as error:
        gateway.ask_model_about_review(
            "Give checks", _review(),
            settings=gateway.ModelSettings(
                provider="openai", model="a", api_key="secret", cloud_opt_in=True
            ),
            transport=transport,
        )
    assert "secret" not in str(error.value)


@pytest.mark.parametrize("mutation,match", [
    (lambda r: r.update(source={"sha256":"wrong","stable_during_review":True}), "stable"),
    (lambda r: r.update(schema="wrong"), "canonical"),
    (lambda r: r.update(summary={"error_count":True}), "summary"),
])
def test_broken_canonical_review_fails_closed(mutation, match):
    r = _review()
    mutation(r)
    with pytest.raises(ValueError, match=match):
        gateway.bounded_review_context(r)


def test_source_identity_checked_before_and_after_request(monkeypatch):
    monkeypatch.setattr(gateway, "build_assistant_review", lambda *args, **kwargs: _review())
    proofs = iter(["a" * 64, "b" * 64])
    monkeypatch.setattr(
        gateway, "capture_project_file_revision",
        lambda *args: SimpleNamespace(exists=True, sha256=next(proofs)),
    )
    calls = []
    with pytest.raises(AssistantSourceChangedError, match="changed"):
        gateway.ask_model_about_saved_project(
            "example.json", "Any missing evidence?",
            settings=gateway.ModelSettings(provider="ollama", model="llama3.2"),
            transport=lambda *args: calls.append(args) or _reply(),
        )
    assert len(calls) == 1


def test_source_change_before_outbound_request_never_transmits(monkeypatch):
    monkeypatch.setattr(gateway, "build_assistant_review", lambda *args, **kwargs: _review())
    monkeypatch.setattr(
        gateway, "capture_project_file_revision",
        lambda *args: SimpleNamespace(exists=True, sha256="b" * 64),
    )
    calls = []
    with pytest.raises(AssistantSourceChangedError):
        gateway.ask_model_about_saved_project(
            "example.json", "Any missing evidence?",
            settings=gateway.ModelSettings(provider="ollama", model="llama3.2"),
            transport=lambda *args: calls.append(args) or _reply(),
        )
    assert not calls


def test_source_identity_stable_response_has_exact_digest(monkeypatch):
    monkeypatch.setattr(gateway, "build_assistant_review", lambda *args, **kwargs: _review())
    monkeypatch.setattr(
        gateway, "capture_project_file_revision",
        lambda *args: SimpleNamespace(exists=True, sha256="a" * 64),
    )
    answer, sha = gateway.ask_model_about_saved_project(
        "example.json", "Any missing evidence?",
        settings=gateway.ModelSettings(provider="ollama", model="llama3.2"),
        transport=lambda *args: _reply(),
    )
    assert answer == "Model suggestion"
    assert sha == "a" * 64
