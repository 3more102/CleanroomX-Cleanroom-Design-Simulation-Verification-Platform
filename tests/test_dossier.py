import hashlib
import json

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
    recovery = [
        {"criterion_status": "incomplete"},
        {"criterion_status": "indeterminate"},
    ]
    uncertainty = [{"requirement": {"status": "indeterminate"}}]
    summary = summarize_dossier_components(
        recovery=recovery,
        uncertainty=uncertainty,
    )
    assert summary["state"] == "attention_required"
    assert summary["adverse_items"]["recovery_incomplete"] == 1
    assert summary["adverse_items"]["recovery_indeterminate"] == 1
    assert summary["adverse_items"]["uncertainty_indeterminate"] == 1


def test_qualification_indeterminate_is_attention_item() -> None:
    qualification = [{"overall_status": "indeterminate"}]
    summary = summarize_dossier_components(qualification=qualification)
    assert summary["state"] == "attention_required"
    assert summary["adverse_items"]["qualification_indeterminate"] == 1


def test_psychrometric_missing_provenance_is_unresolved_not_failure() -> None:
    summary = summarize_dossier_components(
        psychrometric_uncertainty=[
            {"traceability": {"complete": False}},
            {"traceability": {"complete": True}},
        ]
    )
    assert summary["state"] == "complete_with_unchecked"
    assert summary["adverse_item_count"] == 0
    assert (
        summary["unresolved_items"]["psychrometric_uncertainty_missing_provenance"]
        == 1
    )
    component = summary["components"]["psychrometric_uncertainty"]
    assert component["analysis_count"] == 2
    assert component["missing_provenance_analyses"] == 1


def test_thermal_and_fan_states_are_preserved() -> None:
    summary = summarize_dossier_components(
        thermal_uncertainty=[{"overall_status": "indeterminate"}],
        fan_operating_points=[{"status": "no_intersection_in_supplied_range"}],
    )
    assert summary["state"] == "attention_required"
    assert summary["adverse_items"]["thermal_uncertainty_indeterminate"] == 1
    assert summary["adverse_items"]["fan_operating_points_unsolved"] == 1



def test_hvac_fan_curve_duty_state_is_preserved() -> None:
    summary = summarize_dossier_components(
        hvac={
            "rooms": [
                {"air_balance": {"passes_minimum_surplus": True}},
            ],
            "fan_curve_duty_check": {"status": "outside_supplied_range"},
        }
    )
    assert summary["state"] == "attention_required"
    assert summary["adverse_items"]["hvac_fan_curve_duty_unresolved"] == 1


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
    assert len(result["source_files"]) == 11
    assert result["verification"] is not None
    assert result["hvac"] is not None
    assert len(result["recovery_tests"]) == 1
    assert len(result["qualification_analyses"]) == 1
    assert len(result["uncertainty_rooms"]) == 1
    assert len(result["thermal_uncertainty_analyses"]) == 1
    assert len(result["psychrometric_uncertainty_analyses"]) == 1
    assert len(result["fan_operating_point_studies"]) == 1
    assert len(result["fan_duct_network_studies"]) == 1
    assert len(result["fan_parallel_network_studies"]) == 1
    assert len(result["fan_speed_studies"]) == 1
    assert result["fan_operating_point_studies"][0]["status"] == "solved"
    assert result["fan_duct_network_studies"][0]["status"] == "solved"
    assert result["fan_parallel_network_studies"][0]["status"] == "solved"
    assert result["fan_speed_studies"][0]["status"] == "screening_complete"
    assert (
        result["fan_speed_studies"][0]["counts"].get(
            "no_intersection_in_supplied_range", 0
        )
        == 0
    )
    assert all(len(item["sha256"]) == 64 for item in result["source_files"])


def test_markdown_report_includes_new_v013_sections() -> None:
    result = build_dossier("examples/dossier_demo.json")
    text = markdown_dossier_report(result)
    assert "Thermal/HVAC uncertainty screening" in text
    assert "Psychrometric-state uncertainty screening" in text
    assert "Fan/system operating-point studies" in text
    assert "Fan/duct-network operating-point studies" in text
    assert "Fan-driven parallel-network studies" in text
    assert "Fan-speed affinity sweeps" in text
    assert "Source-file fingerprints" in text
    assert "Confirmed recovery min" in text
    confirmed = result["recovery_tests"][0]["uncertainty_assessment"][
        "first_confirmed_recovery_sample_time_minutes"
    ]
    assert confirmed is not None
    assert f"| {confirmed} |" in text


def test_unsolved_integrated_fan_networks_are_attention_items() -> None:
    summary = summarize_dossier_components(
        fan_duct_networks=[{"status": "no_intersection_in_supplied_range"}],
        fan_parallel_networks=[{"status": "no_intersection_in_supplied_range"}],
    )
    assert summary["state"] == "attention_required"
    assert summary["adverse_items"]["fan_duct_networks_unsolved"] == 1
    assert summary["adverse_items"]["fan_parallel_networks_unsolved"] == 1


def test_fan_speed_no_intersection_is_dossier_attention_item() -> None:
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
    assert summary["components"]["fan_speed_studies"]["study_count"] == 1
    assert summary["adverse_items"]["fan_speed_cases_unsolved"] == 1


def test_fan_speed_only_dossier_is_valid(tmp_path) -> None:
    fan_study = {
        "name": "Fan-only dossier sweep",
        "reference_speed_rpm": 1800.0,
        "speed_ratios": [0.75, 1.0],
        "reference_fan_curve": {
            "name": "Reference fan",
            "points": [
                {"airflow_m3_h": 0.0, "pressure_pa": 600.0},
                {"airflow_m3_h": 3000.0, "pressure_pa": 500.0},
                {"airflow_m3_h": 6000.0, "pressure_pa": 300.0},
                {"airflow_m3_h": 8000.0, "pressure_pa": 100.0},
            ],
        },
        "system_curve": {
            "name": "System",
            "fixed_pressure_pa": 80.0,
            "resistance_pa_per_m3_s_squared": 100.0,
        },
    }
    (tmp_path / "fan.json").write_text(
        json.dumps(fan_study),
        encoding="utf-8",
    )
    (tmp_path / "dossier.json").write_text(
        json.dumps(
            {
                "name": "Fan-only dossier",
                "fan_speed_studies": ["fan.json"],
            }
        ),
        encoding="utf-8",
    )

    result = build_dossier(tmp_path / "dossier.json")

    assert len(result["source_files"]) == 1
    assert result["source_files"][0]["kind"] == "fan_speed_study"
    assert len(result["fan_speed_studies"]) == 1
    assert result["fan_speed_studies"][0]["status"] == "screening_complete"
