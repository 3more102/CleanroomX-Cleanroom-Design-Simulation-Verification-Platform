from __future__ import annotations

import math
from dataclasses import dataclass

from .fan_curve import (
    FanCurve,
    FanCurvePoint,
    FanOperatingPointStudy,
    SystemCurve,
    solve_fan_operating_point,
)


def _positive(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{field_name} must be finite and > 0")
    return value


@dataclass(frozen=True)
class FanSpeedStudy:
    name: str
    reference_fan_curve: FanCurve
    system_curve: SystemCurve
    speed_ratios: tuple[float, ...]
    reference_speed_rpm: float | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("fan-speed study name cannot be empty")
        if not self.speed_ratios:
            raise ValueError("fan-speed study requires at least one speed ratio")

        ratios = tuple(
            _positive(value, "speed ratio") for value in self.speed_ratios
        )
        if len(set(ratios)) != len(ratios):
            raise ValueError("fan-speed study speed ratios must be unique")
        object.__setattr__(self, "speed_ratios", ratios)

        if self.reference_speed_rpm is not None:
            object.__setattr__(
                self,
                "reference_speed_rpm",
                _positive(self.reference_speed_rpm, "reference_speed_rpm"),
            )


def scale_fan_curve_for_speed(
    reference_curve: FanCurve,
    speed_ratio: float,
) -> FanCurve:
    """Scale a supplied reference fan curve using the fan affinity laws.

    Airflow scales with speed ratio and pressure scales with speed ratio squared.
    The returned curve is still bounded by the transformed supplied points.
    """
    ratio = _positive(speed_ratio, "speed_ratio")
    return FanCurve(
        name=f"{reference_curve.name} @ {ratio:.6g}x speed",
        points=tuple(
            FanCurvePoint(
                airflow_m3_h=point.airflow_m3_h * ratio,
                pressure_pa=point.pressure_pa * ratio**2,
            )
            for point in reference_curve.points
        ),
    )


def analyze_fan_speed_study(study: FanSpeedStudy) -> dict:
    cases: list[dict] = []
    counts: dict[str, int] = {}

    for ratio in study.speed_ratios:
        scaled_curve = scale_fan_curve_for_speed(
            study.reference_fan_curve,
            ratio,
        )
        solver = solve_fan_operating_point(
            FanOperatingPointStudy(
                name=f"{study.name} @ {ratio:.6g}x",
                fan_curve=scaled_curve,
                system_curve=study.system_curve,
            )
        )
        status = solver["status"]
        counts[status] = counts.get(status, 0) + 1
        cases.append(
            {
                "speed_ratio": round(ratio, 6),
                "speed_rpm": (
                    round(study.reference_speed_rpm * ratio, 3)
                    if study.reference_speed_rpm is not None
                    else None
                ),
                "affinity_scaling": {
                    "airflow_ratio": round(ratio, 6),
                    "pressure_ratio": round(ratio**2, 6),
                    "homologous_input_power_factor": round(ratio**3, 6),
                },
                "scaled_fan_curve_airflow_range_m3_h": (
                    solver["fan_curve_airflow_range_m3_h"]
                ),
                "status": status,
                "operating_point": solver["operating_point"],
                "solver_message": solver["message"],
            }
        )

    unresolved = counts.get("no_intersection_in_supplied_range", 0)
    return {
        "study": study.name,
        "reference_fan_curve": study.reference_fan_curve.name,
        "system_curve": study.system_curve.name,
        "reference_speed_rpm": study.reference_speed_rpm,
        "status": "attention_required" if unresolved else "screening_complete",
        "counts": counts,
        "speed_case_count": len(cases),
        "speed_cases": cases,
        "scope_note": (
            "Each case transforms only the supplied reference fan-curve points using "
            "the fan affinity laws: airflow proportional to speed, pressure proportional "
            "to speed squared, and theoretical fan-power scaling proportional to speed "
            "cubed. The transformed curve is intersected with the explicit fixed-plus-"
            "quadratic system curve using bounded piecewise-linear interpolation only. "
            "The reported Q*pressure air power is not motor input power, and the cubic "
            "power ratio is an affinity-law scaling indicator rather than a manufacturer "
            "efficiency or electrical-energy prediction. No fan-curve extrapolation, "
            "stall/surge acceptance, drive limits, motor limits, system-effect correction, "
            "or manufacturer selection is inferred."
        ),
    }
