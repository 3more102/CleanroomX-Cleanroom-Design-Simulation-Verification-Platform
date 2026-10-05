"""Real Tk coverage for the production engineering output/verification workspace."""
from __future__ import annotations

import copy
import os
import tkinter as tk

import pytest

import cleanroomx.gui_panels as gui_panels_module
from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path
from cleanroomx.gui_errors import GuiErrorReport
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

def test_problem_browser_surfaces_backend_failure_with_reference_and_retry_guidance(
    app,
    monkeypatch,
    tmp_path,
):
    report = GuiErrorReport(
        reference="CX-DIAG-1234",
        operation="Refresh project diagnostics",
        exception_type="RuntimeError",
        summary="synthetic diagnostics failure",
        log_path=tmp_path / "gui.log",
    )
    recorded = []

    def fail_diagnostics(*args, **kwargs):
        raise RuntimeError("synthetic diagnostics failure")

    monkeypatch.setattr(
        gui_panels_module,
        "analyze_project_diagnostics",
        fail_diagnostics,
    )
    monkeypatch.setattr(
        gui_panels_module,
        "record_gui_exception",
        lambda operation, exc: recorded.append((operation, exc)) or report,
    )

    panel = app.problems_panel
    result = panel.refresh()
    app.root.update()

    assert result is None
    assert panel.last_result is None
    assert panel.last_error_report is report
    assert panel.summary_var.get() == "Diagnostics unavailable · CX-DIAG-1234"
    assert panel.visible_var.get() == "0 visible"
    assert "CX-DIAG-1234" in app.status_var.get()
    detail = panel.detail.get("1.0", "end").strip()
    assert "Refresh project diagnostics did not complete." in detail
    assert "synthetic diagnostics failure" in detail
    assert "Error reference: CX-DIAG-1234" in detail
    assert "Use Refresh to retry project diagnostics." in detail
    assert "Traceback" not in detail
    assert recorded
    assert recorded[0][0] == "Refresh project diagnostics"
    assert isinstance(recorded[0][1], RuntimeError)

def test_problem_table_layout_survives_workstation_state_capture_and_restore(app):
    behavior = app.problems_panel.table_behavior
    tree = app.problems_panel.tree

    tree.column("description", width=640)
    assert behavior.set_column_visible("source", False)
    behavior.sort_by("code")

    captured = app._capture_ui_layout_state()
    problems_layout = captured["table_layouts"]["problems"]
    assert "source" not in problems_layout["visible_columns"]
    assert problems_layout["column_widths"]["description"] == 640
    assert problems_layout["sort_column"] == "code"

    behavior.show_all_columns()
    tree.column("description", width=240)
    behavior.sort_by("description")
    app._ui_layout_state = captured
    app._restore_ui_layout_state()
    app.root.update()

    assert "source" not in behavior.visible_columns()
    assert int(tree.column("description", "width")) == 640
    assert behavior.sort_column == "code"

