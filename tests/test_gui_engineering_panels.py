"""Real Tk coverage for the production engineering output/verification workspace."""
from __future__ import annotations

import copy
import os
import tkinter as tk

import pytest

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path
from cleanroomx.gui_panels import diagnostic_domain, filter_project_diagnostics
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


def test_industrial_dashboard_and_status_chrome_are_first_class(app):
    tabs = _tab_texts(app.notebook)
    assert "Dashboard" in tabs
    assert app.dashboard.readiness_var.get().endswith("%")
    assert app.save_state_var.get() == "SAVED"
    assert app.diagnostics_state_var.get().startswith("DIAGNOSTICS ")
    assert app.verification_state_var.get()
    assert "Problems " in app.output_summary_var.get()
    assert "Verification " in app.output_summary_var.get()

    app.analysis_tree.selection_set("nav-dashboard")
    app.analysis_tree.focus("nav-dashboard")
    app._on_navigator_selected()
    app.root.update()

    assert app.notebook.select() == str(app.dashboard)
    assert app.workspace_status_var.get() == "Workspace: Dashboard"
    assert app.selection_status_var.get() == "Selected: Dashboard"



def test_engineering_navigator_routes_workstation_domains_and_outputs(app):
    app.analysis_tree.selection_set("nav-building")
    app.analysis_tree.focus("nav-building")
    app._on_navigator_selected()
    app.root.update()

    assert app.notebook.select() == str(app.spatial_workspace)
    assert app.workspace_status_var.get() == "Workspace: Building / Geometry"

    app.hide_output_panel()
    assert not app.output_panel_visible_var.get()
    app.analysis_tree.selection_set("nav-reports")
    app.analysis_tree.focus("nav-reports")
    app._on_navigator_selected()
    app.root.update()

    assert app.output_panel_visible_var.get()
    assert app.output_notebook.select() == str(app.report_text.master)
    assert app.workspace_status_var.get() == "Workspace: Reports"


def test_problem_severity_colors_follow_active_theme_palette(app):
    app.set_theme("dark", persist=False)
    app.root.update()

    assert app.problems_panel.tree.tag_configure("error", "foreground") == app._theme_palette["error"]
    assert app.problems_panel.tree.tag_configure("warning", "foreground") == app._theme_palette["warning"]
    assert app.problems_panel.tree.tag_configure("info", "foreground") == app._theme_palette["info"]



def test_dense_workstation_controls_have_discoverable_tooltips(app):
    assert "Ctrl+Shift+P" in app.toolbar_commands_button._cleanroomx_tooltip.text
    assert "diagnostics" in app.diagnostics_state_label._cleanroomx_tooltip.text.casefold()
    assert "verification" in app.verification_state_label._cleanroomx_tooltip.text.casefold()
    assert "Industry Foundation Classes" in app.navigator_import_ifc_button._cleanroomx_tooltip.text
    assert "Ctrl+J" in app.output_close_button._cleanroomx_tooltip.text


def test_engineering_output_workspace_exposes_first_class_panels(app):
    tabs = _tab_texts(app.output_notebook)
    assert tabs[:5] == [
        "Problems",
        "Diagnostics",
        "Verification",
        "Console",
        "Evidence",
    ]
    assert "Simulation" in tabs
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


def test_completed_run_selects_readable_simulation_summary(app):
    run = app.smoke_run_active()
    app.root.update()

    assert run.result
    assert app.output_notebook.select() == str(app.simulation_panel)
    assert app.simulation_panel.status_var.get() == str(run.status).upper()
    assert app.simulation_panel.title_var.get() == run.title
    assert app.simulation_panel.tree.get_children()
    assert app.result_text.get("1.0", "end").strip()
    assert app.problems_panel.last_result is not None
    assert app.analysis_run_state_var.get() != "IDLE"


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


