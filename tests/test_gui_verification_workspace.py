from __future__ import annotations

import os
import tkinter as tk

import pytest

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path
from cleanroomx.gui_verification import verification_workspace_projection


def test_verification_workspace_projection_preserves_canonical_currency_states():
    state = verification_workspace_projection(
        {
            "verification": {
                "configured_analysis_count": 3,
                "current_count": 1,
                "stale_count": 1,
                "not_verified_count": 1,
                "not_configured_count": 2,
                "dependency_freshness_unverifiable_count": 0,
            },
            "verification_items": [
                {
                    "analysis_id": "a1",
                    "analysis_name": "Room ACH",
                    "analysis_kind": "room",
                    "state": "current",
                },
                {
                    "analysis_id": "a2",
                    "analysis_name": "Pressure",
                    "analysis_kind": "project",
                    "state": "stale",
                    "explanation": "The persisted verification identity no longer matches current inputs.",
                    "mismatch_reasons": ["analysis_input_sha256"],
                    "active_mapping_ids": ["map-1", "map-2"],
                    "external_dependency_count": 1,
                },
            ],
            "diagnostics": {
                "summary": {
                    "issue_count": 4,
                    "error_count": 1,
                    "warning_count": 3,
                }
            },
            "evidence": {"record_count": 5, "proofgraph_count": 2},
        }
    )

    assert state["state"] == "stale"
    assert state["configured"] == 3
    assert state["current"] == 1
    assert state["stale"] == 1
    assert state["not_verified"] == 1
    assert "persisted verification identity" in state["rows"][1]["detail"]
    assert "analysis_input_sha256" in state["rows"][1]["detail"]
    assert state["rows"][1]["mapping_count"] == 2
    assert state["rows"][1]["external_dependency_count"] == 1
    assert state["evidence_count"] == 5


def test_verification_workspace_projection_does_not_invent_configured_verification():
    state = verification_workspace_projection({})
    assert state["state"] == "not configured"
    assert state["configured"] == 0
    assert state["current"] == 0
    assert state["rows"] == ()


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


def test_navigator_routes_verification_to_first_class_workspace(app):
    app.analysis_tree.selection_set("nav-verification")
    app.analysis_tree.focus("nav-verification")
    app._on_navigator_selected()
    app.root.update_idletasks()

    assert app.notebook.select() == str(app.verification_workspace)
    assert app.workspace_status_var.get() == "Workspace: Verification"


def test_verification_workspace_projection_keeps_unverifiable_distinct_from_stale():
    state = verification_workspace_projection(
        {
            "verification": {
                "configured_analysis_count": 1,
                "current_count": 0,
                "stale_count": 0,
                "not_verified_count": 0,
                "dependency_freshness_unverifiable_count": 1,
            }
        }
    )
    assert state["state"] == "dependency freshness unverifiable"
