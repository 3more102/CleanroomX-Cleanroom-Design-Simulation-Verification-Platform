import pytest

from cleanroomx.loop_network import LoopedFlowNetwork, QuadraticFlowEdge
from cleanroomx.loop_network_io import looped_flow_network_from_dict
from cleanroomx.variable_friction_loop import (
    solve_variable_friction_looped_network,
)
from cleanroomx.variable_friction_loop_report import (
    markdown_variable_friction_loop_report,
)


def _automatic_geometry(
    name: str,
    start: str,
    end: str,
    *,
    diameter_m: float = 0.5,
    reference_airflow_m3_h: float = 900.0,
) -> dict:
    return {
        "name": name,
        "start_node": start,
        "end_node": end,
        "duct_geometry": {
            "length_m": 12.0,
            "air_density_kg_m3": 1.2,
            "local_loss_coefficient": 0.5,
            "diameter_m": diameter_m,
            "absolute_roughness_m": 0.00015,
            "kinematic_viscosity_m2_s": 1.5e-5,
            "reference_airflow_m3_h": reference_airflow_m3_h,
        },
    }


def test_single_edge_recomputes_friction_at_solved_airflow() -> None:
    network = looped_flow_network_from_dict(
        {
            "name": "Single automatic edge",
            "reference_node": "Supply",
            "node_injections_m3_h": {
                "Supply": 3600.0,
                "Return": -3600.0,
            },
            "edges": [
                _automatic_geometry("Duct", "Supply", "Return")
            ],
        }
    )
    initial_resistance = (
        network.edges[0].resistance_pa_per_m3_s_squared
    )

    result = solve_variable_friction_looped_network(
        network,
        relaxation=1.0,
        resistance_relative_tolerance=1e-9,
    )

    edge = result["edges"][0]
    assert result["status"] == "solved"
    assert result["variable_friction"]["converged"] is True
    assert result["variable_friction"]["outer_iterations"] == 2
    assert (
        result["variable_friction"][
            "max_relative_resistance_closure_error"
        ]
        <= 1e-9
    )
    assert edge["resistance_pa_per_m3_s_squared"] != pytest.approx(
        initial_resistance
    )
    assert edge["resistance_evidence"][
        "reference_airflow_m3_h"
    ] == pytest.approx(3600.0)
    assert edge["resistance_evidence"]["reynolds_number"] > 2300.0


def test_parallel_automatic_edges_converge_with_mass_balance() -> None:
    network = looped_flow_network_from_dict(
        {
            "name": "Parallel automatic edges",
            "reference_node": "Supply",
            "node_injections_m3_h": {
                "Supply": 3600.0,
                "Return": -3600.0,
            },
            "edges": [
                _automatic_geometry(
                    "Large duct",
                    "Supply",
                    "Return",
                    diameter_m=0.5,
                    reference_airflow_m3_h=1800.0,
                ),
                _automatic_geometry(
                    "Small duct",
                    "Supply",
                    "Return",
                    diameter_m=0.35,
                    reference_airflow_m3_h=1800.0,
                ),
            ],
        }
    )

    result = solve_variable_friction_looped_network(
        network,
        relaxation=1.0,
        resistance_relative_tolerance=1e-6,
    )
    flows = [edge["airflow_m3_h"] for edge in result["edges"]]

    assert sum(flows) == pytest.approx(3600.0, abs=1e-5)
    assert result["max_abs_mass_balance_residual_m3_h"] <= 1e-6
    assert result["variable_friction"][
        "automatic_friction_edge_count"
    ] == 2
    assert result["variable_friction"]["outer_iterations"] >= 2
    assert (
        result["variable_friction"][
            "max_relative_resistance_closure_error"
        ]
        <= 1e-6
    )


def test_manual_geometry_friction_remains_fixed() -> None:
    network = looped_flow_network_from_dict(
        {
            "name": "Manual friction",
            "reference_node": "A",
            "node_injections_m3_h": {
                "A": 3600.0,
                "B": -3600.0,
            },
            "edges": [
                {
                    "name": "AB",
                    "start_node": "A",
                    "end_node": "B",
                    "duct_geometry": {
                        "length_m": 10.0,
                        "air_density_kg_m3": 1.2,
                        "friction_factor": 0.02,
                        "local_loss_coefficient": 0.4,
                        "diameter_m": 0.5,
                    },
                }
            ],
        }
    )
    initial_resistance = (
        network.edges[0].resistance_pa_per_m3_s_squared
    )

    result = solve_variable_friction_looped_network(network)

    assert result["variable_friction"][
        "automatic_friction_edge_count"
    ] == 0
    assert result["variable_friction"]["outer_iterations"] == 0
    assert result["edges"][0][
        "resistance_pa_per_m3_s_squared"
    ] == pytest.approx(initial_resistance)


