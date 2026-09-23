import math

import pytest

from cleanroomx.branch_network import analyze_branch_flow_network
from cleanroomx.duct import DuctSection, analyze_duct_section
from cleanroomx.fan_duct_network import analyze_fan_duct_network
from cleanroomx.fan_duct_network_io import fan_duct_network_study_from_dict
from cleanroomx.friction import colebrook_darcy_friction_factor
from cleanroomx.hvac_io import (
    branch_flow_network_from_dict,
    duct_network_from_dict,
)


def test_colebrook_solver_matches_equation_residual() -> None:
    reynolds = 44444.44444444444
    relative_roughness = 0.00027
    friction_factor = colebrook_darcy_friction_factor(
        reynolds, relative_roughness
    )

    assert friction_factor == pytest.approx(0.0223309783, rel=1e-8)
    residual = (
        1.0 / math.sqrt(friction_factor)
        + 2.0
        * math.log10(
            relative_roughness / 3.7
            + 2.51 / (reynolds * math.sqrt(friction_factor))
        )
    )
    assert residual == pytest.approx(0.0, abs=1e-10)


def test_duct_section_auto_friction_uses_colebrook() -> None:
    result = analyze_duct_section(
        DuctSection(
            name="Auto rectangular",
            length_m=10.0,
            airflow_m3_h=900.0,
            friction_factor=None,
            air_density_kg_m3=1.2,
            local_loss_coefficient=2.0,
            width_m=0.5,
            height_m=0.25,
            absolute_roughness_m=0.00009,
            kinematic_viscosity_m2_s=1.5e-5,
        )
    )

    assert result["friction_factor_method"] == "colebrook"
    assert result["reynolds_number"] == pytest.approx(44444.444, abs=0.001)
    assert result["friction_factor"] == pytest.approx(0.022331, abs=1e-6)
    assert result["friction_pressure_drop_pa"] == pytest.approx(1.6078, abs=1e-4)
    assert result["total_pressure_drop_pa"] == pytest.approx(6.4078, abs=1e-4)


def test_circular_laminar_auto_friction_uses_64_over_re() -> None:
    result = analyze_duct_section(
        DuctSection(
            name="Laminar circular",
            length_m=5.0,
            airflow_m3_h=10.0,
            friction_factor=None,
            air_density_kg_m3=1.2,
            diameter_m=0.2,
            absolute_roughness_m=0.0,
            kinematic_viscosity_m2_s=1.5e-5,
        )
    )

    assert result["friction_factor_method"] == "laminar_64_over_re"
    assert result["reynolds_number"] < 2300
    assert result["friction_factor"] == pytest.approx(
        64.0 / result["reynolds_number"], rel=2e-5
    )


def test_rectangular_laminar_auto_friction_requires_explicit_factor() -> None:
    section = DuctSection(
        name="Laminar rectangular",
        length_m=5.0,
        airflow_m3_h=10.0,
        friction_factor=None,
        air_density_kg_m3=1.2,
        width_m=0.5,
        height_m=0.25,
        absolute_roughness_m=0.00009,
        kinematic_viscosity_m2_s=1.5e-5,
    )

    with pytest.raises(ValueError, match="only for circular ducts"):
        analyze_duct_section(section)


def test_manual_and_auto_friction_inputs_are_mutually_exclusive() -> None:
    with pytest.raises(ValueError, match="either friction_factor"):
        DuctSection(
            name="Ambiguous",
            length_m=5.0,
            airflow_m3_h=900.0,
            friction_factor=0.02,
            air_density_kg_m3=1.2,
            width_m=0.5,
            height_m=0.25,
            absolute_roughness_m=0.00009,
            kinematic_viscosity_m2_s=1.5e-5,
        )


def test_json_duct_loader_allows_omitted_friction_factor_in_auto_mode() -> None:
    network = duct_network_from_dict(
        {
            "paths": [
                {
                    "name": "Auto path",
                    "sections": [
                        {
                            "name": "S1",
                            "length_m": 10.0,
                            "airflow_m3_h": 900.0,
                            "air_density_kg_m3": 1.2,
                            "local_loss_coefficient": 2.0,
                            "width_m": 0.5,
                            "height_m": 0.25,
                            "absolute_roughness_m": 0.00009,
                            "kinematic_viscosity_m2_s": 1.5e-5,
                        }
                    ],
                }
            ]
        }
    )

    assert network.paths[0].sections[0].friction_factor is None
    assert (
        analyze_duct_section(network.paths[0].sections[0])[
            "friction_factor_method"
        ]
        == "colebrook"
    )


def test_branch_tree_resolves_friction_at_solved_branch_flow() -> None:
    network = branch_flow_network_from_dict(
        {
            "source_node": "AHU",
            "branches": [
                {
                    "name": "Main",
                    "upstream_node": "AHU",
                    "downstream_node": "Room",
                    "length_m": 10.0,
                    "air_density_kg_m3": 1.2,
                    "local_loss_coefficient": 1.0,
                    "width_m": 0.5,
                    "height_m": 0.25,
                    "absolute_roughness_m": 0.00009,
                    "kinematic_viscosity_m2_s": 1.5e-5,
                }
            ],
            "terminal_demands": [
                {"node": "Room", "airflow_m3_h": 900.0}
            ],
        }
    )

    result = analyze_branch_flow_network(network)
    branch = result["branches"][0]
    assert branch["airflow_m3_h"] == 900.0
    assert branch["friction_factor_method"] == "colebrook"
    assert branch["reynolds_number"] == pytest.approx(44444.444, abs=0.001)


def test_reference_flow_fan_duct_study_uses_auto_friction() -> None:
    study = fan_duct_network_study_from_dict(
        {
            "name": "Auto-friction fan duct",
            "reference_system_airflow_m3_h": 900.0,
            "fixed_pressure_pa": 80.0,
            "fan_curve": {
                "name": "Fan",
                "points": [
                    {"airflow_m3_h": 0.0, "pressure_pa": 600.0},
                    {"airflow_m3_h": 6000.0, "pressure_pa": 300.0},
                ],
            },
            "duct_network": {
                "paths": [
                    {
                        "name": "Path",
                        "sections": [
                            {
                                "name": "S1",
                                "length_m": 10.0,
                                "airflow_m3_h": 900.0,
                                "air_density_kg_m3": 1.2,
                                "local_loss_coefficient": 2.0,
                                "width_m": 0.5,
                                "height_m": 0.25,
                                "absolute_roughness_m": 0.00009,
                                "kinematic_viscosity_m2_s": 1.5e-5,
                            }
                        ],
                    }
                ]
            },
        }
    )

    result = analyze_fan_duct_network(study)
    assert result["status"] == "solved"
    section = result["paths"][0]["sections"][0]
    assert section["friction_factor_method"] == "colebrook"
    assert section["friction_factor"] == pytest.approx(0.022331, abs=1e-6)


def test_transition_reynolds_range_requires_explicit_factor() -> None:
    section = DuctSection(
        name="Transition circular",
        length_m=5.0,
        airflow_m3_h=52.0,
        friction_factor=None,
        air_density_kg_m3=1.2,
        diameter_m=0.2,
        absolute_roughness_m=0.00009,
        kinematic_viscosity_m2_s=1.5e-5,
    )

    with pytest.raises(ValueError, match="transition"):
        analyze_duct_section(section)
