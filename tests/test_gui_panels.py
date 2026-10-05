from __future__ import annotations

from cleanroomx.gui_panels import (
    _diagnostic_detail_lines,
    _engineering_detail_pairs,
    diagnostic_filter_options,
    diagnostic_matches_filters,
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


def test_diagnostic_filter_options_are_deterministic_and_use_target_type():
    issues = [
        {
            "severity": "warning",
            "category": "traceability",
            "element": {"type": "analysis", "id": "a1"},
        },
        {
            "severity": "error",
            "category": "spatial",
            "element": {"type": "spatial_element", "id": "r1"},
        },
        {
            "severity": "info",
            "category": "traceability",
            "element": {},
        },
    ]

    assert diagnostic_filter_options(issues, "category") == (
        "All",
        "spatial",
        "traceability",
    )
    assert diagnostic_filter_options(issues, "target_type") == (
        "All",
        "analysis",
        "project",
        "spatial_element",
    )


def test_diagnostic_matches_filters_combines_domain_target_severity_and_search_tokens():
    issue = {
        "severity": "warning",
        "rule": "verification_currency.stale",
        "category": "traceability",
        "message": "Persisted verification no longer matches current configuration.",
        "suggested_action": "Run verification again.",
        "element": {"type": "analysis", "id": "ach-1", "name": "Room ACH"},
        "details": {"analysis_kind": "ach", "level": "L2"},
    }

    assert diagnostic_matches_filters(
        issue,
        severity="Warning",
        category="traceability",
        target_type="analysis",
        query="room ach l2",
    )
    assert not diagnostic_matches_filters(issue, severity="Error")
    assert not diagnostic_matches_filters(issue, category="spatial")
    assert not diagnostic_matches_filters(issue, target_type="spatial_element")
    assert not diagnostic_matches_filters(issue, query="pressure cascade")


def test_diagnostic_matches_filters_does_not_require_missing_optional_fields():
    issue = {
        "severity": "info",
        "rule": "engineering_sync.not_configured",
        "category": "engineering_sync",
        "message": "Synchronization authority is not configured.",
    }

    assert diagnostic_matches_filters(issue, target_type="project")
    assert diagnostic_matches_filters(issue, query="sync configured")
