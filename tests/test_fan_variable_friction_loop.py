import json
import sys

import pytest

from cleanroomx.fan_curve import FanCurve, FanCurvePoint
from cleanroomx.fan_loop_network import (
    FanLoopNetworkStudy,
    solve_fan_loop_network,
)
from cleanroomx.fan_variable_friction_loop import (
    FanVariableFrictionLoopStudy,
    _fan_curve_supplied_point_residual_audit,
    _with_selected_crossing_feature,
    solve_fan_variable_friction_loop,
)
from cleanroomx.fan_variable_friction_loop_cli import (
    main as fan_variable_loop_main,
)
from cleanroomx.fan_variable_friction_loop_io import (
    fan_variable_friction_loop_study_from_dict,
    load_fan_variable_friction_loop_study,
)
from cleanroomx.fan_variable_friction_loop_report import (
    markdown_fan_variable_friction_loop_report,
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


def test_fixed_resistance_case_matches_existing_fan_loop_solver() -> None:
    network = _fixed_network()
    curve = _fixed_curve()
    old = solve_fan_loop_network(
        FanLoopNetworkStudy(
            name="Fixed compatibility",
            fan_curve=curve,
            loop_network=network,
            fan_discharge_node="Supply",
            fan_suction_node="Return",
        )
    )
    new = solve_fan_variable_friction_loop(
        FanVariableFrictionLoopStudy(
            name="Fixed compatibility",
            fan_curve=curve,
            loop_network=network,
            fan_discharge_node="Supply",
            fan_suction_node="Return",
        )
    )

    assert new["status"] == "solved"
    assert new["fan_operating_point"]["airflow_m3_h"] == pytest.approx(
        old["fan_operating_point"]["airflow_m3_h"], abs=1e-6
    )
    assert new["fan_operating_point"]["system_pressure_pa"] == pytest.approx(
        old["fan_operating_point"]["system_pressure_pa"], abs=1e-6
    )
    assert new["operating_network_solution"]["variable_friction"][
        "automatic_friction_edge_count"
    ] == 0
    assert new["power_evidence"]["shaft_power_kw"] is None
    assert new["power_evidence"]["electrical_input_kw"] is None


def test_automatic_friction_example_converges_at_bounded_operating_point() -> None:
    study = load_fan_variable_friction_loop_study(
        "examples/fan_variable_friction_loop_demo.json"
    )
    result = solve_fan_variable_friction_loop(study)

    assert result["status"] == "solved"
    point = result["fan_operating_point"]
    network = result["operating_network_solution"]
    diagnostics = result["solver_diagnostics"]

    assert 0.0 < point["airflow_m3_h"] < 9000.0
    assert abs(point["pressure_residual_pa"]) <= 1e-6
    assert abs(
        result["system_pressure_check"]["fan_minus_system_pressure_pa"]
    ) <= 1e-6
    assert network["max_abs_mass_balance_residual_m3_h"] <= 1e-6
    assert diagnostics["network_max_relative_resistance_closure_error"] <= 1e-6
    assert network["variable_friction"]["automatic_friction_edge_count"] == 3
    power = result["power_evidence"]
    assert power["shaft_power_kw"] is not None
    assert power["electrical_input_kw"] is not None
    assert power["specific_fan_power_w_per_m3_s"] is not None
    components = power["system_components"]
    assert abs(components["loop_network_energy_balance_residual_w"]) <= 1e-6
    assert abs(components["fan_to_fixed_plus_edge_loss_residual_w"]) <= 1e-5
    assert all(
        row["state"] == "automatic_friction"
        for row in network["variable_friction"]["edge_closure"]
    )


def test_bounded_bisection_search_evidence_is_explicit() -> None:
    result = solve_fan_variable_friction_loop(
        FanVariableFrictionLoopStudy(
            name="Bisection evidence",
            fan_curve=FanCurve(
                "Bisection curve",
                (
                    FanCurvePoint(0.0, 500.0),
                    FanCurvePoint(3600.0, 200.0),
                    FanCurvePoint(7200.0, 0.0),
                ),
            ),
            loop_network=_fixed_network(),
            fan_discharge_node="Supply",
            fan_suction_node="Return",
        )
    )

    assert result["status"] == "solved"
    diagnostics = result["solver_diagnostics"]
    evidence = result["operating_point_search_evidence"]
    bracket = evidence["final_bisection_bracket"]
    point = result["fan_operating_point"]

    assert diagnostics["termination_reason"] == "pressure_residual"
    assert evidence["method"] == "bounded_bisection"
    assert evidence["selected_supplied_point_index"] is None
    assert bracket is not None
    assert bracket["iteration"] == diagnostics["operating_iterations"]
    assert bracket["low_fan_minus_system_pressure_pa"] > 0.0
    assert bracket["high_fan_minus_system_pressure_pa"] < 0.0
    assert abs(bracket["selected_fan_minus_system_pressure_pa"]) <= (
        diagnostics["operating_pressure_tolerance_pa"]
    )
    assert bracket["width_m3_h"] == pytest.approx(
        bracket["high_airflow_m3_h"] - bracket["low_airflow_m3_h"],
        abs=1e-9,
    )
    assert bracket["half_width_m3_h"] == pytest.approx(
        0.5 * bracket["width_m3_h"],
        abs=1e-9,
    )
    assert point["airflow_m3_h"] == pytest.approx(
        0.5
        * (
            bracket["low_airflow_m3_h"]
            + bracket["high_airflow_m3_h"]
        ),
        abs=1e-6,
    )
    supplied_span = (
        evidence["supplied_segment_high_airflow_m3_h"]
        - evidence["supplied_segment_low_airflow_m3_h"]
    )
    assert bracket["width_fraction_of_supplied_segment"] == pytest.approx(
        bracket["width_m3_h"] / supplied_span,
        abs=1e-12,
    )
    invariant = bracket["invariant_audit"]
    assert invariant["strict_sign_change_preserved"] is True
    assert invariant["selected_airflow_is_bracket_midpoint"] is True
    assert invariant["binary_contraction_step_count"] == (
        bracket["iteration"] - 1
    )
    expected_fraction = 0.5 ** (bracket["iteration"] - 1)
    assert invariant[
        "expected_width_fraction_of_supplied_segment"
    ] == pytest.approx(expected_fraction, abs=1e-15)
    assert invariant[
        "actual_width_fraction_of_supplied_segment"
    ] == pytest.approx(
        bracket["width_fraction_of_supplied_segment"],
        abs=1e-12,
    )
    assert invariant[
        "absolute_width_fraction_consistency_error"
    ] == pytest.approx(
        abs(
            bracket["width_fraction_of_supplied_segment"]
            - expected_fraction
        ),
        abs=1e-12,
    )

    trace = evidence["bisection_trace"]
    trace_audit = evidence["bisection_trace_audit"]
    assert trace is not None
    assert trace_audit is not None
    assert len(trace) == diagnostics["operating_iterations"]
    assert trace[-1]["decision"] == "accept_pressure_tolerance"
    assert trace[-1]["iteration"] == diagnostics["operating_iterations"]
    assert trace[-1]["midpoint_airflow_m3_h"] == pytest.approx(
        point["airflow_m3_h"],
        abs=1e-6,
    )
    for index, step in enumerate(trace, start=1):
        assert step["iteration"] == index
        assert step["strict_sign_change_before_evaluation"] is True
        assert step["midpoint_is_arithmetic_bracket_midpoint"] is True
        assert step["width_fraction_of_supplied_segment"] == pytest.approx(
            0.5 ** (index - 1),
            abs=1e-12,
        )
    assert trace_audit["step_count"] == len(trace)
    assert trace_audit["trace_matches_operating_iterations"] is True
    assert trace_audit[
        "all_steps_preserve_strict_sign_change_before_evaluation"
    ] is True
    assert trace_audit[
        "all_midpoints_are_arithmetic_bracket_midpoints"
    ] is True
    assert trace_audit["termination_record_count"] == 1
    assert trace_audit["termination_record_is_last"] is True
    assert trace_audit["iterations_are_contiguous_from_one"] is True
    assert trace_audit["transition_record_count"] == len(trace) - 1
    assert trace_audit[
        "all_airflow_bracket_transitions_replay_recorded_decisions"
    ] is True
    assert trace_audit[
        "all_residual_bracket_transitions_replay_recorded_decisions"
    ] is True
    assert trace_audit[
        "all_state_transitions_replay_recorded_decisions"
    ] is True
    assert all(
        check["state_transition_replays_recorded_decision"]
        for check in trace_audit["transition_checks"]
    )
    assert trace_audit["decision_sequence"].endswith("T")
    assert len(trace_audit["decision_sequence"]) == len(trace)

    report = markdown_fan_variable_friction_loop_report(result)
    assert "Operating-point search evidence" in report
    assert "Final bisection bracket width" in report
    assert "Strict sign-change bracket preserved" in report
    assert "Absolute binary-width consistency error" in report
    assert "Bisection decision-trace steps" in report
    assert "Bisection decision sequence (L/H/T)" in report
    assert "numerical search" in report


def test_iteration_limit_retains_terminal_bisection_evidence() -> None:
    result = solve_fan_variable_friction_loop(
        FanVariableFrictionLoopStudy(
            name="Iteration-limit evidence",
            fan_curve=FanCurve(
                "Bisection curve",
                (
                    FanCurvePoint(0.0, 500.0),
                    FanCurvePoint(3600.0, 200.0),
                    FanCurvePoint(7200.0, 0.0),
                ),
            ),
            loop_network=_fixed_network(),
            fan_discharge_node="Supply",
            fan_suction_node="Return",
            operating_pressure_tolerance_pa=1e-15,
            max_operating_iterations=1,
        )
    )

    assert result["status"] == "non_converged"
    diagnostics = result["solver_diagnostics"]
    assert diagnostics["termination_reason"] == "bisection_iteration_limit"
    assert diagnostics["operating_iterations"] == 1
    assert result["fan_operating_point"] is None

    evidence = result["operating_point_search_evidence"]
    assert evidence is not None
    assert evidence["method"] == "bounded_bisection"
    assert evidence["final_bisection_bracket"] is None
    limit = evidence["iteration_limit_evidence"]
    assert limit is not None
    assert limit["pressure_tolerance_satisfied"] is False

    remaining = limit["remaining_bisection_bracket"]
    assert remaining["low_fan_minus_system_pressure_pa"] > 0.0
    assert remaining["high_fan_minus_system_pressure_pa"] < 0.0
    assert remaining["width_m3_h"] == pytest.approx(
        remaining["high_airflow_m3_h"] - remaining["low_airflow_m3_h"],
        abs=1e-9,
    )
    assert remaining["half_width_m3_h"] == pytest.approx(
        0.5 * remaining["width_m3_h"],
        abs=1e-9,
    )
    invariant = remaining["invariant_audit"]
    assert invariant["strict_sign_change_preserved"] is True
    assert invariant["binary_contraction_step_count"] == 1
    assert invariant[
        "expected_width_fraction_of_supplied_segment"
    ] == pytest.approx(0.5, abs=1e-15)
    assert invariant[
        "actual_width_fraction_of_supplied_segment"
    ] == pytest.approx(0.5, abs=1e-12)
    assert invariant[
        "absolute_width_fraction_consistency_error"
    ] == pytest.approx(0.0, abs=1e-18)

    report = markdown_fan_variable_friction_loop_report(result)
    assert "Accepted operating point: **none (iteration limit)**" in report
    assert "Remaining active bisection bracket" in report
    assert "Remaining bracket strict sign change preserved" in report
    assert "Remaining-bracket binary-width consistency error" in report


def test_supplied_point_contact_does_not_fabricate_bisection_bracket() -> None:
    result = solve_fan_variable_friction_loop(
        FanVariableFrictionLoopStudy(
            name="Point contact evidence",
            fan_curve=_fixed_curve(),
            loop_network=_fixed_network(),
            fan_discharge_node="Supply",
            fan_suction_node="Return",
        )
    )

    assert result["status"] == "solved"
    assert result["solver_diagnostics"]["termination_reason"] == (
        "fan_curve_point_residual"
    )
    evidence = result["operating_point_search_evidence"]
    assert evidence["method"] == "supplied_point_tolerance_contact"
    assert evidence["selected_supplied_point_index"] == 1
    assert evidence["operating_iterations"] == 0
    assert evidence["final_bisection_bracket"] is None
    assert evidence["bisection_trace"] is None
    assert evidence["bisection_trace_audit"] is None


def test_high_fixed_pressure_preserves_no_extrapolation_state() -> None:
    study = load_fan_variable_friction_loop_study(
        "examples/fan_variable_friction_loop_demo.json"
    )
    result = solve_fan_variable_friction_loop(
        FanVariableFrictionLoopStudy(
            name=study.name,
            fan_curve=study.fan_curve,
            loop_network=study.loop_network,
            fan_discharge_node=study.fan_discharge_node,
            fan_suction_node=study.fan_suction_node,
            fixed_pressure_pa=2000.0,
        )
    )

    assert result["status"] == "no_intersection_in_supplied_range"
    assert result["fan_operating_point"] is None
    assert result["operating_network_solution"] is None
    assert result["system_pressure_check"] is None
    assert result["power_evidence"] is None
    assert result["solver_diagnostics"]["termination_reason"] == (
        "no_intersection_in_supplied_range"
    )
    audit = result["fan_curve_supplied_point_residual_audit"]
    assert audit["complete_supplied_point_coverage"] is True
    assert audit["candidate_crossing_feature_count"] == 0
    assert audit["residual_monotonic_non_increasing_with_tolerance"] is True


def test_network_nonconvergence_is_reported_without_fake_operating_point() -> None:
    data = json.loads(
        open(
            "examples/fan_variable_friction_loop_demo.json",
            encoding="utf-8",
        ).read()
    )
    data["solver"]["max_outer_iterations"] = 1
    data["solver"]["resistance_relative_tolerance"] = 1e-12
    result = solve_fan_variable_friction_loop(
        fan_variable_friction_loop_study_from_dict(data)
    )

    assert result["status"] == "non_converged"
    assert result["fan_operating_point"] is None
    assert result["operating_network_solution"] is None
    assert result["power_evidence"] is None
    assert result["solver_diagnostics"]["converged"] is False
    assert result["solver_diagnostics"]["termination_reason"] == (
        "network_solver_non_convergence"
    )
    audit = result["fan_curve_supplied_point_residual_audit"]
    assert audit["complete_supplied_point_coverage"] is False
    assert audit["evaluated_supplied_point_count"] < (
        audit["expected_supplied_point_count"]
    )


def test_unknown_solver_option_is_rejected() -> None:
    data = json.loads(
        open(
            "examples/fan_variable_friction_loop_demo.json",
            encoding="utf-8",
        ).read()
    )
    data["solver"]["invented_control"] = 1
    with pytest.raises(ValueError, match="unsupported"):
        fan_variable_friction_loop_study_from_dict(data)


def test_nonzero_internal_injection_is_rejected_by_two_terminal_validation() -> None:
    network = LoopedFlowNetwork(
        name="Unsupported multi-terminal loop",
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
        FanVariableFrictionLoopStudy(
            name="Unsupported",
            fan_curve=_fixed_curve(),
            loop_network=network,
            fan_discharge_node="Supply",
            fan_suction_node="Return",
        )


def test_markdown_report_surfaces_solver_and_friction_evidence() -> None:
    result = solve_fan_variable_friction_loop(
        load_fan_variable_friction_loop_study(
            "examples/fan_variable_friction_loop_demo.json"
        )
    )
    report = markdown_fan_variable_friction_loop_report(result)

    assert "Fan / Variable-Friction Loop Report" in report
    assert "Solver diagnostics" in report
    assert "Variable-friction edge closure" in report
    assert "Supplied fan-curve checks" in report
    assert "Loop edge pressure-power dissipation" in report
    assert "Electrical input" in report


def test_cli_json_example_succeeds(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cleanroomx-fan-loop-friction",
            "examples/fan_variable_friction_loop_demo.json",
            "--format",
            "json",
        ],
    )
    assert fan_variable_loop_main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "solved"
    assert payload["solver_diagnostics"]["converged"] is True

def test_supplied_point_residual_topology_audit_is_explicit() -> None:
    result = solve_fan_variable_friction_loop(
        load_fan_variable_friction_loop_study(
            "examples/fan_variable_friction_loop_demo.json"
        )
    )

    assert result["status"] == "solved"
    audit = result["fan_curve_supplied_point_residual_audit"]
    checks = result["fan_curve_point_checks"]
    tolerance = result["solver_diagnostics"][
        "operating_pressure_tolerance_pa"
    ]

    assert audit["complete_supplied_point_coverage"] is True
    assert audit["evaluated_supplied_point_count"] == len(checks)
    assert audit["expected_supplied_point_count"] == len(checks)
    assert audit["residual_transition_count"] == len(checks) - 1
    assert audit["residual_monotonic_non_increasing_with_tolerance"] is True
    assert audit["residual_increase_transition_count"] == 0

    expected_contacts = sum(
        abs(float(check["pressure_margin_pa"])) <= tolerance
        for check in checks
    )
    expected_brackets = sum(
        float(left["pressure_margin_pa"]) > 0.0
        and float(right["pressure_margin_pa"]) < 0.0
        for left, right in zip(checks, checks[1:])
    )
    assert audit["tolerance_contact_point_count"] == expected_contacts
    assert audit["strict_sign_change_segment_count"] == expected_brackets
    assert audit["candidate_crossing_feature_count"] == (
        expected_contacts + expected_brackets
    )
    assert audit["candidate_crossing_feature_count"] >= 1
    assert audit["minimum_supplied_point_airflow_spacing_m3_h"] > 0.0
    assert audit["maximum_supplied_point_airflow_spacing_m3_h"] >= audit[
        "minimum_supplied_point_airflow_spacing_m3_h"
    ]
    assert audit["supplied_point_airflow_spacing_ratio_max_to_min"] >= 1.0
    candidates = audit["candidate_crossing_features_in_solver_priority_order"]
    selected = audit["selected_candidate_feature"]
    assert selected is not None
    assert audit["selected_candidate_feature_rank"] == 0
    assert selected == candidates[0]
    assert audit["additional_candidate_feature_count"] == len(candidates) - 1
    assert audit["selected_candidate_is_only_discrete_feature"] is (
        len(candidates) == 1
    )
    if result["solver_diagnostics"]["termination_reason"] == (
        "fan_curve_point_residual"
    ):
        assert selected["feature_kind"] == "supplied_point_tolerance_contact"
    else:
        assert selected["feature_kind"] == "strict_sign_change_segment"

    report = markdown_fan_variable_friction_loop_report(result)
    assert "Supplied-point residual topology audit" in report
    assert "Candidate crossing features" in report
    assert "Reverse strict negative-to-positive supplied segments" in report
    assert "Selected discrete candidate" in report
    assert "Selection policy" in report
    if audit["additional_candidate_feature_count"]:
        assert "Nearest alternative candidate interval gap" in report
        assert "gap / supplied fan-curve span" in report
        assert "gap / minimum supplied-point spacing" in report
    assert "not a count or proof of continuous physical intersections" in report

def test_crossing_feature_selection_policy_is_deterministic_with_multiple_candidates() -> None:
    study = load_fan_variable_friction_loop_study(
        "examples/fan_variable_friction_loop_demo.json"
    )
    checks = [
        {
            "airflow_m3_h": 0.0,
            "pressure_margin_pa": 10.0,
        },
        {
            "airflow_m3_h": 1000.0,
            "pressure_margin_pa": -10.0,
        },
        {
            "airflow_m3_h": 2000.0,
            "pressure_margin_pa": 10.0,
        },
        {
            "airflow_m3_h": 3000.0,
            "pressure_margin_pa": -10.0,
        },
    ]
    audit = _fan_curve_supplied_point_residual_audit(study, checks)
    assert audit["strict_sign_change_segment_count"] == 2
    assert audit["reverse_strict_sign_change_segment_count"] == 1
    assert audit["all_strict_sign_change_segment_count"] == 3
    reverse = audit["reverse_strict_sign_change_segments"]
    assert len(reverse) == 1
    assert reverse[0]["low_point_index"] == 1
    assert reverse[0]["high_point_index"] == 2
    assert reverse[0]["low_fan_minus_system_pressure_pa"] == pytest.approx(-10.0)
    assert reverse[0]["high_fan_minus_system_pressure_pa"] == pytest.approx(10.0)
    assert audit["candidate_crossing_feature_count"] == 2

    selected = _with_selected_crossing_feature(
        audit,
        termination_reason="pressure_residual",
        selected_airflow_m3_h=500.0,
        selected_segment_index=0,
    )
    assert selected["selected_candidate_feature_rank"] == 0
    assert selected["selected_candidate_feature"]["feature_kind"] == (
        "strict_sign_change_segment"
    )
    assert selected["selected_candidate_feature"]["low_point_index"] == 0
    assert selected["additional_candidate_feature_count"] == 1
    assert selected["selected_candidate_is_only_discrete_feature"] is False
    alternatives = selected["alternative_candidate_features"]
    assert alternatives is not None
    assert len(alternatives) == 1
    assert alternatives[0]["feature_kind"] == "strict_sign_change_segment"
    assert alternatives[0]["low_point_index"] == 2
    assert alternatives[0]["high_point_index"] == 3
    assert alternatives[0]["airflow_interval_low_m3_h"] == pytest.approx(2000.0)
    assert alternatives[0]["airflow_interval_high_m3_h"] == pytest.approx(3000.0)
    assert alternatives[0][
        "selected_airflow_to_feature_interval_gap_m3_h"
    ] == pytest.approx(1500.0)
    supplied_span = selected["supplied_fan_curve_airflow_span_m3_h"]
    minimum_spacing = selected["minimum_supplied_point_airflow_spacing_m3_h"]
    assert supplied_span > 0.0
    assert minimum_spacing > 0.0
    assert alternatives[0][
        "selected_airflow_to_feature_interval_gap_fraction_of_supplied_curve_span"
    ] == pytest.approx(1500.0 / supplied_span)
    assert alternatives[0][
        "selected_airflow_to_feature_interval_gap_fraction_of_minimum_supplied_point_spacing"
    ] == pytest.approx(1500.0 / minimum_spacing)
    assert selected[
        "nearest_alternative_candidate_airflow_interval_gap_m3_h"
    ] == pytest.approx(1500.0)
    assert selected[
        "nearest_alternative_candidate_airflow_interval_gap_fraction_of_supplied_curve_span"
    ] == pytest.approx(1500.0 / supplied_span)
    assert selected[
        "nearest_alternative_candidate_airflow_interval_gap_fraction_of_minimum_supplied_point_spacing"
    ] == pytest.approx(1500.0 / minimum_spacing)
    assert len(selected["nearest_alternative_candidate_features"]) == 1
    assert (
        selected["selected_airflow_overlaps_alternative_candidate_interval"]
        is False
    )


def test_reverse_sign_change_is_audit_only_and_not_a_solver_candidate() -> None:
    study = load_fan_variable_friction_loop_study(
        "examples/fan_variable_friction_loop_demo.json"
    )
    checks = [
        {"airflow_m3_h": 0.0, "pressure_margin_pa": -10.0},
        {"airflow_m3_h": 1000.0, "pressure_margin_pa": 10.0},
    ]
    audit = _fan_curve_supplied_point_residual_audit(study, checks)

    assert audit["strict_sign_change_segment_count"] == 0
    assert audit["reverse_strict_sign_change_segment_count"] == 1
    assert audit["all_strict_sign_change_segment_count"] == 1
    assert audit["candidate_crossing_feature_count"] == 0
    assert audit["candidate_crossing_features_in_solver_priority_order"] == []
    reverse = audit["reverse_strict_sign_change_segments"][0]
    assert reverse["low_point_index"] == 0
    assert reverse["high_point_index"] == 1
    assert reverse["low_fan_minus_system_pressure_pa"] == pytest.approx(-10.0)
    assert reverse["high_fan_minus_system_pressure_pa"] == pytest.approx(10.0)

