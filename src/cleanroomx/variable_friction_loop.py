from __future__ import annotations

import math

from .loop_network import LoopedFlowNetwork, QuadraticFlowEdge, solve_looped_network
from .loop_resistance import LoopedDuctResistanceInput, derive_loop_edge_resistance


def _positive(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{field_name} must be finite and > 0")
    return value


def _unit_interval(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0 or value > 1:
        raise ValueError(f"{field_name} must be finite and in (0, 1]")
    return value


def _nonnegative(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{field_name} must be finite and >= 0")
    return value


def _is_automatic_geometry_edge(edge: QuadraticFlowEdge) -> bool:
    evidence = edge.resistance_evidence
    return (
        edge.resistance_basis == "duct_geometry"
        and evidence is not None
        and evidence.get("absolute_roughness_m") is not None
        and evidence.get("kinematic_viscosity_m2_s") is not None
    )


def _validate_automatic_geometry_evidence(
    edge: QuadraticFlowEdge,
) -> None:
    evidence = edge.resistance_evidence
    if evidence is None:
        raise ValueError(
            f"automatic-friction edge {edge.name!r} requires resistance evidence"
        )

    required = {
        "length_m",
        "air_density_kg_m3",
        "local_loss_coefficient",
        "absolute_roughness_m",
        "kinematic_viscosity_m2_s",
        "reference_airflow_m3_h",
        "shape",
        "area_m2",
        "hydraulic_diameter_m",
        "friction_factor",
    }
    missing = sorted(required - set(evidence))
    if missing:
        raise ValueError(
            f"automatic-friction edge {edge.name!r} has incomplete resistance "
            "evidence; missing: " + ", ".join(missing)
        )

    reference_airflow = _positive(
        evidence["reference_airflow_m3_h"],
        f"automatic-friction edge {edge.name!r} reference_airflow_m3_h",
    )
    _positive(
        evidence["friction_factor"],
        f"automatic-friction edge {edge.name!r} friction_factor",
    )

    # Reconstruct the geometry/friction calculation at the stored reference
    # airflow. This validates finite physical evidence and the stored shape
    # before any near-zero-flow branch can freeze the resistance and otherwise
    # conceal malformed automatic-friction provenance.
    _target_evidence_at_airflow(edge, reference_airflow)


def _rectangular_dimensions(
    area_m2: float,
    hydraulic_diameter_m: float,
) -> tuple[float, float]:
    area = _positive(area_m2, "area_m2")
    hydraulic_diameter = _positive(
        hydraulic_diameter_m, "hydraulic_diameter_m"
    )
    side_sum = 2.0 * area / hydraulic_diameter
    discriminant = side_sum**2 - 4.0 * area
    tolerance = 1e-12 * max(side_sum**2, 4.0 * area, 1.0)
    if discriminant < -tolerance:
        raise ValueError(
            "stored rectangular duct evidence is geometrically inconsistent"
        )
    discriminant = max(discriminant, 0.0)
    root = math.sqrt(discriminant)
    width = 0.5 * (side_sum + root)
    height = 0.5 * (side_sum - root)
    if width <= 0 or height <= 0:
        raise ValueError(
            "stored rectangular duct evidence has invalid dimensions"
        )
    return width, height


def _target_evidence_at_airflow(
    edge: QuadraticFlowEdge,
    airflow_m3_h: float,
) -> dict:
    evidence = edge.resistance_evidence
    if evidence is None:
        raise ValueError(f"edge {edge.name!r} has no resistance evidence")

    common = {
        "length_m": evidence["length_m"],
        "air_density_kg_m3": evidence["air_density_kg_m3"],
        "local_loss_coefficient": evidence["local_loss_coefficient"],
        "absolute_roughness_m": evidence["absolute_roughness_m"],
        "kinematic_viscosity_m2_s": evidence["kinematic_viscosity_m2_s"],
        "reference_airflow_m3_h": airflow_m3_h,
    }
    shape = evidence["shape"]
    if shape == "circular":
        common["diameter_m"] = evidence["hydraulic_diameter_m"]
    elif shape == "rectangular":
        width, height = _rectangular_dimensions(
            evidence["area_m2"], evidence["hydraulic_diameter_m"]
        )
        common["width_m"] = width
        common["height_m"] = height
    else:
        raise ValueError(f"unsupported stored duct shape {shape!r}")

    try:
        return derive_loop_edge_resistance(
            LoopedDuctResistanceInput(**common)
        )
    except ValueError as exc:
        raise ValueError(
            f"automatic friction update failed for edge {edge.name!r} "
            f"at {airflow_m3_h:.9g} m3/h: {exc}"
        ) from exc


def _relaxed_automatic_edge(
    edge: QuadraticFlowEdge,
    target_evidence: dict,
    relaxation: float,
) -> QuadraticFlowEdge:
    current = edge.resistance_evidence
    assert current is not None
    current_f = float(current["friction_factor"])
    target_f = float(target_evidence["friction_factor"])
    friction_factor = current_f + relaxation * (target_f - current_f)

    length_m = float(target_evidence["length_m"])
    hydraulic_diameter_m = float(target_evidence["hydraulic_diameter_m"])
    local_k = float(target_evidence["local_loss_coefficient"])
    density = float(target_evidence["air_density_kg_m3"])
    area_m2 = float(target_evidence["area_m2"])
    combined_k = (
        friction_factor * length_m / hydraulic_diameter_m + local_k
    )
    resistance = 0.5 * density * combined_k / area_m2**2

    evidence = dict(target_evidence)
    evidence["friction_factor"] = friction_factor
    evidence["combined_loss_coefficient"] = combined_k
    evidence["resistance_pa_per_m3_s_squared"] = resistance
    if relaxation < 1.0:
        evidence["friction_factor_method"] = (
            f"{target_evidence['friction_factor_method']}_relaxed"
        )
    return QuadraticFlowEdge(
        name=edge.name,
        start_node=edge.start_node,
        end_node=edge.end_node,
        resistance_pa_per_m3_s_squared=resistance,
        resistance_basis="duct_geometry",
        resistance_evidence=evidence,
    )


def _edge_target_rows(
    network: LoopedFlowNetwork,
    solved: dict,
    near_zero_airflow_m3_h: float,
) -> tuple[list[dict], float, int]:
    solved_edges = {row["name"]: row for row in solved["edges"]}
    rows: list[dict] = []
    max_relative_change = 0.0
    near_zero_count = 0

    for edge in network.edges:
        solved_edge = solved_edges[edge.name]
        airflow = abs(float(solved_edge["airflow_m3_h"]))
        if not _is_automatic_geometry_edge(edge):
            rows.append(
                {
                    "name": edge.name,
                    "state": "fixed_resistance",
                    "airflow_m3_h": airflow,
                    "used_resistance_pa_per_m3_s_squared": (
                        edge.resistance_pa_per_m3_s_squared
                    ),
                    "target_resistance_pa_per_m3_s_squared": None,
                    "relative_resistance_change": 0.0,
                    "target_evidence": None,
                }
            )
            continue

        if airflow <= near_zero_airflow_m3_h:
            near_zero_count += 1
            rows.append(
                {
                    "name": edge.name,
                    "state": "near_zero_flow_frozen",
                    "airflow_m3_h": airflow,
                    "used_resistance_pa_per_m3_s_squared": (
                        edge.resistance_pa_per_m3_s_squared
                    ),
                    "target_resistance_pa_per_m3_s_squared": None,
                    "relative_resistance_change": 0.0,
                    "target_evidence": None,
                }
            )
            continue

        target = _target_evidence_at_airflow(edge, airflow)
        target_r = float(target["resistance_pa_per_m3_s_squared"])
        used_r = edge.resistance_pa_per_m3_s_squared
        relative = abs(target_r - used_r) / max(
            abs(target_r), abs(used_r), 1e-30
        )
        max_relative_change = max(max_relative_change, relative)
        rows.append(
            {
                "name": edge.name,
                "state": "automatic_friction",
                "airflow_m3_h": airflow,
                "used_resistance_pa_per_m3_s_squared": used_r,
                "target_resistance_pa_per_m3_s_squared": target_r,
                "relative_resistance_change": relative,
                "target_evidence": target,
            }
        )

    return rows, max_relative_change, near_zero_count


def _updated_network(
    network: LoopedFlowNetwork,
    rows: list[dict],
    relaxation: float,
) -> LoopedFlowNetwork:
    row_by_name = {row["name"]: row for row in rows}
    edges: list[QuadraticFlowEdge] = []
    for edge in network.edges:
        row = row_by_name[edge.name]
        target = row["target_evidence"]
        if (
            row["state"] == "automatic_friction"
            and target is not None
        ):
            edges.append(
                _relaxed_automatic_edge(edge, target, relaxation)
            )
        else:
            edges.append(edge)
    return LoopedFlowNetwork(
        name=network.name,
        node_injections_m3_h=network.node_injections_m3_h,
        edges=tuple(edges),
        reference_node=network.reference_node,
    )


def _decorate_result(
    solved: dict,
    *,
    rows: list[dict],
    history: list[dict],
    automatic_edge_count: int,
    near_zero_count: int,
    resistance_relative_tolerance: float,
    relaxation: float,
    near_zero_airflow_m3_h: float,
    max_relative_change: float,
) -> dict:
    result = dict(solved)
    closure_rows = []
    for row in rows:
        target = row["target_evidence"]
        closure_rows.append(
            {
                "name": row["name"],
                "state": row["state"],
                "airflow_m3_h": round(row["airflow_m3_h"], 9),
                "used_resistance_pa_per_m3_s_squared": round(
                    row["used_resistance_pa_per_m3_s_squared"], 12
                ),
                "target_resistance_pa_per_m3_s_squared": (
                    None
                    if row["target_resistance_pa_per_m3_s_squared"]
                    is None
                    else round(
                        row[
                            "target_resistance_pa_per_m3_s_squared"
                        ],
                        12,
                    )
                ),
                "relative_resistance_change": round(
                    row["relative_resistance_change"], 12
                ),
                "target_friction_factor": (
                    None
                    if target is None
                    else round(target["friction_factor"], 12)
                ),
                "target_friction_factor_method": (
                    None
                    if target is None
                    else target["friction_factor_method"]
                ),
                "target_reynolds_number": (
                    None
                    if target is None
                    or target["reynolds_number"] is None
                    else round(target["reynolds_number"], 6)
                ),
            }
        )

    result["variable_friction"] = {
        "converged": True,
        "outer_iterations": len(history),
        "automatic_friction_edge_count": automatic_edge_count,
        "near_zero_frozen_edge_count": near_zero_count,
        "resistance_relative_tolerance": resistance_relative_tolerance,
        "relaxation": relaxation,
        "near_zero_airflow_m3_h": near_zero_airflow_m3_h,
        "max_relative_resistance_closure_error": round(
            max_relative_change, 12
        ),
        "iteration_history": history,
        "edge_closure": closure_rows,
    }
    result["scope_note"] = (
        "This solver adds outer iteration around the fixed-resistance loop "
        "solver for geometry-derived edges whose Darcy friction factor was "
        "configured from explicit absolute roughness and kinematic viscosity. "
        "At each outer iteration, Darcy friction is re-evaluated at the "
        "absolute solved edge airflow and resistance is updated until the "
        "configured relative closure tolerance is met. Explicit resistance "
        "edges and geometry edges with a user-supplied friction factor remain "
        "fixed. Near-zero-flow automatic-friction edges retain their previous "
        "resistance because Reynolds-based friction is undefined at exactly "
        "zero flow. The model keeps density and local-loss coefficients fixed "
        "and does not infer dampers, controls, leakage, system effect, fan "
        "behavior, compressibility, or transients."
    )
    return result


def solve_variable_friction_looped_network(
    network: LoopedFlowNetwork,
    *,
    resistance_relative_tolerance: float = 1e-6,
    relaxation: float = 0.5,
    near_zero_airflow_m3_h: float = 1e-6,
    max_outer_iterations: int = 50,
    mass_balance_tolerance_m3_h: float = 1e-6,
    max_newton_iterations: int = 100,
) -> dict:
    tolerance = _positive(
        resistance_relative_tolerance,
        "resistance_relative_tolerance",
    )
    relaxation = _unit_interval(relaxation, "relaxation")
    near_zero = _nonnegative(
        near_zero_airflow_m3_h,
        "near_zero_airflow_m3_h",
    )
    if (
        isinstance(max_outer_iterations, bool)
        or not isinstance(max_outer_iterations, int)
        or max_outer_iterations <= 0
    ):
        raise ValueError(
            "max_outer_iterations must be an integer > 0"
        )

    automatic_edges = [
        edge for edge in network.edges if _is_automatic_geometry_edge(edge)
    ]
    for edge in automatic_edges:
        _validate_automatic_geometry_evidence(edge)
    automatic_edge_count = len(automatic_edges)

    if automatic_edge_count == 0:
        solved = solve_looped_network(
            network,
            mass_balance_tolerance_m3_h=mass_balance_tolerance_m3_h,
            max_iterations=max_newton_iterations,
        )
        rows, max_relative_change, near_zero_count = (
            _edge_target_rows(network, solved, near_zero)
        )
        return _decorate_result(
            solved,
            rows=rows,
            history=[],
            automatic_edge_count=0,
            near_zero_count=near_zero_count,
            resistance_relative_tolerance=tolerance,
            relaxation=relaxation,
            near_zero_airflow_m3_h=near_zero,
            max_relative_change=max_relative_change,
        )

    current = network
    history: list[dict] = []
    for outer_iteration in range(
        1, max_outer_iterations + 1
    ):
        solved = solve_looped_network(
            current,
            mass_balance_tolerance_m3_h=mass_balance_tolerance_m3_h,
            max_iterations=max_newton_iterations,
        )
        rows, max_relative_change, near_zero_count = (
            _edge_target_rows(current, solved, near_zero)
        )
        history.append(
            {
                "outer_iteration": outer_iteration,
                "max_relative_resistance_change": round(
                    max_relative_change, 12
                ),
                "max_abs_mass_balance_residual_m3_h": solved[
                    "max_abs_mass_balance_residual_m3_h"
                ],
                "near_zero_frozen_edge_count": near_zero_count,
            }
        )
        if max_relative_change <= tolerance:
            return _decorate_result(
                solved,
                rows=rows,
                history=history,
                automatic_edge_count=automatic_edge_count,
                near_zero_count=near_zero_count,
                resistance_relative_tolerance=tolerance,
                relaxation=relaxation,
                near_zero_airflow_m3_h=near_zero,
                max_relative_change=max_relative_change,
            )
        current = _updated_network(
            current, rows, relaxation
        )

    raise RuntimeError(
        "variable-friction loop solver did not converge within "
        "max_outer_iterations; last relative resistance closure "
        f"error was {max_relative_change:.9g}"
    )
