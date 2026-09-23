import math

import pytest

from cleanroomx.loop_network import (
    LoopedFlowNetwork,
    QuadraticFlowEdge,
    solve_looped_network,
)
from cleanroomx.loop_network_io import looped_flow_network_from_dict
from cleanroomx.loop_network_report import markdown_looped_network_report


def _symmetric_loop() -> LoopedFlowNetwork:
    return LoopedFlowNetwork(
        name="Symmetric loop",
        node_injections_m3_h={
            "Source": 3600.0,
            "Mid": 0.0,
            "Sink": -3600.0,
        },
        edges=(
            QuadraticFlowEdge("Direct", "Source", "Sink", 2.0),
            QuadraticFlowEdge("Upper 1", "Source", "Mid", 1.0),
            QuadraticFlowEdge("Upper 2", "Mid", "Sink", 1.0),
        ),
        reference_node="Source",
    )


def test_symmetric_loop_splits_equal_resistance_paths_equally() -> None:
    result = solve_looped_network(_symmetric_loop())
    flows = {edge["name"]: edge["airflow_m3_h"] for edge in result["edges"]}

    assert flows["Direct"] == pytest.approx(1800.0, abs=1e-6)
    assert flows["Upper 1"] == pytest.approx(1800.0, abs=1e-6)
    assert flows["Upper 2"] == pytest.approx(1800.0, abs=1e-6)
    assert result["max_abs_mass_balance_residual_m3_h"] <= 1e-6
    assert result["max_abs_pressure_law_residual_pa"] <= 1e-9


def test_unequal_loop_matches_analytical_parallel_path_ratio() -> None:
    network = LoopedFlowNetwork(
        name="Unequal loop",
        node_injections_m3_h={
            "Source": 3600.0,
            "Mid": 0.0,
            "Sink": -3600.0,
        },
        edges=(
            QuadraticFlowEdge("Direct", "Source", "Sink", 4.0),
            QuadraticFlowEdge("Series 1", "Source", "Mid", 1.0),
            QuadraticFlowEdge("Series 2", "Mid", "Sink", 1.0),
        ),
        reference_node="Source",
    )

    result = solve_looped_network(network)
    flows = {edge["name"]: edge["airflow_m3_h"] for edge in result["edges"]}
    direct = flows["Direct"] / 3600.0
    series = flows["Series 1"] / 3600.0

    assert series / direct == pytest.approx(math.sqrt(2.0), rel=1e-6)
    assert direct + series == pytest.approx(1.0, abs=1e-9)
    assert flows["Series 1"] == pytest.approx(flows["Series 2"], abs=1e-6)


def test_edge_may_solve_opposite_to_declared_direction() -> None:
    network = LoopedFlowNetwork(
        name="Reverse declared edge",
        node_injections_m3_h={
            "Source": 3600.0,
            "Mid": 0.0,
            "Sink": -3600.0,
        },
        edges=(
            QuadraticFlowEdge("Direct reversed", "Sink", "Source", 4.0),
            QuadraticFlowEdge("Series 1", "Source", "Mid", 1.0),
            QuadraticFlowEdge("Series 2", "Mid", "Sink", 1.0),
        ),
        reference_node="Source",
    )

    result = solve_looped_network(network)
    direct = result["edges"][0]

    assert direct["airflow_m3_h"] < 0
    assert direct["flow_direction"] == "Source -> Sink"
    assert result["max_abs_mass_balance_residual_m3_h"] <= 1e-6


def test_multi_loop_network_converges_and_preserves_continuity() -> None:
    network = LoopedFlowNetwork(
        name="Five-edge mesh",
        node_injections_m3_h={
            "A": 3600.0,
            "B": 1800.0,
            "C": -2700.0,
            "D": -2700.0,
        },
        edges=(
            QuadraticFlowEdge("AB", "A", "B", 1.0),
            QuadraticFlowEdge("BC", "B", "C", 2.0),
            QuadraticFlowEdge("CD", "C", "D", 1.5),
            QuadraticFlowEdge("DA", "D", "A", 2.5),
            QuadraticFlowEdge("AC", "A", "C", 3.0),
        ),
        reference_node="A",
    )

    result = solve_looped_network(network)

    assert result["status"] == "solved"
    assert result["iterations"] > 0
    assert result["max_abs_mass_balance_residual_m3_h"] <= 1e-6
    assert result["max_abs_pressure_law_residual_pa"] <= 1e-9


