import json
from pathlib import Path

import pytest

from cleanroomx.consistency import analyze_hvac_fan_airflow_consistency
from cleanroomx.dossier import build_dossier, summarize_dossier_components
from cleanroomx.dossier_report import markdown_dossier_report
from cleanroomx.fan_variable_friction_loop import (
    _bisection_decision_trace_audit,
    _fan_curve_supplied_point_network_state_replay_audit,
    _selected_operating_state_replay_audit,
    solve_fan_variable_friction_loop,
)


def test_repository_nonlinear_uncertainty_dossier_builds_end_to_end() -> None:
    result = build_dossier(
        "examples/dossier_variable_friction_uncertainty_demo.json"
    )

    analyses = result["fan_variable_friction_uncertainty_analyses"]
    assert len(analyses) == 1
    analysis = analyses[0]
    assert analysis["status"] == "complete"
    assert analysis["nominal_status"] == "solved"
    assert analysis["corner_count"] == 8
    assert analysis["solved_corner_count"] == 8
    assert analysis["traceability"]["complete"] is True
    assert analysis["result_integrity"]["algorithm"] == "sha256"
    assert len(analysis["result_integrity"]["sha256"]) == 64
    boundary_summary = analysis["fan_curve_boundary_clearance_summary"]
    bracket_summary = analysis["fan_curve_intersection_bracket_summary"]
    conditioning_summary = analysis["fan_curve_crossing_conditioning_summary"]
    pressure_airflow_summary = analysis[
        "pressure_residual_airflow_equivalence_summary"
    ]
    search_summary = analysis["operating_point_search_resolution_summary"]
    segment_summary = analysis["fan_curve_segment_position_summary"]
    residual_summary = analysis["fan_curve_supplied_point_residual_summary"]
    assert boundary_summary["complete_study_coverage"] is True
    assert bracket_summary["complete_study_coverage"] is True
    assert conditioning_summary["complete_study_coverage"] is True
    assert pressure_airflow_summary["complete_study_coverage"] is True
    assert pressure_airflow_summary["evaluable_corner_count"] == analysis[
        "corner_count"
    ]
    assert pressure_airflow_summary[
        "maximum_configured_tolerance_equivalent_airflow_m3_h"
    ]["value"] >= 0.0
    assert pressure_airflow_summary[
        "maximum_solved_residual_equivalent_airflow_m3_h"
    ]["value"] >= 0.0
    assert search_summary["complete_study_coverage"] is True
    assert search_summary["search_evidence_corner_count"] == analysis[
        "corner_count"
    ]
    assert search_summary["bisection_invariant_evidence_corner_count"] == (
        search_summary["bisection_corner_count"]
    )
    assert search_summary[
        "supplied_point_network_state_replay_complete_coverage"
    ] is True
    assert search_summary[
        "supplied_point_network_state_replay_consistent_corner_count"
    ] == analysis["corner_count"]
    assert search_summary[
        "supplied_point_network_state_replay_violation_corner_indices"
    ] == []
    assert search_summary[
        "supplied_point_network_state_replay_incomplete_corner_indices"
    ] == []
    assert search_summary[
        "supplied_point_network_state_projection_mismatch_count"
    ] == 0
    assert search_summary["strict_sign_change_violation_corner_indices"] == []
    assert search_summary["selected_midpoint_violation_corner_indices"] == []
    assert search_summary["bisection_trace_evidence_corner_count"] == (
        search_summary["bisection_corner_count"]
    )
    assert search_summary["solved_bisection_trace_evidence_corner_count"] == (
        search_summary["bisection_corner_count"]
    )
    assert search_summary[
        "iteration_limit_bisection_trace_evidence_corner_count"
    ] == 0
    assert search_summary["bisection_trace_complete_coverage"] is True
    assert search_summary["bisection_trace_length_violation_corner_indices"] == []
    assert search_summary["bisection_trace_sign_violation_corner_indices"] == []
    assert search_summary["bisection_trace_midpoint_violation_corner_indices"] == []
    assert search_summary["bisection_trace_width_violation_corner_indices"] == []
    assert search_summary[
        "bisection_trace_width_fraction_violation_corner_indices"
    ] == []
    assert search_summary["bisection_trace_geometry_violation_corner_indices"] == []
    assert search_summary["bisection_trace_geometry_consistent_corner_count"] == (
        search_summary["bisection_trace_evidence_corner_count"]
    )
    assert search_summary[
        "maximum_bisection_trace_width_error_m3_h"
    ]["value"] <= 2e-9
    assert search_summary[
        "maximum_bisection_trace_width_fraction_error"
    ]["value"] <= 1e-12
    assert search_summary["bisection_trace_terminal_violation_corner_indices"] == []
    assert search_summary[
        "bisection_trace_iteration_sequence_violation_corner_indices"
    ] == []
    assert search_summary[
        "bisection_trace_state_transition_violation_corner_indices"
    ] == []
    assert search_summary[
        "bisection_trace_decision_semantic_violation_corner_indices"
    ] == []
    assert search_summary[
        "bisection_trace_decision_semantic_consistent_corner_count"
    ] == search_summary["bisection_trace_evidence_corner_count"]
    assert search_summary[
        "bisection_trace_terminal_outcome_violation_corner_indices"
    ] == []
    assert search_summary[
        "bisection_trace_origin_replay_violation_corner_indices"
    ] == []
    assert search_summary[
        "bisection_trace_origin_replay_corner_count"
    ] == search_summary["bisection_trace_evidence_corner_count"]
    assert search_summary[
        "bisection_trace_raw_state_violation_corner_indices"
    ] == []
    assert search_summary[
        "bisection_trace_raw_state_consistent_corner_count"
    ] == search_summary["bisection_trace_evidence_corner_count"]
    assert search_summary[
        "bisection_trace_pressure_state_violation_corner_indices"
    ] == []
    assert search_summary[
        "bisection_trace_pressure_state_consistent_corner_count"
    ] == search_summary["bisection_trace_evidence_corner_count"]
    assert search_summary[
        "maximum_bisection_trace_system_pressure_balance_error_pa"
    ]["value"] <= 2e-9
    assert search_summary[
        "maximum_bisection_trace_residual_balance_error_pa"
    ]["value"] <= 2e-9
    assert search_summary[
        "bisection_trace_residual_replay_violation_corner_indices"
    ] == []
    assert search_summary[
        "bisection_trace_residual_replay_consistent_corner_count"
    ] == search_summary["bisection_trace_evidence_corner_count"]
    assert search_summary[
        "maximum_bisection_trace_residual_replay_error_pa"
    ]["value"] <= 1e-9
    assert search_summary[
        "bisection_trace_pressure_component_replay_violation_corner_indices"
    ] == []
    assert search_summary[
        "bisection_trace_pressure_component_replay_consistent_corner_count"
    ] == search_summary["bisection_trace_evidence_corner_count"]
    assert search_summary[
        "maximum_bisection_trace_pressure_component_replay_error_pa"
    ]["value"] <= 1e-9
    assert search_summary[
        "bisection_trace_network_state_replay_violation_corner_indices"
    ] == []
    assert search_summary[
        "bisection_trace_network_state_replay_consistent_corner_count"
    ] == search_summary["bisection_trace_evidence_corner_count"]
    assert search_summary[
        "terminal_network_state_replay_violation_corner_indices"
    ] == []
    assert search_summary[
        "terminal_network_state_replay_consistent_corner_count"
    ] == search_summary["bisection_trace_evidence_corner_count"]
    assert search_summary["terminal_network_state_replay_violation_count"] == 0
    assert search_summary[
        "terminal_network_state_replay_violation_details"
    ] == []
    assert search_summary[
        "selected_operating_network_state_projection_replay_evidence_corner_count"
    ] == search_summary["solved_search_evidence_corner_count"]
    assert search_summary[
        "selected_operating_network_state_projection_replay_consistent_corner_count"
    ] == search_summary["solved_search_evidence_corner_count"]
    assert search_summary[
        "selected_operating_network_state_projection_replay_violation_corner_indices"
    ] == []
    assert search_summary[
        "selected_operating_network_state_projection_mismatch_count"
    ] == 0
    assert search_summary[
        "terminal_network_state_projection_replay_violation_corner_indices"
    ] == []
    assert search_summary[
        "terminal_network_state_projection_replay_consistent_corner_count"
    ] == search_summary["bisection_trace_evidence_corner_count"]
    assert search_summary[
        "terminal_network_state_projection_replay_violation_count"
    ] == 0
    assert search_summary[
        "terminal_network_state_projection_replay_violation_details"
    ] == []
    assert search_summary[
        "maximum_bisection_trace_midpoint_error_m3_h"
    ]["value"] <= 1e-9
    assert search_summary[
        "iteration_limit_trace_terminal_replay_violation_corner_indices"
    ] == []
    assert search_summary[
        "maximum_bisection_trace_step_count"
    ]["value"] >= 1
    assert search_summary[
        "maximum_final_bisection_half_width_m3_h"
    ]["value"] >= 0.0
    assert segment_summary["complete_study_coverage"] is True
    assert segment_summary["segment_position_evidence_corner_count"] == analysis[
        "corner_count"
    ]
    assert segment_summary[
        "minimum_nearest_segment_endpoint_clearance_m3_h"
    ]["value"] >= 0.0
    assert residual_summary["complete_study_coverage"] is True
    assert residual_summary["selected_candidate_feature_corner_count"] == (
        analysis["solved_corner_count"]
    )
    separation_count = residual_summary[
        "alternative_candidate_separation_evidence_corner_count"
    ]
    alternative_gap = residual_summary[
        "minimum_selected_to_alternative_candidate_interval_gap_m3_h"
    ]
    alternative_gap_fraction = residual_summary[
        "minimum_selected_to_alternative_candidate_interval_gap_fraction_of_supplied_curve_span"
    ]
    alternative_gap_fraction_of_minimum_spacing = residual_summary[
        "minimum_selected_to_alternative_candidate_interval_gap_fraction_of_minimum_supplied_point_spacing"
    ]
    alternative_index_gap = residual_summary[
        "minimum_selected_to_alternative_candidate_feature_index_interval_gap"
    ]
    if separation_count:
        assert alternative_gap is not None
        assert alternative_gap["value"] >= 0.0
        assert alternative_gap["sources"]
        assert alternative_gap_fraction is not None
        assert alternative_gap_fraction["value"] >= 0.0
        assert alternative_gap_fraction["sources"]
        assert alternative_gap_fraction_of_minimum_spacing is not None
        assert alternative_gap_fraction_of_minimum_spacing["value"] >= 0.0
        assert alternative_gap_fraction_of_minimum_spacing["sources"]
        assert alternative_index_gap is not None
        assert alternative_index_gap["value"] >= 1
        assert alternative_index_gap["sources"]
    else:
        assert alternative_gap is None
        assert alternative_gap_fraction is None
        assert alternative_gap_fraction_of_minimum_spacing is None
        assert alternative_index_gap is None
    assert residual_summary["residual_increase_corner_count"] == 0
    assert residual_summary["reverse_strict_sign_change_corner_count"] == 0
    assert residual_summary["reverse_strict_sign_change_corner_indices"] == []
    assert residual_summary["reverse_strict_sign_change_segment_count_total"] == 0
    assert bracket_summary["bracket_evidence_corner_count"] == analysis[
        "corner_count"
    ]
    assert boundary_summary["solved_corner_count"] == analysis["corner_count"]
    assert boundary_summary[
        "minimum_nearest_boundary_headroom_m3_h"
    ]["value"] >= 0.0
    assert analysis["operating_point_envelope"]["air_power_kw"]["lower"] >= 0.0
    assert (
        analysis["operating_point_envelope"]["air_power_kw"]["lower"]
        <= analysis["operating_point_envelope"]["air_power_kw"]["upper"]
    )

    component = result["executive_summary"]["components"][
        "fan_variable_friction_uncertainty"
    ]
    assert component["status"] == "screening_complete"
    assert component["analysis_count"] == 1
    assert component["corner_count"] == 8
    assert component["no_intersection_corner_count"] == 0
    assert component["result_integrity_count"] == 1
    assert component["missing_result_integrity_analyses"] == 0
    assert result["executive_summary"]["state"] == "no_adverse_findings"

    source = next(
        item
        for item in result["source_files"]
        if item["kind"] == "fan_variable_friction_uncertainty_analysis"
    )
    assert source["path"] == "fan_variable_friction_uncertainty_demo.json"
    assert len(source["sha256"]) == 64

    report = markdown_dossier_report(result)
    assert "Fan / variable-friction loop uncertainty analyses" in report
    assert "Variable-friction fan-loop bounded uncertainty" in report
    assert "Air-power envelope kW" in report
    assert "Electrical-input corner range kW" in report
    assert "Electrical coverage" in report
    assert "SFP corner range W/(m³/s)" in report
    assert "SFP coverage" in report
    assert "complete (8/8)" in report
    assert "Solver tolerance audit" in report
    assert "within_configured_tolerances" in report
    assert "Iteration budget audit" in report
    assert "within_configured_iteration_limits" in report
    assert "Airflow excursion from nominal %" in report
    assert "Fan-curve min headroom m³/h" in report
    assert "Boundary evidence" in report
    assert "Min endpoint bracket gap Pa" in report
    assert "Bracket evidence" in report
    assert "Min crossing gradient Pa/(m³/h)" in report
    assert "Crossing evidence" in report
    assert "Max pressure-tolerance airflow equiv m³/h" in report
    assert "Max solved-residual airflow equiv m³/h" in report
    assert "Pressure→airflow evidence" in report
    assert "Max final bisection half-width m³/h" in report
    assert "Search evidence" in report
    assert "Bisection invariant / trace audit" in report
    assert "trace " in report
    assert (
        "trace violations L/S/M/T/I/R/D/A/O/F "
        "0/0/0/0/0/0/0/0/0/0"
        in report
    )
    assert "trace-decision" in report
    assert "trace geometry violations W/N 0/0" in report
    assert "trace-geometry" in report
    assert "trace-raw-state" in report
    assert "raw-state violations 0" in report
    assert "trace-pressure-state" in report
    assert "pressure-state violations 0" in report
    assert "residual-replay" in report
    assert "residual-replay violations 0" in report
    assert "supplied-point-network-state-replay" in report
    assert "supplied-point-network-state-replay coverage" in report
    assert "selected-network-state-projection-replay" in report
    assert "selected-network-state-projection-replay violations 0" in report
    assert "max residual-replay error" in report
    assert "max trace system-pressure identity error" in report
    assert "max trace residual identity error" in report
    assert "max trace midpoint error" in report
    assert "max trace width error" in report
    assert "max trace normalized-width error" in report
    assert "trace-outcome" in report
    assert "limit-final-replay 0/0" in report
    assert "max width-fraction error" in report
    assert "Min segment-point clearance m³/h" in report
    assert "Segment evidence" in report
    assert "Min alternative candidate gap m³/h" in report
    assert "Min alternative candidate gap / supplied curve span" in report
    assert "Min alternative candidate gap / min supplied spacing" in report
    assert "Min alternative candidate index gap" in report
    assert "Residual topology" in report
    assert "reverse 0" in report
    assert "No-intersection boundary cases" in report
    assert "Result SHA-256" in report
    assert analysis["result_integrity"]["sha256"] in report
    assert "8" in report




