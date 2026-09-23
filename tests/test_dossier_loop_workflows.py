from cleanroomx.consistency import analyze_hvac_fan_airflow_consistency
from cleanroomx.dossier import build_dossier, summarize_dossier_components
from cleanroomx.dossier_report import markdown_dossier_report


def test_fan_loop_network_participates_in_hvac_airflow_consistency() -> None:
    result = analyze_hvac_fan_airflow_consistency(
        {"total_governing_airflow_m3_h": 3600.0},
        fan_loop_networks=[
            {
                "study": "Loop fan",
                "status": "solved",
                "fan_operating_point": {"airflow_m3_h": 3602.0},
            }
        ],
        airflow_abs_tolerance_m3_h=5.0,
    )
    assert result["status"] == "pass"
    assert result["study_count"] == 1
    assert result["study_airflow_checks"][0]["study_kind"] == "fan_loop_network"
    assert result["study_airflow_checks"][0]["absolute_difference_m3_h"] == 2.0


def test_unsolved_fan_loop_network_is_preserved_as_unresolved() -> None:
    result = analyze_hvac_fan_airflow_consistency(
        {"total_governing_airflow_m3_h": 3600.0},
        fan_loop_networks=[
            {
                "study": "Unsolved loop fan",
                "status": "no_intersection_in_supplied_range",
                "fan_operating_point": None,
            }
        ],
    )
    assert result["status"] == "not_comparable"
    assert result["mismatch_count"] == 0
    assert result["unresolved_study_count"] == 1


def test_loop_workflow_summary_tracks_fan_loop_attention_and_damper_cases() -> None:
    summary = summarize_dossier_components(
        fan_loop_networks=[{"status": "no_intersection_in_supplied_range"}],
        damper_studies=[{"status": "solved", "cases": [{"name": "A"}, {"name": "B"}]}],
    )
    assert summary["state"] == "attention_required"
    assert summary["components"]["fan_loop_networks"]["study_count"] == 1
    assert summary["adverse_items"]["fan_loop_networks_unsolved"] == 1
    assert summary["components"]["damper_studies"]["study_count"] == 1
    assert summary["components"]["damper_studies"]["case_count"] == 2


def test_repository_loop_workflow_dossier_builds_end_to_end() -> None:
    result = build_dossier("examples/dossier_loop_studies_demo.json")
    assert len(result["fan_loop_network_studies"]) == 1
    assert result["fan_loop_network_studies"][0]["status"] == "solved"
    assert len(result["damper_studies"]) == 1
    assert result["damper_studies"][0]["status"] == "solved"
    assert result["executive_summary"]["components"]["fan_loop_networks"]["status"] == "screening_complete"
    assert result["executive_summary"]["components"]["damper_studies"]["case_count"] == 2
    source_kinds = {item["kind"] for item in result["source_files"]}
    assert "fan_loop_network_study" in source_kinds
    assert "damper_study" in source_kinds
    report = markdown_dossier_report(result)
    assert "Fan/loop-network operating-point studies" in report
    assert "Loop damper-resistance scenario studies" in report
    assert "Fan-driven two-path loop demo" in report
    assert "Loop damper balancing scenarios" in report
