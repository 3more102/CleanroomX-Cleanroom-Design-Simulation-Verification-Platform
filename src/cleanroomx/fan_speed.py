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
class FanSpeedSweepStudy:
    name: str
    reference_fan_curve: FanCurve
    system_curve: SystemCurve
    speed_ratios: tuple[float, ...]
    reference_speed_rpm: float | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("fan-speed sweep study name cannot be empty")
        if not self.speed_ratios:
            raise ValueError("fan-speed sweep requires at least one speed ratio")

        ratios = tuple(
            _positive(ratio, "speed_ratio") for ratio in self.speed_ratios
        )
        if len(ratios) != len(set(ratios)):
            raise ValueError("fan-speed sweep speed ratios must be unique")
        object.__setattr__(self, "speed_ratios", ratios)

        if self.reference_speed_rpm is not None:
            object.__setattr__(
                self,
                "reference_speed_rpm",
                _positive(self.reference_speed_rpm, "reference_speed_rpm"),
            )


def scale_fan_curve_by_speed(
    fan_curve: FanCurve,
    speed_ratio: float,
) -> FanCurve:
    ratio = _positive(speed_ratio, "speed_ratio")
    pressure_ratio = ratio**2
    return FanCurve(
        name=f"{fan_curve.name} @ {ratio:.6g}x speed",
        points=tuple(
            FanCurvePoint(
                airflow_m3_h=point.airflow_m3_h * ratio,
                pressure_pa=point.pressure_pa * pressure_ratio,
            )
            for point in fan_curve.points
        ),
    )


def analyze_fan_speed_sweep(study: FanSpeedSweepStudy) -> dict:
    cases: list[dict] = []

    for ratio in study.speed_ratios:
        scaled_curve = scale_fan_curve_by_speed(
            study.reference_fan_curve,
            ratio,
        )
        fan_result = solve_fan_operating_point(
            FanOperatingPointStudy(
                name=f"{study.name} @ {ratio:.6g}x speed",
                fan_curve=scaled_curve,
                system_curve=study.system_curve,
            )
        )
        cases.append(
            {
                "speed_ratio": round(ratio, 6),
                "speed_percent": round(ratio * 100.0, 3),
                "speed_rpm": (
                    round(study.reference_speed_rpm * ratio, 3)
                    if study.reference_speed_rpm is not None
                    else None
                ),
                "fan_law_power_ratio_to_reference": round(ratio**3, 6),
                "scaled_fan_curve_airflow_range_m3_h": fan_result[
                    "fan_curve_airflow_range_m3_h"
                ],
                "status": fan_result["status"],
                "operating_point": fan_result["operating_point"],
                "message": fan_result["message"],
            }
        )

    solved_count = sum(case["status"] == "solved" for case in cases)
    return {
        "study": study.name,
        "reference_fan_curve": study.reference_fan_curve.name,
        "system_curve": study.system_curve.name,
        "reference_speed_rpm": (
            round(study.reference_speed_rpm, 3)
            if study.reference_speed_rpm is not None
            else None
        ),
        "status": "complete" if solved_count == len(cases) else "partial",
        "solved_case_count": solved_count,
        "case_count": len(cases),
        "cases": cases,
        "scope_note": (
            "Each case is a steady-state affinity-law screening calculation for the "
            "same fan diameter and nominal gas density. Airflow coordinates are scaled "
            "with speed ratio N2/N1 and pressure coordinates with (N2/N1)^2 before the "
            "existing bounded fan/system solver is reused. The reported cubic power "
            "ratio is the ideal fan-law ratio only; it is not an electrical-power or "
            "energy prediction. This workflow does not model efficiency changes, motor "
            "or VFD losses, dynamic control response, PID stability, dampers, system "
            "effect, stall/surge limits, variable friction, or manufacturer acceptance. "
            "Measured multi-speed fan data should be preferred when available."
        ),
    }
