from __future__ import annotations

from cleanroomx.gui_components import diagnostic_issue_rows, verification_rows


def test_diagnostic_issue_rows_project_canonical_report_fields():
    report = {
        "summary": {
            "issue_count": 1,
            "error_count": 1,
            "warning_count": 0,
            "info_count": 0,
        },
        "issues": [
            {
                "sequence": 7,
                "rule": "spatial.room_overlap",
                "category": "spatial",
                "severity": "error",
                "element": {
                    "type": "spatial_element",
                    "id": "room-a",
                    "name": "Process Room",
                },
                "message": "Rooms overlap.",
                "suggested_action": "Move one room.",
                "details": {"floor_name": "Level 00"},
            }
        ],
    }

    rows = diagnostic_issue_rows(report)

    assert rows == [
        {
            "sequence": 7,
            "severity": "error",
            "code": "spatial.room_overlap",
            "description": "Rooms overlap.",
            "object": "Process Room",
            "level": "Level 00",
            "source": "spatial",
            "issue": report["issues"][0],
        }
    ]


def test_diagnostic_issue_rows_ignores_invalid_or_missing_issue_collection():
    assert diagnostic_issue_rows(None) == []
    assert diagnostic_issue_rows({}) == []
    assert diagnostic_issue_rows({"issues": "not-a-list"}) == []


def test_verification_rows_projects_canonical_currency_without_new_verdict_logic():
    record = {
        "analysis_id": "analysis-1",
        "analysis_name": "Room Verification",
        "state": "stale",
        "current": False,
        "complete": True,
        "mismatch_reasons": ["input_sha256", "external_dependency"],
        "latest_record": {
            "sequence": 12,
            "status": "FAIL",
        },
    }
    report = {
        "verification_currency": {
            "summary": {
                "current_count": 0,
                "stale_count": 1,
                "not_verified_count": 0,
            },
            "analyses": [record],
        }
    }

    rows = verification_rows(report)

    assert rows == [
        {
            "analysis_id": "analysis-1",
            "analysis_name": "Room Verification",
            "state": "stale",
            "current": False,
            "complete": True,
            "latest_sequence": 12,
            "latest_status": "FAIL",
            "mismatch_reasons": ("input_sha256", "external_dependency"),
            "record": record,
        }
    ]