def test_dossier_preserves_solver_result_integrity_linkage_corruption(
    monkeypatch,
) -> None:
    call_count = 0

    def corrupt_one_corner(case_study):
        nonlocal call_count
        call_count += 1
        result = solve_fan_variable_friction_loop(case_study)
        if call_count == 2:
            result["solver_diagnostics"]["operating_iterations"] += 1
        return result

    monkeypatch.setattr(
        "cleanroomx.fan_variable_friction_uncertainty."
        "solve_fan_variable_friction_loop",
        corrupt_one_corner,
    )
    dossier = build_dossier(
        "examples/dossier_variable_friction_uncertainty_demo.json"
    )
    analysis = dossier["fan_variable_friction_uncertainty_analyses"][0]
    summary = analysis["solver_result_integrity_summary"]

    assert summary["complete_coverage"] is True
    assert summary["inconsistent_result_count"] == 1
    assert summary["inconsistent_corner_count"] == 1
    assert summary["incomplete_corner_count"] == 0
    assert summary["violating_corner_indices"] == [0]
    assert summary["coverage_gap_corner_indices"] == []
    assert summary["violation_details"][0]["corner_index"] == 0
    assert (
        summary["violation_details"][0]["recorded_sha256"]
        != summary["violation_details"][0]["recomputed_sha256"]
    )

    json.dumps(dossier, sort_keys=True, allow_nan=False)
    report = markdown_dossier_report(dossier)
    assert "Solver-result integrity linkage" in report
    assert "inconsistent=1" in report
    assert "violating_corners=[0]" in report



