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
class FanLoopNetworkStudy:
    name: str
    fan_curve: FanCurve
    loop_network: LoopedFlowNetwork
    fan_discharge_node: str
    fan_suction_node: str
    fixed_pressure_pa: float = 0.0

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("fan/loop-network study name cannot be empty")
        object.__setattr__(
            self,
            "fixed_pressure_pa",
            _nonnegative(self.fixed_pressure_pa, "fixed_pressure_pa"),
        )

        injections = self.loop_network.node_injections_m3_h
        if self.fan_discharge_node not in injections:
            raise ValueError("fan_discharge_node must exist in loop network")
        if self.fan_suction_node not in injections:
            raise ValueError("fan_suction_node must exist in loop network")
        if self.fan_discharge_node == self.fan_suction_node:
            raise ValueError("fan discharge and suction nodes must differ")

        discharge = injections[self.fan_discharge_node]
        suction = injections[self.fan_suction_node]
        if discharge <= 0:
            raise ValueError("fan discharge node must have positive reference injection")
        if suction >= 0:
            raise ValueError("fan suction node must have negative reference injection")
        if abs(discharge + suction) > 1e-6:
            raise ValueError(
                "fan discharge/suction reference injections must be equal and opposite"
            )
        for node, injection in injections.items():
            if node in {self.fan_discharge_node, self.fan_suction_node}:
                continue
            if abs(injection) > 1e-6:
                raise ValueError(
                    "fan/loop-network coupling currently requires zero injection "
                    "at all nodes other than fan discharge and suction"
                )


def _node_pressure(result: dict, node_name: str) -> float:
    for node in result["nodes"]:
        if node["name"] == node_name:
            return float(node["relative_pressure_pa"])
    raise RuntimeError(f"node {node_name!r} missing from loop-network result")


def derive_loop_equivalent_resistance(
    study: FanLoopNetworkStudy,
) -> tuple[float, dict]:
    reference_result = solve_looped_network(study.loop_network)
    discharge_pressure = _node_pressure(
        reference_result, study.fan_discharge_node
    )
    suction_pressure = _node_pressure(
        reference_result, study.fan_suction_node
    )
    network_pressure_pa = discharge_pressure - suction_pressure
    if not math.isfinite(network_pressure_pa) or network_pressure_pa <= 0:
        raise ValueError(
            "reference loop solution must require positive pressure from fan "
            "discharge to suction"
        )

    reference_airflow_m3_h = study.loop_network.node_injections_m3_h[
        study.fan_discharge_node
    ]
    reference_airflow_m3_s = reference_airflow_m3_h / 3600.0
    equivalent_resistance = network_pressure_pa / reference_airflow_m3_s**2
    if not math.isfinite(equivalent_resistance) or equivalent_resistance <= 0:
        raise ValueError("derived loop equivalent resistance must be finite and > 0")
    return equivalent_resistance, reference_result


def _network_at_airflow(
    study: FanLoopNetworkStudy,
    airflow_m3_h: float,
) -> LoopedFlowNetwork:
    reference_airflow = study.loop_network.node_injections_m3_h[
        study.fan_discharge_node
    ]
    scale = airflow_m3_h / reference_airflow
    return LoopedFlowNetwork(
        name=study.loop_network.name,
        node_injections_m3_h={
            node: injection * scale
            for node, injection in study.loop_network.node_injections_m3_h.items()
        },
        edges=study.loop_network.edges,
        reference_node=study.loop_network.reference_node,
    )


def solve_fan_loop_network(study: FanLoopNetworkStudy) -> dict:
    equivalent_resistance, reference_network = derive_loop_equivalent_resistance(
        study
    )
    reference_airflow = study.loop_network.node_injections_m3_h[
        study.fan_discharge_node
    ]
    reference_network_pressure = (
        _node_pressure(reference_network, study.fan_discharge_node)
        - _node_pressure(reference_network, study.fan_suction_node)
    )

    fan_result = solve_fan_operating_point(
        FanOperatingPointStudy(
            name=study.name,
            fan_curve=study.fan_curve,
            system_curve=SystemCurve(
                name=f"{study.name} equivalent loop network",
                fixed_pressure_pa=study.fixed_pressure_pa,
                resistance_pa_per_m3_s_squared=equivalent_resistance,
            ),
        )
    )

    base = {
        "study": study.name,
        "status": fan_result["status"],
        "fan_curve": study.fan_curve.name,
        "fan_discharge_node": study.fan_discharge_node,
        "fan_suction_node": study.fan_suction_node,
        "fixed_pressure_pa": round(study.fixed_pressure_pa, 6),
        "reference_airflow_m3_h": round(reference_airflow, 6),
        "reference_network_pressure_pa": round(reference_network_pressure, 9),
        "equivalent_loop_resistance_pa_per_m3_s_squared": round(
            equivalent_resistance, 9
        ),
        "reference_network_solution": reference_network,
        "fan_operating_point": fan_result["operating_point"],
        "fan_curve_point_checks": fan_result["curve_point_checks"],
        "message": fan_result["message"],
    }

    point = fan_result["operating_point"]
    if point is None:
        return {
            **base,
            "operating_network_solution": None,
            "system_pressure_check": None,
            "scope_note": (
                "The passive fixed-resistance loop network is reduced to a two-terminal "
                "equivalent R*Q^2 law from a declared reference through-flow, then "
                "intersected with the supplied fan curve without extrapolation. "
                "No operating loop solution is produced when no bounded intersection "
                "exists. Friction/resistance remains fixed; controls, leakage, system "
                "effect, compressibility, and transients are outside scope."
            ),
        }

    operating_airflow = point["airflow_m3_h"]
    operating_network = solve_looped_network(
        _network_at_airflow(study, operating_airflow)
    )
    network_pressure = (
        _node_pressure(operating_network, study.fan_discharge_node)
        - _node_pressure(operating_network, study.fan_suction_node)
    )
    total_system_pressure = study.fixed_pressure_pa + network_pressure
    fan_pressure = point["fan_pressure_pa"]
    equivalent_pressure = (
        equivalent_resistance * (operating_airflow / 3600.0) ** 2
    )

    return {
        **base,
        "operating_network_solution": operating_network,
        "system_pressure_check": {
            "fixed_pressure_pa": round(study.fixed_pressure_pa, 6),
            "loop_network_pressure_pa": round(network_pressure, 9),
            "equivalent_curve_network_pressure_pa": round(
                equivalent_pressure, 9
            ),
            "network_pressure_residual_pa": round(
                network_pressure - equivalent_pressure, 9
            ),
            "total_system_pressure_pa": round(total_system_pressure, 9),
            "fan_pressure_pa": round(fan_pressure, 9),
            "fan_minus_system_pressure_pa": round(
                fan_pressure - total_system_pressure, 9
            ),
        },
        "scope_note": (
            "The passive fixed-resistance loop network is reduced to a two-terminal "
            "equivalent R*Q^2 law using a reference solve. The supplied fan curve is "
            "intersected only within its supplied range, then the loop is re-solved at "
            "the operating airflow to recover node pressures and signed edge flows. "
            "Geometry-derived and automatic-friction edge resistance remains frozen at "
            "its declared reference basis. This does not model variable friction, "
            "damper/control action, leakage, system effect, acoustics, stall/surge "
            "limits, compressibility, transients, or manufacturer acceptance."
        ),
    }
