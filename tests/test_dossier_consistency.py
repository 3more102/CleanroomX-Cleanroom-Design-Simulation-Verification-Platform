from cleanroomx.dossier import build_dossier, summarize_dossier_components
from cleanroomx.dossier_report import markdown_dossier_report


def test_consistency_failure_contributes_to_dossier_attention() -> None:
    consistency = {
        "status": "fail",
        "shared_room_count": 2,
        "mismatch_count": 2,
        "room_set_mismatch": True,
    }
    summary = summarize_dossier_components(consistency=consistency)
    assert summary["state"] == "attention_required"
    assert summary["adverse_items"]["cross_module_consistency_failures"] == 3
    assert summary["components"]["cross_module_consistency"]["status"] == "fail"


def test_not_comparable_consistency_is_preserved_as_unresolved() -> None:
    consistency = {
        "status": "not_comparable",
        "shared_room_count": 0,
        "mismatch_count": 0,
        "room_set_mismatch": False,
    }
    summary = summarize_dossier_components(consistency=consistency)
    assert summary["state"] == "complete_with_unchecked"
    assert summary["unresolved_items"]["cross_module_consistency_not_comparable"] == 1


def test_repository_dossier_consistency_demo_builds_end_to_end() -> None:
    result = build_dossier("examples/dossier_consistency_demo.json")
    consistency = result["consistency_checks"]["verification_hvac_airflow"]

    assert consistency is not None
    assert consistency["status"] == "pass"
    assert consistency["shared_room_count"] == 3
    assert consistency["mismatch_count"] == 0
    assert consistency["room_set_mismatch"] is False
    assert (
        result["executive_summary"]["components"]["cross_module_consistency"]["status"]
        == "pass"
    )


def test_dossier_report_includes_consistency_evidence() -> None:
    result = build_dossier("examples/dossier_consistency_demo.json")
    text = markdown_dossier_report(result)

    assert "Cross-module verification / HVAC consistency" in text
    assert "Room airflow absolute consistency tolerance" in text
    assert "| Process | 2700.0 | 2700.0 |" in text
    assert "not a cleanroom acceptance limit" in text