def test_dossier_solver_result_integrity_component_summary_counts() -> None:
    result = build_dossier(
        "examples/dossier_variable_friction_uncertainty_demo.json"
    )
    analysis = result["fan_variable_friction_uncertainty_analyses"][0]
    summary = analysis["solver_result_integrity_summary"]
    component = result["executive_summary"]["components"][
        "fan_variable_friction_uncertainty"
    ]

    assert summary["complete_corner_coverage"] is True
    assert summary["consistent_corner_count"] == analysis["corner_count"]
    assert summary["inconsistent_corner_count"] == 0
    assert summary["incomplete_corner_count"] == 0
    assert component[
        "solver_result_integrity_complete_coverage_analyses"
    ] == 1
    assert component[
        "solver_result_integrity_inconsistent_corner_count"
    ] == 0
    assert component[
        "solver_result_integrity_coverage_gap_corner_count"
    ] == 0

    json.dumps(result, sort_keys=True, allow_nan=False)
    report = markdown_dossier_report(result)
    assert "Solver-result integrity linkage for" in report
    assert "corner_complete=True" in report



def test_dossier_preserves_selected_projection_corruption_evidence(
    monkeypatch,
) -> None:
    call_count = 0

    def corrupt_one_corner(case_study):
        nonlocal call_count
        call_count += 1
        result = solve_fan_variable_friction_loop(case_study)
        if call_count != 2 or result["status"] != "solved":
            return result

        evidence = result["operating_point_search_evidence"]
        replay = evidence["selected_operating_state_replay"]
        pressure = result["system_pressure_check"]
        projection = json.loads(
            json.dumps(replay["recorded_network_state_projection"])
        )
        projection["edges"][0]["airflow_m3_h"] += 2.5
        segment_index = evidence["supplied_segment_index"]
        evidence["selected_operating_state_replay"] = (
            _selected_operating_state_replay_audit(
                case_study,
                selected_airflow_m3_h=replay[
                    "selected_airflow_replay_input_m3_h"
                ],
                recorded_fan_pressure_pa=pressure["fan_pressure_pa"],
                recorded_loop_network_pressure_pa=pressure[
                    "loop_network_pressure_pa"
                ],
                recorded_system_pressure_pa=pressure[
                    "total_system_pressure_pa"
                ],
                recorded_residual_pa=pressure[
                    "fan_minus_system_pressure_pa"
                ],
                recorded_network_state_sha256=replay[
                    "recorded_network_state_sha256"
                ],
                recorded_network_state_projection=projection,
                segment_left=case_study.fan_curve.points[segment_index],
                segment_right=case_study.fan_curve.points[
                    segment_index + 1
                ],
                selected_supplied_point_index=evidence[
                    "selected_supplied_point_index"
                ],
                bisection_trace=evidence["bisection_trace"],
            )
        )
        return result

    monkeypatch.setattr(
        "cleanroomx.fan_variable_friction_uncertainty."
        "solve_fan_variable_friction_loop",
        corrupt_one_corner,
    )
    dossier = build_dossier(
        "examples/dossier_variable_friction_uncertainty_demo.json"
    )
    analysis = dossier["fan_variable_friction_uncertainty_analyses"][0]
    summary = analysis["operating_point_search_resolution_summary"]

    assert summary[
        "selected_operating_network_state_projection_replay_violation_corner_indices"
    ] == [0]
    assert summary[
        "selected_operating_network_state_projection_mismatch_count"
    ] == 1
    details = summary[
        "selected_operating_network_state_projection_replay_violation_details"
    ]
    assert details[0]["mismatch_paths"] == [
        "$.edges[0].airflow_m3_h"
    ]
    mismatch = details[0]["mismatches"][0]
    assert mismatch["absolute_error"] == pytest.approx(2.5)
    assert mismatch["recorded_value"] - mismatch["recomputed_value"] == (
        pytest.approx(2.5)
    )

    json.dumps(dossier, sort_keys=True, allow_nan=False)
    report = markdown_dossier_report(dossier)
    assert "selected-network-state-projection-replay coverage" in report
    assert "$.edges[0].airflow_m3_h" in report
    assert "recorded_value" in report
    assert "recomputed_value" in report




