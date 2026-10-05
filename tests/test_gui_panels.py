from __future__ import annotations

from cleanroomx.gui_panels import (
    _diagnostic_detail_lines,
    _engineering_detail_pairs,
    diagnostic_issue_matches,
    filter_project_diagnostics_result,
)


def test_engineering_detail_pairs_flattens_structured_values_without_raw_dict_dump():
    pairs = _engineering_detail_pairs(
        {
            "required_ach": 20.0,
            "calculated_ach": 17.6,
            "margin_percent": -12.0,
            "context": {"room_class": "ISO 7"},
            "adjacent_rooms": ["CR-103", "CR-105"],
        }
    )

    assert ("Required Ach", "20") in pairs
    assert ("Calculated Ach", "17.6") in pairs
    assert ("Margin Percent", "-12") in pairs
    assert ("Context / Room Class", "ISO 7") in pairs
    assert ("Adjacent Rooms", "CR-103, CR-105") in pairs


def test_diagnostic_detail_lines_are_engineer_facing_and_actionable():
    lines = _diagnostic_detail_lines(
        {
            "severity": "warning",
            "rule": "CRX-AIR-017",
            "category": "airflow_balance",
            "message": "Insufficient ACH",
            "suggested_action": "Increase supply airflow and recalculate.",
            "element": {"type": "room", "id": "CR-104", "name": "CR-104"},
            "details": {
                "required_ach": 20.0,
                "calculated_ach": 17.6,
                "margin_percent": -12.0,
            },
        }
    )

    text = "\n".join(lines)
    assert "WARNING  |  CRX-AIR-017" in text
    assert "Affected object: CR-104" in text
    assert "Engineering domain: airflow balance" in text
    assert "RECOMMENDED RECOVERY" in text
    assert "Required Ach: 20" in text
    assert "Calculated Ach: 17.6" in text
    assert "{\"required_ach\"" not in text


def test_diagnostic_issue_filter_supports_exact_rule_object_and_search():
    issue = {
        "severity": "warning",
        "rule": "CRX-AIR-017",
        "category": "airflow_balance",
        "message": "Insufficient ACH in process room",
        "suggested_action": "Increase supply airflow.",
        "element": {"type": "room", "id": "CR-104", "name": "Process"},
        "details": {"level": "L02", "required_ach": 20.0},
    }

    assert diagnostic_issue_matches(
        issue,
        {
            "severity": "Warning",
            "category": "airflow_balance",
            "object_type": "Room",
            "rule": "CRX-AIR-017",
            "query": "L02",
        },
    )
    assert not diagnostic_issue_matches(issue, {"rule": "CRX-AIR-018"})
    assert not diagnostic_issue_matches(issue, {"object_type": "device"})


def test_filtered_diagnostics_export_recomputes_visible_counts_and_marks_scope():
    result = {
        "schema": "cleanroomx.project_diagnostics",
        "summary": {
            "status": "error",
            "complete": True,
            "issue_count": 3,
            "error_count": 1,
            "warning_count": 1,
            "info_count": 1,
        },
        "issues": [
            {
                "sequence": 1,
                "severity": "error",
                "rule": "CRX-MODEL-001",
                "category": "model",
                "message": "Broken reference",
                "element": {"type": "analysis", "id": "a"},
            },
            {
                "sequence": 2,
                "severity": "warning",
                "rule": "CRX-AIR-017",
                "category": "airflow_balance",
                "message": "Insufficient ACH",
                "element": {"type": "room", "id": "CR-104"},
            },
            {
                "sequence": 3,
                "severity": "info",
                "rule": "CRX-AUDIT-004",
                "category": "audit",
                "message": "Historical record",
                "element": {"type": "project"},
            },
        ],
        "limitations": ["Canonical limitation."],
    }

    filtered = filter_project_diagnostics_result(
        result,
        {"severity": "Warning", "rule": "CRX-AIR-017"},
    )

    assert [item["sequence"] for item in filtered["issues"]] == [2]
    assert filtered["summary"] == {
        "status": "warning",
        "complete": True,
        "issue_count": 1,
        "error_count": 0,
        "warning_count": 1,
        "info_count": 0,
    }
    assert filtered["view_scope"]["source_issue_count"] == 3
    assert filtered["view_scope"]["exported_issue_count"] == 1
    assert filtered["view_scope"]["filters"] == {
        "severity": "Warning",
        "rule": "CRX-AIR-017",
    }
    assert result["summary"]["issue_count"] == 3
    assert "GUI-filtered diagnostics view" in filtered["limitations"][-1]
