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
    _fan_curve_supplied_point_network_state_replay_audit,
    _fan_curve_supplied_point_residual_audit,
    _network_state_sha256,
    _selected_operating_state_replay_audit,
    _solve_network_at_airflow,
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


def test_network_state_fingerprint_is_order_invariant_for_named_collections() -> None:
    network = {
        "network": "Fingerprint fixture",
        "status": "solved",
        "reference_node": "Supply",
        "iterations": 4,
        "mass_balance_tolerance_m3_h": 1e-6,
        "nodes": [
            {
                "name": "Supply",
                "relative_pressure_pa": 10.0,
                "specified_injection_m3_h": 100.0,
                "net_edge_outflow_m3_h": 100.0,
                "mass_balance_residual_m3_h": 0.0,
                "specified_pressure_power_w": 1.0,
            },
            {
                "name": "Return",
                "relative_pressure_pa": 0.0,
                "specified_injection_m3_h": -100.0,
                "net_edge_outflow_m3_h": -100.0,
                "mass_balance_residual_m3_h": 0.0,
                "specified_pressure_power_w": 0.0,
            },
        ],
        "edges": [
            {
                "name": "A",
                "start_node": "Supply",
                "end_node": "Return",
                "resistance_pa_per_m3_s_squared": 100.0,
                "airflow_m3_s": 0.02,
                "airflow_m3_h": 72.0,
                "flow_direction": "Supply -> Return",
                "pressure_difference_pa": 10.0,
                "constitutive_pressure_difference_pa": 10.0,
                "pressure_law_residual_pa": 0.0,
                "dissipated_pressure_power_w": 0.2,
            },
            {
                "name": "B",
                "start_node": "Supply",
                "end_node": "Return",
                "resistance_pa_per_m3_s_squared": 200.0,
                "airflow_m3_s": 0.01,
                "airflow_m3_h": 36.0,
                "flow_direction": "Supply -> Return",
                "pressure_difference_pa": 10.0,
                "constitutive_pressure_difference_pa": 10.0,
                "pressure_law_residual_pa": 0.0,
                "dissipated_pressure_power_w": 0.1,
            },
        ],
        "max_abs_mass_balance_residual_m3_h": 0.0,
        "max_abs_pressure_law_residual_pa": 0.0,
        "pressure_power": {
            "net_node_injection_power_w": 0.3,
            "total_edge_dissipation_w": 0.3,
            "balance_residual_w": 0.0,
        },
        "variable_friction": {
            "converged": True,
            "outer_iterations": 2,
            "resistance_relative_tolerance": 1e-6,
            "relaxation": 0.5,
            "near_zero_airflow_m3_h": 1e-6,
            "automatic_friction_edge_count": 2,
            "near_zero_frozen_edge_count": 0,
            "max_relative_resistance_closure_error": 1e-8,
            "iteration_history": [
                {
                    "outer_iteration": 1,
                    "max_relative_resistance_change": 0.25,
                    "max_abs_mass_balance_residual_m3_h": 1e-10,
                    "near_zero_frozen_edge_count": 0,
                },
                {
                    "outer_iteration": 2,
                    "max_relative_resistance_change": 1e-8,
                    "max_abs_mass_balance_residual_m3_h": 0.0,
                    "near_zero_frozen_edge_count": 0,
                },
            ],
            "edge_closure": [
                {"name": "A", "state": "automatic"},
                {"name": "B", "state": "automatic"},
            ],
        },
    }

    baseline = _network_state_sha256(network)
    reordered = json.loads(json.dumps(network))
    reordered["nodes"].reverse()
    reordered["edges"].reverse()
    reordered["variable_friction"]["edge_closure"].reverse()

    assert _network_state_sha256(reordered) == baseline

    signed_zero = json.loads(json.dumps(network))
    signed_zero["nodes"][0]["mass_balance_residual_m3_h"] = -0.0
    signed_zero["nodes"][1]["specified_pressure_power_w"] = -0.0
    signed_zero["edges"][0]["pressure_law_residual_pa"] = -0.0
    signed_zero["max_abs_mass_balance_residual_m3_h"] = -0.0
    signed_zero["max_abs_pressure_law_residual_pa"] = -0.0
    signed_zero["pressure_power"]["balance_residual_w"] = -0.0
    signed_zero["variable_friction"]["iteration_history"][1][
        "max_abs_mass_balance_residual_m3_h"
    ] = -0.0
    assert _network_state_sha256(signed_zero) == baseline

    reordered["edges"][0]["airflow_m3_h"] += 1.0
    assert _network_state_sha256(reordered) != baseline

    metadata_mutated = json.loads(json.dumps(network))
    metadata_mutated["iterations"] += 1
    assert _network_state_sha256(metadata_mutated) != baseline

    config_mutated = json.loads(json.dumps(network))
    config_mutated["variable_friction"]["relaxation"] = 0.4
    assert _network_state_sha256(config_mutated) != baseline

    history_mutated = json.loads(json.dumps(network))
    history_mutated["variable_friction"]["iteration_history"][0][
        "max_relative_resistance_change"
    ] += 1e-3
    assert _network_state_sha256(history_mutated) != baseline