def test_dossier_preserves_solver_configuration_projection_corruption(
    monkeypatch,
) -> None:
    call_count = 0

    def corrupt_one_corner(case_study):
        nonlocal call_count
        call_count += 1
        result = solve_fan_variable_friction_loop(case_study)
        if call_count != 2 or result["status"] != "solved":
            return result

        evidence = result["operating_point_search_evidence"]
        replay = evidence["selected_operating_state_replay"]
        pressure = result["system_pressure_check"]
        projection = json.loads(
            json.dumps(replay["recorded_network_state_projection"])
        )
        projection["variable_friction"]["relaxation"] += 0.1
        segment_index = evidence["supplied_segment_index"]
        evidence["selected_operating_state_replay"] = (
            _selected_operating_state_replay_audit(
                case_study,
                selected_airflow_m3_h=replay[
                    "selected_airflow_replay_input_m3_h"
                ],
                recorded_fan_pressure_pa=pressure["fan_pressure_pa"],
                recorded_loop_network_pressure_pa=pressure[
                    "loop_network_pressure_pa"
                ],
                recorded_system_pressure_pa=pressure[
                    "total_system_pressure_pa"
                ],
                recorded_residual_pa=pressure[
                    "fan_minus_system_pressure_pa"
                ],
                recorded_network_state_sha256=replay[
                    "recorded_network_state_sha256"
                ],
                recorded_network_state_projection=projection,
                segment_left=case_study.fan_curve.points[segment_index],
                segment_right=case_study.fan_curve.points[
                    segment_index + 1
                ],
                selected_supplied_point_index=evidence[
                    "selected_supplied_point_index"
                ],
                bisection_trace=evidence["bisection_trace"],
            )
        )
        return result

    monkeypatch.setattr(
        "cleanroomx.fan_variable_friction_uncertainty."
        "solve_fan_variable_friction_loop",
        corrupt_one_corner,
    )
    dossier = build_dossier(
        "examples/dossier_variable_friction_uncertainty_demo.json"
    )
    analysis = dossier["fan_variable_friction_uncertainty_analyses"][0]
    summary = analysis["operating_point_search_resolution_summary"]

    assert summary[
        "selected_operating_network_state_projection_replay_violation_corner_indices"
    ] == [0]
    assert summary[
        "selected_operating_network_state_projection_mismatch_count"
    ] == 1
    details = summary[
        "selected_operating_network_state_projection_replay_violation_details"
    ]
    assert details[0]["mismatch_paths"] == [
        "$.variable_friction.relaxation"
    ]
    mismatch = details[0]["mismatches"][0]
    assert mismatch["mismatch_kind"] == "value_mismatch"
    assert mismatch["absolute_error"] == pytest.approx(0.1)

    json.dumps(dossier, sort_keys=True, allow_nan=False)
    report = markdown_dossier_report(dossier)
    assert "$.variable_friction.relaxation" in report
    assert "recorded_value" in report
    assert "recomputed_value" in report


