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
    _bisection_decision_trace_audit,
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
    assert trace_audit["raw_state_check_count"] == len(trace)
    assert trace_audit[
        "all_numeric_brackets_preserve_strict_sign_change"
    ] is True
    assert trace_audit[
        "all_recorded_sign_flags_match_numeric_residuals"
    ] is True
    assert trace_audit[
        "all_numeric_midpoints_are_arithmetic_bracket_midpoints"
    ] is True
    assert trace_audit[
        "all_recorded_midpoint_flags_match_numeric_geometry"
    ] is True
    assert trace_audit["all_trace_raw_state_consistent"] is True
    assert trace_audit[
        "maximum_absolute_trace_midpoint_error_m3_h"
    ] <= 1e-9
    assert trace_audit["all_recorded_widths_match_airflow_brackets"] is True
    assert trace_audit[
        "all_recorded_width_fractions_match_iteration_sequence"
    ] is True
    assert trace_audit["all_trace_geometry_consistent"] is True
    assert trace_audit["geometry_check_count"] == len(trace)
    assert trace_audit["raw_state_check_count"] == len(trace)
    assert trace_audit["all_trace_raw_state_consistent"] is True
    assert trace_audit[
        "all_numeric_brackets_preserve_strict_sign_change"
    ] is True
    assert trace_audit[
        "all_numeric_midpoints_are_arithmetic_bracket_midpoints"
    ] is True
    assert trace_audit["maximum_absolute_trace_midpoint_error_m3_h"] <= 1e-9
    assert trace_audit["maximum_absolute_trace_width_error_m3_h"] <= 2e-9
    assert trace_audit["maximum_absolute_trace_width_fraction_error"] <= 1e-12
    assert trace_audit["termination_record_count"] == 1
    assert trace_audit["termination_record_is_last"] is True
    assert trace_audit["terminal_outcome_consistent"] is True
    assert trace_audit["iteration_limit_terminal_replay"] is None
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
    assert trace_audit["all_decisions_match_midpoint_residual_semantics"] is True
    assert trace_audit["decision_semantic_violation_iterations"] == []
    assert trace_audit["trace_origin_to_terminal_replay_consistent"] is True
    origin_replay = trace_audit["trace_origin_replay"]
    assert origin_replay is not None
    assert origin_replay["initial_bracket_matches_first_trace_step"] is True
    assert origin_replay["all_trace_steps_match_origin_replay"] is True
    assert origin_replay["terminal_bracket_matches_origin_replay"] is True
    assert evidence["initial_bisection_bracket"] is not None
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
    assert (
        "Trace decisions match midpoint residual/tolerance semantics: **True**"
        in report
    )
    assert "Complete trace raw-state audit consistent: **True**" in report
    assert "Maximum absolute trace midpoint-centering error" in report
    assert "Trace origin-to-terminal replay anchored to supplied segment: **True**" in report
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

    trace = evidence["bisection_trace"]
    trace_audit = evidence["bisection_trace_audit"]
    assert trace is not None
    assert trace_audit is not None
    assert len(trace) == diagnostics["operating_iterations"] == 1
    assert trace[0]["decision"] in {
        "replace_low_endpoint",
        "replace_high_endpoint",
    }
    assert trace_audit["trace_matches_operating_iterations"] is True
    assert trace_audit["iterations_are_contiguous_from_one"] is True
    assert trace_audit["termination_record_count"] == 0
    assert trace_audit["termination_record_is_last"] is False
    assert trace_audit["all_recorded_widths_match_airflow_brackets"] is True
    assert trace_audit[
        "all_recorded_width_fractions_match_iteration_sequence"
    ] is True
    assert trace_audit["all_trace_geometry_consistent"] is True
    assert trace_audit["geometry_check_count"] == len(trace)
    assert trace_audit["maximum_absolute_trace_width_error_m3_h"] <= 2e-9
    assert trace_audit["maximum_absolute_trace_width_fraction_error"] <= 1e-12
    assert trace_audit["terminal_outcome_consistent"] is True
    assert trace_audit[
        "all_state_transitions_replay_recorded_decisions"
    ] is True
    assert trace_audit["all_decisions_match_midpoint_residual_semantics"] is True
    assert trace_audit["decision_semantic_violation_iterations"] == []
    assert trace_audit["trace_origin_to_terminal_replay_consistent"] is True
    origin_replay = trace_audit["trace_origin_replay"]
    assert origin_replay is not None
    assert origin_replay["initial_bracket_matches_first_trace_step"] is True
    assert origin_replay["all_trace_steps_match_origin_replay"] is True
    assert origin_replay["terminal_bracket_matches_origin_replay"] is True
    assert evidence["initial_bisection_bracket"] is not None
    terminal_replay = trace_audit["iteration_limit_terminal_replay"]
    assert terminal_replay is not None
    assert terminal_replay[
        "terminal_airflow_bracket_matches_decision"
    ] is True
    assert terminal_replay[
        "terminal_residual_bracket_matches_decision"
    ] is True
    assert terminal_replay[
        "terminal_bracket_replays_recorded_decision"
    ] is True
    assert "T" not in trace_audit["decision_sequence"]

    report = markdown_fan_variable_friction_loop_report(result)
    assert "Accepted operating point: **none (iteration limit)**" in report
    assert "Remaining active bisection bracket" in report
    assert "Remaining bracket strict sign change preserved" in report
    assert "Remaining-bracket binary-width consistency error" in report
    assert "Bisection decision-trace steps" in report
    assert "Trace terminal solver outcome consistent: **True**" in report
    assert (
        "Trace decisions match midpoint residual/tolerance semantics: **True**"
        in report
    )
    assert "Complete trace raw-state audit consistent: **True**" in report
    assert "Complete trace pressure-state audit consistent: **True**" in report
    assert "Maximum absolute trace system-pressure balance error" in report
    assert "Maximum absolute trace residual balance error" in report
    assert "Trace origin-to-terminal replay anchored to supplied segment: **True**" in report
    assert (
        "Iteration-limit remaining bracket replays final L/H decision: **True**"
        in report
    )
    assert "Every recorded trace width matches its airflow endpoints: **True**" in report
    assert (
        "Every recorded trace width fraction matches binary iteration contraction: **True**"
        in report
    )


