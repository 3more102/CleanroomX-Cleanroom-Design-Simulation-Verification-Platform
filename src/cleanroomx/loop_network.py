from __future__ import annotations

import math
from dataclasses import dataclass


def _finite(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite")
    return value


def _positive(value: float, field_name: str) -> float:
    value = _finite(value, field_name)
    if value <= 0:
        raise ValueError(f"{field_name} must be > 0")
    return value


@dataclass(frozen=True)
class QuadraticFlowEdge:
    name: str
    start_node: str
    end_node: str
    resistance_pa_per_m3_s_squared: float
    resistance_basis: str = "explicit"
    resistance_evidence: dict | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("loop-network edge name cannot be empty")
        if not self.start_node.strip() or not self.end_node.strip():
            raise ValueError("loop-network edge node names cannot be empty")
        if self.start_node == self.end_node:
            raise ValueError("loop-network edge cannot connect a node to itself")
        object.__setattr__(
            self,
            "resistance_pa_per_m3_s_squared",
            _positive(
                self.resistance_pa_per_m3_s_squared,
                "resistance_pa_per_m3_s_squared",
            ),
        )
        if self.resistance_basis not in {"explicit", "duct_geometry", "damper_adjusted"}:
            raise ValueError(
                "resistance_basis must be 'explicit', 'duct_geometry', or 'damper_adjusted'"
            )
        if self.resistance_evidence is not None:
            object.__setattr__(
                self, "resistance_evidence", dict(self.resistance_evidence)
            )


@dataclass(frozen=True)
class LoopedFlowNetwork:
    name: str
    node_injections_m3_h: dict[str, float]
    edges: tuple[QuadraticFlowEdge, ...]
    reference_node: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("loop-network name cannot be empty")
        if len(self.node_injections_m3_h) < 2:
            raise ValueError("loop-network requires at least two nodes")
        if not self.reference_node.strip():
            raise ValueError("reference_node cannot be empty")

        injections: dict[str, float] = {}
        for node, injection in self.node_injections_m3_h.items():
            if not isinstance(node, str) or not node.strip():
                raise ValueError("loop-network node names must be non-empty strings")
            injections[node] = _finite(injection, f"node injection for {node}")
        object.__setattr__(self, "node_injections_m3_h", injections)

        if self.reference_node not in injections:
            raise ValueError("reference_node must exist in node_injections_m3_h")
        if not self.edges:
            raise ValueError("loop-network requires at least one edge")

        edge_names = [edge.name for edge in self.edges]
        if len(edge_names) != len(set(edge_names)):
            raise ValueError("loop-network edge names must be unique")
        for edge in self.edges:
            if edge.start_node not in injections or edge.end_node not in injections:
                raise ValueError(
                    f"edge {edge.name!r} references a node that is not configured"
                )

        total = sum(injections.values())
        if abs(total) > 1e-6:
            raise ValueError(
                "node injections must sum to zero within 1e-6 m3/h; "
                f"got {total:.9g} m3/h"
            )

        adjacency = {node: set() for node in injections}
        for edge in self.edges:
            adjacency[edge.start_node].add(edge.end_node)
            adjacency[edge.end_node].add(edge.start_node)
        visited = {self.reference_node}
        pending = [self.reference_node]
        while pending:
            node = pending.pop()
            for neighbor in adjacency[node]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    pending.append(neighbor)
        if len(visited) != len(injections):
            raise ValueError("loop-network graph must be connected")


def _edge_flow_m3_s(
    pressure_difference_pa: float,
    resistance_pa_per_m3_s_squared: float,
) -> float:
    if pressure_difference_pa == 0.0:
        return 0.0
    return math.copysign(
        math.sqrt(abs(pressure_difference_pa) / resistance_pa_per_m3_s_squared),
        pressure_difference_pa,
    )


def _solve_linear_system(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    size = len(rhs)
    augmented = [row[:] + [rhs[index]] for index, row in enumerate(matrix)]

    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-18:
            raise RuntimeError("loop-network Newton system became singular")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]

        for row in range(column + 1, size):
            factor = augmented[row][column] / augmented[column][column]
            if factor == 0.0:
                continue
            for item in range(column, size + 1):
                augmented[row][item] -= factor * augmented[column][item]

    solution = [0.0] * size
    for row in range(size - 1, -1, -1):
        numerator = augmented[row][size] - sum(
            augmented[row][column] * solution[column]
            for column in range(row + 1, size)
        )
        solution[row] = numerator / augmented[row][row]
    return solution


def _initial_node_pressures(network: LoopedFlowNetwork) -> dict[str, float]:
    adjacency: dict[str, list[tuple[str, int]]] = {
        node: [] for node in network.node_injections_m3_h
    }
    for edge_index, edge in enumerate(network.edges):
        adjacency[edge.start_node].append((edge.end_node, edge_index))
        adjacency[edge.end_node].append((edge.start_node, edge_index))

    parent: dict[str, str | None] = {network.reference_node: None}
    parent_edge: dict[str, int] = {}
    order = [network.reference_node]
    for node in order:
        for neighbor, edge_index in adjacency[node]:
            if neighbor in parent:
                continue
            parent[neighbor] = node
            parent_edge[neighbor] = edge_index
            order.append(neighbor)

    subtree_injection_m3_s = {
        node: injection / 3600.0
        for node, injection in network.node_injections_m3_h.items()
    }
    for node in reversed(order[1:]):
        parent_node = parent[node]
        assert parent_node is not None
        subtree_injection_m3_s[parent_node] += subtree_injection_m3_s[node]

    pressures = {network.reference_node: 0.0}
    for node in order[1:]:
        parent_node = parent[node]
        assert parent_node is not None
        edge = network.edges[parent_edge[node]]
        flow_parent_to_child_m3_s = -subtree_injection_m3_s[node]
        pressure_drop_pa = (
            edge.resistance_pa_per_m3_s_squared
            * flow_parent_to_child_m3_s
            * abs(flow_parent_to_child_m3_s)
        )
        pressures[node] = pressures[parent_node] - pressure_drop_pa
    return pressures


def solve_looped_network(
    network: LoopedFlowNetwork,
    *,
    mass_balance_tolerance_m3_h: float = 1e-6,
    max_iterations: int = 100,
) -> dict:
    tolerance_m3_h = _positive(
        mass_balance_tolerance_m3_h, "mass_balance_tolerance_m3_h"
    )
    if (
        isinstance(max_iterations, bool)
        or not isinstance(max_iterations, int)
        or max_iterations <= 0
    ):
        raise ValueError("max_iterations must be an integer > 0")

    nodes = tuple(network.node_injections_m3_h)
    unknown_nodes = tuple(node for node in nodes if node != network.reference_node)
    unknown_index = {node: index for index, node in enumerate(unknown_nodes)}
    injections_m3_s = {
        node: injection / 3600.0
        for node, injection in network.node_injections_m3_h.items()
    }
    pressures = _initial_node_pressures(network)
    tolerance_m3_s = tolerance_m3_h / 3600.0

    def evaluate(
        node_pressures: dict[str, float],
    ) -> tuple[dict[str, float], list[float]]:
        residuals = dict(injections_m3_s)
        edge_flows: list[float] = []
        for edge in network.edges:
            pressure_difference_pa = (
                node_pressures[edge.start_node] - node_pressures[edge.end_node]
            )
            airflow_m3_s = _edge_flow_m3_s(
                pressure_difference_pa,
                edge.resistance_pa_per_m3_s_squared,
            )
            edge_flows.append(airflow_m3_s)
            residuals[edge.start_node] -= airflow_m3_s
            residuals[edge.end_node] += airflow_m3_s
        return residuals, edge_flows

    iterations = 0
    while True:
        residuals, edge_flows = evaluate(pressures)
        max_mass_balance_residual = max(
            abs(residuals[node]) for node in nodes
        )
        if max_mass_balance_residual <= tolerance_m3_s:
            break
        if iterations >= max_iterations:
            raise RuntimeError(
                "loop-network solver did not converge within max_iterations"
            )

        size = len(unknown_nodes)
        jacobian = [[0.0 for _ in range(size)] for _ in range(size)]
        for edge in network.edges:
            pressure_difference_pa = (
                pressures[edge.start_node] - pressures[edge.end_node]
            )
            effective_pressure_pa = max(abs(pressure_difference_pa), 1e-12)
            derivative = 1.0 / (
                2.0
                * math.sqrt(
                    edge.resistance_pa_per_m3_s_squared * effective_pressure_pa
                )
            )

            start_index = unknown_index.get(edge.start_node)
            end_index = unknown_index.get(edge.end_node)
            if start_index is not None:
                jacobian[start_index][start_index] -= derivative
                if end_index is not None:
                    jacobian[start_index][end_index] += derivative
            if end_index is not None:
                if start_index is not None:
                    jacobian[end_index][start_index] += derivative
                jacobian[end_index][end_index] -= derivative

        step = _solve_linear_system(
            jacobian,
            [-residuals[node] for node in unknown_nodes],
        )
        baseline = max_mass_balance_residual
        line_search_scale = 1.0
        accepted = False
        while line_search_scale >= 2.0**-20:
            candidate = dict(pressures)
            for node, delta in zip(unknown_nodes, step):
                candidate[node] = (
                    pressures[node] + line_search_scale * delta
                )
            candidate_residuals, _ = evaluate(candidate)
            candidate_norm = max(
                abs(candidate_residuals[node]) for node in nodes
            )
            if candidate_norm < baseline:
                pressures = candidate
                accepted = True
                break
            line_search_scale *= 0.5

        if not accepted:
            raise RuntimeError(
                "loop-network Newton line search failed to reduce mass-balance residual"
            )
        iterations += 1

    residuals, edge_flows = evaluate(pressures)
    node_results = []
    for node in nodes:
        residual_m3_h = residuals[node] * 3600.0
        injection_m3_h = network.node_injections_m3_h[node]
        node_results.append(
            {
                "name": node,
                "relative_pressure_pa": round(pressures[node], 9),
                "specified_injection_m3_h": round(injection_m3_h, 9),
                "net_edge_outflow_m3_h": round(
                    injection_m3_h - residual_m3_h, 9
                ),
                "mass_balance_residual_m3_h": round(residual_m3_h, 12),
            }
        )

    edge_results = []
    pressure_law_errors = []
    for edge, airflow_m3_s in zip(network.edges, edge_flows):
        actual_pressure_difference_pa = (
            pressures[edge.start_node] - pressures[edge.end_node]
        )
        constitutive_pressure_difference_pa = (
            edge.resistance_pa_per_m3_s_squared
            * airflow_m3_s
            * abs(airflow_m3_s)
        )
        pressure_error_pa = (
            actual_pressure_difference_pa
            - constitutive_pressure_difference_pa
        )
        pressure_law_errors.append(abs(pressure_error_pa))
        if airflow_m3_s > 0:
            direction = f"{edge.start_node} -> {edge.end_node}"
        elif airflow_m3_s < 0:
            direction = f"{edge.end_node} -> {edge.start_node}"
        else:
            direction = "zero flow"
        edge_results.append(
            {
                "name": edge.name,
                "start_node": edge.start_node,
                "end_node": edge.end_node,
                "resistance_pa_per_m3_s_squared": round(
                    edge.resistance_pa_per_m3_s_squared, 9
                ),
                "resistance_basis": edge.resistance_basis,
                "resistance_evidence": edge.resistance_evidence,
                "airflow_m3_s": round(airflow_m3_s, 12),
                "airflow_m3_h": round(airflow_m3_s * 3600.0, 6),
                "flow_direction": direction,
                "pressure_difference_pa": round(
                    actual_pressure_difference_pa, 9
                ),
                "constitutive_pressure_difference_pa": round(
                    constitutive_pressure_difference_pa, 9
                ),
                "pressure_law_residual_pa": round(
                    pressure_error_pa, 12
                ),
            }
        )

    max_mass_balance_error_m3_h = max(
        abs(residuals[node] * 3600.0) for node in nodes
    )
    return {
        "network": network.name,
        "status": "solved",
        "reference_node": network.reference_node,
        "iterations": iterations,
        "mass_balance_tolerance_m3_h": tolerance_m3_h,
        "nodes": node_results,
        "edges": edge_results,
        "max_abs_mass_balance_residual_m3_h": round(
            max_mass_balance_error_m3_h, 12
        ),
        "max_abs_pressure_law_residual_pa": round(
            max(pressure_law_errors, default=0.0), 12
        ),
        "scope_note": (
            "This solver handles connected steady-state networks with arbitrary loops "
            "when every edge uses a fixed quadratic pressure-loss law "
            "deltaP = R*Q*abs(Q) and node injections are explicitly specified and "
            "balanced. Node pressures are relative to the configured reference node. "
            "Edge resistance may be supplied directly or pre-derived from explicit duct "
            "geometry. Geometry-derived resistance remains fixed during the solve. "
            "The solver does not iterate flow-dependent friction, fan curves, dampers, "
            "controls, leakage, compressibility, or transient behavior."
        ),
    }
