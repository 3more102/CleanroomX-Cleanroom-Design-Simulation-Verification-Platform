import math

import pytest

from cleanroomx.duct import DuctSection
from cleanroomx.loop_duct_network import (
    GeometryDerivedLoopEdge,
    GeometryDerivedLoopNetwork,
    analyze_geometry_derived_loop_network,
    derive_edge_resistance,
)
from cleanroomx.loop_duct_network_io import geometry_derived_loop_network_from_dict
from cleanroomx.loop_duct_network_report import markdown_geometry_derived_loop_report


def _loss_only_section(
    name: str,
    airflow_m3_h: float,
    loss_coefficient: float,
) -> DuctSection:
    return DuctSection(
        name=name,
        length_m=0.0,
        airflow_m3_h=airflow_m3_h,
        friction_factor=0.0,
        air_density_kg_m3=2.0,
        local_loss_coefficient=loss_coefficient,
        width_m=1.0,
        height_m=1.0,
    )


def test_manual_geometry_resistance_matches_analytical_equation() -> None:
    section = DuctSection(
        name="Round branch",
        length_m=10.0,
        airflow_m3_h=3600.0,
        friction_factor=0.02,
        air_density_kg_m3=1.2,
        local_loss_coefficient=1.0,
        diameter_m=1.0,
    )
    edge = GeometryDerivedLoopEdge(
        name="AB",
        start_node="A",
        end_node="B",
        reference_airflow_m3_h=3600.0,
        sections=(section,),
    )

    fixed, evidence = derive_edge_resistance(edge)

    area = math.pi / 4.0
    expected = 0.5 * 1.2 * (0.02 * 10.0 / 1.0 + 1.0) / area**2
    assert fixed.resistance_pa_per_m3_s_squared == pytest.approx(expected)
    assert evidence["reference_pressure_drop_pa"] == pytest.approx(expected)
    assert evidence["sections"][0]["friction_factor_method"] == "user_input"


def test_series_section_resistances_add() -> None:
    edge = GeometryDerivedLoopEdge(
        name="Series edge",
        start_node="A",
        end_node="B",
        reference_airflow_m3_h=1800.0,
        sections=(
            _loss_only_section("S1", 1800.0, 1.25),
            _loss_only_section("S2", 1800.0, 2.75),
        ),
    )

    fixed, evidence = derive_edge_resistance(edge)

    assert fixed.resistance_pa_per_m3_s_squared == pytest.approx(4.0)
    assert sum(
        section["quadratic_resistance_pa_per_m3_s_squared"]
        for section in evidence["sections"]
    ) == pytest.approx(4.0)


def test_geometry_derived_loop_matches_equal_parallel_path_solution() -> None:
    network = GeometryDerivedLoopNetwork(
        name="Geometry symmetric loop",
        node_injections_m3_h={
            "Source": 3600.0,
            "Mid": 0.0,
            "Sink": -3600.0,
        },
        edges=(
            GeometryDerivedLoopEdge(
                name="Direct",
                start_node="Source",
                end_node="Sink",
                reference_airflow_m3_h=1800.0,
                sections=(_loss_only_section("Direct section", 1800.0, 2.0),),
            ),
            GeometryDerivedLoopEdge(
                name="Upper 1",
                start_node="Source",
                end_node="Mid",
                reference_airflow_m3_h=1800.0,
                sections=(_loss_only_section("Upper section 1", 1800.0, 1.0),),
            ),
            GeometryDerivedLoopEdge(
                name="Upper 2",
                start_node="Mid",
                end_node="Sink",
                reference_airflow_m3_h=1800.0,
                sections=(_loss_only_section("Upper section 2", 1800.0, 1.0),),
            ),
        ),
        reference_node="Source",
    )

    result = analyze_geometry_derived_loop_network(network)
    flows = {edge["name"]: edge for edge in result["edges"]}

    assert flows["Direct"]["airflow_m3_h"] == pytest.approx(1800.0, abs=1e-6)
    assert flows["Upper 1"]["airflow_m3_h"] == pytest.approx(1800.0, abs=1e-6)
    assert flows["Upper 2"]["airflow_m3_h"] == pytest.approx(1800.0, abs=1e-6)
    assert flows["Direct"]["absolute_solved_to_reference_flow_ratio"] == pytest.approx(1.0)
    assert result["max_abs_mass_balance_residual_m3_h"] <= 1e-6


