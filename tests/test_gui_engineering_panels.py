"""Real Tk coverage for the production engineering output/verification workspace."""
from __future__ import annotations

import copy
import os
import tkinter as tk

import pytest

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path
from cleanroomx.project_diagnostics import PROJECT_DIAGNOSTICS_SCHEMA
from cleanroomx.project_requirements import (
    PROJECT_REQUIREMENTS_METADATA_KEY,
    ProjectRequirement,
    ProjectRequirementSet,
    ProjectRequirements,
)
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



def test_problem_browser_supports_engineering_filters_sorting_and_relative_navigation(app):
    result, issue = _force_room_overlap(app)
    panel = app.problems_panel

    assert issue["category"] in panel.category_combo.cget("values")
    assert issue["element"]["type"] in panel.object_combo.cget("values")

    panel.severity_var.set(str(issue["severity"]).title())
    panel.category_var.set(str(issue["category"]))
    panel.object_var.set(str(issue["element"]["type"]))
    app.root.update()

    visible = panel.tree.get_children()
    assert visible
    for iid in visible:
        candidate = panel._issues_by_iid[iid]
        assert candidate["severity"] == issue["severity"]
        assert candidate["category"] == issue["category"]
        assert candidate["element"]["type"] == issue["element"]["type"]
    assert panel.visible_var.get().endswith(f"of {result['summary']['issue_count']} visible")

    panel._sort_by("code")
    app.root.update()
    codes = [str(panel.tree.set(iid, "code")) for iid in panel.tree.get_children()]
    assert codes == sorted(codes, key=str.casefold)

    panel.clear_filters()
    app.root.update()
    all_items = list(panel.tree.get_children())
    assert len(all_items) == result["summary"]["issue_count"]
    assert panel.visible_var.get() == (
        f"{result['summary']['issue_count']} of "
        f"{result['summary']['issue_count']} visible"
    )

    panel.tree.selection_set(all_items[0])
    panel.tree.focus(all_items[0])
    selected = panel.select_relative(1)
    assert selected is not None
    if len(all_items) > 1:
        assert selected is not panel._issues_by_iid[all_items[0]]


def test_workspace_presets_route_engineers_to_task_oriented_layouts(app):
    workspace = app.spatial_workspace
    project_before = copy.deepcopy(app.project.to_dict())

    app.activate_workspace_profile("design")
    app.root.update()
    assert app.navigator_panel_visible_var.get() is True
    assert app.output_panel_visible_var.get() is False
    assert workspace.inspector_visible()
    assert app.notebook.select() == str(workspace)
    assert app.workspace_status_var.get() == "Workspace: Design"

    app.activate_workspace_profile("simulation")
    app.root.update()
    assert app.navigator_panel_visible_var.get() is True
    assert app.output_panel_visible_var.get() is True
    assert not workspace.inspector_visible()
    assert app.notebook.select() == str(app.plot_tab)
    assert app.output_notebook.select() == str(app.result_text.master)
    assert app.workspace_status_var.get() == "Workspace: Simulation"

    app.activate_workspace_profile("verification")
    app.root.update()
    assert app.notebook.select() == str(workspace)
    assert app.output_notebook.select() == str(app.problems_panel)
    assert app.workspace_status_var.get() == "Workspace: Verification"

    app.activate_workspace_profile("evidence")
    app.root.update()
    assert app.notebook.select() == str(app.proofgraph_viewer)
    assert app.output_notebook.select() == str(app.evidence_text.master)
    assert app.workspace_status_var.get() == "Workspace: Evidence"

    app.activate_workspace_profile("reporting")
    app.root.update()
    assert app.navigator_panel_visible_var.get() is False
    assert app.output_panel_visible_var.get() is True
    assert app.notebook.select() == str(app.plot_tab)
    assert app.output_notebook.select() == str(app.report_text.master)
    assert app.workspace_status_var.get() == "Workspace: Reporting"
    assert app.project.to_dict() == project_before


def test_density_modes_change_engineering_row_density_without_project_mutation(app):
    from tkinter import ttk

    project_before = copy.deepcopy(app.project.to_dict())
    style = ttk.Style(app.root)

    app.set_density("compact", persist=False)
    app.root.update_idletasks()
    assert app.density_var.get() == "compact"
    assert int(style.lookup("Treeview", "rowheight")) == 20

    app.set_density("comfortable", persist=False)
    app.root.update_idletasks()
    assert app.density_var.get() == "comfortable"
    assert int(style.lookup("Treeview", "rowheight")) == 24
    assert app.project.to_dict() == project_before


