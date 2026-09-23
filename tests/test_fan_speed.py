import pytest

from cleanroomx.fan_curve import FanCurve, FanCurvePoint, SystemCurve
from cleanroomx.fan_speed import (
    FanSpeedStudy,
    analyze_fan_speed_study,
    scale_fan_curve_for_speed,
)
from cleanroomx.fan_speed_io import fan_speed_study_from_dict
from cleanroomx.fan_speed_report import markdown_fan_speed_report


def _curve() -> FanCurve:
    return FanCurve(
        "Reference fan",
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


def test_affinity_scaling_transforms_supplied_curve_points() -> None:
    scaled = scale_fan_curve_for_speed(_curve(), 0.5)

    assert scaled.points[0].airflow_m3_h == 0
    assert scaled.points[0].pressure_pa == pytest.approx(150)
    assert scaled.points[1].airflow_m3_h == pytest.approx(1500)
    assert scaled.points[1].pressure_pa == pytest.approx(125)
    assert scaled.points[-1].airflow_m3_h == pytest.approx(4000)
    assert scaled.points[-1].pressure_pa == pytest.approx(25)


def test_speed_sweep_preserves_bounded_no_intersection_state() -> None:
    result = analyze_fan_speed_study(
        FanSpeedStudy(
            "Sweep",
            _curve(),
            _system(),
            speed_ratios=(0.3, 0.5, 1.0),
            reference_speed_rpm=1800,
        )
    )

    assert result["status"] == "attention_required"
    assert result["counts"]["no_intersection_in_supplied_range"] == 1
    assert result["counts"]["solved"] == 2

    low, half, full = result["speed_cases"]
    assert low["operating_point"] is None
    assert low["status"] == "no_intersection_in_supplied_range"
    assert half["speed_rpm"] == pytest.approx(900)
    assert half["affinity_scaling"]["pressure_ratio"] == pytest.approx(0.25)
    assert half["affinity_scaling"]["homologous_input_power_factor"] == pytest.approx(0.125)
    assert half["operating_point"]["airflow_m3_h"] < full["operating_point"]["airflow_m3_h"]


def test_all_solved_cases_report_screening_complete() -> None:
    result = analyze_fan_speed_study(
        FanSpeedStudy(
            "Solved sweep",
            _curve(),
            _system(),
            speed_ratios=(0.5, 0.75, 1.0),
        )
    )

    assert result["status"] == "screening_complete"
    assert result["counts"] == {"solved": 3}


@pytest.mark.parametrize("bad", [0.0, -0.5, float("nan"), float("inf")])
def test_invalid_speed_ratios_are_rejected(bad: float) -> None:
    with pytest.raises(ValueError, match="finite and > 0"):
        FanSpeedStudy(
            "Bad",
            _curve(),
            _system(),
            speed_ratios=(bad,),
        )


def test_duplicate_speed_ratios_are_rejected() -> None:
    with pytest.raises(ValueError, match="unique"):
        FanSpeedStudy(
            "Duplicate",
            _curve(),
            _system(),
            speed_ratios=(0.8, 0.8),
        )


def test_loader_and_markdown_report() -> None:
    study = fan_speed_study_from_dict(
        {
            "name": "Loaded sweep",
            "reference_speed_rpm": 1800,
            "speed_ratios": [0.5, 1.0],
            "reference_fan_curve": {
                "name": "Fan",
                "points": [
                    {"airflow_m3_h": 0, "pressure_pa": 600},
                    {"airflow_m3_h": 8000, "pressure_pa": 100},
                ],
            },
            "system_curve": {
                "name": "System",
                "fixed_pressure_pa": 80,
                "resistance_pa_per_m3_s_squared": 100,
            },
        }
    )
    result = analyze_fan_speed_study(study)
    text = markdown_fan_speed_report(result)

    assert study.reference_speed_rpm == 1800
    assert "Fan-Speed Study" in text
    assert "Homologous input-power factor" in text
    assert "900.0" in text