def test_dossier_preserves_full_trace_projection_corruption_evidence(
    monkeypatch,
) -> None:
    call_count = 0

    def corrupt_one_corner(case_study):
        nonlocal call_count
        call_count += 1
        result = solve_fan_variable_friction_loop(case_study)
        if call_count != 2 or result["status"] != "solved":
            return result

        evidence = result["operating_point_search_evidence"]
        trace = json.loads(json.dumps(evidence["bisection_trace"]))
        trace[0]["low_network_state_projection"]["edges"][0][
            "airflow_m3_h"
        ] += 2.5
        segment_index = evidence["supplied_segment_index"]
        evidence["bisection_trace"] = trace
        evidence["bisection_trace_audit"] = _bisection_decision_trace_audit(
            trace,
            operating_iterations=evidence["operating_iterations"],
            termination_reason=result["solver_diagnostics"][
                "termination_reason"
            ],
            operating_pressure_tolerance_pa=(
                case_study.operating_pressure_tolerance_pa
            ),
            expected_fixed_pressure_pa=case_study.fixed_pressure_pa,
            study=case_study,
            segment_left=case_study.fan_curve.points[segment_index],
            segment_right=case_study.fan_curve.points[segment_index + 1],
            initial_bisection_bracket=evidence[
                "initial_bisection_bracket"
            ],
            solved_terminal_bracket=evidence["final_bisection_bracket"],
        )
        return result

    monkeypatch.setattr(
        "cleanroomx.fan_variable_friction_uncertainty."
        "solve_fan_variable_friction_loop",
        corrupt_one_corner,
    )
    dossier = build_dossier(
        "examples/dossier_variable_friction_uncertainty_demo.json"
    )
    analysis = dossier["fan_variable_friction_uncertainty_analyses"][0]
    summary = analysis["operating_point_search_resolution_summary"]

    assert summary[
        "bisection_trace_network_state_projection_replay_violation_corner_indices"
    ] == [0]
    assert summary[
        "bisection_trace_network_state_projection_replay_mismatch_count"
    ] == 1
    details = summary[
        "bisection_trace_network_state_projection_replay_violation_details"
    ]
    assert len(details) == 1
    assert details[0]["corner_index"] == 0
    assert details[0]["violation_iteration_positions"] == [
        {"iteration": 1, "position": "low"}
    ]
    mismatch = details[0]["mismatches"][0]
    assert mismatch["path"] == "$.edges[0].airflow_m3_h"
    assert mismatch["recorded_value"] - mismatch["recomputed_value"] == (
        pytest.approx(2.5)
    )
    assert mismatch["absolute_error"] == pytest.approx(2.5)

    json.dumps(dossier, sort_keys=True, allow_nan=False)
    report = markdown_dossier_report(dossier)
    assert "full-trace-network-state-projection coverage" in report
    assert "$.edges[0].airflow_m3_h" in report
    assert "recorded_value" in report
    assert "recomputed_value" in report


