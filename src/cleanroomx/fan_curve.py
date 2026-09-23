from __future__ import annotations

import math
from dataclasses import dataclass


def _nonnegative(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{field_name} must be finite and >= 0")
    return value


def _positive(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{field_name} must be finite and > 0")
    return value


@dataclass(frozen=True)
class FanCurvePoint:
    airflow_m3_h: float
    pressure_pa: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "airflow_m3_h", _nonnegative(self.airflow_m3_h, "airflow_m3_h")
        )
        object.__setattr__(
            self, "pressure_pa", _nonnegative(self.pressure_pa, "pressure_pa")
        )


@dataclass(frozen=True)
class FanCurve:
    name: str
    points: tuple[FanCurvePoint, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("fan-curve name cannot be empty")
        if len(self.points) < 2:
            raise ValueError("fan curve requires at least two points")

        for previous, current in zip(self.points, self.points[1:]):
            if current.airflow_m3_h <= previous.airflow_m3_h:
                raise ValueError("fan-curve airflow points must be strictly increasing")
            if current.pressure_pa > previous.pressure_pa:
                raise ValueError(
                    "fan-curve pressure must be non-increasing with airflow"
                )


@dataclass(frozen=True)
class SystemCurve:
    name: str
    fixed_pressure_pa: float
    resistance_pa_per_m3_s_squared: float

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("system-curve name cannot be empty")
        object.__setattr__(
            self,
            "fixed_pressure_pa",
            _nonnegative(self.fixed_pressure_pa, "fixed_pressure_pa"),
        )
        object.__setattr__(
            self,
            "resistance_pa_per_m3_s_squared",
            _positive(
                self.resistance_pa_per_m3_s_squared,
                "resistance_pa_per_m3_s_squared",
            ),
        )

    def pressure_at(self, airflow_m3_h: float) -> float:
        airflow_m3_h = _nonnegative(airflow_m3_h, "airflow_m3_h")
        airflow_m3_s = airflow_m3_h / 3600.0
        return (
            self.fixed_pressure_pa
            + self.resistance_pa_per_m3_s_squared * airflow_m3_s**2
        )


@dataclass(frozen=True)
class FanOperatingPointStudy:
    name: str
    fan_curve: FanCurve
    system_curve: SystemCurve

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("operating-point study name cannot be empty")


def _interpolated_fan_pressure(
    left: FanCurvePoint,
    right: FanCurvePoint,
    airflow_m3_h: float,
) -> float:
    fraction = (
        (airflow_m3_h - left.airflow_m3_h)
        / (right.airflow_m3_h - left.airflow_m3_h)
    )
    return left.pressure_pa + fraction * (right.pressure_pa - left.pressure_pa)


def check_fan_duty_against_curve(
    fan_curve: FanCurve,
    required_airflow_m3_h: float,
    required_pressure_pa: float,
) -> dict:
    """Check whether a supplied fan curve meets one explicit HVAC design duty.

    The check interpolates only inside the supplied fan-curve range. It does not
    construct a system curve, extrapolate fan data, or infer manufacturer limits.
    """
    airflow = _positive(required_airflow_m3_h, "required_airflow_m3_h")
    pressure = _nonnegative(required_pressure_pa, "required_pressure_pa")
    points = fan_curve.points
    low = points[0].airflow_m3_h
    high = points[-1].airflow_m3_h

    base = {
        "fan_curve": fan_curve.name,
        "required_airflow_m3_h": round(airflow, 3),
        "required_pressure_pa": round(pressure, 4),
        "fan_curve_airflow_range_m3_h": [round(low, 3), round(high, 3)],
    }

    if airflow < low or airflow > high:
        return {
            **base,
            "status": "outside_supplied_range",
            "passes_required_duty": None,
            "available_fan_pressure_pa": None,
            "pressure_margin_pa": None,
            "interpolation_segment": None,
            "message": (
                "Required airflow lies outside the supplied fan-curve range; "
                "no fan-curve extrapolation is performed."
            ),
            "scope_note": (
                "This is a design-point pressure-capability screen using only "
                "piecewise-linear interpolation between supplied fan data points. "
                "It is not a fan/system operating-point solution and does not infer "
                "stall/surge limits, fan-law scaling, system effect, controls, or "
                "manufacturer selection."
            ),
        }

    segment_index = len(points) - 2
    for index, (left, right) in enumerate(zip(points, points[1:])):
        if left.airflow_m3_h <= airflow <= right.airflow_m3_h:
            segment_index = index
            break

    left = points[segment_index]
    right = points[segment_index + 1]
    available = _interpolated_fan_pressure(left, right, airflow)
    margin = available - pressure
    tolerance_pa = 1e-9
    passes = margin >= -tolerance_pa

    return {
        **base,
        "status": "pass" if passes else "fail",
        "passes_required_duty": passes,
        "available_fan_pressure_pa": round(available, 4),
        "pressure_margin_pa": round(margin, 4),
        "interpolation_segment": {
            "low_airflow_m3_h": round(left.airflow_m3_h, 3),
            "high_airflow_m3_h": round(right.airflow_m3_h, 3),
        },
        "message": (
            "Supplied fan-curve pressure meets the required HVAC design duty."
            if passes
            else "Supplied fan-curve pressure is below the required HVAC design duty."
        ),
        "scope_note": (
            "This is a design-point pressure-capability screen using only "
            "piecewise-linear interpolation between supplied fan data points. It is "
            "not a fan/system operating-point solution and does not infer stall/surge "
            "limits, fan-law scaling, system effect, controls, or manufacturer selection."
        ),
    }


def solve_fan_operating_point(study: FanOperatingPointStudy) -> dict:
    points = study.fan_curve.points
    residuals = [
        point.pressure_pa - study.system_curve.pressure_at(point.airflow_m3_h)
        for point in points
    ]

    solution: tuple[float, float, int] | None = None
    tolerance_pa = 1e-9

    for index, residual in enumerate(residuals):
        if abs(residual) <= tolerance_pa:
            point = points[index]
            segment_index = min(index, len(points) - 2)
            solution = (point.airflow_m3_h, point.pressure_pa, segment_index)
            break

    if solution is None:
        for index, (left, right) in enumerate(zip(points, points[1:])):
            left_residual = residuals[index]
            right_residual = residuals[index + 1]
            if left_residual > 0 and right_residual < 0:
                low = left.airflow_m3_h
                high = right.airflow_m3_h
                for _ in range(80):
                    mid = 0.5 * (low + high)
                    fan_pressure = _interpolated_fan_pressure(left, right, mid)
                    system_pressure = study.system_curve.pressure_at(mid)
                    if fan_pressure - system_pressure > 0:
                        low = mid
                    else:
                        high = mid
                airflow = 0.5 * (low + high)
                fan_pressure = _interpolated_fan_pressure(left, right, airflow)
                solution = (airflow, fan_pressure, index)
                break

    system_at_points = [
        {
            "airflow_m3_h": round(point.airflow_m3_h, 3),
            "fan_pressure_pa": round(point.pressure_pa, 4),
            "system_pressure_pa": round(
                study.system_curve.pressure_at(point.airflow_m3_h), 4
            ),
            "pressure_margin_pa": round(residual, 4),
        }
        for point, residual in zip(points, residuals)
    ]

    base = {
        "study": study.name,
        "fan_curve": study.fan_curve.name,
        "system_curve": study.system_curve.name,
        "fan_curve_airflow_range_m3_h": [
            round(points[0].airflow_m3_h, 3),
            round(points[-1].airflow_m3_h, 3),
        ],
        "system_model": {
            "fixed_pressure_pa": round(study.system_curve.fixed_pressure_pa, 4),
            "resistance_pa_per_m3_s_squared": round(
                study.system_curve.resistance_pa_per_m3_s_squared, 6
            ),
        },
        "curve_point_checks": system_at_points,
    }

    if solution is None:
        if residuals[0] < 0:
            reason = (
                "System pressure exceeds fan pressure at the lowest supplied airflow "
                "point. No lower-flow extrapolation is performed."
            )
        else:
            reason = (
                "Fan pressure remains above system pressure at the highest supplied "
                "airflow point. No higher-flow extrapolation is performed."
            )
        return {
            **base,
            "status": "no_intersection_in_supplied_range",
            "operating_point": None,
            "message": reason,
            "scope_note": (
                "Fan pressure is linearly interpolated only between supplied curve "
                "points. System pressure is fixed_pressure + R*Q^2 with constant R. "
                "No fan-curve extrapolation, fan-law scaling, variable resistance, "
                "stall/surge assessment, system-effect correction, or manufacturer "
                "selection is inferred."
            ),
        }

    airflow_m3_h, fan_pressure_pa, segment_index = solution
    system_pressure_pa = study.system_curve.pressure_at(airflow_m3_h)
    airflow_m3_s = airflow_m3_h / 3600.0
    air_power_kw = airflow_m3_s * system_pressure_pa / 1000.0
    left = points[segment_index]
    right = points[segment_index + 1]

    return {
        **base,
        "status": "solved",
        "operating_point": {
            "airflow_m3_h": round(airflow_m3_h, 3),
            "airflow_m3_s": round(airflow_m3_s, 6),
            "fan_pressure_pa": round(fan_pressure_pa, 4),
            "system_pressure_pa": round(system_pressure_pa, 4),
            "pressure_residual_pa": round(
                fan_pressure_pa - system_pressure_pa, 9
            ),
            "air_power_kw": round(air_power_kw, 6),
            "interpolation_segment": {
                "low_airflow_m3_h": round(left.airflow_m3_h, 3),
                "high_airflow_m3_h": round(right.airflow_m3_h, 3),
            },
        },
        "message": (
            "Operating point found within the supplied fan-curve range by "
            "piecewise-linear fan interpolation against the explicit system curve."
        ),
        "scope_note": (
            "Fan pressure is linearly interpolated only between supplied curve points. "
            "System pressure is fixed_pressure + R*Q^2 with constant R. Air power is "
            "Q times pressure and is not motor input power. No fan-curve extrapolation, "
            "fan-law scaling, variable resistance, stall/surge assessment, system-effect "
            "correction, or manufacturer selection is inferred."
        ),
    }
