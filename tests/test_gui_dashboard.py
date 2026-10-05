from __future__ import annotations

import copy
import os
import tkinter as tk

import pytest

from cleanroomx.gui_dashboard import ProjectHealthDashboard, project_health_snapshot
from cleanroomx.project import AnalysisDocument, ProjectDocument


def _project() -> ProjectDocument:
    return ProjectDocument(
        name="Dashboard project",
        analyses=[
            AnalysisDocument(
                id="analysis-1",
                name="Room verification",
                kind="room_verification",
                input={},
            )
        ],
        metadata={
            "spatial_layout": {
                "rooms": [{"id": "room-a", "name": "Room A"}],
                "devices": [
                    {"id": "sensor-a", "name": "Sensor A", "type": "sensor"},
                    {"id": "supply-a", "name": "Supply A", "type": "supply"},
                ],
            }
        },
    )


def _diagnostics() -> dict:
    return {
        "summary": {
            "status": "error",
            "error_count": 1,
            "warning_count": 1,
            "info_count": 2,
        },
        "verification_currency": {
            "summary": {
                "configured_analysis_count": 1,
                "current_count": 0,
                "stale_count": 1,
                "not_verified_count": 0,
            }
        },
        "issues": [
            {
                "sequence": 1,
                "severity": "error",
                "rule": "verification_currency.stale",
                "message": "Verification is stale.",
                "element": {
                    "type": "analysis",
                    "id": "analysis-1",
                    "name": "Room verification",
                },
            },
            {
                "sequence": 2,
                "severity": "warning",
                "rule": "run_history.external_dependency_stale",
                "message": "Dependency changed.",
                "element": {
                    "type": "project",
                    "id": "project",
                    "name": "Dashboard project",
                },
            },
        ],
    }


def _proofgraph() -> dict:
    return {
        "id": "graph-1",
        "requirement_set": {
            "requirements": [
                {"id": "REQ-1"},
                {"id": "REQ-2"},
            ]
        },
        "evidence": [{"id": "E-1"}, {"id": "E-2"}],
        "findings": [
            {"id": "F-1", "evidence_present": True},
            {"id": "F-2", "evidence_present": False},
        ],
        "verdicts": [
            {"id": "V-1", "status": "pass"},
            {"id": "V-2", "status": "fail"},
        ],
    }


def test_project_health_snapshot_uses_only_existing_project_and_evidence_state():
    project = _project()
    diagnostics = _diagnostics()
    graph = _proofgraph()
    project_before = copy.deepcopy(project.to_dict())
    diagnostics_before = copy.deepcopy(diagnostics)
    graph_before = copy.deepcopy(graph)

    snapshot = project_health_snapshot(project, diagnostics, [graph])

    assert snapshot["project_name"] == "Dashboard project"
    assert snapshot["analysis_count"] == 1
    assert snapshot["room_count"] == 1
    assert snapshot["device_count"] == 2
    assert snapshot["error_count"] == 1
    assert snapshot["warning_count"] == 1
    assert snapshot["configured_analysis_count"] == 1
    assert snapshot["current_verification_count"] == 0
    assert snapshot["stale_verification_count"] == 1
    assert snapshot["proofgraph_count"] == 1
    assert snapshot["requirement_count"] == 2
    assert snapshot["evidence_count"] == 2
    assert snapshot["unresolved_evidence_count"] == 1
    assert snapshot["evidence_completeness_percent"] == 50.0
    assert snapshot["verdict_pass_count"] == 1
    assert snapshot["verdict_fail_count"] == 1
    assert snapshot["stale_result_issue_count"] == 2

    assert project.to_dict() == project_before
    assert diagnostics == diagnostics_before
    assert graph == graph_before


@pytest.fixture
def root():
    try:
        window = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    window.withdraw()
    try:
        yield window
    finally:
        window.destroy()


def test_dashboard_renders_real_health_and_opens_selected_diagnostic(root):
    invoked: list[object] = []
    dashboard = ProjectHealthDashboard(
        root,
        on_design=lambda: None,
        on_analysis=lambda: None,
        on_problems=lambda: None,
        on_verification=lambda: None,
        on_evidence=lambda: None,
        on_reporting=lambda: None,
        on_diagnostic=invoked.append,
    )
    dashboard.pack(fill="both", expand=True)

    snapshot = dashboard.refresh(_project(), _diagnostics(), [_proofgraph()])
    root.update()

    assert snapshot["diagnostic_status"] == "error"
    assert dashboard._metrics["model"].get() == "1 rooms · 2 devices"
    assert dashboard._metrics["verification"].get() == "0/1 current"
    assert dashboard._metrics["evidence"].get() == "50% complete"
    assert dashboard._metrics["verdicts"].get() == "1 pass · 1 fail"

    rows = dashboard.tree.get_children()
    assert len(rows) == 2
    dashboard.tree.selection_set(rows[0])
    dashboard._open_selected_issue()

    assert invoked == [1]
