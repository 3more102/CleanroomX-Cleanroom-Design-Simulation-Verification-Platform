from __future__ import annotations

import copy

from cleanroomx.spatial import engineering_overlay_state, normalize_layout


def _layout() -> dict:
    return normalize_layout(
        {
            "rooms": [
                {
                    "id": "room-a",
                    "name": "Room A",
                    "analysis_room_name": "Room A",
                    "x_m": 0.0,
                    "y_m": 0.0,
                    "length_m": 5.0,
                    "width_m": 4.0,
                    "height_m": 3.0,
                    "pressure_pa": 15.0,
                },
                {
                    "id": "room-b",
                    "name": "Room B",
                    "analysis_room_name": "Room B",
                    "x_m": 5.0,
                    "y_m": 0.0,
                    "length_m": 4.0,
                    "width_m": 4.0,
                    "height_m": 3.0,
                    "pressure_pa": 5.0,
                },
            ]
        }
    )


def test_ach_overlay_projects_canonical_verification_results_without_mutation():
    layout = _layout()
    result = {
        "rooms": [
            {
                "room": "Room A",
                "ach": 34.2,
                "status": "pass",
                "findings": [
                    {"code": "ACH", "status": "pass", "actual": 34.2, "unit": "1/h"}
                ],
            },
            {
                "room": "Room B",
                "ach": 18.5,
                "status": "fail",
                "findings": [
                    {"code": "ACH", "status": "fail", "actual": 18.5, "unit": "1/h"}
                ],
            },
        ]
    }
    before_layout = copy.deepcopy(layout)
    before_result = copy.deepcopy(result)

    overlay = engineering_overlay_state(layout, result=result, mode="ach")

    assert layout == before_layout
    assert result == before_result
    assert overlay["minimum"] == 18.5
    assert overlay["maximum"] == 34.2
    by_room = {item["room_id"]: item for item in overlay["rooms"]}
    assert by_room["room-a"]["value"] == 34.2
    assert by_room["room-a"]["status"] == "pass"
    assert "ACH: 34.20" in by_room["room-a"]["label"]
    assert by_room["room-b"]["status"] == "fail"


def test_airflow_overlay_uses_existing_hvac_air_balance_values_and_status():
    layout = _layout()
    result = {
        "rooms": [
            {
                "name": "Room A",
                "governing_airflow_m3_h": 1500.0,
                "air_balance": {
                    "supply_airflow_m3_h": 1500.0,
                    "return_airflow_m3_h": 1200.0,
                    "exhaust_airflow_m3_h": 100.0,
                    "passes_minimum_surplus": True,
                },
            },
            {
                "name": "Room B",
                "governing_airflow_m3_h": 900.0,
                "air_balance": {
                    "supply_airflow_m3_h": 900.0,
                    "return_airflow_m3_h": 950.0,
                    "exhaust_airflow_m3_h": 50.0,
                    "passes_minimum_surplus": False,
                },
            },
        ]
    }

    overlay = engineering_overlay_state(layout, result=result, mode="airflow")
    by_room = {item["room_id"]: item for item in overlay["rooms"]}

    assert by_room["room-a"]["details"] == {
        "supply_m3_h": 1500.0,
        "return_m3_h": 1200.0,
        "exhaust_m3_h": 100.0,
    }
    assert by_room["room-a"]["status"] == "pass"
    assert by_room["room-b"]["status"] == "fail"
    assert overlay["minimum"] == 900.0
    assert overlay["maximum"] == 1500.0


def test_status_overlay_uses_result_status_and_never_derives_new_verdicts():
    layout = _layout()
    result = {
        "rooms": [
            {"room": "Room A", "status": "pass", "findings": []},
            {"room": "Room B", "status": "fail", "findings": []},
        ]
    }

    overlay = engineering_overlay_state(layout, result=result, mode="status")
    by_room = {item["room_id"]: item for item in overlay["rooms"]}

    assert by_room["room-a"]["status"] == "pass"
    assert by_room["room-a"]["fill"] == "#dcfce7"
    assert by_room["room-b"]["status"] == "fail"
    assert by_room["room-b"]["fill"] == "#fee2e2"


def test_none_overlay_has_neutral_fill_and_pressure_overlay_preserves_spatial_evidence():
    layout = _layout()

    none_overlay = engineering_overlay_state(layout, result={}, mode="none")
    assert all(item["fill"] == "#dfe7ef" for item in none_overlay["rooms"])

    pressure = engineering_overlay_state(layout, result={}, mode="pressure")
    by_room = {item["room_id"]: item for item in pressure["rooms"]}
    assert by_room["room-a"]["pressure_pa"] == 15.0
    assert by_room["room-b"]["pressure_pa"] == 5.0
    assert pressure["minimum"] == 5.0
    assert pressure["maximum"] == 15.0
