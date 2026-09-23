import pytest

from cleanroomx.loop_geometry import (
    ReferenceDuctEdge,
    ReferenceGeometryLoopNetwork,
    analyze_reference_geometry_loop,
    derive_fixed_resistance,
)
from cleanroomx.loop_geometry_io import reference_geometry_loop_from_dict
from cleanroomx.loop_geometry_report import markdown_reference_geometry_loop_report


def _local_loss_edge(
    name: str,
    start: str,
    end: str,
    local_k: float,
) -> ReferenceDuctEdge:
    return ReferenceDuctEdge(
        name=name,
        start_node=start,
        end_node=end,
        reference_airflow_m3_h=3600.0,
        length_m=0.0,
        air_density_kg_m3=1.0,
        friction_factor=0.0,
        local_loss_coefficient=local_k,
        width_m=1.0,
        height_m=1.0,
    )


def test_reference_geometry_derives_exact_fixed_quadratic_resistance() -> None:
    result = derive_fixed_resistance(
        _local_loss_edge("Local-loss edge", "A", "B", 4.0)
    )

    assert result["reference_airflow_m3_s"] == pytest.approx(1.0)
    assert result["velocity_m_s"] == pytest.approx(1.0)
    assert result["reference_pressure_drop_pa"] == pytest.approx(2.0)
    assert result["derived_resistance_pa_per_m3_s_squared"] == pytest.approx(2.0)
    assert result["friction_factor_method"] == "user_input"


def test_automatic_friction_evidence_is_preserved_in_derivation() -> None:
    result = derive_fixed_resistance(
        ReferenceDuctEdge(
            name="Automatic circular branch",
            start_node="A",
            end_node="B",
            reference_airflow_m3_h=3600.0,
            length_m=10.0,
            air_density_kg_m3=1.2,
            local_loss_coefficient=1.0,
            diameter_m=0.5,
            absolute_roughness_m=0.00009,
            kinematic_viscosity_m2_s=0.000015,
        )
    )

    assert result["friction_factor_method"] == "colebrook"
    assert result["reynolds_number"] > 2300
    assert result["derived_resistance_pa_per_m3_s_squared"] > 0


def test_geometry_derived_loop_reuses_fixed_resistance_solver() -> None:
    network = ReferenceGeometryLoopNetwork(
        name="Equal parallel geometry",
        node_injections_m3_h={
            "Source": 3600.0,
            "Mid": 0.0,
            "Sink": -3600.0,
        },
        edges=(
            _local_loss_edge("Direct", "Source", "Sink", 4.0),
            _local_loss_edge("Upper 1", "Source", "Mid", 2.0),
            _local_loss_edge("Upper 2", "Mid", "Sink", 2.0),
        ),
        reference_node="Source",
    )

    result = analyze_reference_geometry_loop(network)
    solved = result["loop_solution"]
    flows = {edge["name"]: edge["airflow_m3_h"] for edge in solved["edges"]}

    assert flows["Direct"] == pytest.approx(1800.0, abs=1e-6)
    assert flows["Upper 1"] == pytest.approx(1800.0, abs=1e-6)
    assert flows["Upper 2"] == pytest.approx(1800.0, abs=1e-6)
    assert solved["max_abs_mass_balance_residual_m3_h"] <= 1e-6


def test_zero_derived_resistance_is_rejected() -> None:
    edge = ReferenceDuctEdge(
        name="Zero loss",
        start_node="A",
        end_node="B",
        reference_airflow_m3_h=3600.0,
        length_m=1.0,
        air_density_kg_m3=1.0,
        friction_factor=0.0,
        local_loss_coefficient=0.0,
        width_m=1.0,
        height_m=1.0,
    )
    with pytest.raises(ValueError, match="resistance > 0"):
        derive_fixed_resistance(edge)


def test_loader_and_markdown_report_preserve_derivation_scope() -> None:
    network = reference_geometry_loop_from_dict(
        {
            "name": "Loaded geometry loop",
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
                    "length_m": 0.0,
                    "air_density_kg_m3": 1.0,
                    "friction_factor": 0.0,
                    "local_loss_coefficient": 4.0,
                    "width_m": 1.0,
                    "height_m": 1.0,
                },
                {
                    "name": "Upper 1",
                    "start_node": "Source",
                    "end_node": "Mid",
                    "reference_airflow_m3_h": 3600.0,
                    "length_m": 0.0,
                    "air_density_kg_m3": 1.0,
                    "friction_factor": 0.0,
                    "local_loss_coefficient": 2.0,
                    "width_m": 1.0,
                    "height_m": 1.0,
                },
                {
                    "name": "Upper 2",
                    "start_node": "Mid",
                    "end_node": "Sink",
                    "reference_airflow_m3_h": 3600.0,
                    "length_m": 0.0,
                    "air_density_kg_m3": 1.0,
                    "friction_factor": 0.0,
                    "local_loss_coefficient": 2.0,
                    "width_m": 1.0,
                    "height_m": 1.0,
                },
            ],
        }
    )
    result = analyze_reference_geometry_loop(network)
    report = markdown_reference_geometry_loop_report(result)

    assert "Reference resistance derivation" in report
    assert "Fixed-resistance loop solution" in report
    assert "held fixed" in report
    assert result["derived_edges"][0]["derived_resistance_pa_per_m3_s_squared"] == pytest.approx(2.0)
