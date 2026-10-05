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
    assert tabs[:6] == [
        "Problems",
        "Analysis",
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
    assert app.output_notebook.select() == str(app.analysis_result_panel)
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

@pytest.mark.parametrize(
    ("navigator_id", "overlay"),
    (("nav-airflow", "Airflow"), ("nav-ach", "ACH"), ("nav-pressure", "Pressure")),
)
def test_engineering_navigator_opens_real_spatial_overlays(app, navigator_id, overlay):
    assert app.analysis_tree.exists(navigator_id)
    app.analysis_tree.selection_set(navigator_id)
    app.analysis_tree.focus(navigator_id)

    app._on_navigator_selected()
    app.root.update()

    assert app.notebook.select() == str(app.spatial_workspace)
    assert app.spatial_workspace._workspace_mode.get() == "2d"
    assert app.spatial_workspace._overlay_mode.get() == overlay
    assert overlay in app.selection_status_var.get()


def test_requirements_navigator_opens_traceability(app, monkeypatch):
    opened = []
    monkeypatch.setattr(
        app,
        "show_requirements_traceability",
        lambda: opened.append(True) or True,
    )
    app.analysis_tree.selection_set("nav-requirements")
    app.analysis_tree.focus("nav-requirements")

    app._on_navigator_selected()

    assert opened == [True]
    assert app.selection_status_var.get() == "Selected: Requirements traceability"




def test_shell_save_state_and_navigator_domain_cues_are_explicit(app):
    app._update_title()
    app.root.update_idletasks()
    assert app.shell_save_badge_var.get() == "SAVED"

    original = app.name_var.get()
    app.name_var.set(original + " edited")
    app._update_title()
    app.root.update_idletasks()
    assert app.shell_save_badge_var.get() == "UNSAVED"

    app.name_var.set(original)
    app._update_title()
    assert "domain_pressure" in app.analysis_tree.item("nav-pressure", "tags")
    assert "domain_hvac" in app.analysis_tree.item("nav-hvac", "tags")
    assert "domain_verification" in app.analysis_tree.item("nav-verification", "tags")
    assert "domain_evidence" in app.analysis_tree.item("nav-evidence", "tags")



def test_diagnostics_table_exposes_domain_and_selection_action_state(app):
    panel = app.problems_panel
    assert panel.tree.heading("domain", "text") == "Domain"
    assert "Critical" in tuple(panel.severity_picker.cget("values"))

    panel.tree.selection_remove(panel.tree.selection())
    panel._show_selected_detail()
    assert str(panel.locate_button.cget("state")) == "disabled"
    assert str(panel.copy_button.cget("state")) == "disabled"

    children = panel.tree.get_children()
    if children:
        panel.tree.selection_set(children[0])
        panel._show_selected_detail()
        assert str(panel.locate_button.cget("state")) == "normal"
        assert str(panel.copy_button.cget("state")) == "normal"

def test_workspace_layout_profiles_coordinate_shell_and_engineering_tabs(app):
    app._apply_workspace_profile("evidence")
    app.root.update()

    assert app.workspace_profile_var.get() == "evidence"
    assert app.navigator_panel_visible_var.get() is True
    assert app.output_panel_visible_var.get() is True
    assert app.spatial_workspace.inspector_visible() is False
    assert app.notebook.select() == str(app.proofgraph_viewer)
    assert app.output_notebook.select() == str(app.evidence_panel)
    assert app._ui_layout_state["workspace_profile"] == "evidence"

    app._apply_workspace_profile("design")
    app.root.update()

    assert app.workspace_profile_var.get() == "design"
    assert app.navigator_panel_visible_var.get() is True
    assert app.output_panel_visible_var.get() is False
    assert app.spatial_workspace.inspector_visible() is True
    assert app.notebook.select() == str(app.spatial_workspace)
    assert app.spatial_workspace._workspace_mode.get() == "split"


def test_density_switch_is_persisted_and_command_palette_exposes_workstation_layouts(app):
    app.set_density("comfortable")
    app.root.update_idletasks()

    assert app.density_var.get() == "comfortable"
    assert app._ui_layout_state["density"] == "comfortable"

    command_ids = {command.id for command in app._command_palette_commands()}
    assert {
        "workspace.layout.design",
        "workspace.layout.simulation",
        "workspace.layout.verification",
        "workspace.layout.evidence",
        "workspace.layout.reporting",
        "view.density.compact",
        "view.density.comfortable",
        "workspace.simulation",
    } <= command_ids

