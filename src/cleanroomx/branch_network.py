from __future__ import annotations

from dataclasses import dataclass
import math

from .duct import DuctSection, analyze_duct_section


@dataclass(frozen=True)
class BranchDuct:
    name: str
    upstream_node: str
    downstream_node: str
    length_m: float
    friction_factor: float | None
    air_density_kg_m3: float
    local_loss_coefficient: float = 0.0
    diameter_m: float | None = None
    width_m: float | None = None
    height_m: float | None = None
    absolute_roughness_m: float | None = None
    kinematic_viscosity_m2_s: float | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("branch name cannot be empty")
        if not self.upstream_node.strip() or not self.downstream_node.strip():
            raise ValueError("branch node names cannot be empty")
        if self.upstream_node == self.downstream_node:
            raise ValueError("branch upstream and downstream nodes must differ")

        # Reuse the validated v0.6 duct-section model with a placeholder positive flow.
        DuctSection(
            name=self.name,
            length_m=self.length_m,
            airflow_m3_h=1.0,
            friction_factor=self.friction_factor,
            air_density_kg_m3=self.air_density_kg_m3,
            local_loss_coefficient=self.local_loss_coefficient,
            diameter_m=self.diameter_m,
            width_m=self.width_m,
            height_m=self.height_m,
            absolute_roughness_m=self.absolute_roughness_m,
            kinematic_viscosity_m2_s=self.kinematic_viscosity_m2_s,
        )

    def section_at_flow(self, airflow_m3_h: float) -> DuctSection:
        return DuctSection(
            name=self.name,
            length_m=self.length_m,
            airflow_m3_h=airflow_m3_h,
            friction_factor=self.friction_factor,
            air_density_kg_m3=self.air_density_kg_m3,
            local_loss_coefficient=self.local_loss_coefficient,
            diameter_m=self.diameter_m,
            width_m=self.width_m,
            height_m=self.height_m,
            absolute_roughness_m=self.absolute_roughness_m,
            kinematic_viscosity_m2_s=self.kinematic_viscosity_m2_s,
        )


@dataclass(frozen=True)
class TerminalDemand:
    node: str
    airflow_m3_h: float

    def __post_init__(self) -> None:
        if not self.node.strip():
            raise ValueError("terminal node cannot be empty")
        airflow = float(self.airflow_m3_h)
        if not math.isfinite(airflow):
            raise ValueError("terminal airflow_m3_h must be finite")
        if airflow <= 0:
            raise ValueError("terminal airflow_m3_h must be > 0")
        object.__setattr__(self, "airflow_m3_h", airflow)


@dataclass(frozen=True)
class BranchFlowNetwork:
    source_node: str
    branches: tuple[BranchDuct, ...]
    terminal_demands: tuple[TerminalDemand, ...]

    def __post_init__(self) -> None:
        if not self.source_node.strip():
            raise ValueError("source_node cannot be empty")
        if not self.branches:
            raise ValueError("branch-flow network must contain at least one branch")
        if not self.terminal_demands:
            raise ValueError("branch-flow network must contain at least one terminal demand")

        branch_names = [branch.name for branch in self.branches]
        if len(branch_names) != len(set(branch_names)):
            raise ValueError("branch names must be unique")

        terminal_nodes = [terminal.node for terminal in self.terminal_demands]
        if len(terminal_nodes) != len(set(terminal_nodes)):
            raise ValueError("terminal demand nodes must be unique")

        children: dict[str, list[str]] = {}
        incoming: dict[str, str] = {}
        nodes = {self.source_node}

        for branch in self.branches:
            nodes.add(branch.upstream_node)
            nodes.add(branch.downstream_node)
            children.setdefault(branch.upstream_node, []).append(branch.downstream_node)
            if branch.downstream_node in incoming:
                raise ValueError(
                    f"node {branch.downstream_node!r} has more than one incoming branch"
                )
            incoming[branch.downstream_node] = branch.upstream_node

        if self.source_node in incoming:
            raise ValueError("source_node cannot have an incoming branch")

        reachable: set[str] = set()
        stack = [self.source_node]
        while stack:
            node = stack.pop()
            if node in reachable:
                continue
            reachable.add(node)
            stack.extend(children.get(node, ()))

        if reachable != nodes:
            missing = sorted(nodes - reachable)
            raise ValueError(
                "all branch nodes must be reachable from source_node; "
                f"unreachable: {', '.join(missing)}"
            )

        leaves = {node for node in nodes if not children.get(node)}
        terminals = set(terminal_nodes)
        if terminals != leaves:
            missing_demands = sorted(leaves - terminals)
            nonleaf_terminals = sorted(terminals - leaves)
            details: list[str] = []
            if missing_demands:
                details.append(
                    "leaf nodes without terminal demand: " + ", ".join(missing_demands)
                )
            if nonleaf_terminals:
                details.append(
                    "terminal demands on non-leaf nodes: " + ", ".join(nonleaf_terminals)
                )
            raise ValueError("; ".join(details))


