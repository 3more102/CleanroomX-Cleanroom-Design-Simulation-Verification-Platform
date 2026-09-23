import pytest

from cleanroomx.fan_curve import FanCurve, FanCurvePoint
from cleanroomx.fan_loop_damper import (
    DamperState,
    FanLoopDamperStudy,
    solve_fan_loop_damper_study,
)
from cleanroomx.fan_loop_damper_io import fan_loop_damper_study_from_dict
from cleanroomx.fan_loop_damper_report import markdown_fan_loop_damper_report
from cleanroomx.fan_loop_network import FanLoopNetworkStudy
from cleanroomx.loop_network import LoopedFlowNetwork, QuadraticFlowEdge


def _base_study() -> FanLoopNetworkStudy:
    network = LoopedFlowNetwork(
        name="Two-path loop",
        node_injections_m3_h={
            "Supply": 3600.0,
            "Mid": 0.0,
            "Return": -3600.0,
        },
        edges=(
            QuadraticFlowEdge("Direct", "Supply", "Return", 500.0),
            QuadraticFlowEdge("Upper 1", "Supply", "Mid", 250.0),
            QuadraticFlowEdge("Upper 2", "Mid", "Return", 250.0),
        ),
        reference_node="Supply",
    )
    fan = FanCurve(
        name="Reference fan",
        points=(
            FanCurvePoint(0.0, 500.0),
            FanCurvePoint(3600.0, 125.0),
            FanCurvePoint(7200.0, 0.0),
        ),
    )
    return FanLoopNetworkStudy(
        name="Reference fan loop",
        fan_curve=fan,
        loop_network=network,
        fan_discharge_node="Supply",
        fan_suction_node="Return",
    )


def _study() -> FanLoopDamperStudy:
    return FanLoopDamperStudy(
        name="Direct-branch damper sweep",
        base_study=_base_study(),
        states=(
            DamperState(
                name="Open",
                edge_added_resistance_pa_per_m3_s_squared={"Direct": 0.0},
            ),
            DamperState(
                name="Throttled",
                edge_added_resistance_pa_per_m3_s_squared={"Direct": 1500.0},
            ),
        ),
    )


def _edge_flow(state_result: dict, edge_name: str) -> float:
    network = state_result["fan_loop_result"]["operating_network_solution"]
    assert network is not None
    return next(
        edge["airflow_m3_h"]
        for edge in network["edges"]
        if edge["name"] == edge_name
    )


def test_throttling_increases_equivalent_resistance_and_reduces_airflow() -> None:
    result = solve_fan_loop_damper_study(_study())
    assert result["status"] == "solved"
    assert result["solved_state_count"] == 2

    open_state, throttled_state = result["states"]
    assert (
        throttled_state["equivalent_loop_resistance_pa_per_m3_s_squared"]
        > open_state["equivalent_loop_resistance_pa_per_m3_s_squared"]
    )
    assert (
        throttled_state["operating_airflow_m3_h"]
        < open_state["operating_airflow_m3_h"]
    )
    assert _edge_flow(throttled_state, "Direct") < _edge_flow(
        open_state, "Direct"
    )


def test_damper_adjustment_is_reported_without_inventing_position_mapping() -> None:
    result = solve_fan_loop_damper_study(_study())
    adjustment = result["states"][1]["damper_adjustments"][0]
    assert adjustment["edge"] == "Direct"
    assert adjustment["base_resistance_pa_per_m3_s_squared"] == 500.0
    assert adjustment["added_resistance_pa_per_m3_s_squared"] == 1500.0
    assert adjustment["adjusted_resistance_pa_per_m3_s_squared"] == 2000.0
    assert "does not infer resistance from damper position" in result["scope_note"]


def test_unknown_damper_edge_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown edge"):
        FanLoopDamperStudy(
            name="Invalid",
            base_study=_base_study(),
            states=(
                DamperState(
                    name="Bad state",
                    edge_added_resistance_pa_per_m3_s_squared={"Missing": 1.0},
                ),
            ),
        )


@pytest.mark.parametrize("value", [-1.0, float("nan"), float("inf")])
def test_invalid_added_resistance_is_rejected(value: float) -> None:
    with pytest.raises(ValueError, match="finite and >= 0"):
        DamperState(
            name="Invalid",
            edge_added_resistance_pa_per_m3_s_squared={"Direct": value},
        )


def test_loader_and_markdown_report() -> None:
    data = {
        "name": "Loaded damper study",
        "base_study": {
            "name": "Loaded fan loop",
            "fan_discharge_node": "Supply",
            "fan_suction_node": "Return",
            "fan_curve": {
                "name": "Loaded fan",
                "points": [
                    {"airflow_m3_h": 0.0, "pressure_pa": 500.0},
                    {"airflow_m3_h": 3600.0, "pressure_pa": 125.0},
                    {"airflow_m3_h": 7200.0, "pressure_pa": 0.0},
                ],
            },
            "loop_network": {
                "name": "Loaded network",
                "reference_node": "Supply",
                "node_injections_m3_h": {
                    "Supply": 3600.0,
                    "Return": -3600.0,
                },
                "edges": [
                    {
                        "name": "Main",
                        "start_node": "Supply",
                        "end_node": "Return",
                        "resistance_pa_per_m3_s_squared": 125.0,
                    }
                ],
            },
        },
        "damper_states": [
            {
                "name": "Open",
                "edge_added_resistance_pa_per_m3_s_squared": {"Main": 0.0},
            },
            {
                "name": "Restricted",
                "edge_added_resistance_pa_per_m3_s_squared": {"Main": 125.0},
            },
        ],
    }
    study = fan_loop_damper_study_from_dict(data)
    result = solve_fan_loop_damper_study(study)
    report = markdown_fan_loop_damper_report(result)

    assert len(study.states) == 2
    assert "Fan/Loop Damper Study" in report
    assert "Explicit damper resistance adjustments" in report
    assert "Restricted" in report
