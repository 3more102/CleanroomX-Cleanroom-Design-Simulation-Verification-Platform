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
class FanSpeedControlStudy:
    name: str
    reference_fan_curve: FanCurve
    system_curve: SystemCurve
    speed_ratios: tuple[float, ...]
    reference_speed_rpm: float | None = None
    required_airflow_m3_h: float | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("fan-speed control study name cannot be empty")
        if not self.speed_ratios:
            raise ValueError("fan-speed control study requires at least one speed ratio")

        ratios = tuple(_positive(value, "speed_ratio") for value in self.speed_ratios)
        if len(ratios) != len(set(ratios)):
            raise ValueError("speed ratios must be unique")
        object.__setattr__(self, "speed_ratios", ratios)

        if self.reference_speed_rpm is not None:
            object.__setattr__(
                self,
                "reference_speed_rpm",
                _positive(self.reference_speed_rpm, "reference_speed_rpm"),
            )
        if self.required_airflow_m3_h is not None:
            object.__setattr__(
                self,
                "required_airflow_m3_h",
                _positive(self.required_airflow_m3_h, "required_airflow_m3_h"),
            )


def scale_fan_curve_for_speed(
    reference_curve: FanCurve,
    speed_ratio: float,
) -> FanCurve:
    """Scale a reference fan curve using the simplified fan affinity laws.

    For the same fan geometry and comparable air conditions:
      Q2 = Q1 * r
      dP2 = dP1 * r^2

    The function does not infer whether a requested speed is mechanically,
    electrically, aerodynamically, or manufacturer-approved.
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


def analyze_fan_speed_control(study: FanSpeedControlStudy) -> dict:
    scenarios: list[dict] = []

    for ratio in study.speed_ratios:
        scaled_curve = scale_fan_curve_for_speed(study.reference_fan_curve, ratio)
        solved = solve_fan_operating_point(
            FanOperatingPointStudy(
                name=f"{study.name} @ {ratio:.6g}x speed",
                fan_curve=scaled_curve,
                system_curve=study.system_curve,
            )
        )
        point = solved["operating_point"]
        meets_required_airflow = None
        if study.required_airflow_m3_h is not None and point is not None:
            meets_required_airflow = (
                point["airflow_m3_h"] + 1e-9 >= study.required_airflow_m3_h
            )

        scenarios.append(
            {
                "speed_ratio": round(ratio, 6),
                "speed_percent": round(ratio * 100.0, 3),
                "speed_rpm": (
                    None
                    if study.reference_speed_rpm is None
                    else round(study.reference_speed_rpm * ratio, 3)
                ),
                "status": solved["status"],
                "scaled_fan_curve": scaled_curve.name,
                "scaled_curve_points": [
                    {
                        "airflow_m3_h": round(point.airflow_m3_h, 3),
                        "pressure_pa": round(point.pressure_pa, 4),
                    }
                    for point in scaled_curve.points
                ],
                "operating_point": point,
                "meets_required_airflow": meets_required_airflow,
                "message": solved["message"],
            }
        )

    solved_count = sum(item["status"] == "solved" for item in scenarios)
    unresolved_count = len(scenarios) - solved_count
    target_summary = None
    status = (
        "screening_complete"
        if unresolved_count == 0
        else "complete_with_unresolved_scenarios"
    )

    if study.required_airflow_m3_h is not None:
        meeting = [
            item
            for item in scenarios
            if item["meets_required_airflow"] is True
        ]
        if meeting:
            lowest = min(meeting, key=lambda item: item["speed_ratio"])
            target_summary = {
                "status": "met_in_tested_scenarios",
                "required_airflow_m3_h": round(study.required_airflow_m3_h, 3),
                "lowest_tested_speed_ratio_meeting_requirement": lowest["speed_ratio"],
                "lowest_tested_speed_percent_meeting_requirement": lowest["speed_percent"],
                "lowest_tested_speed_rpm_meeting_requirement": lowest["speed_rpm"],
            }
            status = "target_met_in_tested_scenarios"
        else:
            target_summary = {
                "status": "not_met_in_tested_scenarios",
                "required_airflow_m3_h": round(study.required_airflow_m3_h, 3),
                "lowest_tested_speed_ratio_meeting_requirement": None,
                "lowest_tested_speed_percent_meeting_requirement": None,
                "lowest_tested_speed_rpm_meeting_requirement": None,
            }
            status = "target_not_met_in_tested_scenarios"

    return {
        "study": study.name,
        "status": status,
        "reference_fan_curve": study.reference_fan_curve.name,
        "system_curve": study.system_curve.name,
        "reference_speed_rpm": (
            None
            if study.reference_speed_rpm is None
            else round(study.reference_speed_rpm, 3)
        ),
        "required_airflow_m3_h": (
            None
            if study.required_airflow_m3_h is None
            else round(study.required_airflow_m3_h, 3)
        ),
        "scenario_count": len(scenarios),
        "solved_scenario_count": solved_count,
        "unresolved_scenario_count": unresolved_count,
        "target_summary": target_summary,
        "scenarios": scenarios,
        "scope_note": (
            "Each scenario scales the supplied reference fan curve with the simplified "
            "fan affinity laws Q proportional to speed and pressure proportional to "
            "speed squared, then solves the unchanged explicit system curve only inside "
            "the scaled fan-curve range. Speed ratios are user-supplied scenarios, not "
            "manufacturer-approved limits. CleanroomX does not infer motor/VFD limits, "
            "fan efficiency, density corrections, compressibility, stall/surge margins, "
            "structural speed limits, control stability, or equipment acceptance."
        ),
    }
