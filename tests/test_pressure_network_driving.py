from __future__ import annotations

import pytest

from cleanroomx.pressure_driving import (
    StackPressureInput,
    WindPressureInput,
    dry_air_density_kg_m3,
)
from cleanroomx.pressure_network import solve_room_pressure_network
from cleanroomx.pressure_network_io import pressure_network_from_dict


def test_dry_air_density_uses_ideal_gas_relation() -> None:
    density = dry_air_density_kg_m3(101325.0, 293.15)
    assert density == pytest.approx(1.204118316)


def test_wind_pressure_matches_dynamic_pressure_coefficient_form() -> None:
    wind = WindPressureInput(
        air_density_kg_m3=1.2,
        reference_wind_speed_m_s=10.0,
        pressure_coefficient=0.5,
        wind_speed_modifier_coefficient=0.8,
    )
    assert wind.pressure_pa == pytest.approx(24.0)

    suction = WindPressureInput(
        air_density_kg_m3=1.2,
        reference_wind_speed_m_s=10.0,
        pressure_coefficient=-0.5,
        wind_speed_modifier_coefficient=0.8,
    )
    assert suction.pressure_pa == pytest.approx(-24.0)


def test_stack_pressure_uses_incompressible_hydrostatic_terms() -> None:
    stack = StackPressureInput(
        start_air_density_kg_m3=1.2,
        end_air_density_kg_m3=1.0,
        start_height_above_node_reference_m=2.0,
        end_height_above_node_reference_m=2.0,
    )
    assert stack.pressure_difference_pa == pytest.approx(-3.92266)


def test_pressure_network_combines_explicit_wind_and_stack_offsets() -> None:
    network = pressure_network_from_dict(
        {
            "name": "Environmental driving pressure",
            "nodes": [
                {"name": "room"},
                {"name": "outside", "fixed_pressure_pa": 0.0},
            ],
            "paths": [
                {
                    "name": "envelope",
                    "start_node": "room",
                    "end_node": "outside",
                    "kind": "crack",
                    "model": "power_law",
                    "coefficient_m3_s_pa_n": 0.01,
                    "exponent": 1.0,
                    "pressure_offset_pa": 1.0,
                    "wind_pressure": {
                        "air_density_kg_m3": 1.0,
                        "reference_wind_speed_m_s": 2.0,
                        "pressure_coefficient": 1.0,
                    },
                    "stack_pressure": {
                        "start_air_density_kg_m3": 1.0,
                        "end_air_density_kg_m3": 1.0,
                        "start_height_above_node_reference_m": 0.0,
                        "end_height_above_node_reference_m": 0.0,
                    },
                }
            ],
        }
    )

    result = solve_room_pressure_network(network)

    assert result["nodes"][0]["pressure_pa"] == pytest.approx(-3.0)
    path = result["paths"][0]
    assert path["pressure_offset_pa"] == pytest.approx(1.0)
    assert path["driving_pressure_components_pa"] == {
        "explicit": pytest.approx(1.0),
        "wind": pytest.approx(2.0),
        "stack": pytest.approx(0.0),
        "total": pytest.approx(3.0),
    }
    assert path["effective_pressure_difference_pa"] == pytest.approx(0.0)


def test_legacy_network_result_shape_has_no_environmental_component_field() -> None:
    network = pressure_network_from_dict(
        {
            "name": "Legacy",
            "nodes": [
                {"name": "room"},
                {"name": "reference", "fixed_pressure_pa": 0.0},
            ],
            "paths": [
                {
                    "name": "leak",
                    "start_node": "room",
                    "end_node": "reference",
                    "kind": "crack",
                    "model": "power_law",
                    "coefficient_m3_s_pa_n": 0.01,
                    "exponent": 1.0,
                }
            ],
        }
    )

    result = solve_room_pressure_network(network)

    assert "driving_pressure_components_pa" not in result["paths"][0]
    assert "does not infer leakage coefficients" in result["scope_note"]
    assert "wind, stack effect" in result["scope_note"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("air_density_kg_m3", True),
        ("reference_wind_speed_m_s", -1.0),
        ("pressure_coefficient", 1.01),
    ],
)
def test_wind_pressure_rejects_invalid_inputs(field: str, value: object) -> None:
    payload = {
        "air_density_kg_m3": 1.2,
        "reference_wind_speed_m_s": 5.0,
        "pressure_coefficient": 0.5,
    }
    payload[field] = value
    with pytest.raises(ValueError):
        WindPressureInput(**payload)


def test_nested_pressure_driving_json_rejects_unknown_fields() -> None:
    payload = {
        "name": "Bad environmental field",
        "nodes": [
            {"name": "room"},
            {"name": "outside", "fixed_pressure_pa": 0.0},
        ],
        "paths": [
            {
                "name": "envelope",
                "start_node": "room",
                "end_node": "outside",
                "kind": "crack",
                "model": "power_law",
                "coefficient_m3_s_pa_n": 0.01,
                "exponent": 1.0,
                "wind_pressure": {
                    "air_density_kg_m3": 1.2,
                    "reference_wind_speed_m_s": 5.0,
                    "pressure_coefficient": 0.5,
                    "unsupported": 1.0,
                },
            }
        ],
    }
    with pytest.raises(ValueError, match="unsupported wind-pressure field"):
        pressure_network_from_dict(payload)
