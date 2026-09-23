import hashlib

import pytest

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
    summary = summarize_dossier_components(verification, None, [], [])
    assert summary["state"] == "attention_required"
    assert summary["adverse_items"]["verification_failures"] == 1
    assert summary["unresolved_items"]["verification_not_checked"] == 1


def test_summary_preserves_incomplete_and_indeterminate_states() -> None:
    recovery = [{"criterion_status": "incomplete"}]
    uncertainty = [{"requirement": {"status": "indeterminate"}}]
    summary = summarize_dossier_components(None, None, recovery, uncertainty)
    assert summary["state"] == "attention_required"
    assert summary["adverse_items"]["recovery_incomplete"] == 1
    assert summary["adverse_items"]["uncertainty_indeterminate"] == 1


def test_summary_reports_unchecked_without_calling_it_failure() -> None:
    recovery = [{"criterion_status": "not_checked"}]
    summary = summarize_dossier_components(None, None, recovery, [])
    assert summary["state"] == "complete_with_unchecked"
    assert summary["adverse_item_count"] == 0
    assert summary["unresolved_item_count"] == 1


def test_hvac_air_balance_failure_is_attention_item() -> None:
    hvac = {
        "rooms": [
            {"air_balance": {"passes_minimum_surplus": True}},
            {"air_balance": {"passes_minimum_surplus": False}},
        ]
    }
    summary = summarize_dossier_components(None, hvac, [], [])
    assert summary["state"] == "attention_required"
    assert summary["adverse_items"]["hvac_air_balance_failures"] == 1


def test_source_record_hashes_exact_bytes(tmp_path) -> None:
    source = tmp_path / "input.json"
    source.write_bytes(b'{"value":1}\n')
    record = _source_record("test", "input.json", tmp_path)
    assert record["sha256"] == hashlib.sha256(b'{"value":1}\n').hexdigest()


def test_source_record_rejects_missing_file(tmp_path) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        _source_record("test", "missing.json", tmp_path)


def test_markdown_report_contains_scope_and_hash() -> None:
    result = {
        "dossier": "Demo",
        "metadata": {
            "project_reference": "CR-01",
            "revision": None,
            "prepared_by": None,
            "notes": None,
        },
        "executive_summary": summarize_dossier_components(None, None, [], []),
        "source_files": [{"kind": "test", "path": "a.json", "sha256": "abc123"}],
        "verification": None,
        "hvac": None,
        "recovery_tests": [],
        "qualification_analyses": [],
        "uncertainty_rooms": [],
    }
    report = markdown_dossier_report(result)
    assert "CleanroomX Engineering Dossier" in report
    assert "abc123" in report
    assert "not cleanroom certification" in report


def test_qualification_indeterminate_is_attention_item() -> None:
    qualification = [{"overall_status": "indeterminate"}]
    summary = summarize_dossier_components(None, None, [], [], qualification)
    assert summary["state"] == "attention_required"
    assert summary["adverse_items"]["qualification_indeterminate"] == 1


def test_repository_demo_builds_end_to_end() -> None:
    result = build_dossier("examples/dossier_demo.json")
    assert result["dossier"] == "CleanroomX Integrated Engineering Demo"
    assert len(result["source_files"]) == 5
    assert result["verification"] is not None
    assert result["hvac"] is not None
    assert len(result["recovery_tests"]) == 1
    assert len(result["qualification_analyses"]) == 1
    assert len(result["uncertainty_rooms"]) == 1
    assert all(len(item["sha256"]) == 64 for item in result["source_files"])
