import json

import pytest

from cleanroomx.consistency import analyze_hvac_fan_airflow_consistency
from cleanroomx.dossier import build_dossier, summarize_dossier_components
from cleanroomx.dossier_report import markdown_dossier_report


def test_repository_variable_friction_fan_dossier_builds_end_to_end() -> None:
    result = build_dossier(
        "examples/dossier_variable_friction_fan_extensions_demo.json"
    )

    assert len(result["fan_variable_friction_loop_studies"]) == 1
    direct = result["fan_variable_friction_loop_studies"][0]
    assert direct["status"] == "solved"
    assert direct["solver_diagnostics"]["converged"] is True

    assert len(result["fan_variable_friction_speed_studies"]) == 1
    speed = result["fan_variable_friction_speed_studies"][0]
    assert speed["status"] == "screening_complete"
    assert speed["counts"] == {"solved": 3}

    components = result["executive_summary"]["components"]
    assert components["fan_variable_friction_loops"]["status"] == (
        "screening_complete"
    )
    assert components["fan_variable_friction_speed_studies"]["status"] == (
        "screening_complete"
    )
    assert result["executive_summary"]["state"] == "no_adverse_findings"

    source_kinds = {item["kind"] for item in result["source_files"]}
    assert "fan_variable_friction_loop_study" in source_kinds
    assert "fan_variable_friction_speed_study" in source_kinds
    assert all(len(item["sha256"]) == 64 for item in result["source_files"])

    report = markdown_dossier_report(result)
    assert "Fan / variable-friction loop studies" in report
    assert "Fan-speed / variable-friction loop studies" in report
    assert "Fan-driven variable-friction two-path loop" in report
    assert "Variable-friction fan-speed loop sweep" in report
    assert "Resistance closure" in report
    assert "Termination" in report


def test_nonlinear_nonconvergence_is_always_an_attention_item() -> None:
    summary = summarize_dossier_components(
        fan_variable_friction_loops=[
            {"status": "non_converged"},
        ],
        fan_variable_friction_speed_studies=[
            {
                "speed_cases": [
                    {"status": "solved"},
                    {"status": "non_converged"},
                    {"status": "no_intersection_in_supplied_range"},
                ]
            }
        ],
    )

    assert summary["state"] == "attention_required"
    assert summary["components"]["fan_variable_friction_loops"]["status"] == (
        "attention_required"
    )
    assert summary["components"][
        "fan_variable_friction_speed_studies"
    ]["status"] == "attention_required"
    assert summary["adverse_items"][
        "fan_variable_friction_loops_non_converged"
    ] == 1
    assert summary["adverse_items"][
        "fan_variable_friction_speed_studies_non_converged"
    ] == 1
    assert summary["adverse_items"][
        "fan_variable_friction_speed_studies_unsolved"
    ] == 1


def test_hvac_consistency_includes_nonlinear_loop_and_speed_cases() -> None:
    result = analyze_hvac_fan_airflow_consistency(
        {"total_governing_airflow_m3_h": 3600.0},
        fan_variable_friction_loops=[
            {
                "study": "Nonlinear loop",
                "status": "solved",
                "fan_operating_point": {"airflow_m3_h": 3602.0},
            }
        ],
        fan_variable_friction_speed_studies=[
            {
                "study": "Nonlinear speed sweep",
                "speed_cases": [
                    {
                        "speed_ratio": 1.0,
                        "status": "solved",
                        "fan_operating_point": {"airflow_m3_h": 3598.0},
                    },
                    {
                        "speed_ratio": 0.5,
                        "status": "non_converged",
                        "fan_operating_point": None,
                    },
                ],
            }
        ],
        airflow_abs_tolerance_m3_h=5.0,
    )

    assert result["status"] == "pass_with_unresolved_studies"
    assert result["study_count"] == 3
    assert result["solved_study_count"] == 2
    assert result["unresolved_study_count"] == 1
    assert result["mismatch_count"] == 0
    kinds = [item["study_kind"] for item in result["study_airflow_checks"]]
    assert kinds == [
        "fan_variable_friction_loop",
        "fan_variable_friction_speed_case",
        "fan_variable_friction_speed_case",
    ]
    assert result["study_airflow_checks"][2]["study_status"] == "non_converged"
    assert result["study_airflow_checks"][2]["status"] == "not_comparable"


def test_missing_variable_friction_dossier_source_is_rejected(tmp_path) -> None:
    manifest = tmp_path / "dossier.json"
    manifest.write_text(
        json.dumps(
            {
                "name": "Missing nonlinear source",
                "fan_variable_friction_loop_studies": ["missing.json"],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="source file does not exist"):
        build_dossier(manifest)


def test_variable_friction_dossier_fingerprints_and_json_are_deterministic() -> None:
    path = "examples/dossier_variable_friction_fan_extensions_demo.json"
    first = build_dossier(path)
    second = build_dossier(path)

    assert first["source_files"] == second["source_files"]
    assert json.dumps(first, sort_keys=True) == json.dumps(
        second, sort_keys=True
    )
