from __future__ import annotations

import copy
import os
import tkinter as tk

import pytest

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path
from cleanroomx.gui_diagnostics import diagnostics_workspace_projection
from cleanroomx.spatial import SPATIAL_METADATA_KEY


def test_diagnostics_projection_uses_only_canonical_payload():
    state = diagnostics_workspace_projection(
        {
            "summary": {
                "status": "warning",
                "issue_count": 2,
                "error_count": 0,
                "warning_count": 1,
                "info_count": 1,
            },
            "issues": [
                {"severity": "warning", "category": "spatial", "rule": "a"},
                {"severity": "info", "category": "analysis", "rule": "b"},
            ],
        }
    )
    assert state["status"] == "warning"
    assert state["issue_count"] == 2
    assert state["warning_count"] == 1
    assert state["categories"] == ("analysis", "spatial")
    assert len(state["issues"]) == 2


def test_diagnostics_projection_does_not_turn_missing_data_into_pass():
    state = diagnostics_workspace_projection(None)
    assert state["status"] == "not checked"
    assert state["issue_count"] == 0
    assert state["issues"] == ()


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


def test_navigator_routes_diagnostics_to_central_workbench(app):
    app.analysis_tree.selection_set("nav-diagnostics")
    app.analysis_tree.focus("nav-diagnostics")
    app._on_navigator_selected()
    app.root.update_idletasks()

    assert app.notebook.select() == str(app.diagnostics_workspace)
    assert app.workspace_status_var.get() == "Workspace: Diagnostics"


def test_canonical_project_diagnostics_feed_central_workbench(app):
    workspace = app.spatial_workspace
    layout = copy.deepcopy(workspace.layout)
    first, second = layout["rooms"][:2]
    second["x_m"] = first["x_m"]
    second["y_m"] = first["y_m"]
    app.project.metadata[SPATIAL_METADATA_KEY] = layout
    workspace.refresh()

    result = app._refresh_engineering_panels()
    app.root.update_idletasks()

    assert result is not None
    assert app.diagnostics_workspace._result is result
    assert any(
        issue.get("rule") == "spatial.room_overlap"
        for issue in app.diagnostics_workspace._issues_by_iid.values()
    )


def test_diagnostics_workspace_supports_semantic_rows_and_relative_navigation(app):
    result = {
        "summary": {
            "status": "error",
            "issue_count": 2,
            "error_count": 1,
            "warning_count": 1,
            "info_count": 0,
        },
        "issues": [
            {
                "sequence": 1,
                "severity": "error",
                "category": "analysis",
                "rule": "analysis.invalid",
                "message": "Invalid analysis input",
                "suggested_action": "Correct the input.",
            },
            {
                "sequence": 2,
                "severity": "warning",
                "category": "spatial",
                "rule": "spatial.review",
                "message": "Review spatial model",
                "suggested_action": "Inspect the model.",
            },
        ],
    }
    panel = app.diagnostics_workspace
    panel.refresh(result)
    app.root.update_idletasks()

    children = panel.tree.get_children()
    assert len(children) == 2
    assert panel.tree.item(children[0], "tags") == ("severity_error",)
    assert panel.tree.item(children[1], "tags") == ("severity_warning",)

    panel.tree.selection_set(children[0])
    panel.tree.focus(children[0])
    panel._select_relative(1)
    assert panel.selected_issue()["sequence"] == 2

    panel._select_relative(1)
    assert panel.selected_issue()["sequence"] == 1



def test_diagnostics_workspace_target_filter_and_multi_token_search(app):
    result = {
        "summary": {
            "status": "warning",
            "issue_count": 3,
            "error_count": 0,
            "warning_count": 2,
            "info_count": 1,
        },
        "issues": [
            {
                "sequence": 10,
                "severity": "warning",
                "category": "spatial",
                "rule": "spatial.room_overlap",
                "message": "Room geometry overlaps another room.",
                "suggested_action": "Review room placement.",
                "element": {"type": "room", "id": "room-a", "name": "Room A"},
                "details": {"level": "L2", "overlap_m2": 1.25},
            },
            {
                "sequence": 11,
                "severity": "warning",
                "category": "traceability",
                "rule": "verification_currency.stale",
                "message": "Persisted verification is stale.",
                "element": {"type": "analysis", "id": "ach-a", "name": "Room ACH"},
                "details": {"level": "L2"},
            },
            {
                "sequence": 12,
                "severity": "info",
                "category": "engineering_sync",
                "rule": "engineering_sync.not_configured",
                "message": "Synchronization authority is not configured.",
            },
        ],
    }
    panel = app.diagnostics_workspace
    panel.refresh(result)
    app.root.update_idletasks()

    assert tuple(panel.target_combo.cget("values")) == (
        "All",
        "analysis",
        "project",
        "room",
    )
    assert tuple(panel.rule_combo.cget("values")) == (
        "All",
        "engineering_sync.not_configured",
        "spatial.room_overlap",
        "verification_currency.stale",
    )

    panel.rule_var.set("verification_currency.stale")
    app.root.update_idletasks()
    assert {
        issue["sequence"] for issue in panel._issues_by_iid.values()
    } == {11}

    panel.clear_filters()
    app.root.update_idletasks()
    assert panel.rule_var.get() == "All"
    assert len(panel.tree.get_children()) == 3

    panel.target_type_var.set("room")
    app.root.update_idletasks()
    assert len(panel.tree.get_children()) == 1
    assert panel.selected_issue() is None or panel.selected_issue()["sequence"] == 10

    panel.target_type_var.set("All")
    panel.search_var.set("room l2")
    app.root.update_idletasks()
    sequences = {
        issue["sequence"] for issue in panel._issues_by_iid.values()
    }
    assert sequences == {10, 11}
    assert panel.visible_var.get() == "2 / 3 visible"

    payload = panel.filtered_export_payload()
    assert payload["schema"] == "cleanroomx.diagnostics.filtered_presentation_view"
    assert payload["canonical_diagnostics"] is False
    assert payload["visible_issue_count"] == 2
    assert payload["total_issue_count"] == 3
    assert payload["filters"]["search"] == "room l2"
    assert {issue["sequence"] for issue in payload["issues"]} == {10, 11}
    assert len(result["issues"]) == 3


def test_diagnostics_workspace_detail_uses_compact_engineering_fields(app):
    result = {
        "summary": {
            "status": "warning",
            "issue_count": 1,
            "error_count": 0,
            "warning_count": 1,
            "info_count": 0,
        },
        "issues": [
            {
                "sequence": 20,
                "severity": "warning",
                "category": "airflow_balance",
                "rule": "airflow.balance",
                "message": "Airflow balance is outside the persisted rule.",
                "suggested_action": "Review supply and extract paths.",
                "element": {"type": "zone", "id": "zone-a", "name": "Zone A"},
                "details": {
                    "actual_airflow_m3_h": 920.0,
                    "required_airflow_m3_h": 1000.0,
                },
            }
        ],
    }
    panel = app.diagnostics_workspace
    panel.refresh(result)
    iid = panel.tree.get_children()[0]
    panel.tree.selection_set(iid)
    panel.tree.focus(iid)
    panel._show_selected()
    rendered = panel.detail.get("1.0", "end").strip()

    assert "RECOMMENDED RECOVERY" in rendered
    assert "ENGINEERING DETAILS" in rendered
    assert "Actual Airflow M3 H: 920" in rendered
    assert "Required Airflow M3 H: 1,000" in rendered
    assert '"actual_airflow_m3_h"' not in rendered
