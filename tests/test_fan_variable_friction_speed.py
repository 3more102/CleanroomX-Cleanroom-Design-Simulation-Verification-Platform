import json
import sys

import pytest

from cleanroomx.fan_curve import FanCurve, FanCurvePoint
from cleanroomx.fan_loop_speed import FanLoopSpeedStudy, analyze_fan_loop_speed_study
from cleanroomx.fan_variable_friction_speed import (
    FanVariableFrictionSpeedStudy,
    analyze_fan_variable_friction_speed_study,
)
from cleanroomx.fan_variable_friction_speed_cli import (
    main as fan_variable_friction_speed_main,
)
from cleanroomx.fan_variable_friction_speed_io import (
    fan_variable_friction_speed_study_from_dict,
    load_fan_variable_friction_speed_study,
)
from cleanroomx.fan_variable_friction_speed_report import (
    markdown_fan_variable_friction_speed_report,
)
from cleanroomx.loop_network import LoopedFlowNetwork, QuadraticFlowEdge


def _fixed_network() -> LoopedFlowNetwork:
    return LoopedFlowNetwork(
        name="Fixed two-path loop",
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


def _fixed_curve() -> FanCurve:
    return FanCurve(
        "Reference fan",
        (
            FanCurvePoint(0.0, 500.0),
            FanCurvePoint(3600.0, 125.0),
            FanCurvePoint(7200.0, 0.0),
        ),
    )


def test_fixed_resistance_speed_cases_match_existing_loop_speed_solver() -> None:
    ratios = (0.5, 0.75, 1.0)
    old = analyze_fan_loop_speed_study(
        FanLoopSpeedStudy(
            name="Fixed speed compatibility",
            reference_fan_curve=_fixed_curve(),
            loop_network=_fixed_network(),
            fan_discharge_node="Supply",
            fan_suction_node="Return",
            speed_ratios=ratios,
            reference_speed_rpm=1800.0,
        )
    )
    new = analyze_fan_variable_friction_speed_study(
        FanVariableFrictionSpeedStudy(
            name="Fixed speed compatibility",
            reference_fan_curve=_fixed_curve(),
            loop_network=_fixed_network(),
            fan_discharge_node="Supply",
            fan_suction_node="Return",
            speed_ratios=ratios,
            reference_speed_rpm=1800.0,
        )
    )

    assert new["status"] == old["status"] == "screening_complete"
    for old_case, new_case in zip(old["speed_cases"], new["speed_cases"]):
        assert new_case["status"] == old_case["status"] == "solved"
        assert new_case["fan_operating_point"]["airflow_m3_h"] == pytest.approx(
            old_case["fan_operating_point"]["airflow_m3_h"], abs=1e-6
        )
        assert new_case["fan_operating_point"]["system_pressure_pa"] == pytest.approx(
            old_case["fan_operating_point"]["system_pressure_pa"], abs=1e-6
        )
        assert new_case["solver_diagnostics"][
            "network_max_relative_resistance_closure_error"
        ] == 0.0


def test_variable_friction_speed_example_converges_with_residual_evidence() -> None:
    study = load_fan_variable_friction_speed_study(
        "examples/fan_variable_friction_speed_demo.json"
    )
    result = analyze_fan_variable_friction_speed_study(study)

    assert result["status"] == "screening_complete"
    assert result["counts"] == {"solved": 3}
    assert result["unresolved_speed_case_count"] == 0
    for case in result["speed_cases"]:
        point = case["fan_operating_point"]
        network = case["operating_network_solution"]
        diagnostics = case["solver_diagnostics"]
        assert case["status"] == "solved"
        assert case["scaled_fan_curve_airflow_range_m3_h"][1] == pytest.approx(
            9000.0 * case["speed_ratio"], abs=1e-6
        )
        assert abs(point["pressure_residual_pa"]) <= 1e-6
        assert network["max_abs_mass_balance_residual_m3_h"] <= 1e-6
        assert diagnostics[
            "network_max_relative_resistance_closure_error"
        ] <= 1e-6
        assert network["variable_friction"]["automatic_friction_edge_count"] == 3
        assert case["power_evidence"]["shaft_power_kw"] is not None
        assert case["power_evidence"]["electrical_input_kw"] is not None
        assert abs(
            case["power_evidence"]["system_components"][
                "fan_to_fixed_plus_edge_loss_residual_w"
            ]
        ) <= 1e-6


def test_high_fixed_pressure_produces_bounded_unresolved_cases() -> None:
    base = load_fan_variable_friction_speed_study(
        "examples/fan_variable_friction_speed_demo.json"
    )
    result = analyze_fan_variable_friction_speed_study(
        FanVariableFrictionSpeedStudy(
            name="No bounded intersections",
            reference_fan_curve=base.reference_fan_curve,
            loop_network=base.loop_network,
            fan_discharge_node=base.fan_discharge_node,
            fan_suction_node=base.fan_suction_node,
            speed_ratios=(0.5, 1.0),
            fixed_pressure_pa=900.0,
        )
    )

    assert result["status"] == "attention_required"
    assert result["counts"] == {"no_intersection_in_supplied_range": 2}
    assert result["unresolved_speed_case_count"] == 2
    assert all(
        case["fan_operating_point"] is None
        and case["solver_diagnostics"]["converged"] is True
        for case in result["speed_cases"]
    )


def test_network_nonconvergence_is_preserved_per_speed_case() -> None:
    data = json.loads(
        open(
            "examples/fan_variable_friction_speed_demo.json",
            encoding="utf-8",
        ).read()
    )
    data["speed_ratios"] = [1.0]
    data["solver"]["max_outer_iterations"] = 1
    data["solver"]["resistance_relative_tolerance"] = 1e-12
    result = analyze_fan_variable_friction_speed_study(
        fan_variable_friction_speed_study_from_dict(data)
    )

    assert result["status"] == "attention_required"
    assert result["counts"] == {"non_converged": 1}
    case = result["speed_cases"][0]
    assert case["fan_operating_point"] is None
    assert case["solver_diagnostics"]["converged"] is False
    assert case["solver_diagnostics"]["termination_reason"] == (
        "network_solver_non_convergence"
    )


def test_invalid_speed_and_unknown_solver_option_are_rejected() -> None:
    data = json.loads(
        open(
            "examples/fan_variable_friction_speed_demo.json",
            encoding="utf-8",
        ).read()
    )
    data["speed_ratios"] = [1.0, float("nan")]
    with pytest.raises(ValueError, match="speed ratio"):
        fan_variable_friction_speed_study_from_dict(data)

    data = json.loads(
        open(
            "examples/fan_variable_friction_speed_demo.json",
            encoding="utf-8",
        ).read()
    )
    data["solver"]["invented_control"] = 1
    with pytest.raises(ValueError, match="unsupported"):
        fan_variable_friction_speed_study_from_dict(data)


def test_markdown_report_surfaces_each_case_and_diagnostics() -> None:
    result = analyze_fan_variable_friction_speed_study(
        load_fan_variable_friction_speed_study(
            "examples/fan_variable_friction_speed_demo.json"
        )
    )
    report = markdown_fan_variable_friction_speed_report(result)

    assert "Fan-Speed / Variable-Friction Loop Study" in report
    assert "Speed sweep" in report
    assert "Resistance closure" in report
    assert "Variable-friction fan-speed loop sweep" in report
    assert "Fluid air power kW" in report
    assert "Electrical input kW" in report


def test_cli_json_example_succeeds(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cleanroomx-fan-loop-friction-speed",
            "examples/fan_variable_friction_speed_demo.json",
            "--format",
            "json",
        ],
    )
    assert fan_variable_friction_speed_main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "screening_complete"
    assert payload["counts"] == {"solved": 3}
