from __future__ import annotations

import os
import tkinter as tk

import pytest

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path
from cleanroomx.gui_evidence import evidence_workspace_projection


def test_evidence_projection_preserves_retained_record_semantics():
    state = evidence_workspace_projection(
        {
            "evidence_records": [
                {
                    "sequence": 4,
                    "completed_at_utc": "2026-10-05T08:00:00Z",
                    "analysis_id": "room-a",
                    "analysis_name": "Room A",
                    "analysis_kind": "room_verification",
                    "evidence": [{"id": "ev-1"}, {"id": "ev-2"}],
                    "verification": {"status": "pass", "verified": True},
                    "proofgraphs": [
                        {"graph_sha256": "a" * 64},
                        {"graph_sha256": "b" * 64},
                    ],
                    "verification_identity_sha256": "c" * 64,
                    "record_sha256": "d" * 64,
                }
            ]
        }
    )
    assert state["record_count"] == 1
    assert state["evidence_count"] == 2
    assert state["proofgraph_count"] == 2
    assert state["rows"][0]["status"] == "pass"
    assert state["rows"][0]["verified"] is True
    assert state["rows"][0]["identity"] == "c" * 64


def test_evidence_projection_does_not_invent_missing_records():
    state = evidence_workspace_projection({})
    assert state == {
        "record_count": 0,
        "evidence_count": 0,
        "proofgraph_count": 0,
        "rows": (),
    }


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


def test_navigator_routes_evidence_to_first_class_workspace(app):
    app.analysis_tree.selection_set("nav-evidence")
    app.analysis_tree.focus("nav-evidence")
    app._on_navigator_selected()
    app.root.update_idletasks()

    assert app.notebook.select() == str(app.evidence_workspace)
    assert app.workspace_status_var.get() == "Workspace: Evidence"
