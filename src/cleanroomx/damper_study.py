from __future__ import annotations

import math
from dataclasses import dataclass

from .loop_network import LoopedFlowNetwork, QuadraticFlowEdge, solve_looped_network


def _multiplier(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 1.0:
        raise ValueError(f"{field_name} must be finite and >= 1")
    return value


@dataclass(frozen=True)
class DamperResistanceCase:
    name: str
    edge_resistance_multipliers: dict[str, float]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("damper case name cannot be empty")
        if not self.edge_resistance_multipliers:
            raise ValueError(
                "damper case requires at least one edge resistance multiplier"
            )

        normalized: dict[str, float] = {}
        for edge_name, value in self.edge_resistance_multipliers.items():
            if not isinstance(edge_name, str) or not edge_name.strip():
                raise ValueError("damper edge names must be non-empty strings")
            normalized[edge_name] = _multiplier(
                value,
                f"resistance multiplier for {edge_name}",
            )
        object.__setattr__(self, "edge_resistance_multipliers", normalized)


@dataclass(frozen=True)
class LoopDamperStudy:
    name: str
    loop_network: LoopedFlowNetwork
    cases: tuple[DamperResistanceCase, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("damper study name cannot be empty")
        if not self.cases:
            raise ValueError("damper study requires at least one case")

        case_names = [case.name for case in self.cases]
        if len(case_names) != len(set(case_names)):
            raise ValueError("damper case names must be unique")

        edge_names = {edge.name for edge in self.loop_network.edges}
        for case in self.cases:
            unknown = sorted(set(case.edge_resistance_multipliers) - edge_names)
            if unknown:
                raise ValueError(
                    f"damper case {case.name!r} references unknown edge(s): "
                    + ", ".join(unknown)
                )


def _damper_adjusted_edge(
    edge: QuadraticFlowEdge,
    multiplier: float,
) -> QuadraticFlowEdge:
    if multiplier == 1.0:
        return edge

    evidence: dict = {
        "base_resistance_basis": edge.resistance_basis,
        "base_resistance_pa_per_m3_s_squared": (
            edge.resistance_pa_per_m3_s_squared
        ),
        "damper_resistance_multiplier": multiplier,
    }
    if edge.resistance_evidence is not None:
        evidence["base_resistance_evidence"] = edge.resistance_evidence

    return QuadraticFlowEdge(
        name=edge.name,
        start_node=edge.start_node,
        end_node=edge.end_node,
        resistance_pa_per_m3_s_squared=(
            edge.resistance_pa_per_m3_s_squared * multiplier
        ),
        resistance_basis="damper_adjusted",
        resistance_evidence=evidence,
    )


def _case_network(
    study: LoopDamperStudy,
    case: DamperResistanceCase,
) -> LoopedFlowNetwork:
    return LoopedFlowNetwork(
        name=f"{study.loop_network.name} — {case.name}",
        node_injections_m3_h=study.loop_network.node_injections_m3_h,
        edges=tuple(
            _damper_adjusted_edge(
                edge,
                case.edge_resistance_multipliers.get(edge.name, 1.0),
            )
            for edge in study.loop_network.edges
        ),
        reference_node=study.loop_network.reference_node,
    )


def _flow_change_rows(baseline: dict, case_result: dict) -> list[dict]:
    baseline_flows = {
        edge["name"]: float(edge["airflow_m3_h"])
        for edge in baseline["edges"]
    }
    rows = []
    for edge in case_result["edges"]:
        base = baseline_flows[edge["name"]]
        case_flow = float(edge["airflow_m3_h"])
        delta = case_flow - base
        percent = None if abs(base) < 1e-12 else delta / base * 100.0
        rows.append(
            {
                "edge": edge["name"],
                "baseline_airflow_m3_h": round(base, 6),
                "case_airflow_m3_h": round(case_flow, 6),
                "delta_airflow_m3_h": round(delta, 6),
                "percent_change": (
                    None if percent is None else round(percent, 6)
                ),
            }
        )
    return rows


def solve_loop_damper_study(study: LoopDamperStudy) -> dict:
    baseline = solve_looped_network(study.loop_network)
    base_edges = {edge.name: edge for edge in study.loop_network.edges}

    case_results = []
    for case in study.cases:
        solution = solve_looped_network(_case_network(study, case))
        adjustments = []
        for edge_name, multiplier in case.edge_resistance_multipliers.items():
            edge = base_edges[edge_name]
            adjustments.append(
                {
                    "edge": edge_name,
                    "resistance_multiplier": round(multiplier, 9),
                    "base_resistance_pa_per_m3_s_squared": round(
                        edge.resistance_pa_per_m3_s_squared,
                        9,
                    ),
                    "adjusted_resistance_pa_per_m3_s_squared": round(
                        edge.resistance_pa_per_m3_s_squared * multiplier,
                        9,
                    ),
                    "base_resistance_basis": edge.resistance_basis,
                }
            )
        case_results.append(
            {
                "name": case.name,
                "status": solution["status"],
                "adjustments": adjustments,
                "flow_changes": _flow_change_rows(baseline, solution),
                "network_solution": solution,
            }
        )

    return {
        "study": study.name,
        "status": "solved",
        "base_network": study.loop_network.name,
        "baseline_solution": baseline,
        "cases": case_results,
        "scope_note": (
            "Each case applies explicit user-supplied multipliers to selected fixed "
            "quadratic edge resistances and re-solves the same steady-state loop "
            "network. A multiplier >= 1 represents added/throttled resistance only; "
            "CleanroomX does not infer damper blade position, local-loss K, actuator "
            "behavior, automatic balancing, control logic, leakage, variable-friction "
            "iteration, compressibility, or transient response."
        ),
    }
