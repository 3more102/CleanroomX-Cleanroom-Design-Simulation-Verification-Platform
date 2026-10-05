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
