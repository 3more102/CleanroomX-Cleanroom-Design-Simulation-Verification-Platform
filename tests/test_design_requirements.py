import pytest

from cleanroomx.design_requirements import (
    analyze_design_requirements,
    design_requirements_from_dict,
)


def _payload():
    return {
        "name": "Requirements",
        "reference_profiles": [
            {
                "id": "p1",
                "title": "Project URS",
                "source": "URS-001",
                "values": {
                    "min_ach": 30,
                    "temperature_c": {"min": 20, "max": 22},
                    "relative_humidity_percent": {"min": 40, "max": 55},
                    "filtration_requirement": "HEPA per project requirement",
                    "supply_return_strategy": "ceiling supply / low return",
                },
            }
        ],
        "rooms": [
            {
                "name": "Process",
                "profile_id": "p1",
                "classification": "ISO 7 project designation",
                "dimensions_m": {"length": 6, "width": 4, "height": 3},
                "pressure_target_pa": 15,
                "occupancy": 4,
                "occupant_sensible_w_per_person": 75,
                "equipment_sensible_load_w": 8000,
                "process_sensible_load_w": 500,
                "operating_mode": "occupied",
            }
        ],
    }


def test_requirements_engine_derives_targets_with_provenance():
    result = analyze_design_requirements(design_requirements_from_dict(_payload()))
    assert result["status"] == "ready"
    room = result["rooms"][0]
    targets = {item["name"]: item for item in room["targets"]}
    assert targets["floor_area"]["value"] == 24.0
    assert targets["room_volume"]["value"] == 72.0
    assert targets["ach_based_supply_airflow"]["value"] == 2160.0
    assert targets["minimum_ach"]["provenance"]["reference"] == "URS-001"
    assert targets["provided_sensible_load"]["value"] == 8800.0


def test_room_input_overrides_reference_profile_explicitly():
    payload = _payload()
    payload["rooms"][0]["min_ach"] = 45
    result = analyze_design_requirements(design_requirements_from_dict(payload))
    target = {item["name"]: item for item in result["rooms"][0]["targets"]}["minimum_ach"]
    assert target["value"] == 45.0
    assert target["provenance"]["kind"] == "room_input"


def test_missing_ach_remains_unchecked_instead_of_invented():
    payload = _payload()
    payload["rooms"][0].pop("profile_id")
    result = analyze_design_requirements(design_requirements_from_dict(payload))
    target = {item["name"]: item for item in result["rooms"][0]["targets"]}["ach_based_supply_airflow"]
    assert result["status"] == "warning"
    assert target["value"] is None
    assert target["status"] == "unchecked"


def test_unknown_reference_profile_fails_closed():
    payload = _payload()
    payload["rooms"][0]["profile_id"] = "missing"
    with pytest.raises(ValueError, match="unknown reference profile"):
        design_requirements_from_dict(payload)
