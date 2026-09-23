from __future__ import annotations

import math
from dataclasses import dataclass

from .fan_curve import (
    FanCurve,
    FanOperatingPointStudy,
    SystemCurve,
    solve_fan_operating_point,
)
from .loop_network import LoopedFlowNetwork, solve_looped_network


def _nonnegative(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{field_name} must be finite and >= 0")
    return value


@dataclass(frozen=True)
class FanDrivenLoopNetworkStudy:
    name: str
    fan_curve: FanCurve
    fixed_pressure_pa: float
    reference_network: LoopedFlowNetwork
    source_node: str
    sink_node: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("fan-driven loop-network study name cannot be empty")
        object.__setattr__(
            self,
            "fixed_pressure_pa",
            _nonnegative(self.fixed_pressure_pa, "fixed_pressure_pa"),
        )
        if not self.source_node.strip() or not self.sink_node.strip():
            raise ValueError("source_node and sink_node cannot be empty")
        if self.source_node == self.sink_node:
            raise ValueError("source_node and sink_node must be different")

        injections = self.reference_network.node_injections_m3_h
        if self.source_node not in injections or self.sink_node not in injections:
            raise ValueError("source_node and sink_node must exist in the reference network")

        source_airflow = injections[self.source_node]
        sink_airflow = injections[self.sink_node]
        if source_airflow <= 0:
            raise ValueError("reference-network source injection must be > 0")
        if abs(source_airflow + sink_airflow) > 1e-6:
            raise ValueError(
                "reference-network sink injection must exactly balance the source "
                "within 1e-6 m3/h"
            )

        for node, injection in injections.items():
            if node in {self.source_node, self.sink_node}:
                continue
            if abs(injection) > 1e-6:
                raise ValueError(
                    "fan-driven loop coupling currently requires zero injection at "
                    "all nodes except source_node and sink_node"
                )

    @property
    def reference_airflow_m3_h(self) -> float:
        return self.reference_network.node_injections_m3_h[self.source_node]


def _relative_pressure(result: dict, node_name: str) -> float:
    for node in result["nodes"]:
        if node["name"] == node_name:
            return float(node["relative_pressure_pa"])
    raise RuntimeError(f"node {node_name!r} missing from loop-network result")


def derive_equivalent_loop_resistance(
    study: FanDrivenLoopNetworkStudy,
    *,
    mass_balance_tolerance_m3_h: float = 1e-6,
    max_iterations: int = 100,
) -> dict:
    reference_result = solve_looped_network(
        study.reference_network,
        mass_balance_tolerance_m3_h=mass_balance_tolerance_m3_h,
        max_iterations=max_iterations,
    )
    source_pressure = _relative_pressure(reference_result, study.source_node)
    sink_pressure = _relative_pressure(reference_result, study.sink_node)
    network_pressure_pa = source_pressure - sink_pressure
    if not math.isfinite(network_pressure_pa) or network_pressure_pa <= 0:
        raise ValueError(
            "passive loop network must require a positive source-to-sink pressure rise"
        )

    reference_airflow_m3_s = study.reference_airflow_m3_h / 3600.0
    equivalent_resistance = network_pressure_pa / reference_airflow_m3_s**2
    if not math.isfinite(equivalent_resistance) or equivalent_resistance <= 0:
        raise ValueError("derived equivalent loop-network resistance must be > 0")

    return {
        "reference_airflow_m3_h": round(study.reference_airflow_m3_h, 9),
        "source_node": study.source_node,
        "sink_node": study.sink_node,
        "source_relative_pressure_pa": round(source_pressure, 9),
        "sink_relative_pressure_pa": round(sink_pressure, 9),
        "reference_network_pressure_pa": round(network_pressure_pa, 9),
        "equivalent_network_resistance_pa_per_m3_s_squared": round(
            equivalent_resistance, 12
        ),
        "reference_network_solution": reference_result,
    }


def _network_at_airflow(
    study: FanDrivenLoopNetworkStudy,
    airflow_m3_h: float,
) -> LoopedFlowNetwork:
    injections = {
        node: 0.0 for node in study.reference_network.node_injections_m3_h
    }
    injections[study.source_node] = airflow_m3_h
    injections[study.sink_node] = -airflow_m3_h
    return LoopedFlowNetwork(
        name=study.reference_network.name,
        node_injections_m3_h=injections,
        edges=study.reference_network.edges,
        reference_node=study.reference_network.reference_node,
    )


def solve_fan_driven_loop_network(
    study: FanDrivenLoopNetworkStudy,
    *,
    mass_balance_tolerance_m3_h: float = 1e-6,
    max_iterations: int = 100,
) -> dict:
    equivalent = derive_equivalent_loop_resistance(
        study,
        mass_balance_tolerance_m3_h=mass_balance_tolerance_m3_h,
        max_iterations=max_iterations,
    )
    equivalent_resistance = equivalent[
        "equivalent_network_resistance_pa_per_m3_s_squared"
    ]
    system_curve = SystemCurve(
        name=f"{study.name} equivalent loop network",
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

    base = {
        "study": study.name,
        "fan_curve": study.fan_curve.name,
        "status": fan_result["status"],
        "source_node": study.source_node,
        "sink_node": study.sink_node,
        "fixed_pressure_pa": round(study.fixed_pressure_pa, 9),
        "equivalent_loop_network": equivalent,
        "fan_operating_point": fan_result["operating_point"],
        "fan_curve_point_checks": fan_result["curve_point_checks"],
        "message": fan_result["message"],
    }

    if fan_result["operating_point"] is None:
        return {
            **base,
            "operating_network_solution": None,
            "system_pressure_check": None,
            "scope_note": (
                "The passive source-to-sink loop network is reduced to an equivalent "
                "fixed quadratic resistance using one reference solve, then intersected "
                "with the supplied fan curve without extrapolation. No operating network "
                "is reported when no fan/system intersection exists inside supplied data. "
                "Friction/resistance remains fixed; dampers, controls, leakage, system "
                "effect, compressibility, transients, and manufacturer acceptance are "
                "outside this workflow."
            ),
        }

    operating_airflow_m3_h = fan_result["operating_point"]["airflow_m3_h"]
    operating_network = solve_looped_network(
        _network_at_airflow(study, operating_airflow_m3_h),
        mass_balance_tolerance_m3_h=mass_balance_tolerance_m3_h,
        max_iterations=max_iterations,
    )
    source_pressure = _relative_pressure(operating_network, study.source_node)
    sink_pressure = _relative_pressure(operating_network, study.sink_node)
    network_pressure_pa = source_pressure - sink_pressure
    total_system_pressure_pa = study.fixed_pressure_pa + network_pressure_pa
    fan_pressure_pa = fan_result["operating_point"]["fan_pressure_pa"]
    airflow_m3_s = operating_airflow_m3_h / 3600.0
    equivalent_pressure_pa = equivalent_resistance * airflow_m3_s**2

    return {
        **base,
        "operating_network_solution": operating_network,
        "system_pressure_check": {
            "operating_airflow_m3_h": round(operating_airflow_m3_h, 6),
            "fan_pressure_pa": round(fan_pressure_pa, 9),
            "fixed_pressure_pa": round(study.fixed_pressure_pa, 9),
            "loop_network_pressure_pa": round(network_pressure_pa, 9),
            "equivalent_network_pressure_pa": round(equivalent_pressure_pa, 9),
            "total_system_pressure_pa": round(total_system_pressure_pa, 9),
            "fan_minus_system_pressure_pa": round(
                fan_pressure_pa - total_system_pressure_pa, 9
            ),
            "loop_minus_equivalent_pressure_pa": round(
                network_pressure_pa - equivalent_pressure_pa, 9
            ),
        },
        "scope_note": (
            "The passive source-to-sink loop network is reduced to an equivalent fixed "
            "quadratic resistance from a reference solve. The existing bounded fan "
            "operating-point solver finds the intersection only within supplied fan "
            "data, then the full loop network is solved again at that airflow to verify "
            "pressure closure. Geometry-derived edge resistance and automatic friction "
            "remain frozen at their configured basis. The workflow does not infer "
            "variable-friction iteration, dampers, controls, leakage, system effect, "
            "stall/surge limits, compressibility, transients, or manufacturer acceptance."
        ),
    }
