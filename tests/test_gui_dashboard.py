from __future__ import annotations

import os
import tkinter as tk

import pytest

from cleanroomx.gui_dashboard import (
    EngineeringDashboard,
    _status_style,
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
        assert dashboard.model_var.get() == "8 rooms · 21 devices"
        assert dashboard.analysis_var.get() == "4 configured"
        assert dashboard.evidence_var.get() == "7 records"
        assert dashboard.issue_tree.get_children()
    finally:
        root.destroy()



def test_system_status_projection_uses_only_explicit_project_state():
    projected = dict(
        (name, (state, detail))
        for name, state, detail in system_status_projection(
            {
                "diagnostics": {"summary": {"status": "warning", "issue_count": 2}},
                "verification": {
                    "configured_analysis_count": 4,
                    "current_count": 3,
                    "stale_count": 1,
                    "not_verified_count": 0,
                },
                "model": {"room_count": 8},
                "analysis_count": 4,
                "last_run": {"title": "Pressure Network", "status": "completed"},
                "evidence": {"record_count": 7, "proofgraph_count": 4},
            }
        )
    )

    assert projected["MODEL"] == ("ready", "8 rooms")
    assert projected["DIAGNOSTICS"] == ("warning", "2 issues")
    assert projected["VERIFICATION"][0] == "stale"
    assert "1 stale" in projected["VERIFICATION"][1]
    assert projected["ANALYSIS"] == ("completed", "Pressure Network")
    assert projected["EVIDENCE"] == ("available", "7 records · 4 graphs")


def test_system_status_projection_does_not_invent_pass_for_missing_state():
    projected = dict((name, state) for name, state, _detail in system_status_projection({}))
    assert projected["MODEL"] == "not checked"
    assert projected["DIAGNOSTICS"] == "not checked"
    assert projected["VERIFICATION"] == "not checked"
    assert projected["ANALYSIS"] == "not checked"
    assert projected["EVIDENCE"] == "not checked"