def test_dossier_preserves_supplied_point_projection_corruption(
    monkeypatch,
) -> None:
    call_count = 0

    def corrupt_one_corner(case_study):
        nonlocal call_count
        call_count += 1
        result = solve_fan_variable_friction_loop(case_study)
        if call_count != 2:
            return result

        checks = json.loads(json.dumps(result["fan_curve_point_checks"]))
        checks[1]["network_state_projection"]["nodes"][0][
            "relative_pressure_pa"
        ] += 1.25
        result["fan_curve_point_checks"] = checks
        result["fan_curve_supplied_point_network_state_replay"] = (
            _fan_curve_supplied_point_network_state_replay_audit(
                case_study,
                checks,
            )
        )
        return result

    monkeypatch.setattr(
        "cleanroomx.fan_variable_friction_uncertainty."
        "solve_fan_variable_friction_loop",
        corrupt_one_corner,
    )
    dossier = build_dossier(
        "examples/dossier_variable_friction_uncertainty_demo.json"
    )
    analysis = dossier["fan_variable_friction_uncertainty_analyses"][0]
    summary = analysis["operating_point_search_resolution_summary"]

    assert summary[
        "supplied_point_network_state_projection_violation_corner_indices"
    ] == [0]
    assert summary[
        "supplied_point_network_state_projection_mismatch_count"
    ] == 1
    details = summary[
        "supplied_point_network_state_replay_violation_details"
    ]
    assert details[0]["corner_index"] == 0
    assert details[0]["projection_violation_point_indices"] == [1]
    mismatch = details[0]["mismatches"][0]
    assert mismatch["point_index"] == 1
    assert mismatch["path"] == "$.nodes[0].relative_pressure_pa"
    assert mismatch["absolute_error"] == pytest.approx(1.25)

    json.dumps(dossier, sort_keys=True, allow_nan=False)
    report = markdown_dossier_report(dossier)
    assert "supplied-point-network-state-replay" in report
    assert "$.nodes[0].relative_pressure_pa" in report
    assert "point_index" in report
    assert "recorded_value" in report
    assert "recomputed_value" in report