def test_automatic_friction_is_resolved_at_reference_airflow() -> None:
    section = DuctSection(
        name="Automatic branch",
        length_m=12.0,
        airflow_m3_h=1800.0,
        friction_factor=None,
        air_density_kg_m3=1.2,
        local_loss_coefficient=1.5,
        diameter_m=0.5,
        absolute_roughness_m=0.00009,
        kinematic_viscosity_m2_s=1.5e-5,
    )
    edge = GeometryDerivedLoopEdge(
        name="Automatic edge",
        start_node="A",
        end_node="B",
        reference_airflow_m3_h=1800.0,
        sections=(section,),
    )

    fixed, evidence = derive_edge_resistance(edge)
    section_evidence = evidence["sections"][0]

    assert fixed.resistance_pa_per_m3_s_squared > 0
    assert section_evidence["friction_factor_method"] == "colebrook"
    assert section_evidence["reynolds_number"] > 2300
    assert "held fixed" in evidence["basis_note"]


def test_zero_derived_edge_resistance_is_rejected() -> None:
    section = DuctSection(
        name="Zero loss",
        length_m=1.0,
        airflow_m3_h=1000.0,
        friction_factor=0.0,
        air_density_kg_m3=1.2,
        local_loss_coefficient=0.0,
        diameter_m=0.5,
    )
    edge = GeometryDerivedLoopEdge(
        name="Zero edge",
        start_node="A",
        end_node="B",
        reference_airflow_m3_h=1000.0,
        sections=(section,),
    )

    with pytest.raises(ValueError, match="resistance_pa_per_m3_s_squared"):
        derive_edge_resistance(edge)


def test_section_airflow_must_match_edge_reference_airflow() -> None:
    section = _loss_only_section("Mismatch", 900.0, 1.0)
    with pytest.raises(ValueError, match="must equal"):
        GeometryDerivedLoopEdge(
            name="Mismatch edge",
            start_node="A",
            end_node="B",
            reference_airflow_m3_h=1000.0,
            sections=(section,),
        )


def test_loader_owns_section_reference_airflow_and_report_includes_basis() -> None:
    network = geometry_derived_loop_network_from_dict(
        {
            "name": "Loaded geometry loop",
            "reference_node": "A",
            "node_injections_m3_h": {"A": 3600.0, "B": -3600.0},
            "edges": [
                {
                    "name": "AB",
                    "start_node": "A",
                    "end_node": "B",
                    "reference_airflow_m3_h": 3600.0,
                    "sections": [
                        {
                            "name": "AB section",
                            "length_m": 0.0,
                            "friction_factor": 0.0,
                            "air_density_kg_m3": 2.0,
                            "local_loss_coefficient": 2.0,
                            "width_m": 1.0,
                            "height_m": 1.0,
                        }
                    ],
                }
            ],
        }
    )

    result = analyze_geometry_derived_loop_network(network)
    report = markdown_geometry_derived_loop_report(result)

    assert result["edges"][0]["reference_airflow_m3_h"] == 3600.0
    assert result["edges"][0]["resistance_pa_per_m3_s_squared"] == pytest.approx(2.0)
    assert "Resistance derivation evidence" in report
    assert "user_input" in report


def test_loader_rejects_section_level_airflow_override() -> None:
    with pytest.raises(ValueError, match="must not define airflow_m3_h"):
        geometry_derived_loop_network_from_dict(
            {
                "name": "Bad loaded geometry loop",
                "reference_node": "A",
                "node_injections_m3_h": {"A": 1000.0, "B": -1000.0},
                "edges": [
                    {
                        "name": "AB",
                        "start_node": "A",
                        "end_node": "B",
                        "reference_airflow_m3_h": 1000.0,
                        "sections": [
                            {
                                "name": "AB section",
                                "length_m": 1.0,
                                "airflow_m3_h": 900.0,
                                "friction_factor": 0.02,
                                "air_density_kg_m3": 1.2,
                                "diameter_m": 0.5,
                            }
                        ],
                    }
                ],
            }
        )
