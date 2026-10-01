from __future__ import annotations

import math

import pytest

from cleanroomx.consistency import analyze_hvac_fan_airflow_consistency
from cleanroomx.dossier import build_dossier, summarize_dossier_components
from cleanroomx.dossier_report import markdown_dossier_report
from cleanroomx.fan_curve import (
    FanCurve,
    FanCurvePoint,
    FanOperatingPointStudy,
    SystemCurve,
    solve_fan_operating_point,
)
from cleanroomx.hvac import analyze_hvac_project
from cleanroomx.hvac_io import hvac_project_from_dict


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


def test_hvac_fan_airflow_consistency_uses_unrounded_source_project() -> None:
    project = hvac_project_from_dict(
        {
            "name": "Cross-study precision",
            "rooms": [
                {
                    "name": "Room",
                    "cleanroom_airflow_m3_h": 1000.0004,
                    "thermal_design": {
                        "room_air": {
                            "dry_bulb_c": 22.0,
                            "relative_humidity_percent": 45.0,
                        }
                    },
                }
            ],
        }
    )
    presented = analyze_hvac_project(project)
    assert presented["total_governing_airflow_m3_h"] == 1000.0

    result = analyze_hvac_fan_airflow_consistency(
        presented,
        hvac_project=project,
        fan_operating_points=[_fan("Precision fan", 1000.00055)],
        airflow_abs_tolerance_m3_h=0.0002,
    )

    assert result["status"] == "pass"
    assert result["mismatch_count"] == 0
    assert result["hvac_governing_airflow_m3_h"] == 1000.0004
    assert result["study_airflow_checks"][0]["absolute_difference_m3_h"] == 0.00015


def test_hvac_fan_consistency_uses_unrounded_standalone_fan_root() -> None:
    project = hvac_project_from_dict(
        {
            "name": "Cross-study fan precision",
            "rooms": [
                {
                    "name": "Room",
                    "cleanroom_airflow_m3_h": 1000.0004,
                    "thermal_design": {
                        "room_air": {
                            "dry_bulb_c": 22.0,
                            "relative_humidity_percent": 45.0,
                        }
                    },
                }
            ],
        }
    )
    presented_hvac = analyze_hvac_project(project)

    exact_airflow = 1000.00055
    system = SystemCurve(
        "Precision system",
        fixed_pressure_pa=50.0,
        resistance_pa_per_m3_s_squared=100.0,
    )
    exact_pressure = system.pressure_at(exact_airflow)
    study = FanOperatingPointStudy(
        "Precision fan",
        FanCurve(
            "Precision curve",
            (
                FanCurvePoint(0.0, 100.0),
                FanCurvePoint(exact_airflow, exact_pressure),
                FanCurvePoint(2000.0, 20.0),
            ),
        ),
        system,
    )
    presented_fan = solve_fan_operating_point(study)
    assert presented_fan["operating_point"]["airflow_m3_h"] == 1000.001

    result = analyze_hvac_fan_airflow_consistency(
        presented_hvac,
        hvac_project=project,
        fan_operating_points=[presented_fan],
        fan_operating_point_studies=[study],
        airflow_abs_tolerance_m3_h=0.0002,
    )

    assert result["status"] == "pass"
    assert result["mismatch_count"] == 0
    assert result["study_airflow_checks"][0]["fan_operating_airflow_m3_h"] == 1000.00055
    assert result["study_airflow_checks"][0]["absolute_difference_m3_h"] == 0.00015


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

def test_fan_speed_cases_participate_in_hvac_airflow_consistency() -> None:
    result = analyze_hvac_fan_airflow_consistency(
        _hvac(),
        fan_speed_studies=[
            {
                "study": "VFD sweep",
                "speed_cases": [
                    {
                        "speed_ratio": 0.8,
                        "status": "solved",
                        "operating_point": {"airflow_m3_h": 3601.0},
                    },
                    {
                        "speed_ratio": 1.0,
                        "status": "no_intersection_in_supplied_range",
                        "operating_point": None,
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
    assert result["study_airflow_checks"][0]["study_kind"] == "fan_speed_case"

