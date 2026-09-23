from __future__ import annotations

import math
from dataclasses import dataclass

from .fan_curve import FanCurve
from .fan_speed import scale_fan_curve_for_speed
from .fan_variable_friction_loop import (
    FanVariableFrictionLoopStudy,
    solve_fan_variable_friction_loop,
)
from .loop_network import LoopedFlowNetwork


def _positive(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{field_name} must be finite and > 0")
    return value


@dataclass(frozen=True)
class FanVariableFrictionSpeedStudy:
    name: str
    reference_fan_curve: FanCurve
    loop_network: LoopedFlowNetwork
    fan_discharge_node: str
    fan_suction_node: str
    speed_ratios: tuple[float, ...]
    fixed_pressure_pa: float = 0.0
    reference_speed_rpm: float | None = None
    resistance_relative_tolerance: float = 1e-6
    relaxation: float = 0.5
    near_zero_airflow_m3_h: float = 1e-6
    max_outer_iterations: int = 50
    mass_balance_tolerance_m3_h: float = 1e-6
    max_newton_iterations: int = 100
    operating_pressure_tolerance_pa: float = 1e-6
    max_operating_iterations: int = 80

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError(
                "fan-speed/variable-friction loop study name cannot be empty"
            )
        if not self.speed_ratios:
            raise ValueError(
                "fan-speed/variable-friction loop study requires at least one "
                "speed ratio"
            )

        ratios = tuple(
            _positive(value, "speed ratio") for value in self.speed_ratios
        )
        if len(set(ratios)) != len(ratios):
            raise ValueError(
                "fan-speed/variable-friction loop speed ratios must be unique"
            )
        object.__setattr__(self, "speed_ratios", ratios)

        if self.reference_speed_rpm is not None:
            object.__setattr__(
                self,
                "reference_speed_rpm",
                _positive(self.reference_speed_rpm, "reference_speed_rpm"),
            )

        # Reuse the v0.33 study validation for topology, fixed pressure, and
        # every nonlinear solver control. This intentionally avoids creating
        # a second validation path for the coupled solver.
        validated = FanVariableFrictionLoopStudy(
            name=self.name,
            fan_curve=self.reference_fan_curve,
            loop_network=self.loop_network,
            fan_discharge_node=self.fan_discharge_node,
            fan_suction_node=self.fan_suction_node,
            fixed_pressure_pa=self.fixed_pressure_pa,
            resistance_relative_tolerance=self.resistance_relative_tolerance,
            relaxation=self.relaxation,
            near_zero_airflow_m3_h=self.near_zero_airflow_m3_h,
            max_outer_iterations=self.max_outer_iterations,
            mass_balance_tolerance_m3_h=self.mass_balance_tolerance_m3_h,
            max_newton_iterations=self.max_newton_iterations,
            operating_pressure_tolerance_pa=(
                self.operating_pressure_tolerance_pa
            ),
            max_operating_iterations=self.max_operating_iterations,
        )
        for field_name in (
            "fixed_pressure_pa",
            "resistance_relative_tolerance",
            "relaxation",
            "near_zero_airflow_m3_h",
            "max_outer_iterations",
            "mass_balance_tolerance_m3_h",
            "max_newton_iterations",
            "operating_pressure_tolerance_pa",
            "max_operating_iterations",
        ):
            object.__setattr__(
                self, field_name, getattr(validated, field_name)
            )


def _case_solver_study(
    study: FanVariableFrictionSpeedStudy,
    *,
    scaled_curve: FanCurve,
    ratio: float,
) -> FanVariableFrictionLoopStudy:
    return FanVariableFrictionLoopStudy(
        name=f"{study.name} @ {ratio:.6g}x",
        fan_curve=scaled_curve,
        loop_network=study.loop_network,
        fan_discharge_node=study.fan_discharge_node,
        fan_suction_node=study.fan_suction_node,
        fixed_pressure_pa=study.fixed_pressure_pa,
        resistance_relative_tolerance=study.resistance_relative_tolerance,
        relaxation=study.relaxation,
        near_zero_airflow_m3_h=study.near_zero_airflow_m3_h,
        max_outer_iterations=study.max_outer_iterations,
        mass_balance_tolerance_m3_h=study.mass_balance_tolerance_m3_h,
        max_newton_iterations=study.max_newton_iterations,
        operating_pressure_tolerance_pa=study.operating_pressure_tolerance_pa,
        max_operating_iterations=study.max_operating_iterations,
    )


def analyze_fan_variable_friction_speed_study(
    study: FanVariableFrictionSpeedStudy,
) -> dict:
    cases: list[dict] = []
    counts: dict[str, int] = {}

    for ratio in study.speed_ratios:
        scaled_curve = scale_fan_curve_for_speed(
            study.reference_fan_curve,
            ratio,
        )
        solved = solve_fan_variable_friction_loop(
            _case_solver_study(
                study,
                scaled_curve=scaled_curve,
                ratio=ratio,
            )
        )
        status = solved["status"]
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
                "scaled_fan_curve": scaled_curve.name,
                "scaled_fan_curve_airflow_range_m3_h": [
                    round(scaled_curve.points[0].airflow_m3_h, 6),
                    round(scaled_curve.points[-1].airflow_m3_h, 6),
                ],
                "status": status,
                "fan_operating_point": solved["fan_operating_point"],
                "operating_network_solution": (
                    solved["operating_network_solution"]
                ),
                "system_pressure_check": solved["system_pressure_check"],
                "fan_curve_point_checks": solved["fan_curve_point_checks"],
                "solver_diagnostics": solved["solver_diagnostics"],
                "solver_message": solved["message"],
            }
        )

    unresolved_count = sum(
        count
        for status, count in counts.items()
        if status != "solved"
    )
    return {
        "study": study.name,
        "reference_fan_curve": study.reference_fan_curve.name,
        "loop_network": study.loop_network.name,
        "fan_discharge_node": study.fan_discharge_node,
        "fan_suction_node": study.fan_suction_node,
        "fixed_pressure_pa": round(study.fixed_pressure_pa, 6),
        "reference_speed_rpm": study.reference_speed_rpm,
        "status": (
            "screening_complete"
            if unresolved_count == 0
            else "attention_required"
        ),
        "counts": counts,
        "speed_case_count": len(cases),
        "unresolved_speed_case_count": unresolved_count,
        "speed_cases": cases,
        "scope_note": (
            "Each case transforms only the supplied reference fan-curve "
            "points using the existing CleanroomX fan affinity-law "
            "implementation, then delegates the operating-point calculation "
            "to the bounded fan/variable-friction loop solver. The complete "
            "loop network is re-solved at every evaluated airflow and "
            "automatic Darcy friction is recomputed from solved branch flow. "
            "Every transformed fan curve remains bounded by its transformed "
            "supplied points and is never extrapolated. Speed cases preserve "
            "solved, no-intersection, and non-converged states independently. "
            "No acceptable VFD range, motor limit, efficiency, damper/control "
            "action, system effect, stall/surge acceptance, or manufacturer "
            "selection is inferred."
        ),
    }
