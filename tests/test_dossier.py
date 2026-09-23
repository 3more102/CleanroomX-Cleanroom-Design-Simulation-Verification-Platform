import hashlib

from cleanroomx.dossier import _source_record, build_dossier, summarize_dossier_components
from cleanroomx.dossier_report import markdown_dossier_report


def test_summary_marks_failures_as_attention_required() -> None:
    verification = {
        "rooms": [
            {
                "findings": [
                    {"status": "pass"},
                    {"status": "fail"},
                    {"status": "not_checked"},
                ]
            }
        ],
        "pressure_cascade": [],
    }
    summary = summarize_dossier_components(verification=verification)
    assert summary["state"] == "attention_required"
    assert summary["adverse_items"]["verification_failures"] == 1
    assert summary["unresolved_items"]["verification_not_checked"] == 1


def test_summary_preserves_incomplete_and_indeterminate_states() -> None:
    recovery = [{"criterion_status": "incomplete"}]
    uncertainty = [{"requirement": {"status": "indeterminate"}}]
    summary = summarize_dossier_components(
        recovery=recovery,
        uncertainty=uncertainty,
    )
    assert summary["state"] == "attention_required"
    assert summary["adverse_items"]["recovery_incomplete"] == 1
    assert summary["adverse_items"]["uncertainty_indeterminate"] == 1


def test_qualification_indeterminate_is_attention_item() -> None:
    qualification = [{"overall_status": "indeterminate"}]
    summary = summarize_dossier_components(qualification=qualification)
    assert summary["state"] == "attention_required"
    assert summary["adverse_items"]["qualification_indeterminate"] == 1


def test_thermal_and_fan_states_are_preserved() -> None:
    summary = summarize_dossier_components(
        thermal_uncertainty=[{"overall_status": "indeterminate"}],
        fan_operating_points=[{"status": "no_intersection_in_supplied_range"}],
    )
    assert summary["state"] == "attention_required"
    assert summary["adverse_items"]["thermal_uncertainty_indeterminate"] == 1
    assert summary["adverse_items"]["fan_operating_points_unsolved"] == 1


def test_source_record_contains_exact_sha256(tmp_path) -> None:
    source = tmp_path / "input.json"
    source.write_text('{"demo": true}\n', encoding="utf-8")
    record = _source_record("demo", "input.json", tmp_path)
    expected = hashlib.sha256(source.read_bytes()).hexdigest()
    assert record["sha256"] == expected
    assert record["path"] == "input.json"


def test_repository_demo_builds_end_to_end() -> None:
    result = build_dossier("examples/dossier_demo.json")
    assert result["dossier"] == "CleanroomX Integrated Engineering Demo"
    assert len(result["source_files"]) == 7
    assert result["verification"] is not None
    assert result["hvac"] is not None
    assert len(result["recovery_tests"]) == 1
    assert len(result["qualification_analyses"]) == 1
    assert len(result["uncertainty_rooms"]) == 1
    assert len(result["thermal_uncertainty_analyses"]) == 1
    assert len(result["fan_operating_point_studies"]) == 1
    assert result["fan_operating_point_studies"][0]["status"] == "solved"
    assert all(len(item["sha256"]) == 64 for item in result["source_files"])


def test_markdown_report_includes_new_v012_sections() -> None:
    result = build_dossier("examples/dossier_demo.json")
    text = markdown_dossier_report(result)
    assert "Thermal/HVAC uncertainty screening" in text
    assert "Fan/system operating-point studies" in text
    assert "Source-file fingerprints" in text