def test_bisection_trace_geometry_audit_detects_corrupted_fields() -> None:
    trace = [
        {
            "iteration": 1,
            "low_airflow_m3_h": 0.0,
            "high_airflow_m3_h": 8.0,
            "midpoint_airflow_m3_h": 4.0,
            "width_m3_h": 8.0,
            "width_fraction_of_supplied_segment": 1.0,
            "low_fan_minus_system_pressure_pa": 4.0,
            "high_fan_minus_system_pressure_pa": -4.0,
            "midpoint_fan_minus_system_pressure_pa": 1.0,
            "decision": "replace_low_endpoint",
            "strict_sign_change_before_evaluation": True,
            "midpoint_is_arithmetic_bracket_midpoint": True,
        },
        {
            "iteration": 2,
            "low_airflow_m3_h": 4.0,
            "high_airflow_m3_h": 8.0,
            "midpoint_airflow_m3_h": 6.0,
            "width_m3_h": 4.0,
            "width_fraction_of_supplied_segment": 0.5,
            "low_fan_minus_system_pressure_pa": 1.0,
            "high_fan_minus_system_pressure_pa": -4.0,
            "midpoint_fan_minus_system_pressure_pa": 0.0,
            "decision": "accept_pressure_tolerance",
            "strict_sign_change_before_evaluation": True,
            "midpoint_is_arithmetic_bracket_midpoint": True,
        },
    ]

    initial_bracket = {
        "low_airflow_m3_h": 0.0,
        "high_airflow_m3_h": 8.0,
        "low_fan_minus_system_pressure_pa": 4.0,
        "high_fan_minus_system_pressure_pa": -4.0,
    }
    solved_terminal_bracket = {
        "low_airflow_m3_h": 4.0,
        "high_airflow_m3_h": 8.0,
        "low_fan_minus_system_pressure_pa": 1.0,
        "high_fan_minus_system_pressure_pa": -4.0,
    }
    clean = _bisection_decision_trace_audit(
        trace,
        operating_iterations=2,
        termination_reason="pressure_residual",
        operating_pressure_tolerance_pa=0.1,
        initial_bisection_bracket=initial_bracket,
        solved_terminal_bracket=solved_terminal_bracket,
    )
    assert clean is not None
    assert clean["all_trace_geometry_consistent"] is True
    assert clean["all_state_transitions_replay_recorded_decisions"] is True
    assert clean["all_decisions_match_midpoint_residual_semantics"] is True
    assert clean["decision_semantic_violation_iterations"] == []
    assert clean["trace_origin_to_terminal_replay_consistent"] is True
    assert clean["all_numeric_brackets_preserve_strict_sign_change"] is True
    assert clean["all_recorded_sign_flags_match_numeric_residuals"] is True
    assert clean[
        "all_numeric_midpoints_are_arithmetic_bracket_midpoints"
    ] is True
    assert clean[
        "all_recorded_midpoint_flags_match_numeric_geometry"
    ] is True
    assert clean["all_trace_raw_state_consistent"] is True
    assert clean["maximum_absolute_trace_midpoint_error_m3_h"] == pytest.approx(
        0.0,
        abs=1e-18,
    )
    assert clean["maximum_absolute_trace_width_error_m3_h"] == pytest.approx(
        0.0,
        abs=1e-18,
    )
    assert clean[
        "maximum_absolute_trace_width_fraction_error"
    ] == pytest.approx(0.0, abs=1e-18)

    corrupted = [dict(step) for step in trace]
    corrupted[0]["width_m3_h"] = 7.0
    corrupted[1]["width_fraction_of_supplied_segment"] = 0.75
    audit = _bisection_decision_trace_audit(
        corrupted,
        operating_iterations=2,
        termination_reason="pressure_residual",
        operating_pressure_tolerance_pa=0.1,
        initial_bisection_bracket=initial_bracket,
        solved_terminal_bracket=solved_terminal_bracket,
    )
    assert audit is not None
    assert audit["trace_origin_to_terminal_replay_consistent"] is True
    assert audit["all_recorded_widths_match_airflow_brackets"] is False
    assert audit[
        "all_recorded_width_fractions_match_iteration_sequence"
    ] is False
    assert audit["all_trace_geometry_consistent"] is False
    assert audit["maximum_absolute_trace_width_error_m3_h"] == pytest.approx(
        1.0,
        abs=1e-18,
    )
    assert audit[
        "maximum_absolute_trace_width_fraction_error"
    ] == pytest.approx(0.25, abs=1e-18)
    assert audit["all_decisions_match_midpoint_residual_semantics"] is True

    flag_corrupted = [dict(step) for step in trace]
    flag_corrupted[0]["strict_sign_change_before_evaluation"] = False
    flag_corrupted[1]["midpoint_is_arithmetic_bracket_midpoint"] = False
    flag_audit = _bisection_decision_trace_audit(
        flag_corrupted,
        operating_iterations=2,
        termination_reason="pressure_residual",
        operating_pressure_tolerance_pa=0.1,
        initial_bisection_bracket=initial_bracket,
        solved_terminal_bracket=solved_terminal_bracket,
    )
    assert flag_audit is not None
    assert flag_audit[
        "all_numeric_brackets_preserve_strict_sign_change"
    ] is True
    assert flag_audit[
        "all_recorded_sign_flags_match_numeric_residuals"
    ] is False
    assert flag_audit[
        "all_numeric_midpoints_are_arithmetic_bracket_midpoints"
    ] is True
    assert flag_audit[
        "all_recorded_midpoint_flags_match_numeric_geometry"
    ] is False
    assert flag_audit["all_trace_raw_state_consistent"] is False
    assert flag_audit["all_decisions_match_midpoint_residual_semantics"] is True

    self_consistent_wrong_midpoint = [dict(step) for step in trace]
    self_consistent_wrong_midpoint[0]["midpoint_airflow_m3_h"] = 3.5
    self_consistent_wrong_midpoint[1]["low_airflow_m3_h"] = 3.5
    self_consistent_wrong_midpoint[1]["midpoint_airflow_m3_h"] = 5.75
    self_consistent_wrong_midpoint[1]["width_m3_h"] = 4.5
    self_consistent_terminal = dict(solved_terminal_bracket)
    self_consistent_terminal["low_airflow_m3_h"] = 3.5
    midpoint_audit = _bisection_decision_trace_audit(
        self_consistent_wrong_midpoint,
        operating_iterations=2,
        termination_reason="pressure_residual",
        operating_pressure_tolerance_pa=0.1,
        initial_bisection_bracket=initial_bracket,
        solved_terminal_bracket=self_consistent_terminal,
    )
    assert midpoint_audit is not None
    assert midpoint_audit[
        "all_state_transitions_replay_recorded_decisions"
    ] is True
    assert midpoint_audit["trace_origin_to_terminal_replay_consistent"] is True
    assert midpoint_audit["all_decisions_match_midpoint_residual_semantics"] is True
    assert midpoint_audit["all_trace_geometry_consistent"] is True
    assert midpoint_audit[
        "all_numeric_midpoints_are_arithmetic_bracket_midpoints"
    ] is False
    assert midpoint_audit[
        "all_recorded_midpoint_flags_match_numeric_geometry"
    ] is False
    assert midpoint_audit[
        "maximum_absolute_trace_midpoint_error_m3_h"
    ] == pytest.approx(0.5, abs=1e-18)
    assert midpoint_audit["all_trace_raw_state_consistent"] is False

    wrong_decision = [dict(step) for step in trace]
    wrong_decision[0]["decision"] = "replace_high_endpoint"
    decision_audit = _bisection_decision_trace_audit(
        wrong_decision,
        operating_iterations=2,
        termination_reason="pressure_residual",
        operating_pressure_tolerance_pa=0.1,
        initial_bisection_bracket=initial_bracket,
        solved_terminal_bracket=solved_terminal_bracket,
    )
    assert decision_audit is not None
    assert decision_audit[
        "all_decisions_match_midpoint_residual_semantics"
    ] is False
    assert decision_audit["decision_semantic_violation_iterations"] == [1]

    wrong_origin = dict(initial_bracket)
    wrong_origin["low_airflow_m3_h"] = 1.0
    origin_audit = _bisection_decision_trace_audit(
        trace,
        operating_iterations=2,
        termination_reason="pressure_residual",
        operating_pressure_tolerance_pa=0.1,
        initial_bisection_bracket=wrong_origin,
        solved_terminal_bracket=solved_terminal_bracket,
    )
    assert origin_audit is not None
    assert origin_audit["all_trace_geometry_consistent"] is True
    assert origin_audit[
        "all_state_transitions_replay_recorded_decisions"
    ] is True
    assert origin_audit["trace_origin_replay"][
        "initial_bracket_matches_first_trace_step"
    ] is False
    assert origin_audit["trace_origin_replay"][
        "terminal_bracket_matches_origin_replay"
    ] is True
    assert origin_audit["trace_origin_to_terminal_replay_consistent"] is False


