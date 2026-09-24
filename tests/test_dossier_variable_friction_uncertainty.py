import json
from pathlib import Path

import pytest

from cleanroomx.consistency import analyze_hvac_fan_airflow_consistency
from cleanroomx.dossier import build_dossier, summarize_dossier_components
from cleanroomx.dossier_report import markdown_dossier_report


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
    assert search_summary["strict_sign_change_violation_corner_indices"] == []
    assert search_summary["selected_midpoint_violation_corner_indices"] == []
    assert search_summary["solved_bisection_trace_evidence_corner_count"] == (
        search_summary["bisection_corner_count"]
    )
    assert search_summary["bisection_trace_length_violation_corner_indices"] == []
    assert search_summary["bisection_trace_sign_violation_corner_indices"] == []
    assert search_summary["bisection_trace_midpoint_violation_corner_indices"] == []
    assert search_summary["bisection_trace_outcome_violation_corner_indices"] == []
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
    else:
        assert alternative_gap is None
        assert alternative_gap_fraction is None
        assert alternative_gap_fraction_of_minimum_spacing is None
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
    assert "trace-outcome" in report
    assert "trace length/geometry violations 0/0" in report
    assert "max width-fraction error" in report
    assert "Min segment-point clearance m³/h" in report
    assert "Segment evidence" in report
    assert "Min alternative candidate gap m³/h" in report
    assert "Min alternative candidate gap / supplied curve span" in report
    assert "Min alternative candidate gap / min supplied spacing" in report
    assert "Residual topology" in report
    assert "reverse 0" in report
    assert "No-intersection boundary cases" in report
    assert "Result SHA-256" in report
    assert analysis["result_integrity"]["sha256"] in report
    assert "8" in report


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
