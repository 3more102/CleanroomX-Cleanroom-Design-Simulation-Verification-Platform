"""Real Tk coverage for the production engineering output/verification workspace."""
from __future__ import annotations

import copy
import os
import tkinter as tk

import pytest

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path
from cleanroomx.gui_theme import theme_palette
from cleanroomx.project_diagnostics import PROJECT_DIAGNOSTICS_SCHEMA
from cleanroomx.spatial import SPATIAL_METADATA_KEY, _Hit


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


def _tab_texts(notebook) -> list[str]:
    return [notebook.tab(tab_id, "text") for tab_id in notebook.tabs()]


def _force_room_overlap(app: CleanroomXApp) -> tuple[dict, dict]:
    workspace = app.spatial_workspace
    assert len(workspace.layout["rooms"]) >= 2
    layout = copy.deepcopy(workspace.layout)
    first = layout["rooms"][0]
    second = layout["rooms"][1]
    second["x_m"] = first["x_m"]
    second["y_m"] = first["y_m"]
    app.project.metadata[SPATIAL_METADATA_KEY] = layout
    workspace.refresh()
    result = app._refresh_engineering_panels()
    assert result is not None
    issue = next(
        item
        for item in result["issues"]
        if item["rule"] == "spatial.room_overlap"
    )
    return result, issue


def test_engineering_output_workspace_exposes_first_class_panels(app):
    tabs = _tab_texts(app.output_notebook)
    assert tabs[:5] == [
        "Problems",
        "Diagnostics",
        "Verification",
        "Console",
        "Evidence",
    ]
    assert "Results" in tabs
    assert "Report" in tabs

    result = app.problems_panel.last_result
    assert result is not None
    assert result["schema"] == PROJECT_DIAGNOSTICS_SCHEMA
    assert app.verification_text.get("1.0", "end").strip()
    assert app.console_text.get("1.0", "end").strip()
    assert app.evidence_text.get("1.0", "end").strip()


def test_problem_filter_and_navigation_use_canonical_spatial_issue(app):
    result, issue = _force_room_overlap(app)
    assert result["summary"]["issue_count"] >= 1
    assert issue["element"]["type"] == "spatial_element"

    panel = app.problems_panel
    panel.search_var.set("room_overlap")
    app.root.update()
    visible = panel.tree.get_children()
    assert visible
    assert all(
        "room_overlap" in str(panel._issues_by_iid[iid]["rule"])
        for iid in visible
    )

    target_iid = next(
        iid
        for iid, candidate in panel._issues_by_iid.items()
        if candidate["sequence"] == issue["sequence"]
    )
    panel.tree.selection_set(target_iid)
    panel.tree.focus(target_iid)
    panel._navigate_selected()
    app.root.update()

    assert app.spatial_workspace.selected == _Hit(
        "room",
        issue["element"]["id"],
    )
    assert app.notebook.select() == str(app.spatial_workspace)


def test_analysis_diagnostic_navigation_opens_analysis_input(app):
    analysis = app.project.analyses[0]
    issue = {
        "rule": "analysis.input_invalid",
        "element": {
            "type": "analysis",
            "id": analysis.id,
            "name": analysis.name,
        },
    }

    app._navigate_project_diagnostic(issue)
    app.root.update()

    assert app.analysis_tree.selection() == (analysis.id,)
    assert app.notebook.select() == str(app.input_tab)


def test_completed_run_selects_results_in_bottom_workspace(app):
    run = app.smoke_run_active()
    app.root.update()

    assert run.result
    assert app.output_notebook.select() == str(app.result_text.master)
    assert app.problems_panel.last_result is not None


def test_fit_selected_preserves_engineering_geometry(app):
    workspace = app.spatial_workspace
    room = workspace.layout["rooms"][0]
    geometry_before = {
        "rooms": copy.deepcopy(workspace.layout["rooms"]),
        "devices": copy.deepcopy(workspace.layout["devices"]),
    }

    assert workspace.select_item("room", room["id"])
    assert workspace.fit_selected()
    app.root.update()

    assert workspace.layout["rooms"] == geometry_before["rooms"]
    assert workspace.layout["devices"] == geometry_before["devices"]
    assert 0.2 <= workspace.layout["view"]["zoom_2d"] <= 8.0
    assert 0.2 <= workspace.layout["view"]["zoom_3d"] <= 8.0


def test_problem_severity_is_accessible_and_follows_dark_theme(app):
    _result, issue = _force_room_overlap(app)
    panel = app.problems_panel
    target_iid = next(
        iid
        for iid, candidate in panel._issues_by_iid.items()
        if candidate["sequence"] == issue["sequence"]
    )

    severity_text = panel.tree.set(target_iid, "severity")
    assert severity_text == "✕ ERROR"

    app.set_theme("dark", persist=False)
    app.root.update_idletasks()
    palette = theme_palette("dark")
    assert panel.detail.cget("background").lower() == palette["field"].lower()