def analyze_branch_flow_network(network: BranchFlowNetwork) -> dict:
    """Propagate fixed terminal demands upstream through a directed supply tree."""
    branches_by_upstream: dict[str, list[BranchDuct]] = {}
    incoming_branch: dict[str, BranchDuct] = {}
    for branch in network.branches:
        branches_by_upstream.setdefault(branch.upstream_node, []).append(branch)
        incoming_branch[branch.downstream_node] = branch

    demand_by_node = {
        terminal.node: terminal.airflow_m3_h
        for terminal in network.terminal_demands
    }
    subtree_flow: dict[str, float] = {}

    def required_flow(node: str) -> float:
        if node in subtree_flow:
            return subtree_flow[node]
        children = branches_by_upstream.get(node, ())
        if not children:
            flow = demand_by_node[node]
        else:
            flow = sum(required_flow(branch.downstream_node) for branch in children)
        subtree_flow[node] = flow
        return flow

    source_airflow = required_flow(network.source_node)

    branch_results_by_name: dict[str, dict] = {}
    for branch in network.branches:
        airflow = required_flow(branch.downstream_node)
        section = analyze_duct_section(branch.section_at_flow(airflow))
        branch_results_by_name[branch.name] = {
            **section,
            "upstream_node": branch.upstream_node,
            "downstream_node": branch.downstream_node,
        }

    terminal_results: list[dict] = []
    for terminal in network.terminal_demands:
        node = terminal.node
        branch_path: list[str] = []
        while node != network.source_node:
            branch = incoming_branch[node]
            branch_path.append(branch.name)
            node = branch.upstream_node
        branch_path.reverse()
        pressure_drop = sum(
            branch_results_by_name[name]["total_pressure_drop_pa"]
            for name in branch_path
        )
        terminal_results.append(
            {
                "node": terminal.node,
                "airflow_m3_h": round(terminal.airflow_m3_h, 3),
                "branch_path": branch_path,
                "total_pressure_drop_pa": round(pressure_drop, 4),
            }
        )

    critical = max(
        terminal_results,
        key=lambda terminal: terminal["total_pressure_drop_pa"],
    )

    all_nodes = {network.source_node}
    for branch in network.branches:
        all_nodes.add(branch.downstream_node)

    continuity: list[dict] = []
    for node in sorted(all_nodes):
        incoming_flow = (
            source_airflow
            if node == network.source_node
            else required_flow(node)
        )
        outgoing_flow = sum(
            required_flow(branch.downstream_node)
            for branch in branches_by_upstream.get(node, ())
        )
        terminal_flow = demand_by_node.get(node, 0.0)
        residual = incoming_flow - outgoing_flow - terminal_flow
        continuity.append(
            {
                "node": node,
                "incoming_airflow_m3_h": round(incoming_flow, 3),
                "outgoing_airflow_m3_h": round(outgoing_flow, 3),
                "terminal_demand_m3_h": round(terminal_flow, 3),
                "continuity_residual_m3_h": round(residual, 9),
            }
        )

    return {
        "source_node": network.source_node,
        "source_airflow_m3_h": round(source_airflow, 3),
        "branch_count": len(network.branches),
        "terminal_count": len(network.terminal_demands),
        "branches": [
            branch_results_by_name[branch.name] for branch in network.branches
        ],
        "terminals": terminal_results,
        "critical_terminal": critical["node"],
        "critical_path": critical["branch_path"],
        "critical_path_pressure_drop_pa": critical["total_pressure_drop_pa"],
        "continuity": continuity,
        "max_abs_continuity_residual_m3_h": round(
            max(abs(item["continuity_residual_m3_h"]) for item in continuity),
            9,
        ),
        "scope_note": (
            "Branch airflows are solved by mass continuity from explicit fixed terminal "
            "demands in a directed tree. Pressure losses then use the existing "
            "Darcy-Weisbach/local-K section model, including optional Reynolds/roughness-"
            "based friction at each solved branch flow. This is not a nonlinear pressure-"
            "balancing solver: loops, parallel feeds, pressure-driven terminal flows, "
            "damper positions, fan curves, and control interactions are not inferred."
        ),
    }
