from cleanroomx.dossier import build_dossier, summarize_dossier_components
from cleanroomx.dossier_report import markdown_dossier_report


def test_fan_speed_unsolved_case_contributes_to_dossier_attention() -> None:
    summary = summarize_dossier_components(
        fan_speed_studies=[
            {
                "status": "attention_required",
                "counts": {
                    "solved": 2,
                    "no_intersection_in_supplied_range": 1,
                },
            }
        ]
    )
    assert summary["state"] == "attention_required"
    assert summary["adverse_items"]["fan_speed_cases_unsolved"] == 1
    assert summary["components"]["fan_speed_studies"]["study_count"] == 1


def test_repository_fan_speed_dossier_builds_end_to_end() -> None:
    result = build_dossier("examples/dossier_fan_speed_demo.json")

    assert result["dossier"] == "CleanroomX Fan-Speed Dossier Demo"
    assert len(result["source_files"]) == 1
    assert len(result["fan_speed_studies"]) == 1
    study = result["fan_speed_studies"][0]
    assert study["speed_case_count"] == 4
    assert study["counts"]["solved"] == 3
    assert study["counts"]["no_intersection_in_supplied_range"] == 1
    assert result["executive_summary"]["state"] == "attention_required"


def test_fan_speed_dossier_report_preserves_case_evidence() -> None:
    result = build_dossier("examples/dossier_fan_speed_demo.json")
    text = markdown_dossier_report(result)

    assert "Fan-speed affinity-law studies" in text
    assert "VFD fan-speed operating-point sweep" in text
    assert "| 0.3 |" in text
    assert "no_intersection_in_supplied_range" in text
    assert "Source-file fingerprints" in text