def test_engineering_dashboard_reflects_canonical_project_health(app):
    result = app.problems_panel.last_result
    assert result is not None

    app._activate_dashboard_workspace()
    app.root.update()

    assert "Dashboard" in _tab_texts(app.notebook)
    assert app.notebook.select() == str(app.dashboard_panel)
    assert app.workspace_mode_buttons["dashboard"].cget("style") == (
        "CX.ModeDashboardActive.TButton"
    )

    summary = result["summary"]
    expected_health = (
        "ERRORS PRESENT"
        if summary["error_count"]
        else ("ATTENTION" if summary["warning_count"] else "PASS")
    )
    assert app.dashboard_panel.health_var.get() == expected_health
    assert f"{summary['error_count']} errors" in app.dashboard_panel.diagnostics_var.get()
    assert f"{result['project']['spatial_room_count']} rooms" in (
        app.dashboard_panel.spatial_var.get()
    )
    assert f"{result['project']['verification_run_count']} persisted verification" in (
        app.dashboard_panel.evidence_var.get()
    )
    assert "%" not in app.dashboard_panel.health_var.get()


def test_engineering_dashboard_promotes_and_locates_canonical_error(app):
    _result, issue = _force_room_overlap(app)
    dashboard = app.dashboard_panel

    assert dashboard.health_var.get() == "ERRORS PRESENT"
    target_iid = next(
        iid
        for iid, candidate in dashboard._issues_by_iid.items()
        if candidate["sequence"] == issue["sequence"]
    )
    assert dashboard.issue_tree.set(target_iid, "severity") == "✕ ERROR"

    dashboard.issue_tree.selection_set(target_iid)
    dashboard.issue_tree.focus(target_iid)
    dashboard._show_detail()
    assert dashboard.locate_button.instate(["!disabled"])
    dashboard._locate_selected()
    app.root.update()

    assert app.spatial_workspace.selected == _Hit(
        "room",
        issue["element"]["id"],
    )
    assert app.notebook.select() == str(app.spatial_workspace)

def test_dashboard_verification_progress_uses_canonical_currency(app):
    result = app.problems_panel.last_result
    assert isinstance(result, dict)
    currency = result.get("verification_currency", {})
    summary = currency.get("summary", {}) if isinstance(currency, dict) else {}
    configured = int(summary.get("configured_analysis_count") or 0)
    current = int(summary.get("current_count") or 0)
    expected = int(round((current / configured) * 100)) if configured else 0

    assert int(float(app.dashboard_panel.verification_progress.cget("value"))) == expected
    assert app.dashboard_panel.verification_percent_var.get() == (
        f"{expected}% current" if configured else "not checked"
    )

def test_problem_issue_inspector_prioritizes_engineering_context(app):
    _result, issue = _force_room_overlap(app)
    panel = app.problems_panel
    target_iid = next(
        iid
        for iid, candidate in panel._issues_by_iid.items()
        if candidate["sequence"] == issue["sequence"]
    )
    panel.tree.selection_set(target_iid)
    panel.tree.focus(target_iid)
    panel._show_selected_detail()
    app.root.update_idletasks()

    detail = panel.detail.get("1.0", "end")
    assert "Object:" in detail
    assert "Engineering finding" in detail
    assert "Suggested recovery" in detail
    assert str(panel.locate_button.cget("state")) == "normal"



def test_analysis_activity_indicator_tracks_worker_ui_state(app):
    app._set_running(True)
    app.root.update()
    assert app.run_state_var.get() == "RUNNING"
    assert app.run_button.instate(["disabled"])
    assert app.cancel_button.instate(["!disabled"])
    assert str(app.input_text.cget("state")) == "disabled"

    app._set_running(False)
    app.root.update()
    assert app.run_state_var.get() == "IDLE"
    assert app.run_button.instate(["!disabled"])
    assert app.cancel_button.instate(["disabled"])
    assert str(app.input_text.cget("state")) == "normal"

def test_analysis_execution_state_is_semantic_and_non_compliance_claiming(app):
    assert app.run_state_var.get() == "IDLE"
    assert app.run_state_badge.cget("style") == "CX.Status.Neutral.TLabel"

    app._set_running(True)
    app.root.update_idletasks()
    assert app.run_state_var.get() == "RUNNING"
    assert app.run_state_badge.cget("style") == "CX.Status.Simulation.TLabel"
    assert str(app.run_button.cget("state")) == "disabled"

    app._set_running(False)
    app._set_run_state("FAILED")
    app.root.update_idletasks()
    assert app.run_state_var.get() == "FAILED"
    assert app.run_state_badge.cget("style") == "CX.Status.Fail.TLabel"

    app._set_run_state("COMPLETE")
    assert app.run_state_var.get() == "COMPLETE"
    assert app.run_state_badge.cget("style") == "CX.Status.Info.TLabel"

