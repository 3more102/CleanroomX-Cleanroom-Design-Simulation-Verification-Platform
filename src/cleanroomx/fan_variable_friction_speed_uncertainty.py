from __future__ import annotations

import math
from dataclasses import dataclass

from .fan_curve import FanCurve
from .fan_speed import scale_fan_curve_for_speed
from .fan_variable_friction_uncertainty import (
    FanVariableFrictionLoopUncertaintyStudy,
    analyze_fan_variable_friction_loop_uncertainty,
)
from .loop_network import LoopedFlowNetwork
from .pressure_power import FanPowerEfficiencies
from .uncertainty_models import Provenance, UncertainValue


def _positive(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{field_name} must be finite and > 0")
    return value


@dataclass(frozen=True)
class FanVariableFrictionSpeedUncertaintyStudy:
    name: str
    reference_fan_curve: FanCurve
    loop_network: LoopedFlowNetwork
    fan_discharge_node: str
    fan_suction_node: str
    speed_ratios: tuple[float, ...]
    fixed_pressure_pa: UncertainValue
    edge_local_loss_coefficient: dict[str, UncertainValue]
    fan_curve_provenance: Provenance | None = None
    reference_speed_rpm: float | None = None
    max_corner_cases: int = 256
    max_total_cases: int = 1024
    power_efficiencies: FanPowerEfficiencies | None = None
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
                "fan-speed/variable-friction uncertainty study name cannot be empty"
            )
        if not self.speed_ratios:
            raise ValueError(
                "fan-speed/variable-friction uncertainty study requires at least "
                "one speed ratio"
            )
        ratios = tuple(_positive(value, "speed ratio") for value in self.speed_ratios)
        if len(set(ratios)) != len(ratios):
            raise ValueError(
                "fan-speed/variable-friction uncertainty speed ratios must be unique"
            )
        object.__setattr__(self, "speed_ratios", ratios)

        if self.reference_speed_rpm is not None:
            object.__setattr__(
                self,
                "reference_speed_rpm",
                _positive(self.reference_speed_rpm, "reference_speed_rpm"),
            )
        if (
            isinstance(self.max_total_cases, bool)
            or not isinstance(self.max_total_cases, int)
            or self.max_total_cases <= 0
        ):
            raise ValueError("max_total_cases must be an integer > 0")

        validated = FanVariableFrictionLoopUncertaintyStudy(
            name=self.name,
            fan_curve=self.reference_fan_curve,
            loop_network=self.loop_network,
            fan_discharge_node=self.fan_discharge_node,
            fan_suction_node=self.fan_suction_node,
            fixed_pressure_pa=self.fixed_pressure_pa,
            edge_local_loss_coefficient=self.edge_local_loss_coefficient,
            fan_curve_provenance=self.fan_curve_provenance,
            max_corner_cases=self.max_corner_cases,
            power_efficiencies=self.power_efficiencies,
            resistance_relative_tolerance=self.resistance_relative_tolerance,
            relaxation=self.relaxation,
            near_zero_airflow_m3_h=self.near_zero_airflow_m3_h,
            max_outer_iterations=self.max_outer_iterations,
            mass_balance_tolerance_m3_h=self.mass_balance_tolerance_m3_h,
            max_newton_iterations=self.max_newton_iterations,
            operating_pressure_tolerance_pa=self.operating_pressure_tolerance_pa,
            max_operating_iterations=self.max_operating_iterations,
        )
        for field_name in (
            "max_corner_cases",
            "resistance_relative_tolerance",
            "relaxation",
            "near_zero_airflow_m3_h",
            "max_outer_iterations",
            "mass_balance_tolerance_m3_h",
            "max_newton_iterations",
            "operating_pressure_tolerance_pa",
            "max_operating_iterations",
        ):
            object.__setattr__(self, field_name, getattr(validated, field_name))


