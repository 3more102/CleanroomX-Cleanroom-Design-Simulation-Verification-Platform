import json

import pytest

from cleanroomx.consistency import analyze_hvac_fan_airflow_consistency
from cleanroomx.dossier import build_dossier, summarize_dossier_components
from cleanroomx.dossier_report import markdown_dossier_report


def test_repository_fan_loop_extensions_dossier_builds_end_to_end() -> None:
    result = build_dossier("examples/dossier_fan_loop_extensions_demo.json")

    assert len(result["fan_loop_uncertainty_analyses"]) == 1
    assert result["fan_loop_uncertainty_analyses"][0]["status"] == "complete"
    assert len(result["fan_loop_speed_studies"]) == 1
    assert result["fan_loop_speed_studies"][0]["status"] == "screening_complete"

    components = result["executive_summary"]["components"]
    assert components["fan_loop_uncertainty"]["status"] == "screening_complete"
    assert components["fan_loop_uncertainty"]["analysis_count"] == 1
    assert components["fan_loop_speed_studies"]["status"] == "screening_complete"
    assert components["fan_loop_speed_studies"]["speed_case_count"] == 3

    source_kinds = {item["kind"] for item in result["source_files"]}
    assert "fan_loop_uncertainty_analysis" in source_kinds
    assert "fan_loop_speed_study" in source_kinds
    assert all(len(item["sha256"]) == 64 for item in result["source_files"])

    report = markdown_dossier_report(result)
    assert "Fan/loop-network uncertainty analyses" in report
    assert "Fan-speed / loop-network studies" in report
    assert "Fan/loop uncertainty demo" in report
    assert "Two-path loop fan-speed sweep" in report


def test_fan_loop_uncertainty_and_speed_adverse_states_propagate() -> None:
    summary = summarize_dossier_components(
        fan_loop_uncertainty=[
            {
                "status": "indeterminate",
                "traceability": {
                    "complete": False,
                    "missing_provenance": ["fan_curve"],
                },
            }
        ],
        fan_loop_speed_studies=[
            {
                "status": "attention_required",
                "speed_cases": [
                    {"status": "solved"},
                    {"status": "no_intersection_in_supplied_range"},
                ],
            }
        ],
    )

    assert summary["state"] == "attention_required"
    assert summary["adverse_items"]["fan_loop_uncertainty_indeterminate"] == 1
    assert summary["adverse_items"]["fan_loop_speed_studies_unsolved"] == 1
    assert summary["unresolved_items"]["fan_loop_uncertainty_missing_provenance"] == 1


def test_hvac_fan_consistency_includes_loop_speed_cases() -> None:
    result = analyze_hvac_fan_airflow_consistency(
        {"total_governing_airflow_m3_h": 3600.0},
        fan_loop_speed_studies=[
            {
                "study": "Loop speed",
                "speed_cases": [
                    {
                        "speed_ratio": 1.0,
                        "status": "solved",
                        "fan_operating_point": {"airflow_m3_h": 3602.0},
                    },
                    {
                        "speed_ratio": 0.5,
                        "status": "no_intersection_in_supplied_range",
                        "fan_operating_point": None,
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
    assert result["study_airflow_checks"][0]["study_kind"] == "fan_loop_speed_case"
    assert result["study_airflow_checks"][0]["absolute_difference_m3_h"] == 2.0
    assert result["study_airflow_checks"][1]["status"] == "not_comparable"


def test_missing_fan_loop_uncertainty_source_is_rejected(tmp_path) -> None:
    manifest = tmp_path / "dossier.json"
    manifest.write_text(
        json.dumps(
            {
                "name": "Missing source",
                "fan_loop_uncertainty_analyses": ["missing.json"],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="source file does not exist"):
        build_dossier(manifest)


def test_dossier_source_fingerprints_are_deterministic() -> None:
    first = build_dossier("examples/dossier_fan_loop_extensions_demo.json")
    second = build_dossier("examples/dossier_fan_loop_extensions_demo.json")
    assert first["source_files"] == second["source_files"]