def test_problem_browser_can_focus_global_search_result(app):
    _result, issue = _force_room_overlap(app)
    panel = app.problems_panel
    panel.search_var.set("definitely-no-match")
    panel.severity_var.set("Warning")
    app.root.update()
    assert panel.tree.get_children() == ()

    assert panel.focus_issue(issue)
    app.root.update()
    assert panel.search_var.get() == ""
    assert panel.severity_var.get() == "All"
    selected = panel.selected_issue()
    assert selected is not None
    assert selected["sequence"] == issue["sequence"]


def test_project_navigator_projects_requirements_and_diagnostic_state(app, monkeypatch):
    requirement = ProjectRequirement(
        id="req-nav-ach",
        title="Navigator minimum ACH",
        description="Navigator regression requirement.",
        discipline="HVAC",
        category="air_change_rate",
        source="GUI regression",
        source_revision="R1",
        unit="1/h",
        minimum=15.0,
        applicability="applicable",
        scope=("room-a",),
        verification_method="analysis",
        required_evidence=("analysis_result",),
        status="approved",
    )
    requirements = ProjectRequirements(
        sets=(
            ProjectRequirementSet(
                id="set-nav",
                title="Navigator requirements",
                source="GUI regression",
                source_revision="R1",
                requirements=(requirement,),
            ),
        )
    )
    app.project.metadata[PROJECT_REQUIREMENTS_METADATA_KEY] = requirements.to_dict()
    result, issue = _force_room_overlap(app)
    app.root.update()

    assert app.analysis_tree.item("nav-requirements", "text") == "Requirements (1)"
    requirement_iid = "requirement:req-nav-ach"
    assert app.analysis_tree.exists(requirement_iid)
    assert "APPROVED" in app.analysis_tree.item(requirement_iid, "text")

    summary = result["summary"]
    diagnostics_label = app.analysis_tree.item("nav-diagnostics", "text")
    assert f"{summary['error_count']} E" in diagnostics_label
    assert f"{summary['warning_count']} W" in diagnostics_label
    severity_iid = f"nav-diagnostics:{issue['severity']}"
    assert app.analysis_tree.exists(severity_iid)

    opened: list[str] = []
    monkeypatch.setattr(
        app,
        "_open_requirement_search_result",
        lambda requirement_id: opened.append(requirement_id),
    )
    app.analysis_tree.selection_set(requirement_iid)
    app._on_navigator_selected()
    assert opened == ["req-nav-ach"]

    app.analysis_tree.selection_set(severity_iid)
    app._on_navigator_selected()
    app.root.update()
    assert app.output_notebook.select() == str(app.problems_panel)
    assert app.problems_panel.severity_var.get() == str(issue["severity"]).title()


def test_navigator_evidence_and_report_sections_reveal_hidden_output(app):
    app.output_panel_visible_var.set(False)
    app._sync_output_panel_visibility()
    app.root.update()
    assert not app._paned_contains(app.workspace_panes, app.output_panel)

    app.analysis_tree.selection_set("nav-evidence")
    app._on_navigator_selected()
    app.root.update()
    assert app._paned_contains(app.workspace_panes, app.output_panel)
    assert app.output_notebook.select() == str(app.evidence_text.master)

    app.hide_output_panel()
    app.analysis_tree.selection_set("nav-reports")
    app._on_navigator_selected()
    app.root.update()
    assert app._paned_contains(app.workspace_panes, app.output_panel)
    assert app.output_notebook.select() == str(app.report_text.master)


def test_status_bar_tracks_canonical_diagnostics_and_run_state(app):
    result = app._refresh_engineering_panels()
    assert result is not None
    summary = result["summary"]
    assert app.verification_status_var.get() == (
        f"DRC: {summary['error_count']}E/{summary['warning_count']}W"
    )
    assert app.engineering_status_var.get().startswith(
        app.verification_status_var.get()
    )
    assert "RUN: idle" in app.engineering_status_var.get()

    app._set_running(True)
    app.root.update_idletasks()
    assert app.run_status_var.get() == "RUN: running"
    assert "RUN: running" in app.engineering_status_var.get()

    app._set_running(False)
    app.root.update_idletasks()
    assert app.run_status_var.get() == "RUN: idle"
    assert app.run_button.cget("state") == "normal"
    assert app.input_text.cget("state") == "normal"


def test_engineering_health_status_remains_visible_at_minimum_window(app):
    app.root.geometry("1050x680")
    app.root.update()

    label = app.engineering_status_label
    assert label.winfo_ismapped()
    assert label.winfo_x() + label.winfo_width() <= app.status_bar.winfo_width()
