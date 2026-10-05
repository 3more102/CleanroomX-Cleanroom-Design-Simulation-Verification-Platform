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



def test_problem_browser_supports_category_rule_filters_and_filtered_export(app):
    result, issue = _force_room_overlap(app)
    panel = app.problems_panel

    assert "spatial" in panel.category_picker.cget("values")
    assert "spatial.room_overlap" in panel.rule_picker.cget("values")

    panel.category_var.set("spatial")
    panel.rule_var.set("spatial.room_overlap")
    app.root.update()

    visible = panel.tree.get_children()
    assert visible
    assert all(
        panel._issues_by_iid[iid]["category"] == "spatial"
        and panel._issues_by_iid[iid]["rule"] == "spatial.room_overlap"
        for iid in visible
    )
    assert f"{len(visible)}/{result['summary']['issue_count']} shown" in panel.summary_var.get()

    filtered = panel.filtered_result()
    assert filtered is not None
    assert filtered is not result
    assert filtered["summary"]["issue_count"] == len(visible)
    assert filtered["issues"]
    assert all(item["rule"] == "spatial.room_overlap" for item in filtered["issues"])
    assert result["summary"]["issue_count"] >= filtered["summary"]["issue_count"]
    assert any(
        item["sequence"] == issue["sequence"]
        for item in filtered["issues"]
    )

    exported = []
    panel._export_callback = lambda payload: exported.append(payload)
    panel._export()
    assert len(exported) == 1
    assert exported[0]["issues"] == filtered["issues"]
    assert exported[0]["summary"] == filtered["summary"]


def test_problem_browser_previous_next_cycles_visible_diagnostics(app):
    _force_room_overlap(app)
    panel = app.problems_panel
    panel.clear_filters()

    issues = list(panel._issues_from_result(panel.last_result))
    assert issues
    if len(issues) == 1:
        duplicate = copy.deepcopy(issues[0])
        duplicate["sequence"] = int(issues[0]["sequence"]) + 1000
        duplicate["rule"] = "test.second_diagnostic"
        panel.last_result["issues"].append(duplicate)
        panel.last_result["summary"]["issue_count"] += 1
        panel._refresh_filter_choices()
        panel._populate()

    children = list(panel.tree.get_children())
    assert len(children) >= 2

    panel.tree.selection_set(children[0])
    panel.tree.focus(children[0])
    panel._step_selection(1)
    assert panel.tree.selection() == (children[1],)

    panel._step_selection(-1)
    assert panel.tree.selection() == (children[0],)


def test_problem_browser_clear_filters_restores_all_findings(app):
    result, _issue = _force_room_overlap(app)
    panel = app.problems_panel

    panel.search_var.set("room_overlap")
    panel.severity_var.set("Warning")
    panel.category_var.set("spatial")
    panel.rule_var.set("spatial.room_overlap")
    app.root.update()
    assert len(panel.tree.get_children()) <= result["summary"]["issue_count"]

    panel.clear_filters()
    app.root.update()
    assert panel.search_var.get() == ""
    assert panel.severity_var.get() == "All"
    assert panel.category_var.get() == "All"
    assert panel.rule_var.get() == "All"
    assert len(panel.tree.get_children()) == result["summary"]["issue_count"]
