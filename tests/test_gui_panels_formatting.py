from __future__ import annotations

from cleanroomx.gui_panels import _diagnostic_detail_lines


def test_diagnostic_detail_lines_prioritize_engineering_context_without_raw_json():
    issue = {
        "severity": "warning",
        "rule": "CRX-AIR-017",
        "category": "airflow",
        "message": "Insufficient ACH",
        "suggested_action": "Recalculate airflow after correcting the room inputs.",
        "element": {"type": "room", "id": "CR-104", "name": "CR-104"},
        "details": {
            "required_ach": 20,
            "calculated_ach": 17.6,
            "provenance": {"source": "solver"},
            "related_checks": ["ach", "air-balance"],
        },
    }

    rendered = "\n".join(_diagnostic_detail_lines(issue))

    assert "WARNING  |  CRX-AIR-017" in rendered
    assert "Engineering domain: Airflow" in rendered
    assert "Affected object: CR-104" in rendered
    assert "Insufficient ACH" in rendered
    assert "RECOMMENDED RECOVERY" in rendered
    assert "• Required Ach: 20" in rendered
    assert "• Calculated Ach: 17.6" in rendered
    assert "• Provenance / Source: solver" in rendered
    assert "• Related Checks: ach, air-balance" in rendered
    assert "{\"" not in rendered
