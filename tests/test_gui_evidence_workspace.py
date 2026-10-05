from __future__ import annotations

import os
import tkinter as tk

import pytest

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path
from cleanroomx.gui_evidence import (
    evidence_record_matches_filters,
    evidence_workspace_projection,
)


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


def test_evidence_workspace_retained_state_is_not_a_pass_verdict(app):
    app.evidence_workspace.refresh(
        {
            "evidence_records": [
                {
                    "sequence": 1,
                    "analysis_id": "a1",
                    "analysis_name": "A1",
                    "analysis_kind": "room",
                    "verification": {"status": "fail", "verified": True},
                    "evidence": [{"id": "ev-1"}],
                    "record_sha256": "a" * 64,
                }
            ]
        }
    )
    app.root.update_idletasks()

    assert app.evidence_workspace.status_var.get() == "RETAINED"
    assert app.evidence_workspace.status_label.cget("style") == "CX.Status.Info.TLabel"



def test_evidence_record_filters_use_persisted_ledger_fields_only():
    row = {
        "sequence": 7,
        "completed": "2026-10-05T08:00:00Z",
        "analysis_id": "room-a",
        "analysis_name": "Room A",
        "analysis_kind": "room_verification",
        "status": "pass",
        "identity": "abc123",
        "record_sha256": "def456",
    }

    assert evidence_record_matches_filters(
        row,
        verdict="pass",
        analysis_kind="room_verification",
        query="room 2026",
    )
    assert evidence_record_matches_filters(row, query="abc123")
    assert not evidence_record_matches_filters(row, verdict="fail")
    assert not evidence_record_matches_filters(row, query="pressure cascade")


def test_evidence_workspace_filters_retained_records_and_preserves_counts(app):
    app.evidence_workspace.refresh(
        {
            "evidence_records": [
                {
                    "sequence": 1,
                    "analysis_id": "room-a",
                    "analysis_name": "Room A",
                    "analysis_kind": "ach",
                    "completed_at_utc": "2026-10-05T08:00:00Z",
                    "verification": {"status": "pass", "verified": True},
                    "evidence": [{"id": "ev-1"}],
                    "proofgraphs": [{"id": "pg-a"}],
                },
                {
                    "sequence": 2,
                    "analysis_id": "zone-b",
                    "analysis_name": "Zone B",
                    "analysis_kind": "pressure",
                    "completed_at_utc": "2026-10-05T09:00:00Z",
                    "verification": {"status": "fail", "verified": True},
                    "evidence": [{"id": "ev-2"}, {"id": "ev-3"}],
                    "proofgraphs": [{"id": "pg-b"}],
                },
            ]
        }
    )
    panel = app.evidence_workspace
    app.root.update_idletasks()

    assert panel.records_var.get() == "2"
    assert panel.evidence_var.get() == "3"
    assert panel.graphs_var.get() == "2"
    assert panel.visible_var.get() == "2 / 2 visible"

    panel.verdict_var.set("fail")
    app.root.update_idletasks()
    assert len(panel.tree.get_children()) == 1
    assert panel.visible_var.get() == "1 / 2 visible"
    assert next(iter(panel._rows.values()))["sequence"] == 2

    panel.verdict_var.set("All")
    panel.search_var.set("room ach")
    app.root.update_idletasks()
    assert len(panel.tree.get_children()) == 1
    assert next(iter(panel._rows.values()))["sequence"] == 1


def test_evidence_workspace_relative_review_wraps_visible_records(app):
    app.evidence_workspace.refresh(
        {
            "evidence_records": [
                {
                    "sequence": 1,
                    "analysis_name": "A",
                    "analysis_kind": "ach",
                    "verification": {"status": "pass"},
                },
                {
                    "sequence": 2,
                    "analysis_name": "B",
                    "analysis_kind": "pressure",
                    "verification": {"status": "warning"},
                },
            ]
        }
    )
    panel = app.evidence_workspace
    children = panel.tree.get_children()
    assert len(children) == 2
    panel.tree.selection_set(children[0])
    panel.tree.focus(children[0])

    panel._select_relative(1)
    assert panel._rows[panel.tree.selection()[0]]["sequence"] == 1

    panel._select_relative(1)
    assert panel._rows[panel.tree.selection()[0]]["sequence"] == 2