def test_unbalanced_injections_are_rejected() -> None:
    with pytest.raises(ValueError, match="sum to zero"):
        LoopedFlowNetwork(
            name="Unbalanced",
            node_injections_m3_h={"A": 1000.0, "B": -900.0},
            edges=(QuadraticFlowEdge("AB", "A", "B", 1.0),),
            reference_node="A",
        )


def test_large_flow_relative_balance_does_not_hide_absolute_mismatch() -> None:
    with pytest.raises(ValueError, match="sum to zero"):
        LoopedFlowNetwork(
            name="Large-flow imbalance",
            node_injections_m3_h={
                "A": 1_000_000_000.0,
                "B": -999_999_999.9,
            },
            edges=(QuadraticFlowEdge("AB", "A", "B", 1.0),),
            reference_node="A",
        )


def test_disconnected_graph_is_rejected() -> None:
    with pytest.raises(ValueError, match="connected"):
        LoopedFlowNetwork(
            name="Disconnected",
            node_injections_m3_h={
                "A": 1000.0,
                "B": -1000.0,
                "C": 0.0,
            },
            edges=(QuadraticFlowEdge("AB", "A", "B", 1.0),),
            reference_node="A",
        )


@pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_edge_resistance_is_rejected(bad: float) -> None:
    with pytest.raises(ValueError):
        QuadraticFlowEdge("Bad", "A", "B", bad)


def test_loader_and_markdown_report() -> None:
    network = looped_flow_network_from_dict(
        {
            "name": "Loaded loop",
            "reference_node": "Supply",
            "node_injections_m3_h": {
                "Supply": 3600.0,
                "Junction": 0.0,
                "Return": -3600.0,
            },
            "edges": [
                {
                    "name": "Direct",
                    "start_node": "Supply",
                    "end_node": "Return",
                    "resistance_pa_per_m3_s_squared": 2.0,
                },
                {
                    "name": "Branch A",
                    "start_node": "Supply",
                    "end_node": "Junction",
                    "resistance_pa_per_m3_s_squared": 1.0,
                },
                {
                    "name": "Branch B",
                    "start_node": "Junction",
                    "end_node": "Return",
                    "resistance_pa_per_m3_s_squared": 1.0,
                },
            ],
        }
    )
    result = solve_looped_network(network)
    report = markdown_looped_network_report(result)

    assert network.reference_node == "Supply"
    assert "Looped-Network Flow Report" in report
    assert "Maximum node continuity residual" in report
    assert "Supply -> Return" in report


def test_reported_reference_residual_respects_requested_tolerance() -> None:
    network = LoopedFlowNetwork(
        name="Residual tolerance mesh",
        node_injections_m3_h={
            "A": 5000.0,
            "B": 1000.0,
            "C": -2200.0,
            "D": -1800.0,
            "E": -2000.0,
        },
        edges=(
            QuadraticFlowEdge("AB", "A", "B", 1.1),
            QuadraticFlowEdge("BC", "B", "C", 1.7),
            QuadraticFlowEdge("CD", "C", "D", 1.3),
            QuadraticFlowEdge("DE", "D", "E", 2.1),
            QuadraticFlowEdge("EA", "E", "A", 1.9),
            QuadraticFlowEdge("AC", "A", "C", 2.8),
            QuadraticFlowEdge("BD", "B", "D", 2.5),
        ),
        reference_node="A",
    )

    tolerance = 1e-8
    result = solve_looped_network(
        network,
        mass_balance_tolerance_m3_h=tolerance,
    )

    assert result["max_abs_mass_balance_residual_m3_h"] <= tolerance
    reference = next(
        node for node in result["nodes"]
        if node["name"] == result["reference_node"]
    )
    assert abs(reference["mass_balance_residual_m3_h"]) <= tolerance
