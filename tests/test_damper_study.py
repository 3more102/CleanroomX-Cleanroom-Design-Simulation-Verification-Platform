import pytest

from cleanroomx.damper_study import (
    DamperResistanceCase,
    LoopDamperStudy,
    solve_loop_damper_study,
)
from cleanroomx.damper_study_io import loop_damper_study_from_dict
from cleanroomx.damper_study_report import markdown_loop_damper_study_report
from cleanroomx.loop_network import LoopedFlowNetwork, QuadraticFlowEdge


def _network() -> LoopedFlowNetwork:
    return LoopedFlowNetwork(
        name="Two-path balancing mesh",
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


def test_throttling_one_path_redistributes_flow_without_changing_total() -> None:
    study = LoopDamperStudy(
        name="Direct throttling",
        loop_network=_network(),
        cases=(
            DamperResistanceCase(
                "Direct x4",
                {"Direct": 4.0},
            ),
        ),
    )

    result = solve_loop_damper_study(study)
    baseline = {
        edge["name"]: edge["airflow_m3_h"]
        for edge in result["baseline_solution"]["edges"]
    }
    case = {
        edge["name"]: edge["airflow_m3_h"]
        for edge in result["cases"][0]["network_solution"]["edges"]
    }

    assert baseline["Direct"] == pytest.approx(1800.0, abs=1e-5)
    assert baseline["Upper 1"] == pytest.approx(1800.0, abs=1e-5)
    assert baseline["Upper 2"] == pytest.approx(1800.0, abs=1e-5)

    assert case["Direct"] == pytest.approx(1200.0, abs=1e-4)
    assert case["Upper 1"] == pytest.approx(2400.0, abs=1e-4)
    assert case["Upper 2"] == pytest.approx(2400.0, abs=1e-4)
    assert result["cases"][0]["network_solution"][
        "max_abs_mass_balance_residual_m3_h"
    ] <= 1e-6


def test_unity_multiplier_preserves_baseline_solution() -> None:
    result = solve_loop_damper_study(
        LoopDamperStudy(
            name="Unity case",
            loop_network=_network(),
            cases=(
                DamperResistanceCase("No change", {"Direct": 1.0}),
            ),
        )
    )

    baseline = {
        edge["name"]: edge["airflow_m3_h"]
        for edge in result["baseline_solution"]["edges"]
    }
    case = {
        edge["name"]: edge["airflow_m3_h"]
        for edge in result["cases"][0]["network_solution"]["edges"]
    }
    assert case == baseline


@pytest.mark.parametrize(
    "bad",
    [0.0, 0.99, -1.0, float("nan"), float("inf")],
)
def test_invalid_resistance_multiplier_is_rejected(bad: float) -> None:
    with pytest.raises(ValueError, match=">= 1"):
        DamperResistanceCase("Bad", {"Direct": bad})


def test_unknown_edge_is_rejected_before_solving() -> None:
    with pytest.raises(ValueError, match="unknown edge"):
        LoopDamperStudy(
            name="Bad edge",
            loop_network=_network(),
            cases=(
                DamperResistanceCase("Bad", {"Missing": 2.0}),
            ),
        )


def test_adjusted_edge_preserves_base_geometry_provenance() -> None:
    network = LoopedFlowNetwork(
        name="Geometry provenance",
        node_injections_m3_h={
            "Supply": 1000.0,
            "Return": -1000.0,
        },
        edges=(
            QuadraticFlowEdge(
                "Geometry edge",
                "Supply",
                "Return",
                100.0,
                resistance_basis="duct_geometry",
                resistance_evidence={
                    "shape": "circular",
                    "area_m2": 0.2,
                },
            ),
        ),
        reference_node="Supply",
    )

    result = solve_loop_damper_study(
        LoopDamperStudy(
            name="Geometry throttle",
            loop_network=network,
            cases=(
                DamperResistanceCase(
                    "Throttle",
                    {"Geometry edge": 2.0},
                ),
            ),
        )
    )

    edge = result["cases"][0]["network_solution"]["edges"][0]
    assert edge["resistance_basis"] == "damper_adjusted"
    assert (
        edge["resistance_evidence"]["base_resistance_basis"]
        == "duct_geometry"
    )
    assert (
        edge["resistance_evidence"]["base_resistance_evidence"]["shape"]
        == "circular"
    )


def test_loader_and_markdown_report() -> None:
    study = loop_damper_study_from_dict(
        {
            "name": "Loaded damper study",
            "loop_network": {
                "name": "Loaded loop",
                "reference_node": "Supply",
                "node_injections_m3_h": {
                    "Supply": 3600.0,
                    "Mid": 0.0,
                    "Return": -3600.0,
                },
                "edges": [
                    {
                        "name": "Direct",
                        "start_node": "Supply",
                        "end_node": "Return",
                        "resistance_pa_per_m3_s_squared": 500.0,
                    },
                    {
                        "name": "Upper 1",
                        "start_node": "Supply",
                        "end_node": "Mid",
                        "resistance_pa_per_m3_s_squared": 250.0,
                    },
                    {
                        "name": "Upper 2",
                        "start_node": "Mid",
                        "end_node": "Return",
                        "resistance_pa_per_m3_s_squared": 250.0,
                    },
                ],
            },
            "cases": [
                {
                    "name": "Throttle direct",
                    "edge_resistance_multipliers": {
                        "Direct": 4.0,
                    },
                },
            ],
        }
    )

    result = solve_loop_damper_study(study)
    report = markdown_loop_damper_study_report(result)

    assert (
        result["cases"][0]["adjustments"][0]["resistance_multiplier"]
        == 4.0
    )
    assert "Loop Damper-Resistance Study" in report
    assert "Flow redistribution" in report
    assert "Throttle direct" in report
