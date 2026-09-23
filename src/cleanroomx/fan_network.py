from __future__ import annotations

import math
from dataclasses import dataclass

from .duct_flow import (
    ParallelFlowNetwork,
    ParallelFlowPath,
    solve_parallel_branch_flows,
)
from .fan_curve import FanCurve, FanOperatingPointStudy, SystemCurve, solve_fan_operating_point


def _nonnegative(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{field_name} must be finite and >= 0")
    return value


@dataclass(frozen=True)
class FanDrivenParallelNetworkStudy:
    name: str
    fan_curve: FanCurve
    fixed_pressure_pa: float
    paths: tuple[ParallelFlowPath, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("fan-driven network study name cannot be empty")
        object.__setattr__(
            self,
            "fixed_pressure_pa",
            _nonnegative(self.fixed_pressure_pa, "fixed_pressure_pa"),
        )
        if len(self.paths) < 2:
            raise ValueError("fan-driven parallel network requires at least two paths")
        names = [path.name for path in self.paths]
        if len(names) != len(set(names)):
            raise ValueError("parallel-flow path names must be unique")


def equivalent_parallel_resistance(
    paths: tuple[ParallelFlowPath, ...],
) -> float:
    if len(paths) < 2:
        raise ValueError("equivalent parallel resistance requires at least two paths")
    resistances = [path.resistance_pa_per_m3_s_squared for path in paths]
    if any(
        not math.isfinite(resistance) or resistance <= 0
        for resistance in resistances
    ):
        raise ValueError("all parallel-flow paths must have finite positive resistance")
    conductance_sum = sum(1.0 / math.sqrt(resistance) for resistance in resistances)
    return 1.0 / conductance_sum**2


def solve_fan_driven_parallel_network(
    study: FanDrivenParallelNetworkStudy,
) -> dict:
    equivalent_resistance = equivalent_parallel_resistance(study.paths)
    system_curve = SystemCurve(
        name=f"{study.name} equivalent parallel network",
        fixed_pressure_pa=study.fixed_pressure_pa,
        resistance_pa_per_m3_s_squared=equivalent_resistance,
    )
    fan_result = solve_fan_operating_point(
        FanOperatingPointStudy(
            name=study.name,
            fan_curve=study.fan_curve,
            system_curve=system_curve,
        )
    )

    path_resistances = [
        {
            "name": path.name,
            "resistance_pa_per_m3_s_squared": round(
                path.resistance_pa_per_m3_s_squared, 6
            ),
        }
        for path in study.paths
    ]

    base = {
        "study": study.name,
        "fan_curve": study.fan_curve.name,
        "status": fan_result["status"],
        "fixed_pressure_pa": round(study.fixed_pressure_pa, 4),
        "equivalent_network_resistance_pa_per_m3_s_squared": round(
            equivalent_resistance, 6
        ),
        "path_resistances": path_resistances,
        "fan_operating_point": fan_result["operating_point"],
        "fan_curve_point_checks": fan_result["curve_point_checks"],
        "message": fan_result["message"],
    }

    if fan_result["operating_point"] is None:
        return {
            **base,
            "network_solution": None,
            "system_pressure_check": None,
            "scope_note": (
                "The passive parallel network is reduced analytically to an equivalent "
                "constant R*Q^2 resistance and combined with the explicit fixed pressure "
                "term. Fan pressure is interpolated only inside supplied fan-curve data. "
                "No fan extrapolation, arbitrary loop solving, variable friction factor, "
                "damper/control action, leakage, system effect, or manufacturer selection "
                "is inferred."
            ),
        }

    operating_airflow_m3_h = fan_result["operating_point"]["airflow_m3_h"]
    network_result = solve_parallel_branch_flows(
        ParallelFlowNetwork(
            name=study.name,
            total_airflow_m3_h=operating_airflow_m3_h,
            paths=study.paths,
        )
    )
    variable_pressure_pa = network_result["common_pressure_drop_pa"]
    total_system_pressure_pa = study.fixed_pressure_pa + variable_pressure_pa
    fan_pressure_pa = fan_result["operating_point"]["fan_pressure_pa"]

    return {
        **base,
        "network_solution": network_result,
        "system_pressure_check": {
            "fixed_pressure_pa": round(study.fixed_pressure_pa, 4),
            "parallel_network_pressure_pa": round(variable_pressure_pa, 4),
            "total_system_pressure_pa": round(total_system_pressure_pa, 4),
            "fan_pressure_pa": round(fan_pressure_pa, 4),
            "fan_minus_system_pressure_pa": round(
                fan_pressure_pa - total_system_pressure_pa, 6
            ),
        },
        "scope_note": (
            "The passive parallel network is reduced analytically to an equivalent "
            "constant R*Q^2 resistance, intersected with the supplied fan curve, and the "
            "solved total airflow is redistributed through the same paths. Friction "
            "factors, air density, and local-loss coefficients are held constant. The "
            "model does not solve arbitrary looped networks, variable friction factor, "
            "damper/control action, leakage, system effect, acoustics, stall/surge "
            "limits, or manufacturer acceptance."
        ),
    }
