from cleanroomx.consistency import analyze_hvac_fan_airflow_consistency
from cleanroomx.dossier import build_dossier, summarize_dossier_components
from cleanroomx.dossier_report import markdown_dossier_report


def test_fan_loop_speed_cases_participate_in_hvac_airflow_consistency() -> None:
    result = analyze_hvac_fan_airflow_consistency(
        {"total_governing_airflow_m3_h": 3600.0},
        fan_loop_speed_studies=[
            {
                "study": "Loop VFD sweep",
                "speed_cases": [
                    {
                        "speed_ratio": 1.0,
                        "status": "solved",
                        "fan_operating_point": {"airflow_m3_h": 3601.0},
                    },
                    {
                        "speed_ratio": 0.4,
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


def test_fan_loop_speed_mismatch_is_preserved_as_failure() -> None:
    result = analyze_hvac_fan_airflow_consistency(
        {"total_governing_airflow_m3_h": 3600.0},
        fan_loop_speed_studies=[
            {
                "study": "Loop VFD sweep",
                "speed_cases": [
                    {
                        "speed_ratio": 1.0,
                        "status": "solved",
                        "fan_operating_point": {"airflow_m3_h": 3700.0},
                    }
                ],
            }
        ],
        airflow_abs_tolerance_m3_h=25.0,
    )
    assert result["status"] == "fail"
    assert result["mismatch_count"] == 1


def test_fan_loop_speed_summary_tracks_unresolved_cases() -> None:
    summary = summarize_dossier_components(
        fan_loop_speed_studies=[
            {
                "speed_cases": [
                    {"status": "solved"},
                    {"status": "no_intersection_in_supplied_range"},
                ]
            }
        ]
    )
    assert summary["state"] == "attention_required"
    assert summary["components"]["fan_loop_speed_studies"]["study_count"] == 1
    assert summary["components"]["fan_loop_speed_studies"]["speed_case_count"] == 2
    assert summary["adverse_items"]["fan_loop_speed_studies_unsolved"] == 1


def test_repository_fan_loop_speed_dossier_builds_end_to_end() -> None:
    result = build_dossier("examples/dossier_fan_loop_speed_demo.json")
    assert len(result["fan_loop_speed_studies"]) == 1
    study = result["fan_loop_speed_studies"][0]
    assert study["status"] == "screening_complete"
    assert study["speed_case_count"] == 3
    assert result["executive_summary"]["components"]["fan_loop_speed_studies"][
        "status"
    ] == "screening_complete"
    assert result["source_files"][0]["kind"] == "fan_loop_speed_study"

    report = markdown_dossier_report(result)
    assert "Fan-speed / loop-network studies" in report
    assert "Two-path loop fan-speed sweep" in report
    assert "Continuity residual" in report