def test_problem_filter_helpers_preserve_canonical_issue_payloads():
    issues = [
        {
            "sequence": 1,
            "severity": "error",
            "rule": "spatial.room_overlap",
            "category": "spatial",
            "message": "Rooms overlap",
            "suggested_action": "Move one room",
            "element": {"type": "spatial_element", "id": "room-a", "name": "Room A"},
            "details": {"floor": "Level 01"},
        },
        {
            "sequence": 2,
            "severity": "warning",
            "rule": "analysis.result_stale",
            "category": "analysis",
            "message": "Result is stale",
            "element": {"type": "analysis", "id": "analysis-a", "name": "ACH"},
            "details": {},
        },
    ]
    before = copy.deepcopy(issues)

    assert diagnostic_domain(issues[0]) == "Spatial"
    assert diagnostic_domain(issues[1]) == "Analysis"
    assert filter_project_diagnostics(
        issues,
        severity="Error",
        domain="Spatial",
        query="room_overlap",
    ) == [issues[0]]
    assert filter_project_diagnostics(
        issues,
        severity="All",
        domain="Analysis",
        query="stale",
    ) == [issues[1]]
    assert issues == before


def test_problem_panel_domain_and_relative_navigation(app):
    _force_room_overlap(app)
    panel = app.problems_panel
    panel.domain_var.set("Spatial")
    app.root.update()

    visible = list(panel.tree.get_children())
    assert visible
    assert all(
        diagnostic_domain(panel._issues_by_iid[iid]) == "Spatial"
        for iid in visible
    )
    assert panel.visible_var.get() == f"{len(visible)} shown"

    panel.tree.selection_remove(panel.tree.selection())
    panel.select_relative(1)
    assert panel.selected_issue() is not None
    assert str(panel.locate_button.cget("state")) == "normal"

    panel.clear_filters()
    app.root.update()
    assert panel.search_var.get() == ""
    assert panel.severity_var.get() == "All"
    assert panel.domain_var.get() == "All"


def test_task_workspace_profiles_route_existing_engineering_surfaces(app):
    app.apply_workspace_profile("design", persist=False)
    app.root.update()
    assert app.workspace_profile_var.get() == "design"
    assert app.notebook.select() == str(app.spatial_workspace)
    assert app.navigator_panel_visible_var.get()
    assert not app.output_panel_visible_var.get()
    assert app.spatial_workspace.inspector_visible()

    app.apply_workspace_profile("simulation", persist=False)
    app.root.update()
    assert app.notebook.select() == str(app.input_tab)
    assert app.output_panel_visible_var.get()
    assert app.output_notebook.tab(app.output_notebook.select(), "text") == "Simulation"
    assert not app.spatial_workspace.inspector_visible()

    app.apply_workspace_profile("verification", persist=False)
    app.root.update()
    assert app.notebook.select() == str(app.dashboard)
    assert app.output_notebook.tab(app.output_notebook.select(), "text") == "Problems"

    app.apply_workspace_profile("evidence", persist=False)
    app.root.update()
    assert app.notebook.select() == str(app.proofgraph_viewer)
    assert app.output_notebook.tab(app.output_notebook.select(), "text") == "Evidence"

    app.apply_workspace_profile("reporting", persist=False)
    app.root.update()
    assert app.notebook.select() == str(app.dashboard)
    assert app.output_notebook.tab(app.output_notebook.select(), "text") == "Report"


def test_workspace_profile_capture_and_restore_preserves_saved_panel_visibility(app):
    app.apply_workspace_profile("evidence", persist=False)
    app.navigator_panel_visible_var.set(False)
    app.output_panel_visible_var.set(True)
    app.spatial_workspace.set_inspector_visible(True)
    state = app._capture_ui_layout_state()

    assert state["workspace_profile"] == "evidence"
    assert state["navigator_visible"] is False
    assert state["output_visible"] is True
    assert state["inspector_visible"] is True

    app.workspace_profile_var.set("start")
    app.navigator_panel_visible_var.set(True)
    app.output_panel_visible_var.set(False)
    app.spatial_workspace.set_inspector_visible(False)
    app._ui_layout_state = state
    app._restore_ui_layout_state()
    app.root.update()

    assert app.workspace_profile_var.get() == "evidence"
    assert not app.navigator_panel_visible_var.get()
    assert app.output_panel_visible_var.get()
    assert app.spatial_workspace.inspector_visible()
    assert app.notebook.select() == str(app.proofgraph_viewer)
    assert app.output_notebook.tab(app.output_notebook.select(), "text") == "Evidence"
