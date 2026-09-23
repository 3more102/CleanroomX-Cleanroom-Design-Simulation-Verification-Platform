import pytest

from cleanroomx.duct import DuctSection
from cleanroomx.loop_network_geometry import (
    GeometryLoopedFlowNetwork,
    LoopDuctEdge,
    derive_loop_duct_edge_resistance,
    solve_geometry_looped_network,
)
from cleanroomx.loop_network_geometry_io import (
    geometry_looped_flow_network_from_dict,
    load_geometry_looped_flow_network,
)
from cleanroomx.loop_network_geometry_report import (
    markdown_geometry_looped_network_report,
)


def _manual_section(name: str, length_m: float, airflow_m3_h: float = 1800.0) -> DuctSection:
    return DuctSection(
        name=name,
        length_m=length_m,
        airflow_m3_h=airflow_m3_h,
        friction_factor=0.02,
        air_density_kg_m3=1.2,
        diameter_m=0.5,
    )


def test_geometry_derived_loop_matches_symmetric_parallel_split() -> None:
    network = GeometryLoopedFlowNetwork(
        name="Geometry symmetric loop",
        node_injections_m3_h={
            "Source": 3600.0,
            "Mid": 0.0,
            "Sink": -3600.0,
        },
        edges=(
            LoopDuctEdge(
                "Direct",
                "Source",
                "Sink",
                (_manual_section("Direct duct", 20.0),),
            ),
            LoopDuctEdge(
                "Upper 1",
                "Source",
                "Mid",
                (_manual_section("Upper first", 10.0),),
            ),
            LoopDuctEdge(
                "Upper 2",
                "Mid",
                "Sink",
                (_manual_section("Upper second", 10.0),),
            ),
        ),
        reference_node="Source",
    )

    result = solve_geometry_looped_network(network)
    flows = {edge["name"]: edge["airflow_m3_h"] for edge in result["edges"]}

    assert flows["Direct"] == pytest.approx(1800.0, abs=1e-6)
    assert flows["Upper 1"] == pytest.approx(1800.0, abs=1e-6)
    assert flows["Upper 2"] == pytest.approx(1800.0, abs=1e-6)
    assert result["max_abs_mass_balance_residual_m3_h"] <= 1e-6
    assert result["resistance_basis"] == (
        "duct_geometry_with_friction_frozen_at_reference_airflow"
    )


def test_automatic_friction_is_frozen_at_explicit_reference_airflow() -> None:
    edge = LoopDuctEdge(
        name="Automatic edge",
        start_node="A",
        end_node="B",
        sections=(
            DuctSection(
                name="Round duct",
                length_m=12.0,
                airflow_m3_h=1800.0,
                friction_factor=None,
                air_density_kg_m3=1.2,
                diameter_m=0.5,
                absolute_roughness_m=0.00009,
                kinematic_viscosity_m2_s=1.5e-5,
            ),
        ),
    )

    result = derive_loop_duct_edge_resistance(edge)
    section = result["sections"][0]

    assert result["resistance_pa_per_m3_s_squared"] > 0
    assert result["reference_pressure_drop_pa"] > 0
    assert section["friction_factor_method"] == "colebrook"
    assert section["reynolds_number"] > 2300
    assert section["reference_airflow_m3_h"] == 1800.0


def test_loop_edge_requires_one_reference_airflow_for_all_series_sections() -> None:
    with pytest.raises(ValueError, match="same explicit reference airflow"):
        LoopDuctEdge(
            name="Bad edge",
            start_node="A",
            end_node="B",
            sections=(
                _manual_section("S1", 5.0, 1000.0),
                _manual_section("S2", 5.0, 1100.0),
            ),
        )


def test_geometry_loader_supports_automatic_friction_inputs() -> None:
    network = geometry_looped_flow_network_from_dict(
        {
            "name": "Loaded geometry loop",
            "reference_node": "A",
            "node_injections_m3_h": {
                "A": 3600.0,
                "B": 0.0,
                "C": -3600.0,
            },
            "edges": [
                {
                    "name": "Direct",
                    "start_node": "A",
                    "end_node": "C",
                    "sections": [
                        {
                            "name": "Direct duct",
                            "length_m": 20.0,
                            "airflow_m3_h": 1800.0,
                            "air_density_kg_m3": 1.2,
                            "diameter_m": 0.5,
                            "absolute_roughness_m": 0.00009,
                            "kinematic_viscosity_m2_s": 1.5e-5,
                        }
                    ],
                },
                {
                    "name": "Upper 1",
                    "start_node": "A",
                    "end_node": "B",
                    "sections": [
                        {
                            "name": "Upper first",
                            "length_m": 10.0,
                            "airflow_m3_h": 1800.0,
                            "air_density_kg_m3": 1.2,
                            "diameter_m": 0.5,
                            "absolute_roughness_m": 0.00009,
                            "kinematic_viscosity_m2_s": 1.5e-5,
                        }
                    ],
                },
                {
                    "name": "Upper 2",
                    "start_node": "B",
                    "end_node": "C",
                    "sections": [
                        {
                            "name": "Upper second",
                            "length_m": 10.0,
                            "airflow_m3_h": 1800.0,
                            "air_density_kg_m3": 1.2,
                            "diameter_m": 0.5,
                            "absolute_roughness_m": 0.00009,
                            "kinematic_viscosity_m2_s": 1.5e-5,
                        }
                    ],
                },
            ],
        }
    )
    result = solve_geometry_looped_network(network)

    assert result["status"] == "solved"
    assert result["edges"][0]["sections"][0]["friction_factor_method"] == "colebrook"


def test_repository_geometry_example_builds_and_reports() -> None:
    network = load_geometry_looped_flow_network(
        "examples/looped_network_geometry_demo.json"
    )
    result = solve_geometry_looped_network(network)
    report = markdown_geometry_looped_network_report(result)

    assert result["status"] == "solved"
    assert result["max_abs_mass_balance_residual_m3_h"] <= 1e-6
    assert "Geometry-derived fixed-resistance basis" in report
    assert "colebrook" in report
    assert "Reference airflow" in report
