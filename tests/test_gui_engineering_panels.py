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
    app.root.update()

    assert str(panel.navigate_button.cget("state")) == "normal"
    panel.navigate_button.invoke()
    app.root.update()

    assert app.spatial_workspace.selected == _Hit(
        "room",
        issue["element"]["id"],
    )
    assert app.notebook.select() == str(app.spatial_workspace)


def test_problem_panel_explains_when_filters_hide_all_issues(app):
    _result, _issue = _force_room_overlap(app)
    panel = app.problems_panel

    panel.search_var.set("__no_matching_cleanroomx_diagnostic__")
    app.root.update()

    assert not panel.tree.get_children()
    assert str(panel.navigate_button.cget("state")) == "disabled"
    assert "No diagnostics match" in panel.detail.get("1.0", "end").strip()


def test_room_diagnostic_navigation_opens_design_workspace(app):
    room = app.spatial_workspace.layout["rooms"][0]
    issue = {
        "rule": "engineering_sync.geometry_newer",
        "element": {
            "type": "room",
            "id": room["id"],
            "name": room.get("name", room["id"]),
        },
    }

    app._navigate_project_diagnostic(issue)
    app.root.update()

    assert app.spatial_workspace.selected == _Hit("room", room["id"])
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


def test_problem_panel_disables_navigation_for_project_level_issue(app):
    panel = app.problems_panel
    panel.last_result = {
        "issues": [
            {
                "sequence": 1,
                "severity": "warning",
                "rule": "project.example",
                "category": "project",
                "message": "Project-level guidance",
                "suggested_action": "Review the project.",
                "element": {"type": "project", "name": app.project.name},
            }
        ]
    }
    panel._populate()
    iid = panel.tree.get_children()[0]
    panel.tree.selection_set(iid)
    panel.tree.focus(iid)
    app.root.update()

    assert str(panel.navigate_button.cget("state")) == "disabled"


def test_problem_panel_preserves_failed_refresh_message(app, monkeypatch):
    panel = app.problems_panel

    def fail(*_args, **_kwargs):
        raise RuntimeError("diagnostic service failed")

    monkeypatch.setattr("cleanroomx.gui_panels.analyze_project_diagnostics", fail)
    assert panel.refresh() is None
    app.root.update()

    detail = panel.detail.get("1.0", "end").strip()
    assert "could not be refreshed" in detail
    assert "diagnostic service failed" in detail
