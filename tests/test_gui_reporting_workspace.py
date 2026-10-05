from __future__ import annotations

import os
import tkinter as tk

import pytest

from cleanroomx.gui import CleanroomXApp
from cleanroomx.gui_reporting import (
    ReportingWorkspace,
    reporting_section_plan,
    reporting_status_projection,
    reporting_template_sections,
)


def test_reporting_projection_keeps_missing_state_explicit() -> None:
    projected = reporting_status_projection(
        {
            "project_name": "Fab",
            "source": "Unsaved project",
            "saved": False,
            "diagnostics": {},
            "verification": {},
            "evidence_record_count": None,
            "proofgraph_count": "bad",
        }
    )

    assert projected["project_name"] == "Fab"
    assert projected["save_state"] == "unsaved"
    assert projected["diagnostic_state"] == "not checked"
    assert projected["verification_state"] == "not configured"
    assert projected["analysis_state"] == "not run"
    assert projected["evidence_detail"] == "0 verification records · 0 ProofGraphs"


def test_reporting_section_plan_does_not_invent_availability() -> None:
    plan = reporting_section_plan(
        {
            "project_name": "Fab",
            "saved": False,
            "diagnostics": {},
            "verification": {},
            "evidence_record_count": 0,
            "proofgraph_count": 0,
        }
    )

    assert plan["project"]["available"] is True
    assert plan["diagnostics"]["available"] is False
    assert plan["verification"]["available"] is False
    assert plan["analysis"]["available"] is False
    assert plan["evidence"]["available"] is False
    assert reporting_template_sections("Verification") == (
        "project",
        "verification",
        "diagnostics",
        "evidence",
    )


@pytest.fixture
def root():
    try:
        window = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    window.withdraw()
    try:
        yield window
    finally:
        window.destroy()


def test_reporting_workspace_composes_selected_summary_from_current_state(root) -> None:
    workspace = ReportingWorkspace(
        root,
        on_export_dossier=lambda: None,
        on_export_diagnostics=lambda: None,
        on_export_result_json=lambda: None,
        on_export_run_bundle=lambda: None,
        on_export_markdown=lambda: None,
        on_export_html=lambda: None,
        on_export_selected_summary=lambda: None,
    )
    workspace.pack(fill="both", expand=True)
    workspace.refresh(
        {
            "project_name": "Fab",
            "source": "/projects/fab.cleanroomx.json",
            "saved": True,
            "diagnostics": {"status": "warning"},
            "verification": {
                "configured_analysis_count": 2,
                "current_count": 1,
                "stale_count": 1,
                "not_verified_count": 0,
            },
            "last_run": {"title": "Air Balance", "status": "completed"},
            "evidence_record_count": 3,
            "proofgraph_count": 2,
        }
    )
    workspace.template_var.set("Diagnostics")
    workspace._apply_template()
    root.update_idletasks()

    assert workspace.selected_sections() == ("project", "diagnostics")
    summary = workspace.build_selected_summary_markdown()
    assert "# CleanroomX Report Summary — Fab" in summary
    assert "## Project context" in summary
    assert "## Diagnostics" in summary
    assert "## Verification" not in summary
    assert "Missing data remains missing" in summary
    assert str(workspace.dossier_button.cget("state")) == "normal"
    assert str(workspace.diagnostics_button.cget("state")) == "normal"
    assert all(
        str(button.cget("state")) == "normal"
        for button in workspace.analysis_export_buttons
    )


def test_reporting_workspace_gates_exports_when_state_is_unavailable(root) -> None:
    workspace = ReportingWorkspace(
        root,
        on_export_dossier=lambda: None,
        on_export_diagnostics=lambda: None,
        on_export_result_json=lambda: None,
        on_export_run_bundle=lambda: None,
        on_export_markdown=lambda: None,
        on_export_html=lambda: None,
    )
    workspace.refresh(
        {
            "project_name": "Fab",
            "source": "Unsaved project",
            "saved": False,
            "diagnostics": {},
            "verification": {},
        }
    )
    root.update_idletasks()

    assert str(workspace.dossier_button.cget("state")) == "disabled"
    assert str(workspace.diagnostics_button.cget("state")) == "disabled"
    assert all(
        str(button.cget("state")) == "disabled"
        for button in workspace.analysis_export_buttons
    )


def test_guided_report_and_navigator_open_reporting_workspace(root, tmp_path) -> None:
    app = CleanroomXApp(
        root,
        autosave_interval_seconds=0,
        ui_state_path=tmp_path / "gui-layout.json",
    )
    root.update()

    app.workflow_report_button.invoke()
    root.update_idletasks()
    assert app.notebook.select() == str(app.reporting_workspace)
    assert app.workspace_status_var.get() == "Workspace: Reports"

    app.analysis_tree.selection_set("nav-reports")
    app.analysis_tree.focus("nav-reports")
    app._on_navigator_selected()
    root.update_idletasks()
    assert app.notebook.select() == str(app.reporting_workspace)
    assert app.selection_status_var.get() == "Selected: Reports"

    commands = {command.command_id: command for command in app._command_palette_commands()}
    assert "workspace.reports" in commands
    assert "report.summary" in commands
