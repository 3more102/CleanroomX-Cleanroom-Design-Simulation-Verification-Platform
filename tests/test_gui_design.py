from __future__ import annotations

from cleanroomx.gui_design import design_summary, extract_design_rooms


def test_extract_design_rooms_uses_dimensional_rooms():
    payload = {
        "rooms": [
            {
                "name": "Process",
                "length_m": 6,
                "width_m": 5,
                "height_m": 3,
                "supply_airflow_m3_h": 2700,
            },
            {
                "name": "Ante",
                "length_m": 4,
                "width_m": 3,
                "height_m": 3,
                "supply_airflow_m3_h": 720,
            },
        ]
    }

    rooms = extract_design_rooms(payload)

    assert [room["name"] for room in rooms] == ["Process", "Ante"]
    assert rooms[0]["length_m"] == 6.0
    assert rooms[0]["width_m"] == 5.0


def test_extract_design_rooms_finds_nested_room_geometry():
    payload = {
        "facility": {
            "rooms": [
                {"name": "Nested", "length_m": 5, "width_m": 4, "height_m": 3}
            ]
        }
    }

    rooms = extract_design_rooms(payload)

    assert len(rooms) == 1
    assert rooms[0]["name"] == "Nested"


def test_extract_design_rooms_ignores_non_dimensional_rooms():
    payload = {
        "rooms": [
            {"name": "Thermal only", "cleanroom_airflow_m3_h": 1200},
            {"name": "Invalid", "length_m": -1, "width_m": 4},
        ]
    }

    assert extract_design_rooms(payload) == []


def test_design_summary_reports_area_volume_and_supply():
    payload = {
        "rooms": [
            {
                "name": "Process",
                "length_m": 6,
                "width_m": 5,
                "height_m": 3,
                "supply_airflow_m3_h": 2700,
            },
            {
                "name": "Ante",
                "length_m": 4,
                "width_m": 3,
                "height_m": 3,
                "supply_airflow_m3_h": 720,
            },
        ]
    }

    summary = design_summary(payload)

    assert "2 rooms" in summary
    assert "42.0 m²" in summary
    assert "126.0 m³" in summary
    assert "3,420 m³/h supply" in summary