def test_bisection_trace_pressure_state_audit_detects_corruption() -> None:
    study = load_fan_variable_friction_loop_study(
        "examples/fan_variable_friction_loop_demo.json"
    )
    result = solve_fan_variable_friction_loop(study)
    evidence = result["operating_point_search_evidence"]
    trace = evidence["bisection_trace"]
    clean = evidence["bisection_trace_audit"]

    assert result["status"] == "solved"
    assert evidence["method"] == "bounded_bisection"
    assert trace is not None
    assert clean is not None
    assert clean["pressure_state_check_count"] == len(trace)
    assert clean["pressure_state_evidence_complete"] is True
    assert clean["all_recorded_fixed_pressure_values_match_study"] is True
    assert clean[
        "all_recorded_system_pressures_match_fixed_plus_loop"
    ] is True
    assert clean["all_recorded_residuals_match_fan_minus_system"] is True
    assert clean["all_trace_pressure_state_consistent"] is True
    assert clean[
        "maximum_absolute_trace_system_pressure_balance_error_pa"
    ] <= 2e-9
    assert clean[
        "maximum_absolute_trace_residual_balance_error_pa"
    ] <= 2e-9

    for step in trace:
        assert step["midpoint_system_pressure_pa"] == pytest.approx(
            step["midpoint_fixed_pressure_pa"]
            + step["midpoint_loop_network_pressure_pa"],
            abs=2e-9,
        )
        assert step["midpoint_fan_minus_system_pressure_pa"] == pytest.approx(
            step["midpoint_fan_pressure_pa"]
            - step["midpoint_system_pressure_pa"],
            abs=2e-9,
        )

    corrupted = [dict(step) for step in trace]
    corrupted[0]["midpoint_system_pressure_pa"] += 0.5
    audit = _bisection_decision_trace_audit(
        corrupted,
        operating_iterations=evidence["operating_iterations"],
        termination_reason="pressure_residual",
        operating_pressure_tolerance_pa=study.operating_pressure_tolerance_pa,
        expected_fixed_pressure_pa=study.fixed_pressure_pa,
        initial_bisection_bracket=evidence["initial_bisection_bracket"],
        solved_terminal_bracket=evidence["final_bisection_bracket"],
    )
    assert audit is not None
    assert audit["pressure_state_evidence_complete"] is True
    assert audit[
        "all_recorded_system_pressures_match_fixed_plus_loop"
    ] is False
    assert audit["all_recorded_residuals_match_fan_minus_system"] is False
    assert audit["all_trace_pressure_state_consistent"] is False
    assert audit[
        "maximum_absolute_trace_system_pressure_balance_error_pa"
    ] == pytest.approx(0.5, abs=2e-9)
    assert audit[
        "maximum_absolute_trace_residual_balance_error_pa"
    ] == pytest.approx(0.5, abs=2e-9)

    fixed_corrupted = [dict(step) for step in trace]
    fixed_corrupted[0]["midpoint_fixed_pressure_pa"] += 1.0
    fixed_corrupted[0]["midpoint_loop_network_pressure_pa"] -= 1.0
    fixed_audit = _bisection_decision_trace_audit(
        fixed_corrupted,
        operating_iterations=evidence["operating_iterations"],
        termination_reason="pressure_residual",
        operating_pressure_tolerance_pa=study.operating_pressure_tolerance_pa,
        expected_fixed_pressure_pa=study.fixed_pressure_pa,
        initial_bisection_bracket=evidence["initial_bisection_bracket"],
        solved_terminal_bracket=evidence["final_bisection_bracket"],
    )
    assert fixed_audit is not None
    assert fixed_audit[
        "all_recorded_system_pressures_match_fixed_plus_loop"
    ] is True
    assert fixed_audit["all_recorded_residuals_match_fan_minus_system"] is True
    assert fixed_audit[
        "all_recorded_fixed_pressure_values_match_study"
    ] is False
    assert fixed_audit["all_trace_pressure_state_consistent"] is False