def test_supplied_point_network_state_replay_is_complete_and_reported() -> None:
    study = load_fan_variable_friction_loop_study(
        "examples/fan_variable_friction_loop_demo.json"
    )
    result = solve_fan_variable_friction_loop(study)

    assert result["status"] == "solved"
    checks = result["fan_curve_point_checks"]
    replay = result["fan_curve_supplied_point_network_state_replay"]
    assert replay["available"] is True
    assert replay["algorithm"] == "sha256"
    assert replay["canonicalization"].endswith("compact-utf8-v3")
    assert replay["evaluated_supplied_point_count"] == len(checks)
    assert replay["expected_supplied_point_count"] == len(checks)
    assert replay["replay_check_count"] == len(checks)
    assert replay["complete_supplied_point_coverage"] is True
    assert replay["replay_evidence_complete"] is True
    assert replay[
        "all_evaluated_supplied_point_network_state_hashes_match_independent_replay"
    ] is True
    assert replay[
        "all_evaluated_supplied_point_network_state_projections_match_independent_replay"
    ] is True
    assert replay["complete_supplied_point_network_state_replay"] is True
    assert replay["matching_hash_count"] == len(checks)
    assert replay["matching_projection_count"] == len(checks)
    assert replay["hash_violation_point_indices"] == []
    assert replay["projection_violation_point_indices"] == []
    assert replay["violation_count"] == 0
    assert replay["violations"] == []
    for check in checks:
        assert len(check["network_state_sha256"]) == 64
        assert check["network_state_projection"]

    report = markdown_fan_variable_friction_loop_report(result)
    assert "Supplied-point network-state replay audit" in report
    assert (
        "All evaluated supplied-point network-state hashes match independent replay: "
        "**True**"
        in report
    )
    assert (
        "All evaluated supplied-point network-state projections match independent replay: "
        "**True**"
        in report
    )
    assert "Supplied-point hash replay violation points: **[]**" in report
    assert "Supplied-point projection replay violation points: **[]**" in report


def test_supplied_point_network_state_replay_detects_hash_corruption() -> None:
    study = load_fan_variable_friction_loop_study(
        "examples/fan_variable_friction_loop_demo.json"
    )
    result = solve_fan_variable_friction_loop(study)
    checks = json.loads(json.dumps(result["fan_curve_point_checks"]))
    assert len(checks) >= 2

    original_hash = checks[1]["network_state_sha256"]
    checks[1]["network_state_sha256"] = "0" * 64
    replay = _fan_curve_supplied_point_network_state_replay_audit(
        study,
        checks,
    )

    assert replay["complete_supplied_point_coverage"] is True
    assert replay[
        "all_evaluated_supplied_point_network_state_hashes_match_independent_replay"
    ] is False
    assert replay[
        "all_evaluated_supplied_point_network_state_projections_match_independent_replay"
    ] is True
    assert replay["complete_supplied_point_network_state_replay"] is False
    assert replay["hash_violation_point_indices"] == [1]
    assert replay["projection_violation_point_indices"] == []
    assert replay["violation_count"] == 1
    violation = replay["violations"][0]
    assert violation["point_index"] == 1
    assert violation["recorded_network_state_sha256"] == "0" * 64
    assert violation["recomputed_network_state_sha256"] == original_hash
    assert violation["network_state_hash_matches_independent_replay"] is False
    assert (
        violation["network_state_projection_matches_independent_replay"]
        is True
    )


