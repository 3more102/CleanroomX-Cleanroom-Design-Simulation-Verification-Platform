import math

import pytest

from cleanroomx.fan_curve import (
    FanCurve,
    FanCurvePoint,
    SystemCurve,
    solve_fan_operating_point,
    FanOperatingPointStudy,
)
from cleanroomx.fan_speed import (
    FanSpeedSweepStudy,
    analyze_fan_speed_sweep,
    scale_fan_curve_by_speed,
)
from cleanroomx.fan_speed_io import fan_speed_sweep_study_from_dict
from cleanroomx.fan_speed_report import markdown_fan_speed_sweep_report


def _curve() -> FanCurve:
    return FanCurve(
        "Supply fan",
        (
            FanCurvePoint(0, 600),
            FanCurvePoint(3000, 500),
            FanCurvePoint(6000, 300),
            FanCurvePoint(8000, 100),
        ),
    )


def _system() -> SystemCurve:
    return SystemCurve(
        "System",
        fixed_pressure_pa=80,
        resistance_pa_per_m3_s_squared=100,
    )


def test_scales_reference_curve_with_affinity_laws() -> None:
    scaled = scale_fan_curve_by_speed(_curve(), 0.5)

    assert scaled.points[1].airflow_m3_h == 1500
    assert scaled.points[1].pressure_pa == 125
    assert scaled.points[-1].airflow_m3_h == 4000
    assert scaled.points[-1].pressure_pa == 25


def test_reference_speed_case_reuses_existing_operating_point_solver() -> None:
    sweep = analyze_fan_speed_sweep(
        FanSpeedSweepStudy(
            "Sweep",
            _curve(),
            _system(),
            (1.0,),
            reference_speed_rpm=1500,
        )
    )
    direct = solve_fan_operating_point(
        FanOperatingPointStudy("Direct", _curve(), _system())
    )

    assert sweep["status"] == "complete"
    assert sweep["cases"][0]["speed_rpm"] == 1500
    assert sweep["cases"][0]["operating_point"] == direct["operating_point"]


def test_speed_sweep_solves_multiple_static_cases() -> None:
    result = analyze_fan_speed_sweep(
        FanSpeedSweepStudy(
            "Sweep",
            _curve(),
            _system(),
            (1.0, 0.8, 0.6, 0.4),
            reference_speed_rpm=1500,
        )
    )

    assert result["status"] == "complete"
    assert result["solved_case_count"] == 4
    assert result["cases"][1]["speed_rpm"] == 1200
    assert result["cases"][1]["fan_law_power_ratio_to_reference"] == pytest.approx(
        0.512
    )
    assert result["cases"][1]["operating_point"]["airflow_m3_h"] == pytest.approx(
        4266.483, abs=0.001
    )


def test_low_speed_preserves_no_extrapolation_behavior() -> None:
    result = analyze_fan_speed_sweep(
        FanSpeedSweepStudy(
            "Low speed",
            _curve(),
            _system(),
            (0.3,),
        )
    )

    assert result["status"] == "partial"
    assert result["cases"][0]["status"] == "no_intersection_in_supplied_range"
    assert result["cases"][0]["operating_point"] is None
    assert "lower-flow extrapolation" in result["cases"][0]["message"]


@pytest.mark.parametrize("bad", [0.0, -0.1, float("nan"), float("inf")])
def test_invalid_speed_ratio_is_rejected(bad: float) -> None:
    with pytest.raises(ValueError, match="speed_ratio"):
        FanSpeedSweepStudy("Bad", _curve(), _system(), (bad,))


def test_duplicate_speed_ratios_are_rejected() -> None:
    with pytest.raises(ValueError, match="unique"):
        FanSpeedSweepStudy("Bad", _curve(), _system(), (1.0, 1.0))


def test_invalid_reference_speed_is_rejected() -> None:
    with pytest.raises(ValueError, match="reference_speed_rpm"):
        FanSpeedSweepStudy(
            "Bad",
            _curve(),
            _system(),
            (1.0,),
            reference_speed_rpm=math.nan,
        )


def test_json_loader_and_markdown_report() -> None:
    study = fan_speed_sweep_study_from_dict(
        {
            "name": "Loaded sweep",
            "reference_speed_rpm": 1500,
            "speed_ratios": [1.0, 0.8],
            "reference_fan_curve": {
                "name": "Fan",
                "points": [
                    {"airflow_m3_h": 0, "pressure_pa": 600},
                    {"airflow_m3_h": 6000, "pressure_pa": 300},
                ],
            },
            "system_curve": {
                "name": "System",
                "fixed_pressure_pa": 80,
                "resistance_pa_per_m3_s_squared": 100,
            },
        }
    )
    result = analyze_fan_speed_sweep(study)
    report = markdown_fan_speed_sweep_report(result)

    assert study.reference_speed_rpm == 1500
    assert study.speed_ratios == (1.0, 0.8)
    assert "Fan Affinity-Law Speed Sweep" in report
    assert "1200.0" in report
