import json
import sys

import pytest

from cleanroomx.fan_curve import FanCurve, FanCurvePoint
from cleanroomx.fan_loop_speed import FanLoopSpeedStudy, analyze_fan_loop_speed_study
from cleanroomx.fan_loop_speed_cli import main as fan_loop_speed_main
from cleanroomx.fan_loop_speed_io import fan_loop_speed_study_from_dict
from cleanroomx.fan_loop_speed_report import markdown_fan_loop_speed_report
from cleanroomx.loop_network import LoopedFlowNetwork, QuadraticFlowEdge


def _curve() -> FanCurve:
    return FanCurve(
        "Reference loop fan",
        (
            FanCurvePoint(0.0, 500.0),
            FanCurvePoint(3600.0, 125.0),
            FanCurvePoint(7200.0, 0.0),
        ),
    )


def _loop() -> LoopedFlowNetwork:
    return LoopedFlowNetwork(
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


def _study(**overrides) -> FanLoopSpeedStudy:
    values = {
        "name": "Loop speed sweep",
        "reference_fan_curve": _curve(),
        "loop_network": _loop(),
        "fan_discharge_node": "Supply",
        "fan_suction_node": "Return",
        "speed_ratios": (0.5, 0.75, 1.0),
        "fixed_pressure_pa": 0.0,
        "reference_speed_rpm": 1800.0,
    }
    values.update(overrides)
    return FanLoopSpeedStudy(**values)


def test_zero_fixed_pressure_homologous_speed_cases_scale_operating_flow() -> None:
    result = analyze_fan_loop_speed_study(_study())

    assert result["status"] == "screening_complete"
    assert result["counts"] == {"solved": 3}
    assert result["speed_case_count"] == 3

    for case, expected_airflow in zip(result["speed_cases"], (1800.0, 2700.0, 3600.0)):
        assert case["fan_operating_point"]["airflow_m3_h"] == pytest.approx(
            expected_airflow, abs=1e-3
        )
        assert case["operating_network_solution"][
            "max_abs_mass_balance_residual_m3_h"
        ] <= 1e-6
        assert abs(
            case["system_pressure_check"]["fan_minus_system_pressure_pa"]
        ) <= 1e-6
        assert abs(
            case["system_pressure_check"]["network_pressure_residual_pa"]
        ) <= 1e-6

    assert result["speed_cases"][0]["speed_rpm"] == pytest.approx(900.0)
    assert result["speed_cases"][0]["affinity_scaling"][
        "homologous_input_power_factor"
    ] == pytest.approx(0.125)


def test_low_speed_with_fixed_pressure_preserves_no_intersection_state() -> None:
    result = analyze_fan_loop_speed_study(
        _study(
            speed_ratios=(0.4, 1.0),
            fixed_pressure_pa=100.0,
        )
    )

    assert result["status"] == "attention_required"
    assert result["counts"]["no_intersection_in_supplied_range"] == 1
    low, full = result["speed_cases"]
    assert low["fan_operating_point"] is None
    assert low["operating_network_solution"] is None
    assert low["system_pressure_check"] is None
    assert full["status"] == "solved"


@pytest.mark.parametrize("bad", [0.0, -0.1, float("nan"), float("inf")])
def test_invalid_speed_ratio_is_rejected(bad: float) -> None:
    with pytest.raises(ValueError, match="finite and > 0"):
        _study(speed_ratios=(bad,))


def test_duplicate_speed_ratios_are_rejected() -> None:
    with pytest.raises(ValueError, match="unique"):
        _study(speed_ratios=(0.8, 0.8))


def test_two_terminal_validation_is_reused() -> None:
    network = LoopedFlowNetwork(
        name="Unsupported injected loop",
        node_injections_m3_h={
            "Supply": 3600.0,
            "Process": 100.0,
            "Relief": -100.0,
            "Return": -3600.0,
        },
        edges=(
            QuadraticFlowEdge("SP", "Supply", "Process", 100.0),
            QuadraticFlowEdge("PR", "Process", "Return", 100.0),
            QuadraticFlowEdge("SR", "Supply", "Return", 200.0),
            QuadraticFlowEdge("RL", "Relief", "Return", 150.0),
            QuadraticFlowEdge("PL", "Process", "Relief", 150.0),
        ),
        reference_node="Supply",
    )
    with pytest.raises(ValueError, match="zero injection"):
        _study(loop_network=network)


def test_loader_and_markdown_report() -> None:
    study = fan_loop_speed_study_from_dict(
        json.loads(open("examples/fan_loop_speed_demo.json", encoding="utf-8").read())
    )
    result = analyze_fan_loop_speed_study(study)
    report = markdown_fan_loop_speed_report(result)

    assert study.reference_speed_rpm == 1800.0
    assert result["status"] == "screening_complete"
    assert "Fan-Speed / Loop-Network Study" in report
    assert "Fan-system residual" in report
    assert "0.5" in report


def test_cli_json_example_succeeds(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cleanroomx-fan-loop-speed",
            "examples/fan_loop_speed_demo.json",
            "--format",
            "json",
        ],
    )
    assert fan_loop_speed_main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "screening_complete"
    assert payload["speed_case_count"] == 3
