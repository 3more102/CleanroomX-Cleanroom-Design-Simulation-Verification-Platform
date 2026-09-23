from __future__ import annotations

import math
from dataclasses import dataclass

from .fan_curve import FanCurve, FanOperatingPointStudy, SystemCurve, solve_fan_operating_point


def _finite_in_range(value: float, field_name: str, low: float, high: float) -> float:
    value = float(value)
    if not math.isfinite(value) or value < low or value > high:
        raise ValueError(
            f"{field_name} must be finite and between {low:g} and {high:g}"
        )
    return value


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
class FanControlState:
    name: str
    control_signal_percent: float
    fan_curve: FanCurve

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("fan-control state name cannot be empty")
        object.__setattr__(
            self,
            "control_signal_percent",
            _finite_in_range(
                self.control_signal_percent,
                "control_signal_percent",
                0.0,
                100.0,
            ),
        )


@dataclass(frozen=True)
class FanControlStudy:
    name: str
    system_curve: SystemCurve
    states: tuple[FanControlState, ...]
    target_airflow_m3_h: float | None = None
    target_tolerance_m3_h: float = 0.0

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("fan-control study name cannot be empty")
        if len(self.states) < 2:
            raise ValueError("fan-control study requires at least two control states")
        if len({state.name for state in self.states}) != len(self.states):
            raise ValueError("fan-control state names must be unique")
        for previous, current in zip(self.states, self.states[1:]):
            if current.control_signal_percent <= previous.control_signal_percent:
                raise ValueError(
                    "control_signal_percent values must be strictly increasing"
                )

        tolerance = _nonnegative(
            self.target_tolerance_m3_h, "target_tolerance_m3_h"
        )
        object.__setattr__(self, "target_tolerance_m3_h", tolerance)
        if self.target_airflow_m3_h is None:
            if tolerance != 0:
                raise ValueError(
                    "target_tolerance_m3_h requires target_airflow_m3_h"
                )
        else:
            target = _positive(self.target_airflow_m3_h, "target_airflow_m3_h")
            if tolerance > target:
                raise ValueError(
                    "target_tolerance_m3_h cannot exceed target_airflow_m3_h"
                )
            object.__setattr__(self, "target_airflow_m3_h", target)


def _target_state(
    airflow_m3_h: float,
    target_airflow_m3_h: float | None,
    target_tolerance_m3_h: float,
) -> tuple[str, float | None]:
    if target_airflow_m3_h is None:
        return "not_checked", None

    error = airflow_m3_h - target_airflow_m3_h
    low = target_airflow_m3_h - target_tolerance_m3_h
    high = target_airflow_m3_h + target_tolerance_m3_h
    if airflow_m3_h < low:
        return "below_target_band", error
    if airflow_m3_h > high:
        return "above_target_band", error
    return "within_target_band", error


def analyze_fan_control_study(study: FanControlStudy) -> dict:
    """Evaluate explicit fan curves at ordered discrete control states.

    Every state is solved independently against one explicit system curve. The
    analysis does not scale fan curves, interpolate between control states, or
    infer controller dynamics.
    """
    state_results: list[dict] = []
    solved_airflows: list[tuple[float, float, str]] = []

    for state in study.states:
        operating = solve_fan_operating_point(
            FanOperatingPointStudy(
                name=f"{study.name} — {state.name}",
                fan_curve=state.fan_curve,
                system_curve=study.system_curve,
            )
        )
        point = operating["operating_point"]
        if point is None:
            target_status = "not_comparable"
            airflow_error = None
        else:
            airflow = float(point["airflow_m3_h"])
            target_status, airflow_error = _target_state(
                airflow,
                study.target_airflow_m3_h,
                study.target_tolerance_m3_h,
            )
            solved_airflows.append(
                (state.control_signal_percent, airflow, state.name)
            )

        state_results.append(
            {
                "state": state.name,
                "control_signal_percent": round(state.control_signal_percent, 3),
                "fan_curve": state.fan_curve.name,
                "status": operating["status"],
                "target_status": target_status,
                "airflow_error_m3_h": (
                    None if airflow_error is None else round(airflow_error, 3)
                ),
                "fan_operating_point": operating,
            }
        )

    unresolved_count = sum(
        1 for item in state_results if item["status"] != "solved"
    )
    if len(solved_airflows) < 2:
        monotonic = None
    else:
        monotonic = all(
            current[1] >= previous[1] - 1e-9
            for previous, current in zip(
                solved_airflows, solved_airflows[1:]
            )
        )

    target_band = None
    target_status = "not_checked"
    closest = None
    if study.target_airflow_m3_h is not None:
        target_band = [
            round(
                study.target_airflow_m3_h - study.target_tolerance_m3_h,
                3,
            ),
            round(
                study.target_airflow_m3_h + study.target_tolerance_m3_h,
                3,
            ),
        ]
        target_status = (
            "target_met"
            if any(
                item["target_status"] == "within_target_band"
                for item in state_results
            )
            else "target_not_met"
        )
        solved_items = [
            item
            for item in state_results
            if item["airflow_error_m3_h"] is not None
        ]
        if solved_items:
            item = min(
                solved_items,
                key=lambda row: abs(row["airflow_error_m3_h"]),
            )
            point = item["fan_operating_point"]["operating_point"]
            closest = {
                "state": item["state"],
                "control_signal_percent": item["control_signal_percent"],
                "airflow_m3_h": point["airflow_m3_h"],
                "airflow_error_m3_h": item["airflow_error_m3_h"],
                "target_status": item["target_status"],
            }

    analysis_status = (
        "attention_required"
        if unresolved_count > 0 or monotonic is False
        else "screening_complete"
    )

    return {
        "study": study.name,
        "system_curve": study.system_curve.name,
        "analysis_status": analysis_status,
        "target_status": target_status,
        "target_airflow_m3_h": (
            None
            if study.target_airflow_m3_h is None
            else round(study.target_airflow_m3_h, 3)
        ),
        "target_tolerance_m3_h": round(
            study.target_tolerance_m3_h, 3
        ),
        "target_band_m3_h": target_band,
        "unresolved_state_count": unresolved_count,
        "response_monotonic_non_decreasing": monotonic,
        "closest_solved_state": closest,
        "states": state_results,
        "scope_note": (
            "Each control state uses an explicit supplied fan curve and the shared "
            "fixed-plus-quadratic system curve. CleanroomX does not scale fan curves "
            "with fan laws, interpolate between control signals, infer VFD/controller "
            "dynamics, electrical power, stall/surge limits, or manufacturer acceptance."
        ),
    }
