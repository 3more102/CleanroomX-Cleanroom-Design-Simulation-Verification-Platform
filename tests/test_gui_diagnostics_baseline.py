"""Interactive GUI baseline comparisons; display-only evidence and no project mutation."""
from __future__ import annotations

import os
import tkinter as tk

import pytest

from cleanroomx.gui_panels import ProjectDiagnosticsPanel
from cleanroomx.project import AnalysisDocument, ProjectDocument, save_project_document
from cleanroomx.project_diagnostics_cli import main as diagnostics_main


@pytest.fixture
def workspace(tmp_path):
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    errors = []
    root.report_callback_exception = lambda *args: errors.append(args)
    project = save_project_document(
        tmp_path / "example.cleanroomx.json", ProjectDocument(name="Example")
    )
    baseline = tmp_path / "baseline.json"
    assert diagnostics_main([str(project), "--output", str(baseline)]) == 0
    current = {"project": ProjectDocument(name="Example")}
    status = []
    panel = ProjectDiagnosticsPanel(
        root,
        project_getter=lambda: current["project"],
        base_dir_getter=lambda: tmp_path,
        source_path_getter=lambda: project,
        navigate_callback=lambda issue: None,
        status_setter=status.append,
    )
    panel.pack(fill="both", expand=True)
    panel.refresh()
    root.update()
    try:
        yield root, panel, project, baseline, current, status
        assert not errors
    finally:
        root.destroy()


def test_gui_baseline_filter_updates_from_real_analysis_changes(workspace):
    root, panel, project, baseline, current, status = workspace
    assert str(panel.delta_combo.cget("state")) == "disabled"
    assert panel.load_baseline_path(baseline)["regressed"] is False
    assert str(panel.delta_combo.cget("state")) == "readonly"
    assert panel.baseline_comparison["summary"]["new_issue_count"] == 0

    current["project"] = ProjectDocument(
        name="Example",
        analyses=[
            AnalysisDocument(
                id="broken", name="Broken", kind="room_verification",
                input={"name": "incomplete"},
            ),
        ],
        active_analysis_id="broken",
    )
    panel.refresh()
    root.update()
    summary = panel.baseline_comparison["summary"]
    assert summary["new_actionable_count"] >= 1
    assert summary["new_issue_count"] >= 1
    assert "Δ +" in panel.summary_var.get()

    panel.delta_var.set("New")
    root.update()
    assert len(panel.tree.get_children()) == summary["new_issue_count"]
    assert len(panel._filtered_issues()) == summary["new_issue_count"]
    panel.clear_baseline()
    root.update()
    assert panel.delta_var.get() == "All"
    assert panel.baseline_comparison is None
    assert str(panel.delta_combo.cget("state")) == "disabled"
    assert len(panel.tree.get_children()) == panel.last_result["summary"]["issue_count"]


def test_gui_rejects_baseline_from_different_project_file(workspace, tmp_path):
    root, panel, project, baseline, current, status = workspace
    other = save_project_document(
        tmp_path / "other.cleanroomx.json", ProjectDocument(name="Example")
    )
    wrong = tmp_path / "wrong.json"
    assert diagnostics_main([str(other), "--output", str(wrong)]) == 0
    with pytest.raises(ValueError, match="baseline source does not match"):
        panel.load_baseline_path(wrong)
    assert panel.baseline_comparison is None


def test_gui_discards_stale_baseline_on_refresh(workspace):
    root, panel, project, baseline, current, status = workspace
    panel.load_baseline_path(baseline)
    baseline.write_bytes(baseline.read_bytes() + b" ")
    panel.refresh()
    root.update()
    assert panel.baseline_comparison is None
    assert panel.delta_var.get() == "All"
    assert any("baseline changed" in item.lower() for item in status)


def test_gui_rejects_unsaved_project_baseline(workspace):
    root, panel, project, baseline, current, status = workspace
    panel._source_path_getter = lambda: None
    with pytest.raises(ValueError, match="Save the project"):
        panel.load_baseline_path(baseline)
