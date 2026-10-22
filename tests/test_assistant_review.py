from __future__ import annotations

import copy
import json

import pytest

from cleanroomx.assistant_review import (
    ASSISTANT_REVIEW_SCHEMA,
    AssistantSourceChangedError,
    build_assistant_review,
    markdown_assistant_review,
    prioritize_project_diagnostics,
    register_project_review_agent,
)
from cleanroomx.multi_agent import ChatSessionStore, MultiAgentCoordinator
from cleanroomx.project import ProjectDocument, save_project_document
from cleanroomx.project_diagnostics import PROJECT_DIAGNOSTICS_SCHEMA
import cleanroomx.assistant_review as assistant


def _diagnostics(issues=()):
    issues = copy.deepcopy(list(issues))
    return {
        "schema": PROJECT_DIAGNOSTICS_SCHEMA,
        "project": {"name": "Demo", "analysis_count": 1},
        "summary": {
            "error_count": sum(issue["severity"] == "error" for issue in issues),
            "warning_count": sum(issue["severity"] == "warning" for issue in issues),
            "info_count": sum(issue["severity"] == "info" for issue in issues),
            "issue_count": len(issues),
        },
        "issues": issues,
        "verification_currency": {"summary": {"current_count": 0}},
        "limitations": ["No certification claim."],
    }


def _issue(sequence, severity, rule):
    return {
        "sequence": sequence,
        "severity": severity,
        "rule": rule,
        "category": "traceability",
        "element": {"type": "analysis", "id": "test"},
        "message": f"Finding for {rule}",
        "suggested_action": f"Correct {rule}",
    }


def _review(diagnostics, **kwargs):
    return prioritize_project_diagnostics(
        diagnostics,
        source_sha256="a" * 64,
        source_size_bytes=100,
        **kwargs,
    )


def test_assistant_prioritizes_errors_and_preserves_canonical_references():
    result = _review(
        _diagnostics([
            _issue(1, "info", "info-x"),
            _issue(2, "warning", "warning-x"),
            _issue(3, "error", "error-x"),
            _issue(4, "error", "error-y"),
        ]),
        max_findings=2,
    )
    assert result["schema"] == ASSISTANT_REVIEW_SCHEMA
    assert result["mode"] == "deterministic-read-only"
    assert result["decision"] == "review_required"
    assert [item["rule"] for item in result["findings"]] == ["error-x", "error-y"]
    assert [item["evidence_ref"] for item in result["findings"]] == [
        "diagnostics.issue.3",
        "diagnostics.issue.4",
    ]
    assert result["omitted_findings"] == 2
    assert result["summary"] == {
        "error_count": 2, "warning_count": 1, "info_count": 1, "issue_count": 4,
    }
    assert "2 additional findings omitted" in markdown_assistant_review(result)
    json.dumps(result, allow_nan=False)


def test_assistant_never_calls_no_findings_certification():
    result = _review(_diagnostics())
    assert result["decision"] == "no_blocking_diagnostic_findings"
    assert result["findings"] == []
    assert any("never demonstrates converged CFD" in item for item in result["limitations"])
    assert "No findings" in markdown_assistant_review(result)


@pytest.mark.parametrize("limit", [0, -1, 51, True, 1.0, "2"])
def test_assistant_rejects_invalid_limits(limit):
    with pytest.raises(ValueError, match="max_findings"):
        _review(_diagnostics(), max_findings=limit)


def test_assistant_fails_closed_on_inconsistent_diagnostic_counts():
    diagnostics = _diagnostics([_issue(1, "warning", "stale-input")])
    diagnostics["summary"]["warning_count"] = 0
    with pytest.raises(ValueError, match="counts"):
        _review(diagnostics)


def test_assistant_reports_exact_project_digest_and_revision(tmp_path, monkeypatch):
    path = tmp_path / "project.cleanroomx.json"
    save_project_document(path, ProjectDocument(name="Demo"))
    monkeypatch.setattr(assistant, "analyze_project_diagnostics", lambda *args, **kwargs: _diagnostics())
    result = build_assistant_review(path, question="What should I fix?", max_findings=5)
    assert result["question"] == "What should I fix?"
    assert result["source"]["size_bytes"] == path.stat().st_size
    import hashlib
    assert result["source"]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_assistant_refuses_project_changed_during_diagnostics(tmp_path, monkeypatch):
    path = tmp_path / "project.cleanroomx.json"
    save_project_document(path, ProjectDocument(name="Demo"))

    def changed(*args, **kwargs):
        path.write_bytes(path.read_bytes() + b" ")
        return _diagnostics()

    monkeypatch.setattr(assistant, "analyze_project_diagnostics", changed)
    with pytest.raises(AssistantSourceChangedError, match="changed during"):
        build_assistant_review(path)


def test_assistant_review_agent_uses_multi_chat_coordinator(tmp_path, monkeypatch):
    path = tmp_path / "project.cleanroomx.json"
    save_project_document(path, ProjectDocument(name="Demo"))
    monkeypatch.setattr(
        assistant,
        "analyze_project_diagnostics",
        lambda *args, **kwargs: _diagnostics([_issue(1, "warning", "missing-evidence")]),
    )
    store = ChatSessionStore()
    store.create_session("review-chat", "Review")
    coordinator = MultiAgentCoordinator(store)
    spec = register_project_review_agent(
        coordinator, "evidence-review", project_path=path,
    )
    assert "read-only" in spec.capabilities
    batch = coordinator.run(
        "review-chat",
        "What should I fix first?",
        agent_ids=["evidence-review"],
        task_id="task-evidence-review",
    )
    assert batch.commit_state == "committed"
    assert batch.results[0].state == "completed"
    assert batch.results[0].data["findings"][0]["rule"] == "missing-evidence"
    assert batch.results[0].data["source"]["stable_during_review"] is True
    assert "missing-evidence" in batch.results[0].content
