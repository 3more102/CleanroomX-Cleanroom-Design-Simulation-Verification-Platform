import pytest

from cleanroomx.loop_geometry import (
    ReferenceDuctEdge,
    ReferenceDuctSection,
    ReferenceGeometryLoopNetwork,
    derive_reference_edge_resistance,
    solve_reference_geometry_loop,
)
from cleanroomx.loop_geometry_io import reference_geometry_loop_from_dict
from cleanroomx.loop_geometry_report import markdown_reference_geometry_loop_report


def _loss_section(name: str, local_k: float) -> ReferenceDuctSection:
    return ReferenceDuctSection(
        name=name,
        length_m=0.0,
        air_density_kg_m3=1.0,
        friction_factor=0.0,
        local_loss_coefficient=local_k,
        width_m=1.0,
        height_m=1.0,
    )


def test_reference_edge_sums_multiple_series_section_resistances() -> None:
    edge = ReferenceDuctEdge(
        name="Series edge",
        start_node="A",
        end_node="B",
        reference_airflow_m3_h=3600.0,
        sections=(
            _loss_section("S1", 2.0),
            _loss_section("S2", 4.0),
        ),
    )
    result = derive_reference_edge_resistance(edge)

    assert result["reference_pressure_drop_pa"] == pytest.approx(3.0)
    assert result["derived_resistance_pa_per_m3_s_squared"] == pytest.approx(3.0)
    assert result["section_count"] == 2


def test_automatic_friction_is_resolved_once_at_reference_flow() -> None:
    edge = ReferenceDuctEdge(
        name="Automatic edge",
        start_node="A",
        end_node="B",
        reference_airflow_m3_h=3600.0,
        sections=(
            ReferenceDuctSection(
                name="Circular",
                length_m=10.0,
                air_density_kg_m3=1.2,
                local_loss_coefficient=1.0,
                diameter_m=0.5,
                absolute_roughness_m=0.00009,
                kinematic_viscosity_m2_s=0.000015,
            ),
        ),
    )
    result = derive_reference_edge_resistance(edge)
    section = result["sections"][0]

    assert section["friction_factor_method"] == "colebrook"
    assert section["reynolds_number"] > 2300
    assert section["derived_resistance_pa_per_m3_s_squared"] > 0


def test_reference_geometry_loop_reuses_fixed_resistance_solver() -> None:
    network = ReferenceGeometryLoopNetwork(
        name="Equal equivalent paths",
        node_injections_m3_h={
            "Source": 3600.0,
            "Mid": 0.0,
            "Sink": -3600.0,
        },
        edges=(
            ReferenceDuctEdge(
                "Direct",
                "Source",
                "Sink",
                3600.0,
                (
                    _loss_section("Direct 1", 2.0),
                    _loss_section("Direct 2", 2.0),
                ),
            ),
            ReferenceDuctEdge(
                "Upper 1",
                "Source",
                "Mid",
                3600.0,
                (_loss_section("Upper 1 section", 2.0),),
            ),
            ReferenceDuctEdge(
                "Upper 2",
                "Mid",
                "Sink",
                3600.0,
                (_loss_section("Upper 2 section", 2.0),),
            ),
        ),
        reference_node="Source",
    )

    result = solve_reference_geometry_loop(network)
    flows = {edge["name"]: edge["airflow_m3_h"] for edge in result["edges"]}

    assert flows["Direct"] == pytest.approx(1800.0, abs=1e-6)
    assert flows["Upper 1"] == pytest.approx(1800.0, abs=1e-6)
    assert flows["Upper 2"] == pytest.approx(1800.0, abs=1e-6)
    assert result["max_abs_mass_balance_residual_m3_h"] <= 1e-6
    assert result["max_abs_geometry_pressure_residual_pa"] <= 1e-6


def test_zero_reference_loss_is_rejected() -> None:
    edge = ReferenceDuctEdge(
        name="Zero loss",
        start_node="A",
        end_node="B",
        reference_airflow_m3_h=3600.0,
        sections=(
            ReferenceDuctSection(
                name="Zero",
                length_m=1.0,
                air_density_kg_m3=1.0,
                friction_factor=0.0,
                local_loss_coefficient=0.0,
                width_m=1.0,
                height_m=1.0,
            ),
        ),
    )
    with pytest.raises(ValueError, match="resistance > 0"):
        derive_reference_edge_resistance(edge)


def test_manual_and_automatic_friction_inputs_are_not_mixed() -> None:
    with pytest.raises(ValueError, match="either friction_factor"):
        ReferenceDuctEdge(
            name="Ambiguous",
            start_node="A",
            end_node="B",
            reference_airflow_m3_h=3600.0,
            sections=(
                ReferenceDuctSection(
                    name="S",
                    length_m=1.0,
                    air_density_kg_m3=1.2,
                    friction_factor=0.02,
                    diameter_m=0.5,
                    absolute_roughness_m=0.00009,
                    kinematic_viscosity_m2_s=0.000015,
                ),
            ),
        )


def test_loader_and_markdown_report_preserve_reference_evidence() -> None:
    network = reference_geometry_loop_from_dict(
        {
            "name": "Loaded reference geometry",
            "reference_node": "Source",
            "node_injections_m3_h": {
                "Source": 3600.0,
                "Mid": 0.0,
                "Sink": -3600.0,
            },
            "edges": [
                {
                    "name": "Direct",
                    "start_node": "Source",
                    "end_node": "Sink",
                    "reference_airflow_m3_h": 3600.0,
                    "sections": [
                        {
                            "name": "D1",
                            "length_m": 0.0,
                            "air_density_kg_m3": 1.0,
                            "friction_factor": 0.0,
                            "local_loss_coefficient": 2.0,
                            "width_m": 1.0,
                            "height_m": 1.0
                        },
                        {
                            "name": "D2",
                            "length_m": 0.0,
                            "air_density_kg_m3": 1.0,
                            "friction_factor": 0.0,
                            "local_loss_coefficient": 2.0,
                            "width_m": 1.0,
                            "height_m": 1.0
                        }
                    ]
                },
                {
                    "name": "Upper 1",
                    "start_node": "Source",
                    "end_node": "Mid",
                    "reference_airflow_m3_h": 3600.0,
                    "sections": [
                        {
                            "name": "U1",
                            "length_m": 0.0,
                            "air_density_kg_m3": 1.0,
                            "friction_factor": 0.0,
                            "local_loss_coefficient": 2.0,
                            "width_m": 1.0,
                            "height_m": 1.0
                        }
                    ]
                },
                {
                    "name": "Upper 2",
                    "start_node": "Mid",
                    "end_node": "Sink",
                    "reference_airflow_m3_h": 3600.0,
                    "sections": [
                        {
                            "name": "U2",
                            "length_m": 0.0,
                            "air_density_kg_m3": 1.0,
                            "friction_factor": 0.0,
                            "local_loss_coefficient": 2.0,
                            "width_m": 1.0,
                            "height_m": 1.0
                        }
                    ]
                }
            ]
        }
    )
    result = solve_reference_geometry_loop(network)
    report = markdown_reference_geometry_loop_report(result)

    assert result["status"] == "solved"
    assert "Reference-Geometry Looped-Duct Report" in report
    assert "Section reference evidence" in report
    assert "held fixed" in result["scope_note"]
