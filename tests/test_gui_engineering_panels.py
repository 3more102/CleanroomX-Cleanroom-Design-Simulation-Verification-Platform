"""Real Tk coverage for the production engineering output/verification workspace."""
from __future__ import annotations

import copy
import os
import tkinter as tk

import pytest

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path
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


def test_dashboard_projects_live_engineering_health_without_mutating_project(app):
    project_before = copy.deepcopy(app.project.to_dict())
    tabs = _tab_texts(app.notebook)
    assert "Dashboard" in tabs

    app._activate_dashboard_workspace()
    app.root.update()

    layout = app.project.metadata[SPATIAL_METADATA_KEY]
    assert app.notebook.select() == str(app.dashboard)
    assert app.workspace_status_var.get() == "Workspace: Dashboard"
    assert app.dashboard.rooms_var.get() == str(len(layout["rooms"]))
    assert app.dashboard.devices_var.get() == str(len(layout["devices"]))
    assert app.dashboard.analyses_var.get() == str(len(app.project.analyses))
    assert len(app.dashboard.health_tree.get_children()) == 4
    assert app.project.to_dict() == project_before


def test_navigator_dashboard_and_shell_health_badges_are_first_class(app):
    assert app.analysis_tree.exists("nav-dashboard")
    app.analysis_tree.selection_set("nav-dashboard")
    app.analysis_tree.focus("nav-dashboard")
    app._on_navigator_selected()
    app.root.update()

    assert app.notebook.select() == str(app.dashboard)
    assert app.project_state_var.get() in {"SAVED", "UNSAVED", "RUNNING"}
    assert app.diagnostics_state_var.get().startswith("DIAGNOSTICS")
    assert app.verification_state_var.get().startswith("VERIFY")
    assert app.evidence_state_var.get().startswith("EVIDENCE")


def test_problem_detail_is_engineering_focused_not_raw_json_dump(app):
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
    text = panel.detail.get("1.0", "end").strip()

    assert "Affected object:" in text
    assert "Engineering domain:" in text
    assert "Recommended recovery" in text
    assert not text.startswith("{")


def test_simulation_workspace_exposes_real_runner_state(app):
    project_before = copy.deepcopy(app.project.to_dict())
    assert "Simulation" in _tab_texts(app.notebook)

    app._activate_simulation_workspace()
    app.root.update()
    analysis = app.project.analysis_by_id(app.project.active_analysis_id)

    assert app.notebook.select() == str(app.simulation_workspace)
    assert app.workspace_status_var.get() == "Workspace: Simulation"
    assert app.simulation_workspace.analysis_var.get() == analysis.name
    assert app.simulation_workspace.kind_var.get() == analysis.kind
    assert app.simulation_workspace.state_var.get() in {"READY", "PASS", "PASSED", "OK", "SUCCESS"}
    assert app.project.to_dict() == project_before


def test_simulation_workspace_tracks_completed_session_result(app):
    analysis = app.project.analysis_by_id(app.project.active_analysis_id)
    run = app.smoke_run_active()
    app._activate_simulation_workspace()
    app.root.update()

    assert app.simulation_workspace.analysis_var.get() == analysis.name
    assert run.title in app.simulation_workspace.result_var.get()
    assert run.status.upper() == app.simulation_workspace.state_var.get()
    assert app.simulation_workspace.cancel_button.cget("state") == "disabled"


def test_workspace_presets_rearrange_real_workspaces_without_model_mutation(app):
    project_before = copy.deepcopy(app.project.to_dict())

    app.activate_workspace_preset("design")
    app.root.update()
    assert app.notebook.select() == str(app.spatial_workspace)
    assert app.navigator_panel_visible_var.get() is True
    assert app.output_panel_visible_var.get() is False
    assert app.spatial_workspace.inspector_visible()

    app.activate_workspace_preset("simulation")
    app.root.update()
    assert app.notebook.select() == str(app.simulation_workspace)
    assert app.output_panel_visible_var.get() is True
    assert app.output_notebook.select() == str(app.result_text.master)
    assert not app.spatial_workspace.inspector_visible()

    app.activate_workspace_preset("verification")
    app.root.update()
    assert app.notebook.select() == str(app.dashboard)
    assert app.output_notebook.select() == str(app.problems_panel)

    app.activate_workspace_preset("evidence")
    app.root.update()
    assert app.notebook.select() == str(app.proofgraph_viewer)
    assert app.output_notebook.select() == str(app.evidence_text.master)

    app.activate_workspace_preset("reporting")
    app.root.update()
    assert app.notebook.select() == str(app.dashboard)
    assert app.navigator_panel_visible_var.get() is False
    assert app.output_notebook.select() == str(app.report_text.master)

    assert app.project.to_dict() == project_before


def test_workspace_preset_rejects_unknown_layout(app):
    with pytest.raises(ValueError, match="unsupported workspace preset"):
        app.activate_workspace_preset("unknown")
