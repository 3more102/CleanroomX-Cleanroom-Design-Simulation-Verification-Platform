import math

import pytest

from cleanroomx.fan_curve import (
    FanCurvePoint,
    FanOperatingPointCase,
    FanStaticPressureCurve,
    QuadraticSystemCurve,
    solve_fan_operating_point,
)
from cleanroomx.fan_curve_io import fan_operating_point_case_from_dict


def _case() -> FanOperatingPointCase:
    return FanOperatingPointCase(
        name="Exact intersection",
        fan_curve=FanStaticPressureCurve(
            name="AHU-1",
            points=(
                FanCurvePoint(0, 800),
                FanCurvePoint(7200, 400),
            ),
        ),
        system_curve=QuadraticSystemCurve(
            name="Supply system",
            fixed_pressure_pa=100,
            resistance_pa_per_m3_s_squared=500,
        ),
    )


def test_solves_exact_piecewise_linear_fan_system_intersection() -> None:
    result = solve_fan_operating_point(_case())
    point = result["operating_point"]

    assert result["status"] == "solved"
    assert point is not None
    assert point["airflow_m3_h"] == pytest.approx(3600, abs=0.001)
    assert point["airflow_m3_s"] == pytest.approx(1.0, abs=1e-9)
    assert point["static_pressure_pa"] == pytest.approx(600, abs=0.001)
    assert point["pressure_residual_pa"] == pytest.approx(0, abs=1e-7)
    assert point["air_power_kw"] == pytest.approx(0.6, abs=1e-6)


def test_multisegment_curve_selects_segment_containing_intersection() -> None:
    case = FanOperatingPointCase(
        name="Three points",
        fan_curve=FanStaticPressureCurve(
            name="Fan",
            points=(
                FanCurvePoint(0, 900),
                FanCurvePoint(3600, 700),
                FanCurvePoint(7200, 300),
            ),
        ),
        system_curve=QuadraticSystemCurve(
            name="System",
            fixed_pressure_pa=100,
            resistance_pa_per_m3_s_squared=500,
        ),
    )

    result = solve_fan_operating_point(case)
    point = result["operating_point"]

    assert point is not None
    assert 3600 < point["airflow_m3_h"] < 7200
    assert point["fan_curve_segment"] == 2
    assert point["pressure_residual_pa"] == pytest.approx(0, abs=1e-6)


def test_no_intersection_does_not_extrapolate_above_curve_range() -> None:
    case = FanOperatingPointCase(
        name="Outside range",
        fan_curve=FanStaticPressureCurve(
            name="Fan",
            points=(
                FanCurvePoint(0, 1000),
                FanCurvePoint(3600, 800),
            ),
        ),
        system_curve=QuadraticSystemCurve(
            name="Low resistance",
            fixed_pressure_pa=100,
            resistance_pa_per_m3_s_squared=100,
        ),
    )

    result = solve_fan_operating_point(case)

    assert result["status"] == "no_intersection"
    assert result["operating_point"] is None
    assert "extrapolation" in result["reason"]


def test_no_intersection_detected_when_system_is_above_curve_at_min_flow() -> None:
    case = FanOperatingPointCase(
        name="Insufficient pressure",
        fan_curve=FanStaticPressureCurve(
            name="Fan",
            points=(
                FanCurvePoint(1000, 400),
                FanCurvePoint(3600, 200),
            ),
        ),
        system_curve=QuadraticSystemCurve(
            name="High fixed pressure",
            fixed_pressure_pa=500,
            resistance_pa_per_m3_s_squared=100,
        ),
    )

    result = solve_fan_operating_point(case)

    assert result["status"] == "no_intersection"
    assert result["operating_point"] is None
    assert "minimum supplied airflow" in result["reason"]


def test_rejects_nonmonotonic_fan_pressure_curve() -> None:
    with pytest.raises(ValueError, match="non-increasing"):
        FanStaticPressureCurve(
            name="Bad fan",
            points=(
                FanCurvePoint(0, 500),
                FanCurvePoint(1000, 600),
            ),
        )


def test_rejects_duplicate_or_decreasing_airflow_points() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        FanStaticPressureCurve(
            name="Bad airflow",
            points=(
                FanCurvePoint(1000, 500),
                FanCurvePoint(1000, 400),
            ),
        )


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_rejects_nonfinite_curve_inputs(bad: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        FanCurvePoint(bad, 500)

    with pytest.raises(ValueError, match="finite"):
        FanCurvePoint(1000, bad)

    with pytest.raises(ValueError, match="finite"):
        QuadraticSystemCurve("System", 100, bad)


def test_boundary_intersection_is_not_duplicated_across_segments() -> None:
    case = FanOperatingPointCase(
        name="Boundary",
        fan_curve=FanStaticPressureCurve(
            name="Fan",
            points=(
                FanCurvePoint(0, 800),
                FanCurvePoint(3600, 600),
                FanCurvePoint(7200, 400),
            ),
        ),
        system_curve=QuadraticSystemCurve(
            name="System",
            fixed_pressure_pa=100,
            resistance_pa_per_m3_s_squared=500,
        ),
    )

    result = solve_fan_operating_point(case)
    point = result["operating_point"]

    assert point is not None
    assert point["airflow_m3_h"] == pytest.approx(3600, abs=0.001)


def test_json_loader_builds_case() -> None:
    case = fan_operating_point_case_from_dict(
        {
            "name": "Loaded",
            "fan_curve": {
                "name": "Fan",
                "points": [
                    {"airflow_m3_h": 0, "static_pressure_pa": 800},
                    {"airflow_m3_h": 7200, "static_pressure_pa": 400},
                ],
            },
            "system_curve": {
                "name": "System",
                "fixed_pressure_pa": 100,
                "resistance_pa_per_m3_s_squared": 500,
            },
        }
    )

    result = solve_fan_operating_point(case)
    assert result["status"] == "solved"
    assert result["operating_point"]["airflow_m3_h"] == pytest.approx(3600)


def test_result_values_are_finite_for_valid_case() -> None:
    result = solve_fan_operating_point(_case())
    point = result["operating_point"]

    assert point is not None
    assert all(
        math.isfinite(point[key])
        for key in (
            "airflow_m3_h",
            "airflow_m3_s",
            "static_pressure_pa",
            "fan_static_pressure_pa",
            "system_static_pressure_pa",
            "pressure_residual_pa",
            "air_power_kw",
        )
    )
