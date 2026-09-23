from __future__ import annotations

import math
from dataclasses import dataclass


def _finite(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite")
    return value


def _nonnegative(value: float, field_name: str) -> float:
    value = _finite(value, field_name)
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return value


def _positive(value: float, field_name: str) -> float:
    value = _finite(value, field_name)
    if value <= 0:
        raise ValueError(f"{field_name} must be > 0")
    return value


@dataclass(frozen=True)
class FanCurvePoint:
    airflow_m3_h: float
    static_pressure_pa: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "airflow_m3_h",
            _nonnegative(self.airflow_m3_h, "airflow_m3_h"),
        )
        object.__setattr__(
            self,
            "static_pressure_pa",
            _nonnegative(self.static_pressure_pa, "static_pressure_pa"),
        )


@dataclass(frozen=True)
class FanStaticPressureCurve:
    name: str
    points: tuple[FanCurvePoint, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("fan-curve name cannot be empty")
        if len(self.points) < 2:
            raise ValueError("fan curve requires at least two points")

        for previous, current in zip(self.points, self.points[1:]):
            if current.airflow_m3_h <= previous.airflow_m3_h:
                raise ValueError(
                    "fan-curve airflow values must be strictly increasing"
                )
            if current.static_pressure_pa > previous.static_pressure_pa:
                raise ValueError(
                    "fan-curve static pressure must be non-increasing with airflow"
                )

    @property
    def min_airflow_m3_h(self) -> float:
        return self.points[0].airflow_m3_h

    @property
    def max_airflow_m3_h(self) -> float:
        return self.points[-1].airflow_m3_h


@dataclass(frozen=True)
class QuadraticSystemCurve:
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

    def pressure_pa(self, airflow_m3_s: float) -> float:
        airflow_m3_s = _nonnegative(airflow_m3_s, "airflow_m3_s")
        return (
            self.fixed_pressure_pa
            + self.resistance_pa_per_m3_s_squared * airflow_m3_s**2
        )


@dataclass(frozen=True)
class FanOperatingPointCase:
    name: str
    fan_curve: FanStaticPressureCurve
    system_curve: QuadraticSystemCurve

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("fan operating-point case name cannot be empty")


def _fan_pressure_on_segment(
    point_a: FanCurvePoint,
    point_b: FanCurvePoint,
    airflow_m3_s: float,
) -> float:
    q1 = point_a.airflow_m3_h / 3600.0
    q2 = point_b.airflow_m3_h / 3600.0
    slope = (point_b.static_pressure_pa - point_a.static_pressure_pa) / (q2 - q1)
    intercept = point_a.static_pressure_pa - slope * q1
    return slope * airflow_m3_s + intercept


def _segment_roots(
    point_a: FanCurvePoint,
    point_b: FanCurvePoint,
    system_curve: QuadraticSystemCurve,
) -> list[float]:
    q1 = point_a.airflow_m3_h / 3600.0
    q2 = point_b.airflow_m3_h / 3600.0
    slope = (point_b.static_pressure_pa - point_a.static_pressure_pa) / (q2 - q1)
    intercept = point_a.static_pressure_pa - slope * q1

    # R*Q^2 + P_fixed = slope*Q + intercept
    a = system_curve.resistance_pa_per_m3_s_squared
    b = -slope
    c = system_curve.fixed_pressure_pa - intercept
    discriminant = b * b - 4.0 * a * c

    scale = max(abs(b * b), abs(4.0 * a * c), 1.0)
    if discriminant < -1e-12 * scale:
        return []
    discriminant = max(discriminant, 0.0)
    sqrt_discriminant = math.sqrt(discriminant)

    roots = [
        (-b - sqrt_discriminant) / (2.0 * a),
        (-b + sqrt_discriminant) / (2.0 * a),
    ]
    tolerance = 1e-10 * max(1.0, abs(q1), abs(q2))
    return [
        root
        for root in roots
        if q1 - tolerance <= root <= q2 + tolerance and root >= -tolerance
    ]


def solve_fan_operating_point(case: FanOperatingPointCase) -> dict:
    """Find the fan/system intersection without extrapolating the fan curve."""
    candidates: list[tuple[float, int]] = []
    for index, (point_a, point_b) in enumerate(
        zip(case.fan_curve.points, case.fan_curve.points[1:])
    ):
        for root in _segment_roots(point_a, point_b, case.system_curve):
            root = max(root, 0.0)
            if not any(
                math.isclose(root, existing[0], rel_tol=1e-9, abs_tol=1e-10)
                for existing in candidates
            ):
                candidates.append((root, index))

    min_q = case.fan_curve.min_airflow_m3_h / 3600.0
    max_q = case.fan_curve.max_airflow_m3_h / 3600.0
    min_fan_pressure = case.fan_curve.points[0].static_pressure_pa
    max_fan_pressure = case.fan_curve.points[-1].static_pressure_pa
    min_system_pressure = case.system_curve.pressure_pa(min_q)
    max_system_pressure = case.system_curve.pressure_pa(max_q)
    min_margin = min_fan_pressure - min_system_pressure
    max_margin = max_fan_pressure - max_system_pressure

    result = {
        "case": case.name,
        "fan_curve": case.fan_curve.name,
        "system_curve": case.system_curve.name,
        "fan_curve_airflow_range_m3_h": [
            round(case.fan_curve.min_airflow_m3_h, 3),
            round(case.fan_curve.max_airflow_m3_h, 3),
        ],
        "fixed_pressure_pa": round(case.system_curve.fixed_pressure_pa, 4),
        "resistance_pa_per_m3_s_squared": round(
            case.system_curve.resistance_pa_per_m3_s_squared, 6
        ),
        "fan_minus_system_pressure_at_min_flow_pa": round(min_margin, 6),
        "fan_minus_system_pressure_at_max_flow_pa": round(max_margin, 6),
        "operating_point": None,
    }

    if not candidates:
        if min_margin < 0:
            reason = (
                "System pressure is already above the fan curve at the minimum "
                "supplied airflow; no in-range intersection exists."
            )
        elif max_margin > 0:
            reason = (
                "Fan pressure remains above the system curve at the maximum "
                "supplied airflow; an operating point would require fan-curve "
                "extrapolation, which CleanroomX does not perform."
            )
        else:
            reason = "No intersection was found inside the supplied fan-curve range."
        return {
            **result,
            "status": "no_intersection",
            "reason": reason,
            "scope_note": _scope_note(),
        }

    if len(candidates) != 1:
        raise RuntimeError(
            "validated monotonic fan/system curves produced multiple intersections"
        )

    airflow_m3_s, segment_index = candidates[0]
    point_a = case.fan_curve.points[segment_index]
    point_b = case.fan_curve.points[segment_index + 1]
    fan_pressure = _fan_pressure_on_segment(point_a, point_b, airflow_m3_s)
    system_pressure = case.system_curve.pressure_pa(airflow_m3_s)
    pressure = (fan_pressure + system_pressure) / 2.0

    return {
        **result,
        "status": "solved",
        "reason": None,
        "operating_point": {
            "airflow_m3_h": round(airflow_m3_s * 3600.0, 3),
            "airflow_m3_s": round(airflow_m3_s, 9),
            "static_pressure_pa": round(pressure, 4),
            "fan_static_pressure_pa": round(fan_pressure, 4),
            "system_static_pressure_pa": round(system_pressure, 4),
            "pressure_residual_pa": round(fan_pressure - system_pressure, 9),
            "air_power_kw": round(airflow_m3_s * pressure / 1000.0, 6),
            "fan_curve_segment": segment_index + 1,
        },
        "scope_note": _scope_note(),
    }


def _scope_note() -> str:
    return (
        "The operating point is the intersection of user-supplied piecewise-linear "
        "fan static-pressure data and an explicit fixed-plus-quadratic system curve. "
        "CleanroomX does not extrapolate the fan curve or infer manufacturer data, "
        "fan speed laws, efficiency curves, motor input, variable friction factor, "
        "system effect, controls, leakage, or transient behavior."
    )
