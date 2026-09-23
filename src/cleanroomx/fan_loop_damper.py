from __future__ import annotations

import math
from dataclasses import dataclass

from .fan_loop_network import FanLoopNetworkStudy, solve_fan_loop_network
from .loop_network import LoopedFlowNetwork, QuadraticFlowEdge


def _nonnegative(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{field_name} must be finite and >= 0")
    return value


@dataclass(frozen=True)
class DamperState:
    name: str
    edge_added_resistance_pa_per_m3_s_squared: dict[str, float]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("damper state name cannot be empty")
        normalized: dict[str, float] = {}
        for edge_name, added_resistance in (
            self.edge_added_resistance_pa_per_m3_s_squared.items()
        ):
            if not isinstance(edge_name, str) or not edge_name.strip():
                raise ValueError("damper edge names must be non-empty strings")
            normalized[edge_name] = _nonnegative(
                added_resistance,
                f"added resistance for edge {edge_name}",
            )
        if not normalized:
            raise ValueError("damper state must configure at least one edge")
        object.__setattr__(
            self,
            "edge_added_resistance_pa_per_m3_s_squared",
            normalized,
        )


@dataclass(frozen=True)
class FanLoopDamperStudy:
    name: str
    base_study: FanLoopNetworkStudy
    states: tuple[DamperState, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("fan/loop damper study name cannot be empty")
        if not self.states:
            raise ValueError("fan/loop damper study requires at least one state")

        state_names = [state.name for state in self.states]
        if len(state_names) != len(set(state_names)):
            raise ValueError("damper state names must be unique")

        edge_names = {edge.name for edge in self.base_study.loop_network.edges}
        for state in self.states:
            unknown = sorted(
                set(state.edge_added_resistance_pa_per_m3_s_squared) - edge_names
            )
            if unknown:
                raise ValueError(
                    f"damper state {state.name!r} references unknown edge(s): "
                    + ", ".join(unknown)
                )


def _apply_damper_state(
    base_study: FanLoopNetworkStudy,
    state: DamperState,
) -> tuple[FanLoopNetworkStudy, list[dict]]:
    adjusted_edges: list[QuadraticFlowEdge] = []
    adjustments: list[dict] = []

    for edge in base_study.loop_network.edges:
        added = state.edge_added_resistance_pa_per_m3_s_squared.get(
            edge.name, 0.0
        )
        if edge.name in state.edge_added_resistance_pa_per_m3_s_squared:
            evidence = dict(edge.resistance_evidence or {})
            evidence["damper_adjustment"] = {
                "state": state.name,
                "added_resistance_pa_per_m3_s_squared": round(added, 9),
                "model": "explicit additive fixed quadratic resistance",
            }
        else:
            evidence = edge.resistance_evidence

        adjusted_resistance = (
            edge.resistance_pa_per_m3_s_squared + added
        )
        adjusted_edges.append(
            QuadraticFlowEdge(
                name=edge.name,
                start_node=edge.start_node,
                end_node=edge.end_node,
                resistance_pa_per_m3_s_squared=adjusted_resistance,
                resistance_basis=edge.resistance_basis,
                resistance_evidence=evidence,
            )
        )

        if edge.name in state.edge_added_resistance_pa_per_m3_s_squared:
            adjustments.append(
                {
                    "edge": edge.name,
                    "base_resistance_pa_per_m3_s_squared": round(
                        edge.resistance_pa_per_m3_s_squared, 9
                    ),
                    "added_resistance_pa_per_m3_s_squared": round(added, 9),
                    "adjusted_resistance_pa_per_m3_s_squared": round(
                        adjusted_resistance, 9
                    ),
                }
            )

    adjusted_network = LoopedFlowNetwork(
        name=f"{base_study.loop_network.name} — {state.name}",
        node_injections_m3_h=dict(
            base_study.loop_network.node_injections_m3_h
        ),
        edges=tuple(adjusted_edges),
        reference_node=base_study.loop_network.reference_node,
    )
    adjusted_study = FanLoopNetworkStudy(
        name=f"{base_study.name} — {state.name}",
        fan_curve=base_study.fan_curve,
        loop_network=adjusted_network,
        fan_discharge_node=base_study.fan_discharge_node,
        fan_suction_node=base_study.fan_suction_node,
        fixed_pressure_pa=base_study.fixed_pressure_pa,
    )
    return adjusted_study, adjustments


def solve_fan_loop_damper_study(study: FanLoopDamperStudy) -> dict:
    state_results: list[dict] = []
    solved_count = 0

    for state in study.states:
        adjusted_study, adjustments = _apply_damper_state(
            study.base_study, state
        )
        result = solve_fan_loop_network(adjusted_study)
        if result["status"] == "solved":
            solved_count += 1

        point = result["fan_operating_point"]
        state_results.append(
            {
                "state": state.name,
                "status": result["status"],
                "damper_adjustments": adjustments,
                "equivalent_loop_resistance_pa_per_m3_s_squared": result[
                    "equivalent_loop_resistance_pa_per_m3_s_squared"
                ],
                "operating_airflow_m3_h": (
                    None if point is None else point["airflow_m3_h"]
                ),
                "fan_pressure_pa": (
                    None if point is None else point["fan_pressure_pa"]
                ),
                "fan_loop_result": result,
            }
        )

    if solved_count == len(state_results):
        status = "solved"
    elif solved_count:
        status = "partially_solved"
    else:
        status = "no_state_solved"

    return {
        "study": study.name,
        "status": status,
        "fan_curve": study.base_study.fan_curve.name,
        "state_count": len(state_results),
        "solved_state_count": solved_count,
        "states": state_results,
        "scope_note": (
            "Each configured damper state adds an explicit user-supplied fixed "
            "quadratic resistance to selected loop edges, then reuses the bounded "
            "fan/loop-network operating-point solve. CleanroomX does not infer "
            "resistance from damper position, actuator signal, blade angle, or a "
            "generic valve characteristic. Added resistance is fixed within each "
            "state; variable-friction iteration, feedback control, actuator dynamics, "
            "leakage, acoustics, system effect, and transients remain outside scope."
        ),
    }
