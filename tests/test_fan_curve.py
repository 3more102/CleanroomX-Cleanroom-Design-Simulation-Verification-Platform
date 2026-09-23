import pytest

from cleanroomx.fan_curve import (
    FanCurve,
    FanCurvePoint,
    FanOperatingPointStudy,
    SystemCurve,
    solve_fan_operating_point,
)
from cleanroomx.fan_curve_io import fan_operating_point_study_from_dict


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


def test_solves_intersection_without_extrapolation() -> None:
    study = FanOperatingPointStudy(
        "Demo",
        _curve(),
        SystemCurve("System", fixed_pressure_pa=80, resistance_pa_per_m3_s_squared=100),
    )

    result = solve_fan_operating_point(study)
    point = result["operating_point"]

    assert result["status"] == "solved"
    assert point is not None
    assert point["airflow_m3_h"] == pytest.approx(5630.598, abs=0.001)
    assert point["fan_pressure_pa"] == pytest.approx(324.6268, abs=0.0001)
    assert point["system_pressure_pa"] == pytest.approx(324.6268, abs=0.0001)
    assert point["pressure_residual_pa"] == pytest.approx(0, abs=1e-7)
    assert point["air_power_kw"] == pytest.approx(0.507734, abs=1e-6)
    assert point["interpolation_segment"] == {
        "low_airflow_m3_h": 3000.0,
        "high_airflow_m3_h": 6000.0,
    }


def test_exact_supplied_curve_point_is_accepted() -> None:
    study = FanOperatingPointStudy(
        "Exact",
        _curve(),
        SystemCurve(
            "System",
            fixed_pressure_pa=100,
            resistance_pa_per_m3_s_squared=576,
        ),
    )

    point = solve_fan_operating_point(study)["operating_point"]

    assert point is not None
    assert point["airflow_m3_h"] == 3000.0
    assert point["fan_pressure_pa"] == 500.0
    assert point["system_pressure_pa"] == 500.0


def test_reports_when_intersection_would_require_higher_flow_extrapolation() -> None:
    result = solve_fan_operating_point(
        FanOperatingPointStudy(
            "Beyond high end",
            _curve(),
            SystemCurve("Low resistance", 0, 1),
        )
    )

    assert result["status"] == "no_intersection_in_supplied_range"
    assert result["operating_point"] is None
    assert "higher-flow extrapolation" in result["message"]


def test_reports_when_system_exceeds_fan_at_lowest_curve_point() -> None:
    result = solve_fan_operating_point(
        FanOperatingPointStudy(
            "Beyond low end",
            _curve(),
            SystemCurve("High static", 700, 100),
        )
    )

    assert result["status"] == "no_intersection_in_supplied_range"
    assert result["operating_point"] is None
    assert "lower-flow extrapolation" in result["message"]


def test_fan_curve_requires_increasing_flow_and_nonincreasing_pressure() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        FanCurve(
            "Bad flow",
            (FanCurvePoint(1000, 500), FanCurvePoint(1000, 400)),
        )

    with pytest.raises(ValueError, match="non-increasing"):
        FanCurve(
            "Bad pressure",
            (FanCurvePoint(1000, 400), FanCurvePoint(2000, 500)),
        )


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_inputs_are_rejected(bad: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        FanCurvePoint(bad, 500)

    with pytest.raises(ValueError, match="finite"):
        SystemCurve("Bad", 0, bad)


def test_json_loader_builds_study() -> None:
    study = fan_operating_point_study_from_dict(
        {
            "name": "Loaded",
            "fan_curve": {
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

    assert study.name == "Loaded"
    assert study.fan_curve.points[1].airflow_m3_h == 6000
    assert study.system_curve.pressure_at(3600) == 180


def test_zero_or_negative_system_resistance_is_rejected() -> None:
    with pytest.raises(ValueError, match="must be finite and > 0"):
        SystemCurve("Bad", 0, 0)
