from __future__ import annotations

import math
from dataclasses import dataclass

from .loop_network import LoopedFlowNetwork, QuadraticFlowEdge, solve_looped_network


def _nonnegative(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{field_name} must be finite and >= 0")
    return value


@dataclass(frozen=True)
class DamperSetting:
    edge_name: str
    added_resistance_pa_per_m3_s_squared: float
    position_percent: float | None = None
    setting_label: str | None = None

    def __post_init__(self) -> None:
        if not self.edge_name.strip():
            raise ValueError("damper edge_name cannot be empty")
        object.__setattr__(
            self,
            "added_resistance_pa_per_m3_s_squared",
            _nonnegative(
                self.added_resistance_pa_per_m3_s_squared,
                "added_resistance_pa_per_m3_s_squared",
            ),
        )
        if self.position_percent is not None:
            position = float(self.position_percent)
            if not math.isfinite(position) or not 0.0 <= position <= 100.0:
                raise ValueError("position_percent must be finite and between 0 and 100")
            object.__setattr__(self, "position_percent", position)
        if self.setting_label is not None:
            label = self.setting_label.strip()
            if not label:
                raise ValueError("setting_label cannot be blank")
            object.__setattr__(self, "setting_label", label)


@dataclass(frozen=True)
class DamperCase:
    name: str
    settings: tuple[DamperSetting, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("damper case name cannot be empty")
        if not self.settings:
            raise ValueError("damper case requires at least one setting")
        edge_names = [setting.edge_name for setting in self.settings]
        if len(edge_names) != len(set(edge_names)):
            raise ValueError("a damper case cannot configure the same edge more than once")


@dataclass(frozen=True)
class DamperStudy:
    name: str
    loop_network: LoopedFlowNetwork
    cases: tuple[DamperCase, ...]

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
            for setting in case.settings:
                if setting.edge_name not in edge_names:
                    raise ValueError(
                        f"damper case {case.name!r} references unknown edge "
                        f"{setting.edge_name!r}"
                    )


def _pressure_span_pa(network_result: dict) -> float:
    pressures = [float(node["relative_pressure_pa"]) for node in network_result["nodes"]]
    return max(pressures) - min(pressures)


def _network_for_case(study: DamperStudy, case: DamperCase) -> LoopedFlowNetwork:
    settings = {setting.edge_name: setting for setting in case.settings}
    edges: list[QuadraticFlowEdge] = []

    for edge in study.loop_network.edges:
        setting = settings.get(edge.name)
        if setting is None:
            edges.append(edge)
            continue

        added = setting.added_resistance_pa_per_m3_s_squared
        total_resistance = edge.resistance_pa_per_m3_s_squared + added
        edges.append(
            QuadraticFlowEdge(
                name=edge.name,
                start_node=edge.start_node,
                end_node=edge.end_node,
                resistance_pa_per_m3_s_squared=total_resistance,
                resistance_basis="explicit",
                resistance_evidence={
                    "source": "damper_case_adjustment",
                    "case": case.name,
                    "base_resistance_pa_per_m3_s_squared": (
                        edge.resistance_pa_per_m3_s_squared
                    ),
                    "base_resistance_basis": edge.resistance_basis,
                    "base_resistance_evidence": edge.resistance_evidence,
                    "damper_added_resistance_pa_per_m3_s_squared": added,
                    "damper_position_percent": setting.position_percent,
                    "damper_setting_label": setting.setting_label,
                },
            )
        )

    return LoopedFlowNetwork(
        name=f"{study.loop_network.name} — {case.name}",
        node_injections_m3_h=study.loop_network.node_injections_m3_h,
        edges=tuple(edges),
        reference_node=study.loop_network.reference_node,
    )


def _edge_results_by_name(result: dict) -> dict[str, dict]:
    return {edge["name"]: edge for edge in result["edges"]}


def solve_damper_study(study: DamperStudy) -> dict:
    baseline = solve_looped_network(study.loop_network)
    baseline_edges = _edge_results_by_name(baseline)
    baseline_span = _pressure_span_pa(baseline)

    case_results = []
    for case in study.cases:
        solved = solve_looped_network(_network_for_case(study, case))
        solved_edges = _edge_results_by_name(solved)
        solved_span = _pressure_span_pa(solved)

        settings = []
        for setting in case.settings:
            base_edge = next(
                edge for edge in study.loop_network.edges if edge.name == setting.edge_name
            )
            solved_edge = solved_edges[setting.edge_name]
            airflow_m3_s = float(solved_edge["airflow_m3_s"])
            damper_pressure_difference_pa = (
                setting.added_resistance_pa_per_m3_s_squared
                * airflow_m3_s
                * abs(airflow_m3_s)
            )
            settings.append(
                {
                    "edge_name": setting.edge_name,
                    "position_percent": setting.position_percent,
                    "setting_label": setting.setting_label,
                    "base_resistance_pa_per_m3_s_squared": round(
                        base_edge.resistance_pa_per_m3_s_squared, 9
                    ),
                    "base_resistance_basis": base_edge.resistance_basis,
                    "added_resistance_pa_per_m3_s_squared": round(
                        setting.added_resistance_pa_per_m3_s_squared, 9
                    ),
                    "total_resistance_pa_per_m3_s_squared": round(
                        base_edge.resistance_pa_per_m3_s_squared
                        + setting.added_resistance_pa_per_m3_s_squared,
                        9,
                    ),
                    "solved_airflow_m3_h": solved_edge["airflow_m3_h"],
                    "solved_flow_direction": solved_edge["flow_direction"],
                    "damper_pressure_difference_pa": round(
                        damper_pressure_difference_pa, 9
                    ),
                }
            )

        flow_changes = []
        for edge in study.loop_network.edges:
            base_flow = float(baseline_edges[edge.name]["airflow_m3_h"])
            case_flow = float(solved_edges[edge.name]["airflow_m3_h"])
            flow_changes.append(
                {
                    "edge_name": edge.name,
                    "baseline_airflow_m3_h": round(base_flow, 6),
                    "case_airflow_m3_h": round(case_flow, 6),
                    "airflow_change_m3_h": round(case_flow - base_flow, 6),
                    "case_flow_direction": solved_edges[edge.name]["flow_direction"],
                }
            )

        case_results.append(
            {
                "name": case.name,
                "status": solved["status"],
                "pressure_span_pa": round(solved_span, 9),
                "pressure_span_change_pa": round(solved_span - baseline_span, 9),
                "settings": settings,
                "flow_changes": flow_changes,
                "network_solution": solved,
            }
        )

    return {
        "study": study.name,
        "status": "solved",
        "network": study.loop_network.name,
        "baseline_pressure_span_pa": round(baseline_span, 9),
        "baseline_solution": baseline,
        "cases": case_results,
        "scope_note": (
            "This study compares explicit steady-state damper cases by adding "
            "user-supplied fixed quadratic resistance to named loop-network edges. "
            "Optional damper position percentages and labels are descriptive only; "
            "CleanroomX does not infer a position-to-loss relationship. Base and added "
            "resistances remain fixed within each case, and node injections remain the "
            "same as the baseline network. The workflow does not perform automatic "
            "balancing/control, optimize damper positions, iterate variable friction, "
            "couple a fan curve, model leakage/system effect/compressibility/transients, "
            "or define commissioning acceptance criteria."
        ),
    }
