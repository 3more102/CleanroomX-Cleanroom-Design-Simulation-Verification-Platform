from __future__ import annotations

from dataclasses import dataclass
import math

from .duct import DuctSection, analyze_duct_section


def _positive_finite(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{field_name} must be finite and > 0")
    return value


@dataclass(frozen=True)
class TerminalAirflowDemand:
    node: str
    airflow_m3_h: float

    def __post_init__(self) -> None:
        if not self.node.strip():
            raise ValueError("terminal-demand node cannot be empty")
        object.__setattr__(
            self,
            "airflow_m3_h",
            _positive_finite(self.airflow_m3_h, "airflow_m3_h"),
        )


@dataclass(frozen=True)
class DuctTreeSection:
    name: str
    from_node: str
    to_node: str
    length_m: float
    friction_factor: float
    air_density_kg_m3: float
    local_loss_coefficient: float = 0.0
    diameter_m: float | None = None
    width_m: float | None = None
    height_m: float | None = None

    def __post_init__(self) -> None:
        if not self.from_node.strip() or not self.to_node.strip():
            raise ValueError("duct-tree section node names cannot be empty")
        if self.from_node == self.to_node:
            raise ValueError("duct-tree section endpoints must be different")

        probe = DuctSection(
            name=self.name,
            length_m=self.length_m,
            airflow_m3_h=1.0,
            friction_factor=self.friction_factor,
            air_density_kg_m3=self.air_density_kg_m3,
            local_loss_coefficient=self.local_loss_coefficient,
            diameter_m=self.diameter_m,
            width_m=self.width_m,
            height_m=self.height_m,
        )
        object.__setattr__(self, "length_m", probe.length_m)
        object.__setattr__(self, "friction_factor", probe.friction_factor)
        object.__setattr__(self, "air_density_kg_m3", probe.air_density_kg_m3)
        object.__setattr__(
            self, "local_loss_coefficient", probe.local_loss_coefficient
        )
        object.__setattr__(self, "diameter_m", probe.diameter_m)
        object.__setattr__(self, "width_m", probe.width_m)
        object.__setattr__(self, "height_m", probe.height_m)


@dataclass(frozen=True)
class DuctTreeNetwork:
    root_node: str
    sections: tuple[DuctTreeSection, ...]
    terminal_demands: tuple[TerminalAirflowDemand, ...]

    def __post_init__(self) -> None:
        if not self.root_node.strip():
            raise ValueError("duct-tree root_node cannot be empty")
        if not self.sections:
            raise ValueError("duct tree must contain at least one section")
        if not self.terminal_demands:
            raise ValueError("duct tree must contain at least one terminal demand")

        section_names = [section.name for section in self.sections]
        if len(section_names) != len(set(section_names)):
            raise ValueError("duct-tree section names must be unique")

        edge_pairs: set[tuple[str, str]] = set()
        incoming: dict[str, DuctTreeSection] = {}
        adjacency: dict[str, list[DuctTreeSection]] = {}
        nodes = {self.root_node}

        for section in self.sections:
            nodes.add(section.from_node)
            nodes.add(section.to_node)
            pair = (section.from_node, section.to_node)
            if pair in edge_pairs:
                raise ValueError(
                    f"duplicate duct-tree edge: {section.from_node!r} -> "
                    f"{section.to_node!r}"
                )
            edge_pairs.add(pair)
            if section.to_node == self.root_node:
                raise ValueError("duct-tree root_node cannot have an incoming section")
            if section.to_node in incoming:
                raise ValueError(
                    f"duct-tree node {section.to_node!r} has more than one incoming "
                    "section"
                )
            incoming[section.to_node] = section
            adjacency.setdefault(section.from_node, []).append(section)

        reachable = {self.root_node}
        stack = [self.root_node]
        while stack:
            node = stack.pop()
            for section in adjacency.get(node, []):
                if section.to_node in reachable:
                    raise ValueError("duct-tree sections contain a directed cycle")
                reachable.add(section.to_node)
                stack.append(section.to_node)

        if reachable != nodes:
            missing = ", ".join(sorted(nodes - reachable))
            raise ValueError(
                "all duct-tree nodes must be reachable from root_node; "
                f"unreachable nodes: {missing}"
            )

        demand_nodes = [demand.node for demand in self.terminal_demands]
        if len(demand_nodes) != len(set(demand_nodes)):
            raise ValueError("terminal-demand nodes must be unique")
        if self.root_node in demand_nodes:
            raise ValueError("duct-tree root_node cannot be a terminal-demand node")
        unknown = sorted(set(demand_nodes) - nodes)
        if unknown:
            raise ValueError(
                "terminal demand references unknown duct-tree node(s): "
                + ", ".join(unknown)
            )

        leaves = {node for node in nodes if not adjacency.get(node)}
        missing_leaf_demands = sorted(leaves - set(demand_nodes))
        if missing_leaf_demands:
            raise ValueError(
                "every duct-tree leaf must have a terminal demand; missing: "
                + ", ".join(missing_leaf_demands)
            )


def _as_duct_section(section: DuctTreeSection, airflow_m3_h: float) -> DuctSection:
    return DuctSection(
        name=section.name,
        length_m=section.length_m,
        airflow_m3_h=airflow_m3_h,
        friction_factor=section.friction_factor,
        air_density_kg_m3=section.air_density_kg_m3,
        local_loss_coefficient=section.local_loss_coefficient,
        diameter_m=section.diameter_m,
        width_m=section.width_m,
        height_m=section.height_m,
    )


def analyze_duct_tree_network(network: DuctTreeNetwork) -> dict:
    """Aggregate fixed terminal demands upstream and evaluate each tree section."""
    adjacency: dict[str, list[DuctTreeSection]] = {}
    parent_section: dict[str, DuctTreeSection] = {}
    for section in network.sections:
        adjacency.setdefault(section.from_node, []).append(section)
        parent_section[section.to_node] = section

    demand_by_node = {
        demand.node: demand.airflow_m3_h for demand in network.terminal_demands
    }
    subtree_flow: dict[str, float] = {}

    def flow_at(node: str) -> float:
        if node in subtree_flow:
            return subtree_flow[node]
        total = demand_by_node.get(node, 0.0)
        for section in adjacency.get(node, []):
            total += flow_at(section.to_node)
        subtree_flow[node] = total
        return total

    root_flow = flow_at(network.root_node)

    section_results: list[dict] = []
    section_result_by_name: dict[str, dict] = {}
    edge_flow_by_child: dict[str, float] = {}
    for section in network.sections:
        airflow = flow_at(section.to_node)
        if airflow <= 0:
            raise ValueError(
                f"duct-tree section {section.name!r} has no downstream terminal airflow"
            )
        edge_flow_by_child[section.to_node] = airflow
        result = analyze_duct_section(_as_duct_section(section, airflow))
        result = {
            "from_node": section.from_node,
            "to_node": section.to_node,
            **result,
        }
        section_results.append(result)
        section_result_by_name[section.name] = result

    terminal_paths: list[dict] = []
    for demand in network.terminal_demands:
        node = demand.node
        reversed_sections: list[str] = []
        while node != network.root_node:
            section = parent_section[node]
            reversed_sections.append(section.name)
            node = section.from_node
        path_sections = list(reversed(reversed_sections))
        pressure_drop = sum(
            section_result_by_name[name]["total_pressure_drop_pa"]
            for name in path_sections
        )
        terminal_paths.append(
            {
                "terminal_node": demand.node,
                "terminal_airflow_m3_h": round(demand.airflow_m3_h, 3),
                "sections": path_sections,
                "total_pressure_drop_pa": round(pressure_drop, 4),
            }
        )

    critical = max(
        terminal_paths, key=lambda item: item["total_pressure_drop_pa"]
    )

    all_nodes = {network.root_node}
    for section in network.sections:
        all_nodes.add(section.from_node)
        all_nodes.add(section.to_node)

    node_balances: list[dict] = []
    for node in sorted(all_nodes):
        incoming_flow = (
            root_flow
            if node == network.root_node
            else edge_flow_by_child[node]
        )
        outgoing_flow = sum(
            edge_flow_by_child[section.to_node]
            for section in adjacency.get(node, [])
        )
        local_demand = demand_by_node.get(node, 0.0)
        residual = incoming_flow - outgoing_flow - local_demand
        node_balances.append(
            {
                "node": node,
                "incoming_or_source_airflow_m3_h": round(incoming_flow, 3),
                "outgoing_airflow_m3_h": round(outgoing_flow, 3),
                "terminal_demand_m3_h": round(local_demand, 3),
                "balance_residual_m3_h": round(residual, 9),
            }
        )

    return {
        "root_node": network.root_node,
        "root_airflow_m3_h": round(root_flow, 3),
        "total_terminal_airflow_m3_h": round(
            sum(demand_by_node.values()), 3
        ),
        "sections": section_results,
        "terminal_paths": terminal_paths,
        "critical_terminal_node": critical["terminal_node"],
        "critical_path_sections": critical["sections"],
        "critical_path_pressure_drop_pa": critical["total_pressure_drop_pa"],
        "node_balances": node_balances,
        "scope_note": (
            "Terminal airflows are fixed project inputs and are aggregated upstream by "
            "mass conservation through a rooted acyclic supply tree. Pressure losses use "
            "the existing Darcy-Weisbach section model with explicit friction factors "
            "and local loss coefficients. This is not a pressure-driven or nonlinear "
            "network solver and does not determine balancing-damper positions, fan "
            "operating point, leakage, or looped-network flow distribution."
        ),
    }