def test_supplied_point_network_state_projection_replay_localizes_corruption() -> None:
    study = load_fan_variable_friction_loop_study(
        "examples/fan_variable_friction_loop_demo.json"
    )
    result = solve_fan_variable_friction_loop(study)
    checks = json.loads(json.dumps(result["fan_curve_point_checks"]))
    assert len(checks) >= 2

    original_hash = checks[1]["network_state_sha256"]
    checks[1]["network_state_projection"]["nodes"][0][
        "relative_pressure_pa"
    ] += 1.0
    replay = _fan_curve_supplied_point_network_state_replay_audit(
        study,
        checks,
    )

    assert replay[
        "all_evaluated_supplied_point_network_state_hashes_match_independent_replay"
    ] is True
    assert replay[
        "all_evaluated_supplied_point_network_state_projections_match_independent_replay"
    ] is False
    assert replay["hash_violation_point_indices"] == []
    assert replay["projection_violation_point_indices"] == [1]
    assert replay["violation_count"] == 1
    violation = replay["violations"][0]
    assert violation["point_index"] == 1
    assert violation["recorded_network_state_sha256"] == original_hash
    assert violation["network_state_hash_matches_independent_replay"] is True
    assert (
        violation["network_state_projection_matches_independent_replay"]
        is False
    )
    assert violation["network_state_projection_mismatch_paths"] == [
        "$.nodes[0].relative_pressure_pa"
    ]


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
    for position in ("low", "high"):
        assert f"{position}_fan_pressure_pa" in remaining
        assert f"{position}_loop_network_pressure_pa" in remaining
        assert f"{position}_system_pressure_pa" in remaining
        assert f"{position}_network_state_sha256" in remaining
        assert len(remaining[f"{position}_network_state_sha256"]) == 64
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
    assert trace_audit["terminal_pressure_component_replay_available"] is True
    assert trace_audit[
        "all_terminal_pressure_components_match_independent_replay"
    ] is True
    assert trace_audit["terminal_pressure_component_replay_violation_count"] == 0
    assert trace_audit["terminal_pressure_component_replay_violations"] == []
    assert trace_audit[
        "maximum_absolute_terminal_pressure_component_replay_error_pa"
    ] <= 1e-9
    terminal_component_replay = trace_audit[
        "terminal_pressure_component_replay"
    ]
    assert terminal_component_replay is not None
    assert terminal_component_replay["terminal_kind"] == (
        "iteration_limit_remaining_bracket"
    )
    assert trace_audit["terminal_network_state_replay_available"] is True
    assert trace_audit[
        "all_terminal_network_states_match_independent_replay"
    ] is True
    assert trace_audit["terminal_network_state_replay_violation_count"] == 0
    assert trace_audit[
        "terminal_network_state_replay_violation_positions"
    ] == []
    assert trace_audit["terminal_network_state_replay_violations"] == []
    terminal_network_replay = trace_audit["terminal_network_state_replay"]
    assert terminal_network_replay is not None
    assert terminal_network_replay["terminal_kind"] == (
        "iteration_limit_remaining_bracket"
    )
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
    assert (
        "Terminal bisection-bracket pressure components match independent replay: **True**"
        in report
    )
    assert "Terminal pressure-component replay violation count: **0**" in report
    assert "Maximum absolute terminal pressure-component replay error" in report
    assert "Exact terminal pressure-component replay violations: **[]**" in report
    assert "Terminal low/high network states match independent replay: **True**" in report
    assert "Terminal network-state replay violation count: **0**" in report
    assert "Terminal network-state replay violating bracket positions: **[]**" in report
    assert "Exact terminal network-state replay violations: **[]**" in report
    assert "Terminal network-state projection replay available: **True**" in report
    assert (
        "Terminal low/high network-state projections match independent replay: "
        "**True**"
    ) in report
    assert "Terminal network-state projection mismatch count: **0**" in report
    assert "Terminal network-state projection mismatch positions: **[]**" in report
    assert "Exact terminal network-state projection mismatches: **[]**" in report
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
    assert "Trace network-state projection replay available: **True**" in report
    assert (
        "Every retained low/midpoint/high network-state projection matches independent replay: "
        "**True**"
        in report
    )
    assert "Trace network-state projection mismatch records: **0**" in report


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
    assert audit["network_state_replay_available"] is True
    assert audit["network_state_replay_evidence_complete"] is True
    assert audit["network_state_replay_check_count"] == len(trace)
    assert audit[
        "all_low_network_states_match_independent_replay"
    ] is True
    assert audit[
        "all_midpoint_network_states_match_independent_replay"
    ] is True
    assert audit[
        "all_high_network_states_match_independent_replay"
    ] is True
    assert audit[
        "all_trace_network_states_match_independent_replay"
    ] is True
    assert audit["network_state_replay_violation_iterations"] == []
    assert audit["network_state_projection_replay_available"] is True
    assert audit["network_state_projection_replay_evidence_complete"] is True
    assert audit[
        "all_low_network_state_projections_match_independent_replay"
    ] is True
    assert audit[
        "all_midpoint_network_state_projections_match_independent_replay"
    ] is True
    assert audit[
        "all_high_network_state_projections_match_independent_replay"
    ] is True
    assert audit[
        "all_trace_network_state_projections_match_independent_replay"
    ] is True
    assert audit["network_state_projection_replay_violation_count"] == 0
    assert audit["network_state_projection_mismatch_count"] == 0
    assert audit["network_state_projection_replay_violation_iterations"] == []
    assert audit["network_state_projection_replay_violation_positions"] == []
    assert audit["network_state_projection_replay_violations"] == []
    assert audit["network_state_projection_maximum_numeric_errors"] == []
    assert all(
        step["low_network_state_projection"]
        and step["midpoint_network_state_projection"]
        and step["high_network_state_projection"]
        for step in trace
    )
    assert audit["terminal_pressure_component_replay_available"] is True
    assert audit[
        "all_terminal_pressure_components_match_independent_replay"
    ] is True
    assert audit["terminal_pressure_component_replay_violation_count"] == 0
    assert audit["terminal_pressure_component_replay_violations"] == []
    terminal_component_replay = audit["terminal_pressure_component_replay"]
    assert terminal_component_replay is not None
    assert terminal_component_replay["terminal_kind"] == "solved_final_bracket"
    assert audit["terminal_network_state_replay_available"] is True
    assert audit[
        "all_terminal_network_states_match_independent_replay"
    ] is True
    assert audit["terminal_network_state_replay_violation_count"] == 0
    assert audit["terminal_network_state_replay_violation_positions"] == []
    assert audit["terminal_network_state_replay_violations"] == []
    terminal_network_replay = audit["terminal_network_state_replay"]
    assert terminal_network_replay is not None
    assert terminal_network_replay["terminal_kind"] == "solved_final_bracket"

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


