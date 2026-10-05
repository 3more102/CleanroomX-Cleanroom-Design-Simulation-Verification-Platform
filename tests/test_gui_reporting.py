from __future__ import annotations

import os
import tkinter as tk

import pytest

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path
from cleanroomx.gui_reporting import reporting_artifacts, reporting_status_projection


def test_reporting_projection_does_not_invent_run_or_verification_state():
    state = reporting_status_projection(
        {
            "project": {"name": "Plant A", "location": "project.cleanroomx.json"},
            "analysis_count": 2,
            "diagnostics": {
                "summary": {
                    "status": "warning",
                    "issue_count": 3,
                    "error_count": 1,
                    "warning_count": 2,
                }
            },
            "verification": {
                "configured_analysis_count": 2,
                "current_count": 1,
                "stale_count": 1,
                "not_verified_count": 0,
            },
            "evidence": {"record_count": 4, "proofgraph_count": 2},
            "last_run": None,
        }
    )

    assert state["project_name"] == "Plant A"
    assert state["has_run"] is False
    assert state["run_status"] == "not run"
    assert state["verification_state"] == "stale"
    assert state["issue_count"] == 3
    assert state["evidence_count"] == 4

    artifacts = {item["id"]: item for item in reporting_artifacts({"last_run": None})}
    assert artifacts["dossier"]["available"] is True
    assert artifacts["diagnostics"]["available"] is True
    assert artifacts["result_json"]["available"] is False
    assert artifacts["run_bundle"]["available"] is False
    assert artifacts["markdown"]["available"] is False
    assert artifacts["html"]["available"] is False


def test_reporting_projection_enables_run_exports_only_when_run_exists():
    artifacts = {
        item["id"]: item
        for item in reporting_artifacts(
            {"last_run": {"title": "ACH", "status": "pass"}}
        )
    }
    assert all(
        artifacts[key]["available"]
        for key in ("result_json", "run_bundle", "markdown", "html")
    )


@pytest.fixture
def app(tmp_path):
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    callback_errors = []
    root.report_callback_exception = lambda *args: callback_errors.append(args)
    application = CleanroomXApp(
        root,
        autosave_interval_seconds=0,
        ui_state_path=tmp_path / "gui-layout.json",
    )
    application.load_project_path(bundled_demo_project_path())
    root.update()
    try:
        yield application
        assert callback_errors == []
    finally:
        root.destroy()


def test_navigator_routes_reports_to_first_class_reporting_workspace(app):
    app.analysis_tree.selection_set("nav-reports")
    app.analysis_tree.focus("nav-reports")
    app._on_navigator_selected()
    app.root.update_idletasks()

    assert app.notebook.select() == str(app.reporting_workspace)
    assert app.workspace_status_var.get() == "Workspace: Reporting"


def test_canonical_run_updates_reporting_workspace_availability(app):
    before = {
        item["id"]: item
        for item in reporting_artifacts(app.reporting_workspace._snapshot)
    }
    assert before["result_json"]["available"] is False

    run = app.smoke_run_active()
    app.root.update_idletasks()

    assert app.reporting_workspace.run_var.get().startswith(str(run.status).upper())
    states = {
        app.reporting_workspace.artifact_tree.item(iid, "text"):
        app.reporting_workspace.artifact_tree.item(iid, "values")[-1]
        for iid in app.reporting_workspace.artifact_tree.get_children()
    }
    assert states["Result JSON"] == "AVAILABLE"
    assert states["Run bundle JSON"] == "AVAILABLE"

def test_reporting_integration_preserves_shell_theme_and_refresh(app):
    original_theme = app.theme_var.get()

    diagnostics = app._refresh_engineering_panels()
    app.set_theme("light", persist=False)
    app.set_theme(original_theme, persist=False)
    app.root.update_idletasks()

    assert isinstance(diagnostics, dict)
    assert app.reporting_workspace._snapshot["project"]["name"] == app.project.name
    assert app.dashboard is not None


def test_reporting_open_output_routes_to_report_tab(app):
    app._open_report_output()
    app.root.update_idletasks()

    assert app.output_panel_visible_var.get() is True
    assert app.output_notebook.select() == str(app.report_text.master)
    assert app.status_var.get() == "Output: Report"

