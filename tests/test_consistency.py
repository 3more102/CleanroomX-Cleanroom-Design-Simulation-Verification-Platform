import pytest

from cleanroomx.consistency import check_verification_hvac_airflow_consistency
from cleanroomx.dossier import build_dossier, summarize_dossier_components
from cleanroomx.dossier_report import markdown_dossier_report


def _verification_result(name: str, airflow_m3_h: float) -> dict:
    volume = 100.0
    return {
        "rooms": [
            {
                "room": name,
                "volume_m3": volume,
                "ach": airflow_m3_h / volume,
                "findings": [],
            }
        ],
        "pressure_cascade": [],
    }


def _hvac_result(name: str, airflow_m3_h: float) -> dict:
    return {
        "rooms": [
            {
                "name": name,
                "cleanroom_airflow_m3_h": airflow_m3_h,
                "air_balance": {"passes_minimum_surplus": True},
            }
        ]
    }


def test_airflow_consistency_passes_with_explicit_tolerance() -> None:
    result = check_verification_hvac_airflow_consistency(
        _verification_result("Process", 2700.0),
        _hvac_result("Process", 2710.0),
        {"airflow_tolerance_percent": 0.5},
    )
    assert result["status"] == "pass"
    assert result["failed_comparison_count"] == 0
    assert result["comparisons"][0]["absolute_deviation_percent"] < 0.5


def test_airflow_consistency_supports_explicit_room_mapping() -> None:
    result = check_verification_hvac_airflow_consistency(
        _verification_result("Process", 2700.0),
        _hvac_result("Process Bay", 2700.0),
        {
            "airflow_tolerance_percent": 0.1,
            "room_map": {"Process": "Process Bay"},
        },
    )
    assert result["status"] == "pass"
    assert result["room_mapping_mode"] == "explicit"
    assert result["comparisons"][0]["hvac_room"] == "Process Bay"


def test_airflow_consistency_fails_mismatch_and_required_unmapped() -> None:
    verification = _verification_result("Process", 2700.0)
    verification["rooms"].append(
        {
            "room": "Ante",
            "volume_m3": 50.0,
            "ach": 20.0,
            "findings": [],
        }
    )
    result = check_verification_hvac_airflow_consistency(
        verification,
        _hvac_result("Process", 3000.0),
        {
            "airflow_tolerance_percent": 1.0,
            "require_all_verification_rooms": True,
        },
    )
    assert result["status"] == "fail"
    assert result["failed_comparison_count"] == 1
    assert result["required_unmapped_verification_rooms"] == ["Ante"]
    assert result["issue_count"] == 2

    summary = summarize_dossier_components(consistency=result)
    assert summary["state"] == "attention_required"
    assert summary["adverse_items"]["cross_module_consistency_issues"] == 2


def test_airflow_consistency_is_not_checked_without_room_pair() -> None:
    result = check_verification_hvac_airflow_consistency(
        _verification_result("Process", 2700.0),
        _hvac_result("Process Bay", 2700.0),
        {"airflow_tolerance_percent": 1.0},
    )
    assert result["status"] == "not_checked"

    summary = summarize_dossier_components(consistency=result)
    assert summary["state"] == "complete_with_unchecked"
    assert summary["unresolved_items"]["cross_module_consistency_not_checked"] == 1


def test_airflow_consistency_requires_explicit_tolerance() -> None:
    with pytest.raises(ValueError, match="airflow_tolerance_percent"):
        check_verification_hvac_airflow_consistency(
            _verification_result("Process", 2700.0),
            _hvac_result("Process", 2700.0),
            {},
        )


def test_airflow_consistency_rejects_duplicate_hvac_mapping() -> None:
    verification = _verification_result("Process", 2700.0)
    verification["rooms"].append(
        {
            "room": "Ante",
            "volume_m3": 50.0,
            "ach": 20.0,
            "findings": [],
        }
    )
    with pytest.raises(ValueError, match="multiple verification rooms"):
        check_verification_hvac_airflow_consistency(
            verification,
            _hvac_result("Process Bay", 2700.0),
            {
                "airflow_tolerance_percent": 1.0,
                "room_map": {
                    "Process": "Process Bay",
                    "Ante": "Process Bay",
                },
            },
        )


def test_repository_consistency_demo_builds_end_to_end() -> None:
    result = build_dossier("examples/dossier_consistency_demo.json")
    consistency = result["consistency_checks"]["verification_hvac_airflow"]
    assert consistency["status"] == "pass"
    assert consistency["comparisons"][0]["verification_room"] == "Process"
    assert consistency["comparisons"][0]["absolute_deviation_percent"] == 0.0


def test_markdown_report_includes_consistency_section() -> None:
    result = build_dossier("examples/dossier_consistency_demo.json")
    text = markdown_dossier_report(result)
    assert "Cross-module verification / HVAC airflow consistency" in text
    assert "User-supplied airflow tolerance" in text
