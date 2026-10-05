from __future__ import annotations

from types import SimpleNamespace

from cleanroomx.gui_dashboard import engineering_dashboard_snapshot


def test_dashboard_snapshot_reports_canonical_scope_and_diagnostics():
    project = SimpleNamespace(
        name="Fab A12",
        analyses=(
            SimpleNamespace(name="Room verification", kind="room_verification"),
            SimpleNamespace(name="Air balance", kind="air_balance"),
        ),
        metadata={
            "spatial_layout": {
                "rooms": [{"id": "CR-104"}, {"id": "CR-105"}],
                "devices": [{"id": "FFU-1"}],
            }
        },
    )
    diagnostics = {
        "summary": {"error_count": 1, "warning_count": 1, "info_count": 0},
        "issues": [
            {
                "sequence": 2,
                "severity": "warning",
                "rule": "analysis.input_warning",
                "category": "analysis",
                "message": "Analysis input needs review.",
                "element": {"id": "analysis-a", "name": "Air balance"},
            },
            {
                "sequence": 1,
                "severity": "error",
                "rule": "spatial.room_overlap",
                "category": "spatial",
                "message": "Rooms overlap.",
                "element": {"id": "CR-104", "name": "CR-104"},
            },
        ],
    }

    snapshot = engineering_dashboard_snapshot(
        project,
        diagnostics,
        proofgraph_count=3,
        verification_state="verified",
    )

    assert snapshot["project_name"] == "Fab A12"
    assert snapshot["health_label"] == "BLOCKED"
    assert snapshot["health_status"] == "fail"
    assert snapshot["room_count"] == 2
    assert snapshot["device_count"] == 1
    assert snapshot["analysis_count"] == 2
    assert snapshot["proofgraph_count"] == 3
    assert snapshot["verification_state"] == "verified"
    assert snapshot["critical_issues"][0]["code"] == "spatial.room_overlap"
    domains = {item["domain"]: item["issue_count"] for item in snapshot["domains"]}
    assert domains["Geometry"] == 1
    assert domains["Analysis"] == 1


def test_dashboard_snapshot_never_invents_readiness_when_not_evaluated():
    project = SimpleNamespace(name="Untitled", analyses=(), metadata={})

    snapshot = engineering_dashboard_snapshot(project, None)

    assert snapshot["health_label"] == "NOT EVALUATED"
    assert snapshot["health_status"] == "unknown"
    assert snapshot["issue_count"] == 0
    assert snapshot["room_count"] == 0
    assert snapshot["analysis_count"] == 0
