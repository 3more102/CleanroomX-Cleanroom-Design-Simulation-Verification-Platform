"""Project-wide baseline comparison and regression-gate integration."""
from __future__ import annotations

import json

import pytest

import cleanroomx.project_diagnostics_cli as cli
from cleanroomx.project import AnalysisDocument, ProjectDocument, save_project_document
from cleanroomx.project_diagnostics_baseline import compare_project_diagnostics
from cleanroomx.project_diagnostics_cli import main


def _issue(rule="model.problem", *, severity="warning", element="room-a"):
    return {
        "rule": rule, "category": "spatial", "severity": severity,
        "element": {"type": "room", "id": element, "name": "Name"},
        "message": "example", "suggested_action": "correct it",
    }


def _report(issues, *, name="Example"):
    return {
        "schema": "cleanroomx.project-diagnostics",
        "schema_version": 1,
        "project": {"name": name},
        "summary": {"issue_count": len(issues)},
        "issues": issues,
    }


def test_comparison_distinguishes_new_resolved_persistent_and_counts():
    old = _report([_issue(), _issue(), _issue("retired", severity="info")])
    now = _report([_issue(), _issue("added"), _issue("added")])
    before = json.dumps(old, sort_keys=True)
    after = json.dumps(now, sort_keys=True)
    delta = compare_project_diagnostics(old, now)
    assert delta["regressed"] is True
    assert delta["summary"] == {
        "new_issue_count": 2, "new_actionable_count": 2,
        "resolved_issue_count": 2, "persistent_issue_count": 1,
    }
    assert delta["new_issues"][0]["count"] == 2
    assert json.dumps(old, sort_keys=True) == before
    assert json.dumps(now, sort_keys=True) == after


def test_comparison_severity_escalation_and_information():
    baseline = _report([_issue(severity="info")])
    current = _report([_issue(severity="warning")])
    delta = compare_project_diagnostics(baseline, current)
    assert delta["regressed"]
    assert delta["summary"]["new_actionable_count"] == 1
    assert delta["summary"]["resolved_issue_count"] == 1
    assert not compare_project_diagnostics(_report([]), baseline)["regressed"]


@pytest.mark.parametrize("bad", [
    [],
    {"schema": "wrong", "schema_version": 1, "project": {"name": "Example"},
     "issues": [], "summary": {"issue_count": 0}},
    _report([] , name="Wrong"),
    _report([{"rule": "bad"}]),
    {**_report([]), "summary": {"issue_count": 4}},
])
def test_comparison_rejects_untrusted_baselines(bad):
    with pytest.raises(ValueError):
        compare_project_diagnostics(bad, _report([]))


def test_cli_baseline_end_to_end_new_and_resolved(tmp_path, capsys):
    path = save_project_document(tmp_path / "project.json", ProjectDocument(name="Example"))
    baseline = tmp_path / "baseline.json"
    assert main([str(path), "--output", str(baseline)]) == 0
    first = json.loads(baseline.read_text())
    assert first["summary"]["issue_count"] == 0

    bad = ProjectDocument(
        name="Example",
        analyses=[AnalysisDocument(
            id="broken", name="Broken", kind="room_verification",
            input={"name": "incomplete"},
        )],
        active_analysis_id="broken",
    )
    save_project_document(path, bad)
    result = tmp_path / "delta.json"
    assert main([str(path), "--baseline", str(baseline),
                 "--fail-on-regression", "--output", str(result)]) == 3
    delta = json.loads(result.read_text())
    assert delta["comparison"]["summary"]["new_actionable_count"] >= 1
    assert len(delta["comparison"]["baseline_report_sha256"]) == 64
    assert delta["source"]["path"] == str(path)

    save_project_document(path, ProjectDocument(name="Example"))
    assert main([str(path), "--baseline", str(baseline),
                 "--fail-on-regression"]) == 0
    final = json.loads(capsys.readouterr().out)
    assert not final["comparison"]["regressed"]


def test_cli_existing_actionable_warning_does_not_fail_delta_only_gate(tmp_path):
    bad = ProjectDocument(
        name="Example",
        analyses=[AnalysisDocument(
            id="broken", name="Broken", kind="room_verification",
            input={"name": "incomplete"},
        )],
        active_analysis_id="broken",
    )
    path = save_project_document(tmp_path / "project.json", bad)
    baseline = tmp_path / "baseline.json"
    assert main([str(path), "--output", str(baseline)]) == 1
    assert main([str(path), "--baseline", str(baseline)]) == 1
    assert main([str(path), "--baseline", str(baseline),
                 "--fail-on-regression"]) == 0


def test_cli_refuses_baseline_overwrite_and_preserves_exact_bytes(tmp_path, capsys):
    path = save_project_document(tmp_path / "project.json", ProjectDocument(name="Example"))
    baseline = tmp_path / "baseline.json"
    assert main([str(path), "--output", str(baseline)]) == 0
    before = baseline.read_bytes()
    assert main([str(path), "--baseline", str(baseline),
                 "--output", str(baseline)]) == 2
    assert baseline.read_bytes() == before
    assert "must not overwrite baseline" in capsys.readouterr().err


def test_cli_detects_changed_baseline_during_analysis_without_output(tmp_path, monkeypatch, capsys):
    path = save_project_document(tmp_path / "project.json", ProjectDocument(name="Example"))
    baseline = tmp_path / "baseline.json"
    assert main([str(path), "--output", str(baseline)]) == 0
    original = cli.analyze_project_diagnostics

    def mutate(project, *, base_dir=None):
        outcome = original(project, base_dir=base_dir)
        baseline.write_bytes(baseline.read_bytes() + b" ")
        return outcome

    monkeypatch.setattr(cli, "analyze_project_diagnostics", mutate)
    assert main([str(path), "--baseline", str(baseline)]) == 2
    assert "baseline changed" in capsys.readouterr().err


def test_cli_unsupported_baseline_and_missing_argument(tmp_path, capsys):
    path = save_project_document(tmp_path / "project.json", ProjectDocument(name="Example"))
    other = tmp_path / "other.json"
    other.write_text('{"schema":"other","issues":[]}')
    assert main([str(path), "--baseline", str(other)]) == 2
    assert main([str(path), "--fail-on-regression"]) == 2
    assert capsys.readouterr().err