def test_zero_flow_automatic_spur_is_explicitly_frozen() -> None:
    network = looped_flow_network_from_dict(
        {
            "name": "Zero-flow automatic spur",
            "reference_node": "Source",
            "node_injections_m3_h": {
                "Source": 3600.0,
                "Sink": -3600.0,
                "DeadEnd": 0.0,
            },
            "edges": [
                {
                    "name": "Main",
                    "start_node": "Source",
                    "end_node": "Sink",
                    "resistance_pa_per_m3_s_squared": 100.0,
                },
                _automatic_geometry(
                    "Zero-flow spur",
                    "Source",
                    "DeadEnd",
                    diameter_m=0.3,
                    reference_airflow_m3_h=100.0,
                ),
            ],
        }
    )

    result = solve_variable_friction_looped_network(
        network,
        relaxation=1.0,
        near_zero_airflow_m3_h=1e-3,
    )
    spur = next(
        row
        for row in result["variable_friction"]["edge_closure"]
        if row["name"] == "Zero-flow spur"
    )

    assert abs(spur["airflow_m3_h"]) <= 1e-3
    assert spur["state"] == "near_zero_flow_frozen"
    assert result["variable_friction"][
        "near_zero_frozen_edge_count"
    ] == 1


def test_rectangular_automatic_geometry_can_be_reconstructed() -> None:
    network = looped_flow_network_from_dict(
        {
            "name": "Rectangular automatic edge",
            "reference_node": "A",
            "node_injections_m3_h": {
                "A": 3600.0,
                "B": -3600.0,
            },
            "edges": [
                {
                    "name": "Rectangular",
                    "start_node": "A",
                    "end_node": "B",
                    "duct_geometry": {
                        "length_m": 8.0,
                        "air_density_kg_m3": 1.2,
                        "local_loss_coefficient": 0.4,
                        "width_m": 0.6,
                        "height_m": 0.4,
                        "absolute_roughness_m": 0.00015,
                        "kinematic_viscosity_m2_s": 1.5e-5,
                        "reference_airflow_m3_h": 1200.0,
                    },
                }
            ],
        }
    )

    result = solve_variable_friction_looped_network(
        network,
        relaxation=1.0,
    )

    evidence = result["edges"][0]["resistance_evidence"]
    assert evidence["shape"] == "rectangular"
    assert evidence["reference_airflow_m3_h"] == pytest.approx(
        3600.0
    )
    assert result["variable_friction"]["converged"] is True


@pytest.mark.parametrize("relaxation", [0.0, -0.1, 1.1])
def test_invalid_relaxation_is_rejected(relaxation: float) -> None:
    network = looped_flow_network_from_dict(
        {
            "name": "Simple",
            "reference_node": "A",
            "node_injections_m3_h": {
                "A": 1000.0,
                "B": -1000.0,
            },
            "edges": [
                {
                    "name": "AB",
                    "start_node": "A",
                    "end_node": "B",
                    "resistance_pa_per_m3_s_squared": 1.0,
                }
            ],
        }
    )
    with pytest.raises(ValueError, match="relaxation"):
        solve_variable_friction_looped_network(
            network, relaxation=relaxation
        )


def test_markdown_report_surfaces_variable_friction_closure() -> None:
    network = looped_flow_network_from_dict(
        {
            "name": "Report network",
            "reference_node": "A",
            "node_injections_m3_h": {
                "A": 3600.0,
                "B": -3600.0,
            },
            "edges": [
                _automatic_geometry("AB", "A", "B")
            ],
        }
    )
    result = solve_variable_friction_looped_network(
        network,
        relaxation=1.0,
    )
    report = markdown_variable_friction_loop_report(result)

    assert "Variable-friction convergence" in report
    assert "Edge closure" in report
    assert "automatic_friction" in report


def test_malformed_automatic_friction_evidence_is_rejected_even_at_zero_flow() -> None:
    edge = QuadraticFlowEdge(
        name="Malformed automatic edge",
        start_node="A",
        end_node="B",
        resistance_pa_per_m3_s_squared=10.0,
        resistance_basis="duct_geometry",
        resistance_evidence={
            "absolute_roughness_m": 0.00015,
            "kinematic_viscosity_m2_s": 1.5e-5,
            "reference_airflow_m3_h": 1000.0,
            "friction_factor": 0.02,
        },
    )
    network = LoopedFlowNetwork(
        name="Malformed evidence at zero flow",
        node_injections_m3_h={"A": 0.0, "B": 0.0},
        edges=(edge,),
        reference_node="A",
    )

    with pytest.raises(ValueError, match="incomplete resistance evidence"):
        solve_variable_friction_looped_network(network)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("reference_airflow_m3_h", 0.0),
        ("reference_airflow_m3_h", float("nan")),
        ("friction_factor", 0.0),
        ("friction_factor", float("inf")),
    ],
)
def test_invalid_stored_automatic_friction_evidence_is_rejected(
    field: str,
    value: float,
) -> None:
    loaded = looped_flow_network_from_dict(
        {
            "name": "Valid automatic evidence source",
            "reference_node": "A",
            "node_injections_m3_h": {"A": 1000.0, "B": -1000.0},
            "edges": [_automatic_geometry("AB", "A", "B")],
        }
    )
    source = loaded.edges[0]
    evidence = dict(source.resistance_evidence)
    evidence[field] = value
    edge = QuadraticFlowEdge(
        name=source.name,
        start_node=source.start_node,
        end_node=source.end_node,
        resistance_pa_per_m3_s_squared=source.resistance_pa_per_m3_s_squared,
        resistance_basis=source.resistance_basis,
        resistance_evidence=evidence,
    )
    network = LoopedFlowNetwork(
        name="Corrupted automatic evidence",
        node_injections_m3_h={"A": 1000.0, "B": -1000.0},
        edges=(edge,),
        reference_node="A",
    )

    with pytest.raises(ValueError):
        solve_variable_friction_looped_network(network)
