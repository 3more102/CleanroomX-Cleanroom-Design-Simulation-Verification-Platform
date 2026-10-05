from __future__ import annotations

import os
from types import SimpleNamespace
import tkinter as tk

import pytest

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path
from cleanroomx.gui_reporting import ReportingWorkspace
from cleanroomx.gui_theme import configure_ttk_theme


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


def test_reporting_workspace_never_invents_missing_report_content():
    root = _root()
    workspace = ReportingWorkspace(
        root,
        on_export_dossier=lambda: None,
        on_export_markdown=lambda: None,
        on_export_html=lambda: None,
        on_export_result_json=lambda: None,
        on_export_run_bundle=lambda: None,
    )
    try:
        workspace.set_context(
            project_name="Demo",
            project_saved=False,
            project_dirty=True,
            run=None,
        )
        root.update_idletasks()

        assert workspace.project_state_var.get() == "SAVE REQUIRED"
        assert workspace.run_state_var.get() == "NO FRESH RUN"
        assert str(workspace.dossier_button.cget("state")) == "disabled"
        assert str(workspace.markdown_button.cget("state")) == "disabled"
        assert "will not synthesize" in workspace.preview.get("1.0", "end").casefold()
    finally:
        root.destroy()


def test_reporting_workspace_previews_exact_current_markdown():
    root = _root()
    workspace = ReportingWorkspace(
        root,
        on_export_dossier=lambda: None,
        on_export_markdown=lambda: None,
        on_export_html=lambda: None,
        on_export_result_json=lambda: None,
        on_export_run_bundle=lambda: None,
    )
    run = SimpleNamespace(
        status="pass",
        title="Airflow Balance",
        markdown="# Canonical Report\n\nVerified backend report.",
    )
    try:
        workspace.set_context(
            project_name="Demo",
            project_saved=True,
            project_dirty=False,
            run=run,
        )
        root.update_idletasks()

        assert workspace.project_state_var.get() == "SAVED REVISION READY"
        assert workspace.run_state_var.get() == "PASS · Airflow Balance"
        assert workspace.preview.get("1.0", "end").strip() == run.markdown
        assert str(workspace.dossier_button.cget("state")) == "normal"
        assert str(workspace.markdown_button.cget("state")) == "normal"
        assert str(workspace.html_button.cget("state")) == "normal"
    finally:
        root.destroy()


@pytest.fixture
def app(tmp_path):
    root = _root()
    application = CleanroomXApp(
        root,
        autosave_interval_seconds=0,
        ui_state_path=tmp_path / "gui-layout.json",
    )
    application.load_project_path(bundled_demo_project_path())
    root.update()
    try:
        yield application
    finally:
        root.destroy()


def test_reports_navigator_routes_to_first_class_reporting_workspace(app):
    app.analysis_tree.selection_set("nav-reports")
    app.analysis_tree.focus("nav-reports")
    app._on_navigator_selected()
    app.root.update_idletasks()

    assert app.notebook.select() == str(app.reporting_workspace)
    assert app.workspace_status_var.get() == "Workspace: Reporting"


def test_canonical_demo_run_populates_reporting_preview(app):
    run = app.smoke_run_active()
    app._activate_reporting_workspace()
    app.root.update_idletasks()

    assert app.reporting_workspace.run_state_var.get().startswith(
        str(run.status).upper()
    )
    assert app.reporting_workspace.preview.get("1.0", "end").strip() == run.markdown