def _case_study(
    study: FanVariableFrictionSpeedUncertaintyStudy,
    *,
    scaled_curve: FanCurve,
    ratio: float,
) -> FanVariableFrictionLoopUncertaintyStudy:
    return FanVariableFrictionLoopUncertaintyStudy(
        name=f"{study.name} @ {ratio:.6g}x",
        fan_curve=scaled_curve,
        loop_network=study.loop_network,
        fan_discharge_node=study.fan_discharge_node,
        fan_suction_node=study.fan_suction_node,
        fixed_pressure_pa=study.fixed_pressure_pa,
        edge_local_loss_coefficient=study.edge_local_loss_coefficient,
        fan_curve_provenance=study.fan_curve_provenance,
        max_corner_cases=study.max_corner_cases,
        power_efficiencies=study.power_efficiencies,
        resistance_relative_tolerance=study.resistance_relative_tolerance,
        relaxation=study.relaxation,
        near_zero_airflow_m3_h=study.near_zero_airflow_m3_h,
        max_outer_iterations=study.max_outer_iterations,
        mass_balance_tolerance_m3_h=study.mass_balance_tolerance_m3_h,
        max_newton_iterations=study.max_newton_iterations,
        operating_pressure_tolerance_pa=study.operating_pressure_tolerance_pa,
        max_operating_iterations=study.max_operating_iterations,
    )


def _uncertainty_corner_count(
    study: FanVariableFrictionSpeedUncertaintyStudy,
) -> int:
    count = len({study.fixed_pressure_pa.lower, study.fixed_pressure_pa.upper})
    for item in study.edge_local_loss_coefficient.values():
        count *= len({item.lower, item.upper})
    return count


def analyze_fan_variable_friction_speed_uncertainty(
    study: FanVariableFrictionSpeedUncertaintyStudy,
) -> dict:
    uncertainty_corner_count = _uncertainty_corner_count(study)
    total_case_count = uncertainty_corner_count * len(study.speed_ratios)
    if total_case_count > study.max_total_cases:
        raise ValueError(
            "fan-speed/variable-friction uncertainty total case count "
            f"{total_case_count} is exceeding max_total_cases="
            f"{study.max_total_cases}"
        )

    cases: list[dict] = []
    counts: dict[str, int] = {}
    for ratio in study.speed_ratios:
        scaled_curve = scale_fan_curve_for_speed(
            study.reference_fan_curve,
            ratio,
        )
        analysis = analyze_fan_variable_friction_loop_uncertainty(
            _case_study(study, scaled_curve=scaled_curve, ratio=ratio)
        )
        status = analysis["status"]
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
                "nominal_status": analysis["nominal_status"],
                "corner_count": analysis["corner_count"],
                "solved_corner_count": analysis["solved_corner_count"],
                "unresolved_corner_count": analysis["unresolved_corner_count"],
                "operating_point_envelope": analysis["operating_point_envelope"],
                "edge_airflow_corner_ranges": analysis[
                    "edge_airflow_corner_ranges"
                ],
                "traceability": analysis["traceability"],
                "uncertainty_analysis": analysis,
            }
        )

    unresolved_speed_case_count = sum(
        count for status, count in counts.items() if status != "complete"
    )
    return {
        "study": study.name,
        "reference_fan_curve": study.reference_fan_curve.name,
        "loop_network": study.loop_network.name,
        "fan_discharge_node": study.fan_discharge_node,
        "fan_suction_node": study.fan_suction_node,
        "reference_speed_rpm": study.reference_speed_rpm,
        "status": (
            "screening_complete"
            if unresolved_speed_case_count == 0
            else "attention_required"
        ),
        "counts": counts,
        "speed_case_count": len(cases),
        "uncertainty_corner_count_per_speed": uncertainty_corner_count,
        "total_speed_corner_case_count": total_case_count,
        "unresolved_speed_case_count": unresolved_speed_case_count,
        "speed_cases": cases,
        "scope_note": (
            "Each explicit speed ratio first transforms only the supplied "
            "reference fan-curve points using the existing CleanroomX affinity-"
            "law implementation. The v0.37 bounded nonlinear uncertainty "
            "analysis is then run independently at that transformed speed: every "
            "fixed-pressure/local-loss corner rebuilds affected geometry evidence, "
            "re-solves the complete Darcy-friction network at every evaluated "
            "airflow, and never extrapolates beyond the transformed supplied fan "
            "curve. Complete envelopes are reported only when the nominal case and "
            "every uncertainty corner solve for that speed. Speed and uncertainty "
            "dimensions are explicit scenario/corner evidence, not statistical "
            "confidence bounds, control predictions, acceptable VFD limits, or "
            "manufacturer equipment selection."
        ),
    }
