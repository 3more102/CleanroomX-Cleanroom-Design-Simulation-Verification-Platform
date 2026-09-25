from __future__ import annotations

from cleanroomx.air_system_design import air_system_design_from_dict
from cleanroomx.design_consistency import analyze_design_air_system_consistency
from cleanroomx.design_requirements import design_requirements_from_dict


def _requirements():
    return design_requirements_from_dict(
        {
            "name": "Requirements",
            "reference_profiles": [
                {
                    "id": "urs",
                    "title": "Project URS",
                    "source": "URS-001 Rev A",
                    "values": {
                        "min_ach": 30,
                        "temperature_c": {"min": 20, "max": 22},
                    },
                }
            ],
            "rooms": [
                {
                    "name": "Process",
                    "profile_id": "urs",
                    "dimensions_m": {"length": 6, "width": 4, "height": 3},
                    "occupancy": 4,
                    "occupant_sensible_w_per_person": 75,
                    "equipment_sensible_load_w": 8000,
                    "process_sensible_load_w": 500,
                }
            ],
        }
    )


def _air_system():
    return air_system_design_from_dict(
        {
            "name": "Air system",
            "rooms": [
                {
                    "name": "Process",
                    "dimensions_m": {"length": 6, "width": 4, "height": 3},
                    "strategy": "ffu_ceiling",
                    "min_ach": 30,
                    "sensible_load_w": 8800,
                    "room_air_temp_c": 22,
                    "supply_air_temp_c": 16,
                }
            ],
        }
    )


def test_design_air_system_consistency_matches_explicit_requirements():
    result = analyze_design_air_system_consistency(_requirements(), _air_system())

    assert result["status"] == "pass"
    assert result["shared_room_count"] == 1
    assert result["geometry_mismatch_count"] == 0
    assert result["ach_mismatch_count"] == 0
    assert result["temperature_mismatch_count"] == 0
    assert result["sensible_load_mismatch_count"] == 0
    room = result["room_checks"][0]
    assert all(item["status"] == "match" for item in room["geometry"])
    assert room["minimum_ach"]["status"] == "match"
    assert room["minimum_ach"]["provenance"]["reference"] == "URS-001 Rev A"
    assert room["room_temperature"]["status"] == "match"
    assert room["sensible_load"]["status"] == "match"


def test_design_air_system_consistency_exposes_requirement_drift():
    requirements = _requirements()
    air = air_system_design_from_dict(
        {
            "name": "Air system",
            "rooms": [
                {
                    "name": "Process",
                    "dimensions_m": {"length": 6.5, "width": 4, "height": 3},
                    "strategy": "ffu_ceiling",
                    "min_ach": 25,
                    "sensible_load_w": 8500,
                    "room_air_temp_c": 23,
                    "supply_air_temp_c": 16,
                }
            ],
        }
    )

    result = analyze_design_air_system_consistency(requirements, air)
    room = result["room_checks"][0]

    assert result["status"] == "fail"
    assert result["geometry_mismatch_count"] == 1
    assert result["ach_mismatch_count"] == 1
    assert result["temperature_mismatch_count"] == 1
    assert result["sensible_load_mismatch_count"] == 1
    assert next(item for item in room["geometry"] if item["field"] == "length_m")[
        "status"
    ] == "mismatch"
    assert room["minimum_ach"]["status"] == "mismatch"
    assert room["room_temperature"]["status"] == "mismatch"
    assert room["sensible_load"]["status"] == "mismatch"


def test_design_air_system_consistency_preserves_room_scope_differences():
    requirements = design_requirements_from_dict(
        {
            "name": "Requirements",
            "rooms": [
                {
                    "name": "Requirement only",
                    "dimensions_m": {"length": 4, "width": 3, "height": 3},
                    "min_ach": 20,
                }
            ],
        }
    )
    air = air_system_design_from_dict(
        {
            "name": "Air system",
            "rooms": [
                {
                    "name": "Design only",
                    "dimensions_m": {"length": 4, "width": 3, "height": 3},
                    "strategy": "ceiling_supply_low_return",
                    "min_ach": 20,
                }
            ],
        }
    )

    result = analyze_design_air_system_consistency(requirements, air)

    assert result["status"] == "review"
    assert result["shared_room_count"] == 0
    assert result["requirements_only_rooms"] == ["Requirement only"]
    assert result["air_system_only_rooms"] == ["Design only"]


def test_design_air_system_consistency_uses_only_floating_point_noise_tolerance():
    requirements = design_requirements_from_dict(
        {
            "name": "Requirements",
            "rooms": [
                {
                    "name": "Process",
                    "dimensions_m": {"length": 4, "width": 3, "height": 3},
                    "min_ach": 20,
                    "occupancy": 3,
                    "occupant_sensible_w_per_person": 0.1,
                }
            ],
        }
    )
    air = air_system_design_from_dict(
        {
            "name": "Air system",
            "rooms": [
                {
                    "name": "Process",
                    "dimensions_m": {"length": 4, "width": 3, "height": 3},
                    "strategy": "ceiling_supply_low_return",
                    "min_ach": 20,
                    "sensible_load_w": 0.3,
                    "room_air_temp_c": 22,
                    "supply_air_temp_c": 16,
                }
            ],
        }
    )

    result = analyze_design_air_system_consistency(requirements, air)

    assert result["status"] == "pass"
    assert result["sensible_load_mismatch_count"] == 0
    assert result["room_checks"][0]["sensible_load"]["status"] == "match"
    assert "not an engineering acceptance tolerance" in result["numeric_comparison"]["purpose"]