def test_nonlinear_uncertainty_indeterminate_propagates_attention() -> None:
    summary = summarize_dossier_components(
        fan_variable_friction_uncertainty=[
            {
                "status": "indeterminate",
                "corner_count": 4,
                "fan_curve_no_intersection_summary": {
                    "no_intersection_corner_count": 3,
                },
                "traceability": {
                    "complete": True,
                    "missing_provenance": [],
                },
            }
        ]
    )

    component = summary["components"]["fan_variable_friction_uncertainty"]
    assert component["status"] == "attention_required"
    assert component["counts"] == {"indeterminate": 1}
    assert component["no_intersection_corner_count"] == 3
    assert summary["adverse_items"][
        "fan_variable_friction_uncertainty_indeterminate"
    ] == 1
    assert summary["state"] == "attention_required"


def test_nonlinear_uncertainty_missing_provenance_is_unresolved() -> None:
    summary = summarize_dossier_components(
        fan_variable_friction_uncertainty=[
            {
                "status": "complete",
                "corner_count": 2,
                "traceability": {
                    "complete": False,
                    "missing_provenance": ["fan_curve"],
                },
            }
        ]
    )

    component = summary["components"]["fan_variable_friction_uncertainty"]
    assert component["status"] == "complete_with_missing_provenance"
    assert component["missing_provenance_analyses"] == 1
    assert summary["unresolved_items"][
        "fan_variable_friction_uncertainty_missing_provenance"
    ] == 1
    assert summary["state"] == "complete_with_unchecked"


