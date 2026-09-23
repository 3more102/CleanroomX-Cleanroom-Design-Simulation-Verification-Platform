from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass


def _nonnegative(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{field_name} must be finite and >= 0")
    return value


@dataclass(frozen=True)
class SupplyNode:
    name: str
    room_name: str | None = None
    fixed_airflow_m3_h: float = 0.0

    def __post_init__(self) -> None:
        name = self.name.strip()
        if not name:
            raise ValueError("supply-node name cannot be empty")
        object.__setattr__(self, "name", name)

        if self.room_name is not None:
            room_name = self.room_name.strip()
            if not room_name:
                raise ValueError("room_name cannot be empty when supplied")
            object.__setattr__(self, "room_name", room_name)

        object.__setattr__(
            self,
            "fixed_airflow_m3_h",
            _nonnegative(self.fixed_airflow_m3_h, "fixed_airflow_m3_h"),
        )


@dataclass(frozen=True)
class SupplyBranch:
    name: str
    upstream_node: str
    downstream_node: str

    def __post_init__(self) -> None:
        name = self.name.strip()
        upstream = self.upstream_node.strip()
        downstream = self.downstream_node.strip()
        if not name:
            raise ValueError("supply-branch name cannot be empty")
        if not upstream or not downstream:
            raise ValueError("supply-branch node names cannot be empty")
        if upstream == downstream:
            raise ValueError("supply branch cannot connect a node to itself")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "upstream_node", upstream)
        object.__setattr__(self, "downstream_node", downstream)


@dataclass(frozen=True)
class SupplyNetwork:
    source_node: str
    nodes: tuple[SupplyNode, ...]
    branches: tuple[SupplyBranch, ...]

    def __post_init__(self) -> None:
        source = self.source_node.strip()
        if not source:
            raise ValueError("source_node cannot be empty")
        object.__setattr__(self, "source_node", source)

        if not self.nodes:
            raise ValueError("supply network must contain at least one node")

        node_names = [node.name for node in self.nodes]
        if len(node_names) != len(set(node_names)):
            raise ValueError("supply-node names must be unique")
        node_set = set(node_names)
        if source not in node_set:
            raise ValueError("source_node must reference a defined supply node")

        branch_names = [branch.name for branch in self.branches]
        if len(branch_names) != len(set(branch_names)):
            raise ValueError("supply-branch names must be unique")

        room_names = [node.room_name for node in self.nodes if node.room_name is not None]
        if len(room_names) != len(set(room_names)):
            raise ValueError("each HVAC room may be referenced by only one supply node")

        incoming_count = {name: 0 for name in node_names}
        outgoing: dict[str, list[str]] = defaultdict(list)
        for branch in self.branches:
            if branch.upstream_node not in node_set:
                raise ValueError(
                    f"supply branch {branch.name!r} references unknown upstream node "
                    f"{branch.upstream_node!r}"
                )
            if branch.downstream_node not in node_set:
                raise ValueError(
                    f"supply branch {branch.name!r} references unknown downstream node "
                    f"{branch.downstream_node!r}"
                )
            incoming_count[branch.downstream_node] += 1
            outgoing[branch.upstream_node].append(branch.downstream_node)

        if incoming_count[source] != 0:
            raise ValueError("source_node cannot have an incoming supply branch")

        for node_name in node_names:
            if node_name == source:
                continue
            if incoming_count[node_name] != 1:
                raise ValueError(
                    "every non-source supply node must have exactly one incoming branch"
                )

        visited: set[str] = set()
        stack = [source]
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            stack.extend(outgoing[current])

        if visited != node_set:
            missing = ", ".join(sorted(node_set - visited))
            raise ValueError(
                f"all supply nodes must be reachable from source_node; unreachable: {missing}"
            )


def solve_supply_network(
    network: SupplyNetwork,
    room_airflows_m3_h: dict[str, float] | None = None,
) -> dict:
    room_airflows_m3_h = room_airflows_m3_h or {}

    children: dict[str, list[SupplyBranch]] = defaultdict(list)
    for branch in network.branches:
        children[branch.upstream_node].append(branch)

    direct_demand: dict[str, float] = {}
    room_component: dict[str, float] = {}
    for node in network.nodes:
        room_flow = 0.0
        if node.room_name is not None:
            if node.room_name not in room_airflows_m3_h:
                raise ValueError(
                    f"supply node {node.name!r} references room {node.room_name!r}, "
                    "but no room airflow was supplied"
                )
            room_flow = _nonnegative(
                room_airflows_m3_h[node.room_name],
                f"room airflow for {node.room_name}",
            )
        room_component[node.name] = room_flow
        direct_demand[node.name] = node.fixed_airflow_m3_h + room_flow

    branch_flow: dict[str, float] = {}
    subtree_flow: dict[str, float] = {}

    def accumulate(node_name: str) -> float:
        total = direct_demand[node_name]
        for branch in children[node_name]:
            downstream_flow = accumulate(branch.downstream_node)
            branch_flow[branch.name] = downstream_flow
            total += downstream_flow
        subtree_flow[node_name] = total
        return total

    source_airflow = accumulate(network.source_node)

    node_results = []
    for node in network.nodes:
        node_results.append(
            {
                "name": node.name,
                "room_name": node.room_name,
                "room_airflow_m3_h": round(room_component[node.name], 3),
                "fixed_airflow_m3_h": round(node.fixed_airflow_m3_h, 3),
                "direct_demand_m3_h": round(direct_demand[node.name], 3),
                "downstream_total_m3_h": round(subtree_flow[node.name], 3),
            }
        )

    branch_results = []
    for branch in network.branches:
        branch_results.append(
            {
                "name": branch.name,
                "upstream_node": branch.upstream_node,
                "downstream_node": branch.downstream_node,
                "airflow_m3_h": round(branch_flow[branch.name], 3),
            }
        )

    total_fixed = sum(node.fixed_airflow_m3_h for node in network.nodes)
    total_room = sum(room_component.values())
    return {
        "source_node": network.source_node,
        "source_airflow_m3_h": round(source_airflow, 3),
        "total_room_airflow_m3_h": round(total_room, 3),
        "total_fixed_airflow_m3_h": round(total_fixed, 3),
        "nodes": node_results,
        "branches": branch_results,
        "scope_note": (
            "Supply-network airflow is a deterministic downstream demand aggregation on "
            "a rooted tree. It does not solve pressure-driven flow distribution, leakage, "
            "damper authority, diversity, fan curves, or control interactions."
        ),
    }