def test_terminal_bracket_component_replay_detects_iteration_limit_corruption() -> None:
    study = FanVariableFrictionLoopStudy(
        name="Terminal bracket pressure-component replay corruption",
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
    result = solve_fan_variable_friction_loop(study)
    assert result["status"] == "non_converged"
    evidence = result["operating_point_search_evidence"]
    assert evidence is not None
    trace = [dict(step) for step in evidence["bisection_trace"]]
    terminal = dict(
        evidence["iteration_limit_evidence"]["remaining_bisection_bracket"]
    )
    audit = evidence["bisection_trace_audit"]
    assert audit["all_trace_pressure_components_match_independent_replay"] is True
    assert audit["pressure_component_replay_violation_count"] == 0
    assert audit["terminal_pressure_component_replay_available"] is True
    assert audit[
        "all_terminal_pressure_components_match_independent_replay"
    ] is True
    assert audit["terminal_pressure_component_replay_violation_count"] == 0

    delta_pa = 1.0
    terminal["low_fan_pressure_pa"] = (
        float(terminal["low_fan_pressure_pa"]) + delta_pa
    )
    terminal["low_loop_network_pressure_pa"] = (
        float(terminal["low_loop_network_pressure_pa"]) + delta_pa
    )
    terminal["low_system_pressure_pa"] = (
        float(terminal["low_system_pressure_pa"]) + delta_pa
    )

    segment_index = evidence["supplied_segment_index"]
    corrupted_audit = _bisection_decision_trace_audit(
        trace,
        operating_iterations=evidence["operating_iterations"],
        termination_reason="bisection_iteration_limit",
        operating_pressure_tolerance_pa=study.operating_pressure_tolerance_pa,
        expected_fixed_pressure_pa=study.fixed_pressure_pa,
        study=study,
        segment_left=study.fan_curve.points[segment_index],
        segment_right=study.fan_curve.points[segment_index + 1],
        initial_bisection_bracket=evidence["initial_bisection_bracket"],
        iteration_limit_terminal_bracket=terminal,
    )
    assert corrupted_audit is not None
    assert corrupted_audit[
        "all_trace_pressure_components_match_independent_replay"
    ] is True
    assert corrupted_audit["pressure_component_replay_violation_count"] == 0
    assert corrupted_audit["terminal_pressure_component_replay_available"] is True
    assert corrupted_audit[
        "all_terminal_pressure_components_match_independent_replay"
    ] is False
    assert corrupted_audit[
        "terminal_pressure_component_replay_violation_count"
    ] == 3
    terminal_violations = corrupted_audit[
        "terminal_pressure_component_replay_violations"
    ]
    assert [(item["position"], item["component"]) for item in terminal_violations] == [
        ("low", "fan"),
        ("low", "loop_network"),
        ("low", "system"),
    ]
    assert all(item["iteration"] == 1 for item in terminal_violations)
    assert corrupted_audit[
        "maximum_absolute_terminal_pressure_component_replay_error_pa"
    ] == pytest.approx(delta_pa, abs=1e-9)
    terminal_witnesses = corrupted_audit[
        "maximum_terminal_pressure_component_replay_error_witnesses"
    ]
    assert terminal_witnesses
    assert all(item["position"] == "low" for item in terminal_witnesses)
    assert all(
        item["absolute_error_pa"] == pytest.approx(delta_pa, abs=1e-9)
        for item in terminal_witnesses
    )
    terminal_check = corrupted_audit["terminal_pressure_component_replay"]
    assert terminal_check is not None
    assert terminal_check["terminal_kind"] == (
        "iteration_limit_remaining_bracket"
    )
    assert terminal_check["low"][
        "all_pressure_components_match_independent_replay"
    ] is False
    assert terminal_check["high"][
        "all_pressure_components_match_independent_replay"
    ] is True


def test_terminal_network_state_replay_detects_iteration_limit_corruption() -> None:
    study = FanVariableFrictionLoopStudy(
        name="Terminal network-state replay corruption",
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
    result = solve_fan_variable_friction_loop(study)
    assert result["status"] == "non_converged"
    evidence = result["operating_point_search_evidence"]
    assert evidence is not None
    trace = [dict(step) for step in evidence["bisection_trace"]]
    terminal = dict(
        evidence["iteration_limit_evidence"]["remaining_bisection_bracket"]
    )
    audit = evidence["bisection_trace_audit"]
    assert audit["all_trace_network_states_match_independent_replay"] is True
    assert audit[
        "all_terminal_pressure_components_match_independent_replay"
    ] is True
    assert audit[
        "all_terminal_network_states_match_independent_replay"
    ] is True

    original_sha256 = terminal["low_network_state_sha256"]
    assert len(original_sha256) == 64
    terminal["low_network_state_sha256"] = "0" * 64

    segment_index = evidence["supplied_segment_index"]
    corrupted_audit = _bisection_decision_trace_audit(
        trace,
        operating_iterations=evidence["operating_iterations"],
        termination_reason="bisection_iteration_limit",
        operating_pressure_tolerance_pa=study.operating_pressure_tolerance_pa,
        expected_fixed_pressure_pa=study.fixed_pressure_pa,
        study=study,
        segment_left=study.fan_curve.points[segment_index],
        segment_right=study.fan_curve.points[segment_index + 1],
        initial_bisection_bracket=evidence["initial_bisection_bracket"],
        iteration_limit_terminal_bracket=terminal,
    )
    assert corrupted_audit is not None
    assert corrupted_audit[
        "all_trace_network_states_match_independent_replay"
    ] is True
    assert corrupted_audit[
        "all_terminal_pressure_components_match_independent_replay"
    ] is True
    assert corrupted_audit[
        "all_terminal_network_states_match_independent_replay"
    ] is False
    assert corrupted_audit[
        "terminal_network_state_replay_violation_count"
    ] == 1
    assert corrupted_audit[
        "terminal_network_state_replay_violation_positions"
    ] == ["low"]
    violations = corrupted_audit["terminal_network_state_replay_violations"]
    assert len(violations) == 1
    assert violations[0]["iteration"] == 1
    assert violations[0]["position"] == "low"
    assert violations[0]["recorded_network_state_sha256"] == "0" * 64
    assert violations[0]["recomputed_network_state_sha256"] == original_sha256
    terminal_replay = corrupted_audit["terminal_network_state_replay"]
    assert terminal_replay is not None
    assert terminal_replay["terminal_kind"] == (
        "iteration_limit_remaining_bracket"
    )
    assert terminal_replay["low"][
        "network_state_matches_independent_replay"
    ] is False
    assert terminal_replay["high"][
        "network_state_matches_independent_replay"
    ] is True


def test_terminal_network_state_projection_replay_localizes_internal_corruption() -> None:
    study = FanVariableFrictionLoopStudy(
        name="Terminal network-state projection corruption",
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
    result = solve_fan_variable_friction_loop(study)
    assert result["status"] == "non_converged"
    evidence = result["operating_point_search_evidence"]
    assert evidence is not None
    trace = [dict(step) for step in evidence["bisection_trace"]]
    terminal = dict(
        evidence["iteration_limit_evidence"]["remaining_bisection_bracket"]
    )
    audit = evidence["bisection_trace_audit"]
    assert audit["terminal_network_state_projection_replay_available"] is True
    assert audit[
        "all_terminal_network_state_projections_match_independent_replay"
    ] is True
    assert audit["terminal_network_state_projection_mismatch_count"] == 0

    recorded_hash = terminal["low_network_state_sha256"]
    projection = terminal["low_network_state_projection"]
    projection["nodes"][0]["relative_pressure_pa"] += 1.0

    segment_index = evidence["supplied_segment_index"]
    corrupted_audit = _bisection_decision_trace_audit(
        trace,
        operating_iterations=evidence["operating_iterations"],
        termination_reason="bisection_iteration_limit",
        operating_pressure_tolerance_pa=study.operating_pressure_tolerance_pa,
        expected_fixed_pressure_pa=study.fixed_pressure_pa,
        study=study,
        segment_left=study.fan_curve.points[segment_index],
        segment_right=study.fan_curve.points[segment_index + 1],
        initial_bisection_bracket=evidence["initial_bisection_bracket"],
        iteration_limit_terminal_bracket=terminal,
    )
    assert corrupted_audit is not None
    assert corrupted_audit[
        "all_terminal_network_states_match_independent_replay"
    ] is True
    assert terminal["low_network_state_sha256"] == recorded_hash
    assert corrupted_audit[
        "all_terminal_network_state_projections_match_independent_replay"
    ] is False
    assert corrupted_audit[
        "terminal_network_state_projection_mismatch_count"
    ] == 1
    assert corrupted_audit[
        "terminal_network_state_projection_mismatch_positions"
    ] == ["low"]
    mismatches = corrupted_audit[
        "terminal_network_state_projection_mismatches"
    ]
    assert len(mismatches) == 1
    mismatch = mismatches[0]
    assert mismatch["iteration"] == 1
    assert mismatch["position"] == "low"
    assert mismatch["mismatch_paths"] == [
        "$.nodes[0].relative_pressure_pa"
    ]
    assert len(mismatch["mismatches"]) == 1
    leaf = mismatch["mismatches"][0]
    assert leaf["path"] == "$.nodes[0].relative_pressure_pa"
    assert leaf["mismatch_kind"] == "value_mismatch"
    assert leaf["absolute_error"] == pytest.approx(1.0)
    assert leaf["numeric_error_field"] == "relative_pressure_pa"
    assert len(mismatch["maximum_numeric_errors"]) == 1
    assert mismatch["maximum_numeric_errors"][0]["field"] == (
        "relative_pressure_pa"
    )
    assert mismatch["maximum_numeric_errors"][0][
        "maximum_absolute_error"
    ] == pytest.approx(1.0)
    terminal_replay = corrupted_audit["terminal_network_state_replay"]
    assert terminal_replay is not None
    assert terminal_replay["low"][
        "network_state_projection_matches_independent_replay"
    ] is False
    assert terminal_replay["high"][
        "network_state_projection_matches_independent_replay"
    ] is True


def test_selected_operating_state_replay_detects_common_mode_corruption() -> None:
    study = FanVariableFrictionLoopStudy(
        name="Selected operating-state replay",
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
    assert evidence["method"] == "bounded_bisection"

    replay = evidence["selected_operating_state_replay"]
    assert replay["available"] is True
    assert replay["selection_source"] == "terminal_bisection_midpoint"
    assert replay["selected_airflow_matches_search_origin"] is True
    assert replay[
        "all_pressure_components_match_independent_replay"
    ] is True
    assert replay[
        "all_selected_operating_state_matches_independent_replay"
    ] is True
    assert replay["network_state_replay_available"] is True
    assert replay["network_state_replay_algorithm"] == "sha256"
    assert len(replay["recorded_network_state_sha256"]) == 64
    assert replay["recorded_network_state_sha256"] == (
        replay["recomputed_network_state_sha256"]
    )
    assert replay["network_state_matches_independent_replay"] is True
    assert replay["network_state_projection_replay_available"] is True
    assert replay[
        "network_state_projection_matches_independent_replay"
    ] is True
    assert replay["network_state_projection_mismatch_count"] == 0
    assert replay["network_state_projection_mismatch_paths"] == []
    assert replay["network_state_projection_mismatches"] == []
    assert replay["network_state_projection_maximum_numeric_errors"] == []
    assert replay["selected_network_state_projection_replay_consistent"] is True
    assert replay["recorded_network_state_projection"] == (
        replay["recomputed_network_state_projection"]
    )
    assert replay["violation_count"] == 0
    assert replay["violations"] == []
    assert replay["maximum_absolute_pressure_replay_error_pa"] <= 1e-9

    operating = result["fan_operating_point"]
    pressure = result["system_pressure_check"]
    segment_index = evidence["supplied_segment_index"]
    delta_pa = 1.0
    replayed_airflow = replay["selected_airflow_replay_input_m3_h"]
    replayed_network, _ = _solve_network_at_airflow(
        study,
        replayed_airflow,
    )
    corrupted = _selected_operating_state_replay_audit(
        study,
        selected_airflow_m3_h=replayed_airflow,
        recorded_fan_pressure_pa=pressure["fan_pressure_pa"] + delta_pa,
        recorded_loop_network_pressure_pa=(
            pressure["loop_network_pressure_pa"] + delta_pa
        ),
        recorded_system_pressure_pa=(
            pressure["total_system_pressure_pa"] + delta_pa
        ),
        recorded_residual_pa=pressure["fan_minus_system_pressure_pa"],
        recorded_network_state_sha256=_network_state_sha256(
            replayed_network
        ),
        segment_left=study.fan_curve.points[segment_index],
        segment_right=study.fan_curve.points[segment_index + 1],
        bisection_trace=evidence["bisection_trace"],
    )
    assert corrupted["selected_airflow_matches_search_origin"] is True
    assert corrupted[
        "all_pressure_components_match_independent_replay"
    ] is False
    assert corrupted[
        "all_selected_operating_state_matches_independent_replay"
    ] is False
    assert corrupted["violation_count"] == 3
    assert [
        item["component"] for item in corrupted["violations"]
    ] == ["fan", "loop_network", "system"]
    assert corrupted[
        "component_checks"
    ]["residual"]["matches_independent_replay"] is True
    assert corrupted["maximum_absolute_pressure_replay_error_pa"] == (
        pytest.approx(delta_pa, abs=1e-9)
    )


def test_selected_operating_state_replay_detects_internal_network_state_corruption() -> None:
    study = FanVariableFrictionLoopStudy(
        name="Selected network-state replay corruption",
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
    pressure = result["system_pressure_check"]
    replay = evidence["selected_operating_state_replay"]
    segment_index = evidence["supplied_segment_index"]

    corrupted = _selected_operating_state_replay_audit(
        study,
        selected_airflow_m3_h=replay["selected_airflow_replay_input_m3_h"],
        recorded_fan_pressure_pa=pressure["fan_pressure_pa"],
        recorded_loop_network_pressure_pa=pressure[
            "loop_network_pressure_pa"
        ],
        recorded_system_pressure_pa=pressure["total_system_pressure_pa"],
        recorded_residual_pa=pressure["fan_minus_system_pressure_pa"],
        recorded_network_state_sha256="0" * 64,
        segment_left=study.fan_curve.points[segment_index],
        segment_right=study.fan_curve.points[segment_index + 1],
        bisection_trace=evidence["bisection_trace"],
    )

    assert corrupted[
        "all_pressure_components_match_independent_replay"
    ] is True
    assert corrupted["network_state_matches_independent_replay"] is False
    assert corrupted[
        "all_selected_operating_state_matches_independent_replay"
    ] is False
    assert corrupted["violation_count"] == 1
    assert corrupted["violations"][0]["component"] == "network_state_sha256"
    assert corrupted["recorded_network_state_sha256"] == "0" * 64
    assert len(corrupted["recomputed_network_state_sha256"]) == 64


def test_selected_operating_state_projection_replay_localizes_corruption() -> None:
    study = FanVariableFrictionLoopStudy(
        name="Selected network-state projection replay corruption",
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
    replay = evidence["selected_operating_state_replay"]
    pressure = result["system_pressure_check"]
    segment_index = evidence["supplied_segment_index"]

    corrupted_projection = json.loads(
        json.dumps(replay["recorded_network_state_projection"])
    )
    corrupted_projection["nodes"][0]["relative_pressure_pa"] += 1.0

    corrupted = _selected_operating_state_replay_audit(
        study,
        selected_airflow_m3_h=replay["selected_airflow_replay_input_m3_h"],
        recorded_fan_pressure_pa=pressure["fan_pressure_pa"],
        recorded_loop_network_pressure_pa=pressure[
            "loop_network_pressure_pa"
        ],
        recorded_system_pressure_pa=pressure["total_system_pressure_pa"],
        recorded_residual_pa=pressure["fan_minus_system_pressure_pa"],
        recorded_network_state_sha256=replay[
            "recorded_network_state_sha256"
        ],
        recorded_network_state_projection=corrupted_projection,
        segment_left=study.fan_curve.points[segment_index],
        segment_right=study.fan_curve.points[segment_index + 1],
        bisection_trace=evidence["bisection_trace"],
    )

    assert corrupted["network_state_matches_independent_replay"] is True
    assert corrupted["network_state_projection_replay_available"] is True
    assert corrupted[
        "network_state_projection_matches_independent_replay"
    ] is False
    assert corrupted["network_state_projection_mismatch_count"] == 1
    assert corrupted["network_state_projection_mismatch_paths"] == [
        "$.nodes[0].relative_pressure_pa"
    ]
    assert corrupted[
        "all_selected_operating_state_matches_independent_replay"
    ] is False
    assert corrupted["violation_count"] == 1
    projection_violation = corrupted["violations"][0]
    assert projection_violation["component"] == "network_state_projection"
    assert projection_violation["mismatch_paths"] == [
        "$.nodes[0].relative_pressure_pa"
    ]
    mismatches = projection_violation["mismatches"]
    assert len(mismatches) == 1
    assert mismatches[0]["path"] == "$.nodes[0].relative_pressure_pa"
    assert mismatches[0]["mismatch_kind"] == "value_mismatch"
    assert mismatches[0]["recorded_present"] is True
    assert mismatches[0]["recomputed_present"] is True
    assert mismatches[0]["recorded_type"] == "number"
    assert mismatches[0]["recomputed_type"] == "number"
    assert (
        mismatches[0]["recorded_value"]
        - mismatches[0]["recomputed_value"]
    ) == pytest.approx(1.0)
    assert mismatches[0]["absolute_error"] == pytest.approx(1.0)
    assert mismatches[0]["numeric_error_field"] == "relative_pressure_pa"
    maximum_errors = projection_violation["maximum_numeric_errors"]
    assert len(maximum_errors) == 1
    assert maximum_errors[0]["field"] == "relative_pressure_pa"
    assert maximum_errors[0]["maximum_absolute_error"] == pytest.approx(1.0)
    assert corrupted[
        "network_state_projection_mismatches"
    ] == mismatches
    assert corrupted[
        "network_state_projection_maximum_numeric_errors"
    ] == maximum_errors


def _selected_projection_replay_with_mutation(mutator):
    study = FanVariableFrictionLoopStudy(
        name="Selected projection corruption fixture",
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
    replay = evidence["selected_operating_state_replay"]
    pressure = result["system_pressure_check"]
    segment_index = evidence["supplied_segment_index"]
    projection = json.loads(
        json.dumps(replay["recorded_network_state_projection"])
    )
    mutator(projection)
    audit = _selected_operating_state_replay_audit(
        study,
        selected_airflow_m3_h=replay["selected_airflow_replay_input_m3_h"],
        recorded_fan_pressure_pa=pressure["fan_pressure_pa"],
        recorded_loop_network_pressure_pa=pressure[
            "loop_network_pressure_pa"
        ],
        recorded_system_pressure_pa=pressure["total_system_pressure_pa"],
        recorded_residual_pa=pressure["fan_minus_system_pressure_pa"],
        recorded_network_state_sha256=replay[
            "recorded_network_state_sha256"
        ],
        recorded_network_state_projection=projection,
        segment_left=study.fan_curve.points[segment_index],
        segment_right=study.fan_curve.points[segment_index + 1],
        selected_supplied_point_index=evidence[
            "selected_supplied_point_index"
        ],
        bisection_trace=evidence["bisection_trace"],
    )
    return result, audit


def test_selected_projection_replay_localizes_edge_state_corruption() -> None:
    _result, audit = _selected_projection_replay_with_mutation(
        lambda projection: projection["edges"][0].__setitem__(
            "airflow_m3_h",
            projection["edges"][0]["airflow_m3_h"] + 2.5,
        )
    )

    assert audit["network_state_matches_independent_replay"] is True
    assert audit["network_state_projection_mismatch_paths"] == [
        "$.edges[0].airflow_m3_h"
    ]
    mismatch = audit["network_state_projection_mismatches"][0]
    assert mismatch["path"] == "$.edges[0].airflow_m3_h"
    assert mismatch["mismatch_kind"] == "value_mismatch"
    assert mismatch["absolute_error"] == pytest.approx(2.5)
    assert audit["selected_network_state_projection_replay_consistent"] is False


def test_selected_projection_replay_localizes_pressure_power_corruption() -> None:
    _result, audit = _selected_projection_replay_with_mutation(
        lambda projection: projection["pressure_power"].__setitem__(
            "balance_residual_w",
            projection["pressure_power"]["balance_residual_w"] + 0.125,
        )
    )

    assert audit["network_state_matches_independent_replay"] is True
    assert audit["network_state_projection_mismatch_paths"] == [
        "$.pressure_power.balance_residual_w"
    ]
    mismatch = audit["network_state_projection_mismatches"][0]
    assert mismatch["recorded_type"] == "number"
    assert mismatch["recomputed_type"] == "number"
    assert mismatch["absolute_error"] == pytest.approx(0.125)


def test_selected_projection_replay_retains_all_mismatches_in_deterministic_order() -> None:
    def mutate(projection):
        projection["pressure_power"]["balance_residual_w"] += 0.125
        projection["nodes"][0]["relative_pressure_pa"] += 1.0
        projection["edges"][0]["airflow_m3_h"] += 2.5

    result, audit = _selected_projection_replay_with_mutation(mutate)

    expected_paths = [
        "$.edges[0].airflow_m3_h",
        "$.nodes[0].relative_pressure_pa",
        "$.pressure_power.balance_residual_w",
    ]
    assert audit["network_state_matches_independent_replay"] is True
    assert audit["network_state_projection_mismatch_count"] == 3
    assert audit["network_state_projection_mismatch_paths"] == expected_paths
    assert [
        mismatch["path"]
        for mismatch in audit["network_state_projection_mismatches"]
    ] == expected_paths
    assert audit["violation_count"] == 1
    assert audit["violations"][0]["mismatch_paths"] == expected_paths

    report_result = json.loads(json.dumps(result))
    report_result["operating_point_search_evidence"][
        "selected_operating_state_replay"
    ] = audit
    report = markdown_fan_variable_friction_loop_report(report_result)
    for path in expected_paths:
        assert path in report
    assert "recorded_value" in report
    assert "recomputed_value" in report


def test_selected_projection_replay_records_type_mismatch_evidence() -> None:
    _result, audit = _selected_projection_replay_with_mutation(
        lambda projection: projection["edges"][0].__setitem__(
            "resistance_pa_per_m3_s_squared",
            "corrupt",
        )
    )

    mismatch = audit["network_state_projection_mismatches"][0]
    assert mismatch["path"] == (
        "$.edges[0].resistance_pa_per_m3_s_squared"
    )
    assert mismatch["mismatch_kind"] == "type_mismatch"
    assert mismatch["recorded_type"] == "string"
    assert mismatch["recomputed_type"] == "number"
    assert mismatch["absolute_error"] is None


def test_network_state_fingerprint_replay_detects_internal_state_corruption() -> None:
    study = FanVariableFrictionLoopStudy(
        name="Network-state replay corruption",
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

    original_sha256 = trace[0]["low_network_state_sha256"]
    assert len(original_sha256) == 64
    trace[0]["low_network_state_sha256"] = "0" * 64

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
    assert audit[
        "all_trace_pressure_components_match_independent_replay"
    ] is True
    assert audit["pressure_component_replay_violation_count"] == 0
    assert audit["network_state_replay_evidence_complete"] is True
    assert audit[
        "all_low_network_states_match_independent_replay"
    ] is False
    assert audit[
        "all_midpoint_network_states_match_independent_replay"
    ] is True
    assert audit[
        "all_high_network_states_match_independent_replay"
    ] is True
    assert audit[
        "all_trace_network_states_match_independent_replay"
    ] is False
    assert audit["network_state_replay_violation_iterations"] == [1]
    first_check = audit["network_state_replay_checks"][0]
    assert first_check["low"][
        "recorded_network_state_sha256"
    ] == "0" * 64
    assert first_check["low"][
        "recomputed_network_state_sha256"
    ] == original_sha256
    assert first_check["low"][
        "network_state_matches_independent_replay"
    ] is False


def test_trace_network_state_projection_replay_localizes_internal_corruption() -> None:
    study = FanVariableFrictionLoopStudy(
        name="Trace network-state projection corruption",
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
    trace = json.loads(json.dumps(evidence["bisection_trace"]))
    assert trace

    original_sha256 = trace[0]["midpoint_network_state_sha256"]
    trace[0]["midpoint_network_state_projection"]["nodes"][0][
        "relative_pressure_pa"
    ] += 1.0

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
    assert audit["all_trace_network_states_match_independent_replay"] is True
    assert trace[0]["midpoint_network_state_sha256"] == original_sha256
    assert audit["network_state_projection_replay_available"] is True
    assert audit["network_state_projection_replay_evidence_complete"] is True
    assert audit[
        "all_low_network_state_projections_match_independent_replay"
    ] is True
    assert audit[
        "all_midpoint_network_state_projections_match_independent_replay"
    ] is False
    assert audit[
        "all_high_network_state_projections_match_independent_replay"
    ] is True
    assert audit[
        "all_trace_network_state_projections_match_independent_replay"
    ] is False
    assert audit["network_state_projection_replay_violation_count"] == 1
    assert audit["network_state_projection_mismatch_count"] == 1
    assert audit["network_state_projection_replay_violation_iterations"] == [1]
    assert audit["network_state_projection_replay_violation_positions"] == [
        "midpoint"
    ]
    violations = audit["network_state_projection_replay_violations"]
    assert len(violations) == 1
    violation = violations[0]
    assert violation["iteration"] == 1
    assert violation["position"] == "midpoint"
    assert violation["mismatch_paths"] == [
        "$.nodes[0].relative_pressure_pa"
    ]
    assert len(violation["mismatches"]) == 1
    leaf = violation["mismatches"][0]
    assert leaf["mismatch_kind"] == "value_mismatch"
    assert leaf["absolute_error"] == pytest.approx(1.0)
    assert leaf["numeric_error_field"] == "relative_pressure_pa"
    maxima = audit["network_state_projection_maximum_numeric_errors"]
    assert len(maxima) == 1
    assert maxima[0]["field"] == "relative_pressure_pa"
    assert maxima[0]["maximum_absolute_error"] == pytest.approx(1.0)
    assert maxima[0]["witnesses"][0]["iteration"] == 1
    assert maxima[0]["witnesses"][0]["position"] == "midpoint"


def test_trace_network_state_projection_replay_is_backward_compatible_with_hash_only_trace() -> None:
    study = FanVariableFrictionLoopStudy(
        name="Legacy hash-only trace replay",
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
    evidence = result["operating_point_search_evidence"]
    trace = json.loads(json.dumps(evidence["bisection_trace"]))
    for step in trace:
        for position in ("low", "midpoint", "high"):
            step.pop(f"{position}_network_state_projection")

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
    assert audit["network_state_replay_evidence_complete"] is True
    assert audit["all_trace_network_states_match_independent_replay"] is True
    assert audit["network_state_projection_replay_available"] is False
    assert audit["network_state_projection_replay_evidence_complete"] is False
    assert audit[
        "all_trace_network_state_projections_match_independent_replay"
    ] is None
    assert audit["network_state_projection_replay_violation_count"] == 0
    assert audit["network_state_projection_mismatch_count"] == 0



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
    replay = evidence["selected_operating_state_replay"]
    assert replay["selection_source"] == "supplied_fan_curve_point"
    assert replay["selected_airflow_matches_search_origin"] is True
    assert replay[
        "all_selected_operating_state_matches_independent_replay"
    ] is True
    assert replay["violation_count"] == 0


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
    network_replay = result["fan_curve_supplied_point_network_state_replay"]
    assert network_replay["complete_supplied_point_coverage"] is True
    assert network_replay[
        "all_evaluated_supplied_point_network_state_hashes_match_independent_replay"
    ] is True
    assert network_replay[
        "all_evaluated_supplied_point_network_state_projections_match_independent_replay"
    ] is True
    assert network_replay["complete_supplied_point_network_state_replay"] is True
    assert network_replay["violation_point_indices"] == []


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
    network_replay = result["fan_curve_supplied_point_network_state_replay"]
    assert network_replay["complete_supplied_point_coverage"] is False
    assert network_replay["complete_supplied_point_network_state_replay"] is False
    assert network_replay["replay_check_count"] == (
        network_replay["evaluated_supplied_point_count"]
    )
    assert network_replay["violation_point_indices"] == []


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


def test_markdown_report_accepts_pre_v095_trace_audit_without_projection_fields() -> None:
    result = solve_fan_variable_friction_loop(
        load_fan_variable_friction_loop_study(
            "examples/fan_variable_friction_loop_demo.json"
        )
    )
    legacy = json.loads(json.dumps(result))
    audit = legacy["operating_point_search_evidence"]["bisection_trace_audit"]
    for key in (
        "network_state_projection_replay_available",
        "network_state_projection_replay_evidence_complete",
        "all_low_network_state_projections_match_independent_replay",
        "all_midpoint_network_state_projections_match_independent_replay",
        "all_high_network_state_projections_match_independent_replay",
        "all_trace_network_state_projections_match_independent_replay",
        "network_state_projection_replay_violation_count",
        "network_state_projection_mismatch_count",
        "network_state_projection_replay_violation_iterations",
        "network_state_projection_replay_violation_positions",
        "network_state_projection_replay_violations",
        "network_state_projection_maximum_numeric_errors",
    ):
        audit.pop(key, None)

    report = markdown_fan_variable_friction_loop_report(legacy)

    assert "Fan / Variable-Friction Loop Report" in report
    assert "Trace network-state projection replay available: **None**" in report


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

