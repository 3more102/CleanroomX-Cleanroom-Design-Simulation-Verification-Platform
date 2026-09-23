from __future__ import annotations

import math
from dataclasses import dataclass

from .duct import DuctSection, analyze_duct_section


@dataclass(frozen=True)
class DuctBranch:
    name: str
    parent_node: str
    child_node: str
    length_m: float
    friction_factor: float
    air_density_kg_m3: float
    local_loss_coefficient: float = 0.0
    diameter_m: float | None = None
    width_m: float | None = None
    height_m: float | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("duct-branch name cannot be empty")
        if not self.parent_node.strip():
            raise ValueError("parent_node cannot be empty")
        if not self.child_node.strip():
            raise ValueError("child_node cannot be empty")
        if self.parent_node == self.child_node:
            raise ValueError("duct branch parent_node and child_node must differ")

        probe = self.section_at_airflow(1.0)
        for field_name in (
            "length_m",
            "friction_factor",
            "air_density_kg_m3",
            "local_loss_coefficient",
            "diameter_m",
            "width_m",
            "height_m",
        ):
            object.__setattr__(self, field_name, getattr(probe, field_name))

    def section_at_airflow(self, airflow_m3_h: float) -> DuctSection:
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
        )


@dataclass(frozen=True)
class DuctTerminal:
    room_name: str
    node: str

    def __post_init__(self) -> None:
        if not self.room_name.strip():
            raise ValueError("duct-terminal room_name cannot be empty")
        if not self.node.strip():
            raise ValueError("duct-terminal node cannot be empty")


@dataclass(frozen=True)
class BranchedDuctNetwork:
    root_node: str
    branches: tuple[DuctBranch, ...]
    terminals: tuple[DuctTerminal, ...]

    def __post_init__(self) -> None:
        if not self.root_node.strip():
            raise ValueError("root_node cannot be empty")
        if not self.branches:
            raise ValueError("branched duct network must contain at least one branch")
        if not self.terminals:
            raise ValueError("branched duct network must contain at least one terminal")

        branch_names = [branch.name for branch in self.branches]
        if len(branch_names) != len(set(branch_names)):
            raise ValueError("duct-branch names must be unique")

        child_nodes = [branch.child_node for branch in self.branches]
        if len(child_nodes) != len(set(child_nodes)):
            raise ValueError(
                "each non-root duct node must have exactly one incoming branch"
            )
        if self.root_node in child_nodes:
            raise ValueError("root_node cannot have an incoming branch")

        known_nodes = {self.root_node, *child_nodes}
        for branch in self.branches:
            if branch.parent_node not in known_nodes:
                raise ValueError(
                    f"branch {branch.name!r} references unknown parent_node "
                    f"{branch.parent_node!r}"
                )

        room_names = [terminal.room_name for terminal in self.terminals]
        if len(room_names) != len(set(room_names)):
            raise ValueError("duct-terminal room names must be unique")

        terminal_nodes = [terminal.node for terminal in self.terminals]
        if len(terminal_nodes) != len(set(terminal_nodes)):
            raise ValueError("duct-terminal nodes must be unique")

        outgoing_nodes = {branch.parent_node for branch in self.branches}
        leaf_nodes = set(child_nodes) - outgoing_nodes
        if set(terminal_nodes) != leaf_nodes:
            raise ValueError("duct terminals must map one-to-one to every leaf node")

        by_parent: dict[str, list[DuctBranch]] = {}
        for branch in self.branches:
            by_parent.setdefault(branch.parent_node, []).append(branch)

        visited_branches: set[str] = set()

        def walk(node: str, ancestry: frozenset[str]) -> None:
            if node in ancestry:
                raise ValueError("branched duct network cannot contain cycles")
            for branch in by_parent.get(node, []):
                visited_branches.add(branch.name)
                walk(branch.child_node, ancestry | {node})

        walk(self.root_node, frozenset())
        if len(visited_branches) != len(self.branches):
            raise ValueError("all duct branches must be connected to root_node")


