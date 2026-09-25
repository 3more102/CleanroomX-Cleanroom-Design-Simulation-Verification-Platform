import math
import pytest

from cleanroomx.air_system_design import (
    air_system_design_from_dict,
    analyze_air_system_design,
)


def _payload():
    return {
        "name": "Air design",
        "air_properties": {
            "density_kg_m3": 1.2,
            "specific_heat_j_kg_k": 1006,
            "source": "project assumption",
        },
        "rooms": [
            {
                "name": "Process",
                "dimensions_m": {"length": 6, "width": 4, "height": 3},
                "strategy": "ffu_ceiling",
                "min_ach": 30,
                "sensible_load_w": 8500,
                "room_air_temp_c": 22,
                "supply_air_temp_c": 16,
                "minimum_outdoor_air_m3_h": 300,
                "exhaust_airflow_m3_h": 200,
                "minimum_surplus_m3_h": 100,
                "filter_unit": {"name": "FFU", "rated_airflow_m3_h": 1200, "design_utilization": 0.9},
                "supply_terminal": {"name": "Supply", "rated_airflow_m3_h": 700, "design_utilization": 0.85},
                "return_terminal": {"name": "Return", "rated_airflow_m3_h": 900, "design_utilization": 0.85},
                "exhaust_terminal": {"name": "Exhaust", "rated_airflow_m3_h": 500, "design_utilization": 0.8},
            }
        ],
    }


def test_air_system_uses_strongest_explicit_airflow_driver():
    result = analyze_air_system_design(air_system_design_from_dict(_payload()))
    room = result["rooms"][0]
    expected_sensible = 8500 / (1.2 * 1006 * 6) * 3600
    assert room["airflow_drivers"]["minimum_ach"]["airflow_m3_h"] == 2160.0
    assert room["airflow_drivers"]["sensible_load"]["airflow_m3_h"] == pytest.approx(expected_sensible)
    assert room["governing_basis"] == "sensible_load"
    assert room["governing_airflow_m3_h"] == pytest.approx(expected_sensible)
    assert room["achieved_surplus_m3_h"] == pytest.approx(100.0)
    assert room["equipment_counts"]["filter_units"] == math.ceil(expected_sensible / 1080.0)


def test_air_system_requires_an_explicit_airflow_driver():
    payload = _payload()
    room = payload["rooms"][0]
    room.pop("min_ach")
    room["sensible_load_w"] = 0
    room.pop("room_air_temp_c")
    room.pop("supply_air_temp_c")
    room["minimum_outdoor_air_m3_h"] = 0
    with pytest.raises(ValueError, match="no airflow driver"):
        analyze_air_system_design(air_system_design_from_dict(payload))


def test_air_system_rejects_non_cooling_supply_for_positive_sensible_load():
    payload = _payload()
    payload["rooms"][0]["supply_air_temp_c"] = 22
    with pytest.raises(ValueError, match="must be below"):
        air_system_design_from_dict(payload)
