from __future__ import annotations

import math

import pytest

from cleanroomx.consistency import analyze_hvac_fan_airflow_consistency
from cleanroomx.dossier import build_dossier, summarize_dossier_components
from cleanroomx.dossier_report import markdown_dossier_report


def _hvac(airflow: float = 3600.0) -> dict:
    return {"total_governing_airflow_m3_h": airflow}


def _fan(study: str, airflow: float | None) -> dict:
    return {
        "study": study,
        "status": "solved" if airflow is not None else "no_intersection_in_supplied_range",
        "operating_point": None if airflow is None else {"airflow_m3_h": airflow},
    }


def test_hvac_fan_airflow_consistency_passes_with_explicit_tolerance() -> None:
    result = analyze_hvac_fan_airflow_consistency(
        _hvac(),
        fan_operating_points=[_fan("Supply fan", 3602.0)],
        airflow_abs_tolerance_m3_h=5.0,
    )
    assert result["status"] == "pass"
    assert result["mismatch_count"] == 0
    assert result["study_airflow_checks"][0]["absolute_difference_m3_h"] == 2.0


def test_hvac_fan_airflow_consistency_fails_on_solved_mismatch() -> None:
    result = analyze_hvac_fan_airflow_consistency(
        _hvac(),
        fan_operating_points=[_fan("Supply fan", 3700.0)],
        airflow_abs_tolerance_m3_h=25.0,
    )
    assert result["status"] == "fail"
    assert result["mismatch_count"] == 1
    assert result["study_airflow_checks"][0]["status"] == "mismatch"


def test_unsolved_study_is_preserved_as_unresolved_not_failed() -> None:
    result = analyze_hvac_fan_airflow_consistency(
        _hvac(),
        fan_operating_points=[
            _fan("Solved fan", 3600.0),
            _fan("Unsolved fan", None),
        ],
    )
    assert result["status"] == "pass_with_unresolved_studies"
    assert result["mismatch_count"] == 0
    assert result["unresolved_study_count"] == 1


def test_all_unsolved_studies_are_not_comparable() -> None:
    result = analyze_hvac_fan_airflow_consistency(
        _hvac(),
        fan_operating_points=[_fan("Unsolved fan", None)],
    )
    assert result["status"] == "not_comparable"
    assert result["solved_study_count"] == 0
    assert result["unresolved_study_count"] == 1


@pytest.mark.parametrize("bad", [-1.0, math.nan, math.inf, -math.inf])
def test_invalid_hvac_fan_airflow_tolerance_is_rejected(bad: float) -> None:
    with pytest.raises(ValueError, match="finite and >= 0"):
        analyze_hvac_fan_airflow_consistency(
            _hvac(),
            fan_operating_points=[_fan("Supply fan", 3600.0)],
            airflow_abs_tolerance_m3_h=bad,
        )


def test_fan_airflow_mismatch_contributes_to_dossier_attention() -> None:
    summary = summarize_dossier_components(
        fan_airflow_consistency={
            "status": "fail",
            "study_count": 2,
            "solved_study_count": 2,
            "mismatch_count": 1,
            "unresolved_study_count": 0,
        }
    )
    assert summary["state"] == "attention_required"
    assert summary["adverse_items"]["hvac_fan_operating_airflow_mismatches"] == 1


def test_unresolved_fan_airflow_study_is_dossier_unresolved() -> None:
    summary = summarize_dossier_components(
        fan_airflow_consistency={
            "status": "pass_with_unresolved_studies",
            "study_count": 2,
            "solved_study_count": 1,
            "mismatch_count": 0,
            "unresolved_study_count": 1,
        }
    )
    assert summary["state"] == "complete_with_unchecked"
    assert summary["unresolved_items"]["hvac_fan_operating_airflow_unresolved"] == 1


def test_repository_fan_airflow_consistency_demo_builds_end_to_end() -> None:
    result = build_dossier("examples/dossier_fan_airflow_consistency_demo.json")
    consistency = result["consistency_checks"]["hvac_fan_operating_airflow"]

    assert consistency is not None
    assert consistency["status"] == "pass"
    assert consistency["study_count"] == 1
    assert consistency["solved_study_count"] == 1
    assert consistency["mismatch_count"] == 0

    text = markdown_dossier_report(result)
    assert "HVAC / fan operating-airflow consistency" in text
    assert "Fan and duct-network operating-point demo" in text
    assert "not establish airflow adequacy" in text
