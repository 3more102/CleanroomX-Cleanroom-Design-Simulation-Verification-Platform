"""Real Tk coverage for the production engineering output/verification workspace."""
from __future__ import annotations

import copy
import os
import tkinter as tk

import pytest

import cleanroomx.gui as gui_module
from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path
from cleanroomx.gui_state import load_gui_layout_state
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


def test_ui_layout_save_failure_uses_non_modal_diagnostic_boundary(app, monkeypatch):
    recorded = {}

    def fail_save(*_args, **_kwargs):
        raise OSError("layout storage unavailable")

    class Report:
        reference = "CX-TEST-LAYOUT"

    def record(operation, exc):
        recorded["operation"] = operation
        recorded["exception"] = exc
        return Report()

    monkeypatch.setattr(gui_module, "save_gui_layout_state", fail_save)
    monkeypatch.setattr(gui_module, "record_gui_exception", record)
    monkeypatch.setattr(
        gui_module.messagebox,
        "showerror",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("layout persistence failures must remain non-modal")
        ),
    )

    app._save_ui_layout_state()

    assert recorded["operation"] == "Save workstation layout"
    assert isinstance(recorded["exception"], OSError)
    assert str(recorded["exception"]) == "layout storage unavailable"
    assert app.status_var.get() == "Workstation layout not saved · CX-TEST-LAYOUT"


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
    assert app.diagnostics_status_var.get().startswith("Problems:")


def test_problem_filter_and_navigation_use_canonical_spatial_issue(app):
    result, issue = _force_room_overlap(app)
    assert result["summary"]["issue_count"] >= 1
    assert issue["element"]["type"] == "spatial_element"
    summary = result["summary"]
    assert app.diagnostics_status_var.get() == (
        f"Problems: {summary['error_count']}E {summary['warning_count']}W"
    )

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


def test_problem_browser_rule_filter_multitoken_search_and_multi_copy(app):
    _result, issue = _force_room_overlap(app)
    panel = app.problems_panel

    assert issue["rule"] in panel.rule_combo.cget("values")
    panel.rule_var.set(issue["rule"])
    app.root.update()
    visible = panel.tree.get_children()
    assert visible
    assert all(
        panel._issues_by_iid[iid]["rule"] == issue["rule"]
        for iid in visible
    )

    panel.rule_var.set("All")
    panel.search_var.set("spatial room_overlap")
    app.root.update()
    visible = panel.tree.get_children()
    assert visible
    assert all(
        "spatial" in panel._issues_by_iid[iid]["rule"].casefold()
        and "room_overlap" in panel._issues_by_iid[iid]["rule"].casefold()
        for iid in visible
    )

    first = copy.deepcopy(issue)
    second = copy.deepcopy(issue)
    first["sequence"] = 9001
    second["sequence"] = 9002
    second["rule"] = "spatial.room_overlap.secondary"
    panel.last_result = {
        "issues": [first, second],
        "summary": {
            "status": "warning",
            "issue_count": 2,
            "error_count": 0,
            "warning_count": 2,
            "info_count": 0,
        },
    }
    panel.search_var.set("")
    panel._refresh_filter_values()
    panel._populate()
    app.root.update()

    items = panel.tree.get_children()
    assert len(items) == 2
    panel.tree.selection_set(items)
    panel.copy_selected()
    copied = __import__("json").loads(panel.clipboard_get())
    assert [item["sequence"] for item in copied] == [9001, 9002]
    assert "2 diagnostics copied" in app.status_var.get()


def test_problem_table_supports_columns_and_select_all_without_domain_mutation(app):
    result, _issue = _force_room_overlap(app)
    panel = app.problems_panel
    snapshot = copy.deepcopy(result)

    assert panel.table_behavior.set_column_visible("level", False)
    assert "level" not in panel.table_behavior.visible_columns()
    assert panel.table_behavior.select_all()
    assert len(panel.tree.selection()) == len(panel.tree.get_children())
    panel.table_behavior.reset_column_layout()

    assert panel.table_behavior.visible_columns() == (
        "severity",
        "state",
        "code",
        "description",
        "object",
        "level",
        "source",
    )
    assert panel.last_result == snapshot


def test_engineering_table_column_layouts_persist_outside_project_data(app):
    metadata_before = copy.deepcopy(app.project.metadata)
    problems = app.problems_panel.table_behavior
    tasks = app.task_center.table_behavior

    assert problems.set_column_visible("level", False)
    app.problems_panel.tree.column("description", width=640)
    problems._notify_layout_change()

    assert tasks.set_column_visible("duration", False)
    app.task_center.tree.column("#0", width=310)
    tasks._notify_layout_change()
    app.root.update()

    persisted = load_gui_layout_state(app._ui_state_path)
    assert persisted["table_layouts"]["project_diagnostics"]["visible_columns"] == [
        "severity",
        "state",
        "code",
        "description",
        "object",
        "source",
    ]
    assert (
        persisted["table_layouts"]["project_diagnostics"]["widths"]["description"]
        == 640
    )
    assert "duration" not in persisted["table_layouts"]["task_center"]["visible_columns"]
    assert persisted["table_layouts"]["task_center"]["widths"]["#0"] == 310
    assert app.project.metadata == metadata_before


def test_problem_browser_projects_only_explicit_canonical_freshness_states(app):
    panel = app.problems_panel
    base = {
        "severity": "warning",
        "category": "verification",
        "message": "Synthetic canonical state projection test",
        "suggested_action": "Use the canonical workflow.",
        "element": {"type": "analysis", "id": "a", "name": "A"},
    }
    issues = [
        dict(base, sequence=7001, rule="verification_currency.stale"),
        dict(base, sequence=7002, rule="verification_currency.not_verified"),
        dict(
            base,
            sequence=7003,
            rule="verification_currency.dependency_freshness_unverifiable",
        ),
        dict(base, sequence=7004, rule="analysis.duplicate_name"),
    ]
    panel.last_result = {
        "issues": issues,
        "summary": {
            "status": "warning",
            "issue_count": 4,
            "error_count": 0,
            "warning_count": 4,
            "info_count": 0,
        },
    }
    panel.clear_filters()
    panel._refresh_filter_values()
    panel._populate()
    app.root.update()

    states = {
        panel._issues_by_iid[iid]["rule"]: panel.tree.set(iid, "state")
        for iid in panel.tree.get_children()
    }
    assert states["verification_currency.stale"] == "STALE"
    assert states["verification_currency.not_verified"] == "UNVERIFIED"
    assert (
        states["verification_currency.dependency_freshness_unverifiable"]
        == "UNVERIFIABLE"
    )
    assert states["analysis.duplicate_name"] == "OPEN"

    panel.state_var.set("Stale")
    app.root.update()
    visible = panel.tree.get_children()
    assert len(visible) == 1
    assert panel._issues_by_iid[visible[0]]["rule"] == "verification_currency.stale"

    panel.state_var.set("All")
    panel._sort_by("state")
    app.root.update()
    assert [panel.tree.set(iid, "state") for iid in panel.tree.get_children()] == [
        "STALE",
        "UNVERIFIABLE",
        "UNVERIFIED",
        "OPEN",
    ]
