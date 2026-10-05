from __future__ import annotations

from cleanroomx.gui_panels import (
    _diagnostic_detail_lines,
    _engineering_detail_pairs,
    verification_evidence_projection,
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

def test_verification_evidence_projection_surfaces_provenance_without_raw_payloads():
    rows = verification_evidence_projection(
        [
            {
                "sequence": 4,
                "analysis_id": "room-a",
                "analysis_name": "Room A verification",
                "analysis_kind": "room_verification",
                "completed_at_utc": "2026-10-05T06:00:00Z",
                "cleanroomx_version": "0.102.1",
                "verification": {"status": "pass", "verified": True},
                "evidence": [
                    {
                        "id": "MAP-ACH",
                        "requirement_id": "REQ-ACH",
                        "subject_ref": "ROOM-A",
                        "property_name": "air_change_rate",
                        "value": 21.3,
                        "unit": "1/h",
                        "source": "room_verification",
                        "source_revision": "Rev C",
                        "calculation_source": "solver",
                        "evidence_locator": "/result/ach",
                        "freshness": "fresh",
                    },
                    {
                        "id": "STRUCTURED",
                        "requirement_id": "REQ-X",
                        "subject_ref": "ROOM-A",
                        "property_name": "structured",
                        "value": {"a": 1, "b": 2},
                        "unit": "",
                        "source": "model",
                        "source_revision": "",
                        "calculation_source": "",
                        "evidence_locator": "/result/structured",
                        "freshness": "fresh",
                    },
                ],
            }
        ]
    )

    assert len(rows) == 1
    record = rows[0]
    assert record["sequence"] == 4
    assert record["analysis"] == "Room A verification"
    assert record["status"] == "pass"
    assert record["version"] == "0.102.1"
    assert record["evidence"][0]["value"] == "21.3"
    assert record["evidence"][0]["source"] == "room_verification · Rev C · solver"
    assert record["evidence"][0]["locator"] == "/result/ach"
    assert record["evidence"][1]["value"] == "2 field(s)"