def analyze_branched_duct_network(
    network: BranchedDuctNetwork,
    terminal_airflows_m3_h: dict[str, float],
) -> dict:
    expected_rooms = {terminal.room_name for terminal in network.terminals}
    provided_rooms = set(terminal_airflows_m3_h)
    if provided_rooms != expected_rooms:
        details: list[str] = []
        missing = sorted(expected_rooms - provided_rooms)
        unexpected = sorted(provided_rooms - expected_rooms)
        if missing:
            details.append("missing: " + ", ".join(missing))
        if unexpected:
            details.append("unexpected: " + ", ".join(unexpected))
        raise ValueError(
            "terminal airflow mapping must match duct terminals ("
            + "; ".join(details)
            + ")"
        )

    terminal_flows: dict[str, float] = {}
    for room_name, airflow in terminal_airflows_m3_h.items():
        airflow = float(airflow)
        if not math.isfinite(airflow) or airflow <= 0:
            raise ValueError(
                f"terminal airflow for {room_name} must be finite and > 0"
            )
        terminal_flows[room_name] = airflow

    branches_by_parent: dict[str, list[DuctBranch]] = {}
    incoming_by_node: dict[str, DuctBranch] = {}
    for branch in network.branches:
        branches_by_parent.setdefault(branch.parent_node, []).append(branch)
        incoming_by_node[branch.child_node] = branch

    terminal_by_node = {terminal.node: terminal for terminal in network.terminals}
    branch_airflow: dict[str, float] = {}

    def downstream_airflow(node: str) -> float:
        total = 0.0
        terminal = terminal_by_node.get(node)
        if terminal is not None:
            total += terminal_flows[terminal.room_name]
        for branch in branches_by_parent.get(node, []):
            downstream = downstream_airflow(branch.child_node)
            branch_airflow[branch.name] = downstream
            total += downstream
        return total

    root_airflow = downstream_airflow(network.root_node)

    branch_results: list[dict] = []
    result_by_branch: dict[str, dict] = {}
    for branch in network.branches:
        result = analyze_duct_section(
            branch.section_at_airflow(branch_airflow[branch.name])
        )
        result["parent_node"] = branch.parent_node
        result["child_node"] = branch.child_node
        branch_results.append(result)
        result_by_branch[branch.name] = result

    terminal_paths: list[dict] = []
    for terminal in network.terminals:
        branch_names: list[str] = []
        node = terminal.node
        while node != network.root_node:
            branch = incoming_by_node[node]
            branch_names.append(branch.name)
            node = branch.parent_node
        branch_names.reverse()

        pressure_drop = sum(
            result_by_branch[name]["total_pressure_drop_pa"]
            for name in branch_names
        )
        terminal_paths.append(
            {
                "room_name": terminal.room_name,
                "terminal_node": terminal.node,
                "airflow_m3_h": round(terminal_flows[terminal.room_name], 3),
                "branch_names": branch_names,
                "total_pressure_drop_pa": round(pressure_drop, 4),
            }
        )

    critical = max(
        terminal_paths,
        key=lambda path: path["total_pressure_drop_pa"],
    )
    return {
        "root_node": network.root_node,
        "root_airflow_m3_h": round(root_airflow, 3),
        "branches": branch_results,
        "terminal_paths": terminal_paths,
        "critical_terminal_room": critical["room_name"],
        "critical_path": " -> ".join(critical["branch_names"]),
        "critical_path_pressure_drop_pa": critical["total_pressure_drop_pa"],
        "scope_note": (
            "Branch airflow is derived by summing the configured governing airflow "
            "of every downstream terminal room in a validated rooted supply tree. "
            "Section pressure loss uses the existing Darcy-Weisbach/local-K model. "
            "This is not a pressure-driven nonlinear network solution and does not "
            "infer leakage, balancing-damper positions, fan operating point, system "
            "effect, acoustic performance, or control interactions."
        ),
    }