def test_independent_residual_replay_detects_self_consistent_pressure_corruption() -> None:
    study = FanVariableFrictionLoopStudy(
        name="Independent residual replay",
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
    result = solve_fan_variable_friction_loop(study)

    assert result["status"] == "solved"
    evidence = result["operating_point_search_evidence"]
    trace = evidence["bisection_trace"]
    audit = evidence["bisection_trace_audit"]
    assert trace is not None
    assert audit is not None
    assert audit["pressure_state_evidence_complete"] is True
    assert audit["all_trace_pressure_state_consistent"] is True
    assert audit["residual_replay_available"] is True
    assert audit["residual_replay_check_count"] == len(trace)
    assert audit[
        "all_recorded_low_residuals_match_independent_replay"
    ] is True
    assert audit[
        "all_recorded_high_residuals_match_independent_replay"
    ] is True
    assert audit[
        "all_recorded_midpoint_residuals_match_independent_replay"
    ] is True
    assert audit["all_trace_residuals_match_independent_replay"] is True
    assert audit[
        "maximum_absolute_trace_residual_replay_error_pa"
    ] <= 1e-9
    assert audit["pressure_component_replay_evidence_complete"] is True
    assert audit["pressure_component_replay_check_count"] == len(trace)
    assert audit[
        "all_midpoint_pressure_components_match_independent_replay"
    ] is True
    assert audit[
        "maximum_absolute_trace_pressure_component_replay_error_pa"
    ] <= 1e-9

    corrupted = [dict(step) for step in trace]
    terminal = corrupted[-1]
    assert terminal["decision"] == "accept_pressure_tolerance"
    tolerance = study.operating_pressure_tolerance_pa
    original_residual = float(
        terminal["midpoint_fan_minus_system_pressure_pa"]
    )
    replacement_residual = (
        -0.9 * tolerance if original_residual >= 0.0 else 0.9 * tolerance
    )
    residual_delta = replacement_residual - original_residual
    terminal["midpoint_fan_minus_system_pressure_pa"] = replacement_residual
    terminal["midpoint_fan_pressure_pa"] = (
        float(terminal["midpoint_fan_pressure_pa"]) + residual_delta
    )

    segment_index = evidence["supplied_segment_index"]
    corrupted_audit = _bisection_decision_trace_audit(
        corrupted,
        operating_iterations=evidence["operating_iterations"],
        termination_reason="pressure_residual",
        operating_pressure_tolerance_pa=tolerance,
        expected_fixed_pressure_pa=study.fixed_pressure_pa,
        study=study,
        segment_left=study.fan_curve.points[segment_index],
        segment_right=study.fan_curve.points[segment_index + 1],
        initial_bisection_bracket=evidence["initial_bisection_bracket"],
        solved_terminal_bracket=evidence["final_bisection_bracket"],
    )
    assert corrupted_audit is not None
    assert corrupted_audit["all_trace_raw_state_consistent"] is True
    assert corrupted_audit["all_trace_pressure_state_consistent"] is True
    assert corrupted_audit[
        "all_decisions_match_midpoint_residual_semantics"
    ] is True
    assert corrupted_audit[
        "trace_origin_to_terminal_replay_consistent"
    ] is True
    assert corrupted_audit[
        "all_trace_residuals_match_independent_replay"
    ] is False
    assert corrupted_audit[
        "maximum_absolute_trace_residual_replay_error_pa"
    ] > 1e-9
    assert corrupted_audit["residual_replay_checks"][-1][
        "midpoint_residual_matches_independent_replay"
    ] is False

    limit_study = FanVariableFrictionLoopStudy(
        name="Independent residual replay iteration limit",
        fan_curve=study.fan_curve,
        loop_network=_fixed_network(),
        fan_discharge_node="Supply",
        fan_suction_node="Return",
        operating_pressure_tolerance_pa=1e-15,
        max_operating_iterations=1,
    )
    limited = solve_fan_variable_friction_loop(limit_study)
    assert limited["status"] == "non_converged"
    limit_evidence = limited["operating_point_search_evidence"]
    assert limit_evidence is not None
    limit_trace = limit_evidence["bisection_trace"]
    limit_audit = limit_evidence["bisection_trace_audit"]
    assert limit_trace is not None
    assert limit_audit is not None
    assert limit_audit["all_trace_pressure_state_consistent"] is True
    assert limit_audit["residual_replay_available"] is True
    assert limit_audit["residual_replay_check_count"] == len(limit_trace)
    assert limit_audit[
        "all_trace_residuals_match_independent_replay"
    ] is True
    assert limit_audit[
        "maximum_absolute_trace_residual_replay_error_pa"
    ] <= 1e-9
    assert limit_audit[
        "pressure_component_replay_evidence_complete"
    ] is True
    assert limit_audit[
        "all_midpoint_pressure_components_match_independent_replay"
    ] is True
    assert limit_audit[
        "maximum_absolute_trace_pressure_component_replay_error_pa"
    ] <= 1e-9

    report = markdown_fan_variable_friction_loop_report(result)
    assert "Independent fan/system residual replay available: **True**" in report
    assert (
        "Every retained trace residual matches independent fan/system replay: "
        "**True**"
        in report
    )
    assert "Maximum absolute trace residual-replay error" in report
    assert (
        "Every retained midpoint pressure component matches independent replay: "
        "**True**"
        in report
    )
    assert "Maximum absolute trace pressure-component replay error" in report


def test_independent_pressure_component_replay_detects_common_mode_corruption() -> None:
    study = FanVariableFrictionLoopStudy(
        name="Pressure component replay corruption",
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
    result = solve_fan_variable_friction_loop(study)
    assert result["status"] == "solved"
    evidence = result["operating_point_search_evidence"]
    trace = [dict(step) for step in evidence["bisection_trace"]]
    assert trace

    corrupted_step = trace[0]
    common_mode_delta_pa = 1.0
    corrupted_step["midpoint_fan_pressure_pa"] = (
        float(corrupted_step["midpoint_fan_pressure_pa"])
        + common_mode_delta_pa
    )
    corrupted_step["midpoint_loop_network_pressure_pa"] = (
        float(corrupted_step["midpoint_loop_network_pressure_pa"])
        + common_mode_delta_pa
    )
    corrupted_step["midpoint_system_pressure_pa"] = (
        float(corrupted_step["midpoint_system_pressure_pa"])
        + common_mode_delta_pa
    )

    segment_index = evidence["supplied_segment_index"]
    audit = _bisection_decision_trace_audit(
        trace,
        operating_iterations=evidence["operating_iterations"],
        termination_reason="pressure_residual",
        operating_pressure_tolerance_pa=study.operating_pressure_tolerance_pa,
        expected_fixed_pressure_pa=study.fixed_pressure_pa,
        study=study,
        segment_left=study.fan_curve.points[segment_index],
        segment_right=study.fan_curve.points[segment_index + 1],
        initial_bisection_bracket=evidence["initial_bisection_bracket"],
        solved_terminal_bracket=evidence["final_bisection_bracket"],
    )
    assert audit is not None
    assert audit["all_trace_raw_state_consistent"] is True
    assert audit["all_trace_pressure_state_consistent"] is True
    assert audit["all_trace_residuals_match_independent_replay"] is True
    assert audit["all_decisions_match_midpoint_residual_semantics"] is True
    assert audit["trace_origin_to_terminal_replay_consistent"] is True
    assert audit["pressure_component_replay_evidence_complete"] is True
    assert audit[
        "all_midpoint_pressure_components_match_independent_replay"
    ] is False
    assert audit[
        "maximum_absolute_trace_pressure_component_replay_error_pa"
    ] == pytest.approx(common_mode_delta_pa, abs=1e-9)
    component_check = audit["pressure_component_replay_checks"][0]
    assert component_check[
        "fan_pressure_matches_independent_replay"
    ] is False
    assert component_check[
        "loop_pressure_matches_independent_replay"
    ] is False
    assert component_check[
        "system_pressure_matches_independent_replay"
    ] is False


def test_independent_residual_replay_detects_self_consistent_corruption() -> None:
    study = FanVariableFrictionLoopStudy(
        name="Residual replay corruption",
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
    result = solve_fan_variable_friction_loop(study)
    assert result["status"] == "solved"
    evidence = result["operating_point_search_evidence"]
    trace = [dict(step) for step in evidence["bisection_trace"]]
    assert len(trace) >= 2
    assert trace[0]["decision"] in {
        "replace_low_endpoint",
        "replace_high_endpoint",
    }

    original_midpoint_residual = float(
        trace[0]["midpoint_fan_minus_system_pressure_pa"]
    )
    assert abs(original_midpoint_residual) > study.operating_pressure_tolerance_pa
    corrupted_midpoint_residual = original_midpoint_residual + (
        1.0 if original_midpoint_residual > 0.0 else -1.0
    )
    trace[0]["midpoint_fan_minus_system_pressure_pa"] = (
        corrupted_midpoint_residual
    )

    terminal_bracket = dict(evidence["final_bisection_bracket"])
    if trace[0]["decision"] == "replace_low_endpoint":
        active = True
        for step in trace[1:]:
            if active:
                step["low_fan_minus_system_pressure_pa"] = (
                    corrupted_midpoint_residual
                )
            if step["decision"] == "replace_low_endpoint":
                active = False
        if active:
            terminal_bracket["low_fan_minus_system_pressure_pa"] = (
                corrupted_midpoint_residual
            )
    else:
        active = True
        for step in trace[1:]:
            if active:
                step["high_fan_minus_system_pressure_pa"] = (
                    corrupted_midpoint_residual
                )
            if step["decision"] == "replace_high_endpoint":
                active = False
        if active:
            terminal_bracket["high_fan_minus_system_pressure_pa"] = (
                corrupted_midpoint_residual
            )

    segment_index = evidence["supplied_segment_index"]
    audit = _bisection_decision_trace_audit(
        trace,
        operating_iterations=evidence["operating_iterations"],
        termination_reason="pressure_residual",
        operating_pressure_tolerance_pa=study.operating_pressure_tolerance_pa,
        initial_bisection_bracket=evidence["initial_bisection_bracket"],
        solved_terminal_bracket=terminal_bracket,
        study=study,
        segment_left=study.fan_curve.points[segment_index],
        segment_right=study.fan_curve.points[segment_index + 1],
    )
    assert audit is not None
    assert audit["all_trace_raw_state_consistent"] is True
    assert audit["all_decisions_match_midpoint_residual_semantics"] is True
    assert audit["all_state_transitions_replay_recorded_decisions"] is True
    assert audit["trace_origin_to_terminal_replay_consistent"] is True
    assert audit["residual_replay_available"] is True
    assert audit["all_trace_residuals_match_independent_replay"] is False
    assert audit["maximum_absolute_trace_residual_replay_error_pa"] > 0.0
    assert any(
        not check["all_residuals_match_independent_replay"]
        for check in audit["residual_replay_checks"]
    )


def test_full_bracket_component_replay_detects_endpoint_corruption() -> None:
    study = FanVariableFrictionLoopStudy(
        name="Full bracket pressure-component replay corruption",
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
    result = solve_fan_variable_friction_loop(study)
    assert result["status"] == "solved"
    evidence = result["operating_point_search_evidence"]
    trace = [dict(step) for step in evidence["bisection_trace"]]
    assert trace
    audit = evidence["bisection_trace_audit"]
    assert audit["all_low_pressure_components_match_independent_replay"] is True
    assert audit["all_high_pressure_components_match_independent_replay"] is True
    assert audit[
        "all_trace_pressure_components_match_independent_replay"
    ] is True
    assert audit["pressure_component_replay_violation_count"] == 0
    assert audit["pressure_component_replay_violation_iterations"] == []
    assert audit["pressure_component_replay_violation_positions"] == []
    assert audit["pressure_component_replay_violation_components"] == []
    assert audit["pressure_component_replay_violations"] == []
    assert isinstance(
        audit["maximum_trace_pressure_component_replay_error_witnesses"],
        list,
    )

    corrupted = [dict(step) for step in trace]
    delta_pa = 1.0
    corrupted[0]["low_fan_pressure_pa"] = (
        float(corrupted[0]["low_fan_pressure_pa"]) + delta_pa
    )
    corrupted[0]["low_loop_network_pressure_pa"] = (
        float(corrupted[0]["low_loop_network_pressure_pa"]) + delta_pa
    )
    corrupted[0]["low_system_pressure_pa"] = (
        float(corrupted[0]["low_system_pressure_pa"]) + delta_pa
    )

    segment_index = evidence["supplied_segment_index"]
    corrupted_audit = _bisection_decision_trace_audit(
        corrupted,
        operating_iterations=evidence["operating_iterations"],
        termination_reason="pressure_residual",
        operating_pressure_tolerance_pa=study.operating_pressure_tolerance_pa,
        expected_fixed_pressure_pa=study.fixed_pressure_pa,
        study=study,
        segment_left=study.fan_curve.points[segment_index],
        segment_right=study.fan_curve.points[segment_index + 1],
        initial_bisection_bracket=evidence["initial_bisection_bracket"],
        solved_terminal_bracket=evidence["final_bisection_bracket"],
    )
    assert corrupted_audit is not None
    assert corrupted_audit["all_trace_raw_state_consistent"] is True
    assert corrupted_audit["all_trace_pressure_state_consistent"] is True
    assert corrupted_audit[
        "all_trace_residuals_match_independent_replay"
    ] is True
    assert corrupted_audit[
        "all_midpoint_pressure_components_match_independent_replay"
    ] is True
    assert corrupted_audit[
        "all_low_pressure_components_match_independent_replay"
    ] is False
    assert corrupted_audit[
        "all_high_pressure_components_match_independent_replay"
    ] is True
    assert corrupted_audit[
        "all_trace_pressure_components_match_independent_replay"
    ] is False
    assert corrupted_audit[
        "maximum_absolute_trace_pressure_component_replay_error_pa"
    ] == pytest.approx(delta_pa, abs=1e-9)
    assert corrupted_audit["pressure_component_replay_violation_count"] == 3
    assert corrupted_audit["pressure_component_replay_violation_iterations"] == [1]
    assert corrupted_audit["pressure_component_replay_violation_positions"] == [
        "low"
    ]
    assert corrupted_audit["pressure_component_replay_violation_components"] == [
        "fan",
        "loop_network",
        "system",
    ]
    violations = corrupted_audit["pressure_component_replay_violations"]
    assert [(item["position"], item["component"]) for item in violations] == [
        ("low", "fan"),
        ("low", "loop_network"),
        ("low", "system"),
    ]
    assert all(item["iteration"] == 1 for item in violations)
    witnesses = corrupted_audit[
        "maximum_trace_pressure_component_replay_error_witnesses"
    ]
    assert witnesses
    assert all(item["position"] == "low" for item in witnesses)
    assert all(
        item["absolute_error_pa"] == pytest.approx(delta_pa, abs=1e-9)
        for item in witnesses
    )
    first_check = corrupted_audit["pressure_component_replay_checks"][0]
    assert first_check[
        "all_low_pressure_components_match_independent_replay"
    ] is False
    assert first_check[
        "all_pressure_components_match_independent_replay"
    ] is True
    assert first_check["low"][
        "fan_pressure_matches_independent_replay"
    ] is False


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
        assert "supplied-point index-interval gap" in report
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
    assert selected["selected_candidate_feature"][
        "supplied_point_index_interval_low"
    ] == 0
    assert selected["selected_candidate_feature"][
        "supplied_point_index_interval_high"
    ] == 1
    assert alternatives[0]["supplied_point_index_interval_low"] == 2
    assert alternatives[0]["supplied_point_index_interval_high"] == 3
    assert alternatives[0][
        "selected_feature_to_candidate_feature_index_interval_gap"
    ] == 1
    assert selected[
        "nearest_alternative_candidate_feature_index_interval_gap"
    ] == 1
    assert len(
        selected[
            "nearest_alternative_candidate_features_by_index_interval_gap"
        ]
    ) == 1
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

