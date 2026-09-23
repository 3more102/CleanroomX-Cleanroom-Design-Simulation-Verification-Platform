from __future__ import annotations

import math
from dataclasses import dataclass

from .fan_curve import FanCurve
from .fan_loop_network import FanLoopNetworkStudy, solve_fan_loop_network
from .fan_speed import scale_fan_curve_for_speed
from .loop_network import LoopedFlowNetwork


def _positive(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{field_name} must be finite and > 0")
    return value


@dataclass(frozen=True)
class FanLoopSpeedStudy:
    name: str
    reference_fan_curve: FanCurve
    loop_network: LoopedFlowNetwork
    fan_discharge_node: str
    fan_suction_node: str
    speed_ratios: tuple[float, ...]
    fixed_pressure_pa: float = 0.0
    reference_speed_rpm: float | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("fan/loop speed-study name cannot be empty")
        if not self.speed_ratios:
            raise ValueError("fan/loop speed-study requires at least one speed ratio")

        ratios = tuple(_positive(value, "speed ratio") for value in self.speed_ratios)
        if len(set(ratios)) != len(ratios):
            raise ValueError("fan/loop speed-study speed ratios must be unique")
        object.__setattr__(self, "speed_ratios", ratios)

        if self.reference_speed_rpm is not None:
            object.__setattr__(
                self,
                "reference_speed_rpm",
                _positive(self.reference_speed_rpm, "reference_speed_rpm"),
            )

        # Reuse v0.26 validation for the passive two-terminal loop and fixed pressure.
        validated = FanLoopNetworkStudy(
            name=self.name,
            fan_curve=self.reference_fan_curve,
            loop_network=self.loop_network,
            fan_discharge_node=self.fan_discharge_node,
            fan_suction_node=self.fan_suction_node,
            fixed_pressure_pa=self.fixed_pressure_pa,
        )
        object.__setattr__(self, "fixed_pressure_pa", validated.fixed_pressure_pa)


def analyze_fan_loop_speed_study(study: FanLoopSpeedStudy) -> dict:
    cases: list[dict] = []
    counts: dict[str, int] = {}
    reference_network_solution: dict | None = None

    for ratio in study.speed_ratios:
        scaled_curve = scale_fan_curve_for_speed(study.reference_fan_curve, ratio)
        solved = solve_fan_loop_network(
            FanLoopNetworkStudy(
                name=f"{study.name} @ {ratio:.6g}x",
                fan_curve=scaled_curve,
                loop_network=study.loop_network,
                fan_discharge_node=study.fan_discharge_node,
                fan_suction_node=study.fan_suction_node,
                fixed_pressure_pa=study.fixed_pressure_pa,
            )
        )
        if reference_network_solution is None:
            reference_network_solution = solved["reference_network_solution"]

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
                    round(scaled_curve.points[0].airflow_m3_h, 3),
                    round(scaled_curve.points[-1].airflow_m3_h, 3),
                ],
                "status": status,
                "equivalent_loop_resistance_pa_per_m3_s_squared": solved[
                    "equivalent_loop_resistance_pa_per_m3_s_squared"
                ],
                "fan_operating_point": solved["fan_operating_point"],
                "operating_network_solution": solved["operating_network_solution"],
                "system_pressure_check": solved["system_pressure_check"],
                "fan_curve_point_checks": solved["fan_curve_point_checks"],
                "solver_message": solved["message"],
            }
        )

    unresolved = counts.get("no_intersection_in_supplied_range", 0)
    return {
        "study": study.name,
        "reference_fan_curve": study.reference_fan_curve.name,
        "loop_network": study.loop_network.name,
        "fan_discharge_node": study.fan_discharge_node,
        "fan_suction_node": study.fan_suction_node,
        "fixed_pressure_pa": round(study.fixed_pressure_pa, 6),
        "reference_speed_rpm": study.reference_speed_rpm,
        "status": "attention_required" if unresolved else "screening_complete",
        "counts": counts,
        "speed_case_count": len(cases),
        "reference_network_solution": reference_network_solution,
        "speed_cases": cases,
        "scope_note": (
            "Each case applies the fan affinity laws only to the supplied reference "
            "fan-curve points, then reuses the bounded fixed-resistance fan/loop-network "
            "solver. Airflow scales with speed ratio, pressure with speed ratio squared, "
            "and the reported cubic factor is only the homologous fan-power scaling "
            "indicator. The transformed fan curve is never extrapolated. Loop edge "
            "resistance remains fixed at its declared basis; geometry-derived automatic "
            "friction is not iterated with operating flow. No acceptable speed range, "
            "motor/VFD limit, efficiency, damper/control action, leakage, system effect, "
            "stall/surge acceptance, compressibility, transient response, or manufacturer "
            "selection is inferred."
        ),
    }
