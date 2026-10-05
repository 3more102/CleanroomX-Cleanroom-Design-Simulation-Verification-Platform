from __future__ import annotations

import os
import tkinter as tk

import pytest

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path
from cleanroomx.gui_reporting import ReportingWorkspace, reporting_status_projection
from cleanroomx.gui_theme import configure_ttk_theme


def test_reporting_projection_is_explicit_about_unsaved_and_unverified_state():
    projected = reporting_status_projection(
        {
            "project_name": "Fab",
            "source": "Unsaved project",
            "saved": False,
            "diagnostics": {},
            "verification": {},
            "evidence_record_count": 0,
            "proofgraph_count": 0,
        }
    )
    assert projected["save_state"] == "unsaved"
    assert projected["diagnostic_state"] == "not checked"
    assert projected["verification_state"] == "not configured"
    assert projected["analysis_state"] == "not run"
    assert projected["dossier_available"] is False
    assert projected["analysis_export_available"] is False


def _root():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    configure_ttk_theme(root, "dark")
    return root


def test_reporting_workspace_surfaces_existing_export_pipeline_without_recalculation():
    root = _root()
    workspace = ReportingWorkspace(
        root,
        on_export_dossier=lambda: None,
        on_export_diagnostics=lambda: None,
        on_export_result_json=lambda: None,
        on_export_run_bundle=lambda: None,
        on_export_markdown=lambda: None,
        on_export_html=lambda: None,
    )
    try:
        workspace.refresh(
            {
                "project_name": "Fab",
                "source": "/tmp/fab.cleanroomx.json",
                "saved": True,
                "diagnostics": {"status": "warning"},
                "verification": {
                    "configured_analysis_count": 2,
                    "current_count": 1,
                    "stale_count": 1,
                    "not_verified_count": 0,
                },
                "last_run": {"title": "Airflow", "status": "pass"},
                "evidence_record_count": 3,
                "proofgraph_count": 2,
            }
        )
        root.update_idletasks()

        assert workspace.save_var.get() == "SAVED"
        assert workspace.diagnostics_var.get() == "WARNING"
        assert workspace.verification_var.get() == "STALE"
        assert workspace.analysis_var.get() == "PASS"
        assert str(workspace.dossier_button.cget("state")) == "normal"
        assert all(
            str(button.cget("state")) == "normal"
            for button in workspace.analysis_export_buttons
        )
        preview = workspace.preview.get("1.0", "end")
        assert "existing canonical dossier" not in preview
        assert "Project engineering dossier" in preview
        assert "1 stale" in preview
    finally:
        root.destroy()


def test_reporting_workspace_disables_unavailable_exports_without_guessing():
    root = _root()
    workspace = ReportingWorkspace(
        root,
        on_export_dossier=lambda: None,
        on_export_diagnostics=lambda: None,
        on_export_result_json=lambda: None,
        on_export_run_bundle=lambda: None,
        on_export_markdown=lambda: None,
        on_export_html=lambda: None,
    )
    try:
        workspace.refresh(
            {
                "project_name": "Unsaved Fab",
                "source": "Unsaved project",
                "saved": False,
                "diagnostics": {"status": "pass"},
                "verification": {},
                "last_run": {"title": "Old airflow", "status": "pass"},
                "current_result_available": False,
                "evidence_record_count": 0,
                "proofgraph_count": 0,
            }
        )
        root.update_idletasks()

        assert str(workspace.dossier_button.cget("state")) == "disabled"
        assert str(workspace.diagnostics_button.cget("state")) == "normal"
        assert all(
            str(button.cget("state")) == "disabled"
            for button in workspace.analysis_export_buttons
        )
        preview = workspace.preview.get("1.0", "end")
        assert "unavailable until the project is saved" in preview
        assert "unavailable until a current result exists" in preview
    finally:
        root.destroy()



@pytest.fixture
def app(tmp_path):
    root = _root()
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


def test_navigator_routes_reports_to_first_class_workspace(app):
    app.analysis_tree.selection_set("nav-reports")
    app.analysis_tree.focus("nav-reports")
    app._on_navigator_selected()
    app.root.update_idletasks()

    assert app.notebook.select() == str(app.reporting_workspace)
    assert app.workspace_status_var.get() == "Workspace: Reports"
