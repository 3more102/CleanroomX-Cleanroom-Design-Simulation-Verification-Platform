from __future__ import annotations

from cleanroomx.gui_panels import _diagnostic_detail_lines, _engineering_detail_pairs


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
    assert "Engineering domain: Airflow Balance" in text
    assert "RECOMMENDED RECOVERY" in text
    assert "Required Ach: 20" in text
    assert "Calculated Ach: 17.6" in text
    assert "{\"required_ach\"" not in text
