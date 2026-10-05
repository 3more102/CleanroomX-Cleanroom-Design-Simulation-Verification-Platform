from __future__ import annotations

import os
import tkinter as tk

import pytest

from cleanroomx.gui_dashboard import (
    EngineeringDashboard,
    _status_style,
    project_readiness_projection,
    system_status_projection,
)


def test_dashboard_status_styles_are_semantic_and_deterministic():
    assert _status_style("pass") == "CX.Status.Pass.TLabel"
    assert _status_style("verified") == "CX.Status.Pass.TLabel"
    assert _status_style("fail") == "CX.Status.Fail.TLabel"
    assert _status_style("stale") == "CX.Status.Warning.TLabel"
    assert _status_style("running") == "CX.Status.Simulation.TLabel"
    assert _status_style("unknown") == "CX.Status.Neutral.TLabel"


def test_dashboard_projects_project_health_without_inventing_engineering_verdicts():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    dashboard = EngineeringDashboard(root)
    try:
        dashboard.refresh(
            {
                "project": {"name": "Fab_A12", "location": "/tmp/fab.cleanroomx.json"},
                "diagnostics": {
                    "summary": {
                        "status": "warning",
                        "issue_count": 3,
                        "error_count": 1,
                        "warning_count": 2,
                    },
                    "issues": [
                        {
                            "sequence": 1,
                            "severity": "error",
                            "rule": "CRX-AIR-017",
                            "category": "airflow",
                            "message": "Insufficient ACH",
                            "element": {"type": "room", "id": "CR-104", "name": "CR-104"},
                        }
                    ],
                },
                "verification": {
                    "configured_analysis_count": 4,
                    "current_count": 3,
                    "stale_count": 1,
                    "not_verified_count": 0,
                },
                "model": {
                    "room_count": 8,
                    "total_floor_area_m2": 325.4,
                    "total_volume_m3": 1042.0,
                    "device_count": 21,
                },
                "analysis_count": 4,
                "last_run": {"title": "Airflow Balance", "status": "completed"},
                "evidence": {"record_count": 7, "proofgraph_count": 4},
            }
        )
        root.update_idletasks()

        assert dashboard.project_var.get() == "Fab_A12"
        assert dashboard.diagnostics_var.get() == "WARNING"
        assert dashboard.verification_var.get() == "STALE"
        assert dashboard.verification_percent_var.get() == "75%"
        assert dashboard.readiness_percent_var.get() == "80%"
        assert dashboard.readiness_var.get() == "WARNING"
        assert dashboard.system_status_vars["MODEL"][0].get() == "READY"
        assert dashboard.system_status_vars["VERIFICATION"][0].get() == "STALE"
        assert dashboard.model_var.get() == "8 rooms · 21 devices"
        assert dashboard.analysis_var.get() == "4 configured"
        assert dashboard.evidence_var.get() == "7 records"
        assert dashboard.issue_tree.get_children()
    finally:
        root.destroy()

def test_dashboard_issue_rows_are_semantic_and_actionable():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")

    opened: list[dict] = []
    dashboard = EngineeringDashboard(root, on_issue=opened.append)
    try:
        dashboard.apply_theme("dark")
        issue = {
            "severity": "error",
            "rule": "spatial.room_overlap",
            "category": "geometry",
            "message": "Two cleanroom zones overlap.",
            "element": {"type": "spatial_element", "id": "CR-104", "name": "CR-104"},
            "sequence": 1,
        }
        dashboard.refresh(
            {
                "project": {"name": "Fab_A12"},
                "diagnostics": {
                    "summary": {
                        "status": "error",
                        "issue_count": 1,
                        "error_count": 1,
                        "warning_count": 0,
                    },
                    "issues": [issue],
                },
                "verification": {},
                "model": {},
                "analysis_count": 0,
                "evidence": {},
            }
        )
        root.update()

        iid = dashboard.issue_tree.get_children()[0]
        assert "error" in dashboard.issue_tree.item(iid, "tags")
        dashboard.issue_tree.selection_set(iid)
        assert dashboard.selected_issue() == issue
        assert dashboard._open_selected_issue() == "break"
        assert opened == [issue]
    finally:
        root.destroy()



def test_system_status_projection_does_not_invent_pass_for_missing_state():
    projected = {
        name: state
        for name, state, _detail in system_status_projection({})
    }
    assert projected["MODEL"] == "not checked"
    assert projected["DIAGNOSTICS"] == "not checked"
    assert projected["VERIFICATION"] == "not checked"
    assert projected["ANALYSIS"] == "not checked"
    assert projected["EVIDENCE"] == "not checked"


def test_project_readiness_projection_uses_only_explicit_subsystem_state():
    snapshot = {
        "diagnostics": {
            "summary": {"status": "warning", "issue_count": 2}
        },
        "verification": {
            "configured_analysis_count": 4,
            "current_count": 3,
            "stale_count": 1,
            "not_verified_count": 0,
        },
        "model": {"room_count": 8},
        "analysis_count": 4,
        "last_run": {
            "title": "Pressure Network",
            "status": "completed",
        },
        "evidence": {"record_count": 7, "proofgraph_count": 4},
    }
    percent, state, detail = project_readiness_projection(snapshot)
    assert percent == 80
    assert state == "warning"
    assert "3/5 subsystems ready" in detail
    assert "2 attention" in detail


def test_project_readiness_projection_does_not_claim_readiness_for_missing_state():
    percent, state, detail = project_readiness_projection({})
    assert percent == 0
    assert state == "not checked"
    assert "0/5 subsystems ready" in detail