def test_missing_nonlinear_uncertainty_source_is_rejected(tmp_path) -> None:
    manifest = tmp_path / "dossier.json"
    manifest.write_text(
        json.dumps(
            {
                "name": "Missing nonlinear uncertainty source",
                "fan_variable_friction_uncertainty_analyses": [
                    "missing.json"
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="source file does not exist"):
        build_dossier(manifest)


def test_nonlinear_uncertainty_dossier_is_deterministic() -> None:
    path = "examples/dossier_variable_friction_uncertainty_demo.json"
    first = build_dossier(path)
    second = build_dossier(path)

    assert first["source_files"] == second["source_files"]
    assert json.dumps(first, sort_keys=True) == json.dumps(
        second,
        sort_keys=True,
    )


def test_hvac_consistency_expands_nonlinear_uncertainty_corners() -> None:
    analysis = build_dossier(
        "examples/dossier_variable_friction_uncertainty_demo.json"
    )["fan_variable_friction_uncertainty_analyses"][0]
    result = analyze_hvac_fan_airflow_consistency(
        {"total_governing_airflow_m3_h": 5000.0},
        fan_variable_friction_uncertainty_analyses=[analysis],
        airflow_abs_tolerance_m3_h=10000.0,
    )

    assert result["status"] == "pass"
    assert result["study_count"] == analysis["corner_count"] == 8
    assert result["solved_study_count"] == 8
    assert result["unresolved_study_count"] == 0
    assert result["mismatch_count"] == 0
    assert {
        item["study_kind"] for item in result["study_airflow_checks"]
    } == {"fan_variable_friction_uncertainty_corner"}


def test_hvac_consistency_preserves_unresolved_uncertainty_corner() -> None:
    result = analyze_hvac_fan_airflow_consistency(
        {"total_governing_airflow_m3_h": 3600.0},
        fan_variable_friction_uncertainty_analyses=[
            {
                "analysis": "Bounded nonlinear loop",
                "corners": [
                    {
                        "status": "solved",
                        "operating_point": {"airflow_m3_h": 3602.0},
                    },
                    {
                        "status": "non_converged",
                        "operating_point": None,
                    },
                ],
            }
        ],
        airflow_abs_tolerance_m3_h=5.0,
    )

    assert result["status"] == "pass_with_unresolved_studies"
    assert result["study_count"] == 2
    assert result["solved_study_count"] == 1
    assert result["unresolved_study_count"] == 1
    assert result["mismatch_count"] == 0
    assert result["study_airflow_checks"][1]["study_status"] == "non_converged"
    assert result["study_airflow_checks"][1]["status"] == "not_comparable"


def test_dossier_wires_nonlinear_uncertainty_into_hvac_consistency(
    tmp_path,
) -> None:
    manifest = tmp_path / "dossier.json"
    manifest.write_text(
        json.dumps(
            {
                "name": "Nonlinear uncertainty airflow consistency",
                "hvac_project": str(
                    Path("examples/semiconductor_thermal_demo.json").resolve()
                ),
                "fan_variable_friction_uncertainty_analyses": [
                    str(
                        Path(
                            "examples/fan_variable_friction_uncertainty_demo.json"
                        ).resolve()
                    )
                ],
                "consistency_checks": {
                    "hvac_fan_operating_airflow": {
                        "airflow_abs_tolerance_m3_h": 1000000.0
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = build_dossier(manifest)
    check = result["consistency_checks"]["hvac_fan_operating_airflow"]
    assert check["status"] == "pass"
    assert check["study_count"] == 8
    assert check["solved_study_count"] == 8
    assert check["unresolved_study_count"] == 0
    assert all(
        item["study_kind"] == "fan_variable_friction_uncertainty_corner"
        for item in check["study_airflow_checks"]
    )


def test_dossier_builds_fan_airflow_uncertainty_end_to_end(tmp_path) -> None:
    manifest = tmp_path / "dossier.json"
    manifest.write_text(
        json.dumps(
            {
                "name": "Fan airflow-coordinate uncertainty dossier",
                "fan_variable_friction_uncertainty_analyses": [
                    str(
                        Path(
                            "examples/fan_variable_friction_fan_airflow_uncertainty_demo.json"
                        ).resolve()
                    )
                ],
            }
        ),
        encoding="utf-8",
    )

    result = build_dossier(manifest)
    analysis = result["fan_variable_friction_uncertainty_analyses"][0]
    assert analysis["status"] == "complete"
    assert analysis["corner_count"] == 4
    assert analysis["solved_corner_count"] == 4
    assert analysis["traceability"]["complete"] is True
    assert set(analysis["input_intervals"]["fan_curve_airflow_m3_h"]) == {
        "1",
        "2",
    }

    component = result["executive_summary"]["components"][
        "fan_variable_friction_uncertainty"
    ]
    assert component["status"] == "screening_complete"
    assert component["corner_count"] == 4
    assert result["executive_summary"]["state"] == "no_adverse_findings"


def test_dossier_builds_whole_fan_curve_scenarios_end_to_end(tmp_path) -> None:
    manifest = tmp_path / "dossier.json"
    manifest.write_text(
        json.dumps(
            {
                "name": "Whole fan-curve scenario dossier",
                "fan_variable_friction_uncertainty_analyses": [
                    str(
                        Path(
                            "examples/fan_variable_friction_curve_scenarios_demo.json"
                        ).resolve()
                    )
                ],
            }
        ),
        encoding="utf-8",
    )

    result = build_dossier(manifest)
    analysis = result["fan_variable_friction_uncertainty_analyses"][0]

    assert analysis["status"] == "complete"
    assert analysis["corner_count"] == 3
    assert analysis["solved_corner_count"] == 3
    assert analysis["traceability"]["complete"] is True
    assert {
        corner["fan_curve_scenario"] for corner in analysis["corners"]
    } == {"nominal", "lower_envelope", "upper_envelope"}

    component = result["executive_summary"]["components"][
        "fan_variable_friction_uncertainty"
    ]
    assert component["status"] == "screening_complete"
    assert component["corner_count"] == 3
    assert component["fan_curve_scenario_count"] == 2
    assert result["executive_summary"]["state"] == "no_adverse_findings"

    report = markdown_dossier_report(result)
    assert "fan_curve_scenarios=2" in report
    assert "Whole fan-curve scenarios" in report
    assert "lower_envelope, upper_envelope" in report


def test_dossier_escapes_whole_fan_curve_scenario_names(tmp_path) -> None:
    analysis_path = tmp_path / "fan-scenarios.json"
    payload = json.loads(
        Path("examples/fan_variable_friction_curve_scenarios_demo.json").read_text(
            encoding="utf-8"
        )
    )
    payload["fan_curve_scenarios"][0]["name"] = "lower | envelope\nA"
    analysis_path.write_text(json.dumps(payload), encoding="utf-8")

    manifest = tmp_path / "dossier.json"
    manifest.write_text(
        json.dumps(
            {
                "name": "Scenario escaping dossier",
                "fan_variable_friction_uncertainty_analyses": [
                    str(analysis_path.resolve())
                ],
            }
        ),
        encoding="utf-8",
    )

    report = markdown_dossier_report(build_dossier(manifest))

    assert "lower \\| envelope<br>A" in report
    assert "lower | envelope\nA" not in report
