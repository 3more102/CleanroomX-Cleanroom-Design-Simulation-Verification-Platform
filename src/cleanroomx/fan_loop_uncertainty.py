from __future__ import annotations

from dataclasses import asdict
from itertools import product
from math import prod

from .fan_loop_network import FanLoopNetworkStudy, solve_fan_loop_network
from .fan_loop_uncertainty_models import (
    EdgeResistanceUncertainty,
    FanLoopNetworkUncertaintyStudy,
)
from .loop_network import LoopedFlowNetwork, QuadraticFlowEdge
from .uncertainty_models import Provenance, UncertainValue


def _provenance_record(
    provenance: Provenance | None,
) -> dict | None:
    return None if provenance is None else asdict(provenance)


def _input_record(name: str, item: UncertainValue) -> dict:
    return {
        "name": name,
        "value": item.value,
        "unit": item.unit,
        "uncertainty_abs": item.uncertainty_abs,
        "lower": item.lower,
        "upper": item.upper,
        "provenance": _provenance_record(item.provenance),
    }


def _edge_input_record(
    edge: QuadraticFlowEdge,
    item: EdgeResistanceUncertainty,
) -> dict:
    nominal = edge.resistance_pa_per_m3_s_squared
    return {
        "name": f"edge:{edge.name}",
        "edge": edge.name,
        "value": nominal,
        "unit": "Pa/(m3/s)^2",
        "uncertainty_abs": item.uncertainty_abs,
        "lower": nominal - item.uncertainty_abs,
        "upper": nominal + item.uncertainty_abs,
        "provenance": _provenance_record(item.provenance),
        "base_resistance_basis": edge.resistance_basis,
        "base_resistance_evidence": edge.resistance_evidence,
    }


def _adjusted_edge(
    edge: QuadraticFlowEdge,
    resistance: float,
    uncertainty: EdgeResistanceUncertainty,
) -> QuadraticFlowEdge:
    if resistance == edge.resistance_pa_per_m3_s_squared:
        return edge

    evidence = {
        "base_resistance_basis": edge.resistance_basis,
        "base_resistance_pa_per_m3_s_squared": (
            edge.resistance_pa_per_m3_s_squared
        ),
        "uncertainty_abs_pa_per_m3_s_squared": (
            uncertainty.uncertainty_abs
        ),
        "corner_resistance_pa_per_m3_s_squared": resistance,
        "uncertainty_provenance": _provenance_record(
            uncertainty.provenance
        ),
    }
    if edge.resistance_evidence is not None:
        evidence["base_resistance_evidence"] = edge.resistance_evidence

    return QuadraticFlowEdge(
        name=edge.name,
        start_node=edge.start_node,
        end_node=edge.end_node,
        resistance_pa_per_m3_s_squared=resistance,
        resistance_basis="uncertainty_adjusted",
        resistance_evidence=evidence,
    )


def _network_at_corner(
    study: FanLoopNetworkUncertaintyStudy,
    edge_resistances: dict[str, float],
) -> LoopedFlowNetwork:
    uncertainty_by_name = {
        item.edge_name: item
        for item in study.edge_resistance_uncertainties
    }
    return LoopedFlowNetwork(
        name=study.loop_network.name,
        node_injections_m3_h=dict(study.loop_network.node_injections_m3_h),
        edges=tuple(
            _adjusted_edge(
                edge,
                edge_resistances.get(
                    edge.name,
                    edge.resistance_pa_per_m3_s_squared,
                ),
                uncertainty_by_name[edge.name],
            )
            if edge.name in edge_resistances
            else edge
            for edge in study.loop_network.edges
        ),
        reference_node=study.loop_network.reference_node,
    )


def _solve_case(
    study: FanLoopNetworkUncertaintyStudy,
    fixed_pressure_pa: float,
    edge_resistances: dict[str, float],
) -> dict:
    return solve_fan_loop_network(
        FanLoopNetworkStudy(
            name=study.name,
            fan_curve=study.fan_curve,
            loop_network=_network_at_corner(study, edge_resistances),
            fan_discharge_node=study.fan_discharge_node,
            fan_suction_node=study.fan_suction_node,
            fixed_pressure_pa=fixed_pressure_pa,
        )
    )


def _metric_envelope(
    values: list[float],
    unit: str,
) -> dict:
    return {
        "lower": round(min(values), 6),
        "upper": round(max(values), 6),
        "unit": unit,
    }


def _edge_airflow_corner_ranges(
    study: FanLoopNetworkUncertaintyStudy,
    solved_networks: list[dict],
) -> list[dict]:
    rows = []
    for edge in study.loop_network.edges:
        values = [
            float(
                next(
                    item
                    for item in network["edges"]
                    if item["name"] == edge.name
                )["airflow_m3_h"]
            )
            for network in solved_networks
        ]
        lower = min(values)
        upper = max(values)
        rows.append(
            {
                "edge": edge.name,
                "lower_airflow_m3_h": round(lower, 6),
                "upper_airflow_m3_h": round(upper, 6),
                "direction_reversal_across_corners": (
                    lower < 0.0 < upper
                ),
            }
        )
    return rows


def analyze_fan_loop_network_uncertainty(
    study: FanLoopNetworkUncertaintyStudy,
) -> dict:
    nominal = _solve_case(
        study,
        study.fixed_pressure_pa.value,
        {},
    )

    fixed_values = sorted(
        {
            study.fixed_pressure_pa.lower,
            study.fixed_pressure_pa.upper,
        }
    )
    base_edges = {edge.name: edge for edge in study.loop_network.edges}
    uncertainty_items = list(study.edge_resistance_uncertainties)
    edge_value_sets = []
    for item in uncertainty_items:
        nominal_r = base_edges[
            item.edge_name
        ].resistance_pa_per_m3_s_squared
        edge_value_sets.append(
            sorted(
                {
                    nominal_r - item.uncertainty_abs,
                    nominal_r + item.uncertainty_abs,
                }
            )
        )

    corner_count = len(fixed_values) * prod(
        len(values) for values in edge_value_sets
    )
    if corner_count > study.max_corner_cases:
        raise ValueError(
            f"fan/loop uncertainty corner count {corner_count} "
            f"exceeding max_corner_cases={study.max_corner_cases}"
        )

    corners = []
    solved_points = []
    solved_networks = []
    equivalent_resistances = []

    for combination in product(
        fixed_values,
        *edge_value_sets,
    ):
        fixed_pressure = combination[0]
        edge_resistances = {
            item.edge_name: value
            for item, value in zip(
                uncertainty_items,
                combination[1:],
            )
        }
        result = _solve_case(
            study,
            fixed_pressure,
            edge_resistances,
        )
        equivalent = float(
            result[
                "equivalent_loop_resistance_pa_per_m3_s_squared"
            ]
        )
        equivalent_resistances.append(equivalent)

        point = result["fan_operating_point"]
        network = result["operating_network_solution"]
        if point is not None and network is not None:
            solved_points.append(point)
            solved_networks.append(network)

        corners.append(
            {
                "fixed_pressure_pa": round(fixed_pressure, 6),
                "edge_resistance_pa_per_m3_s_squared": {
                    name: round(value, 9)
                    for name, value in edge_resistances.items()
                },
                "status": result["status"],
                "equivalent_loop_resistance_pa_per_m3_s_squared": (
                    round(equivalent, 9)
                ),
                "operating_point": point,
                "max_abs_mass_balance_residual_m3_h": (
                    None
                    if network is None
                    else network[
                        "max_abs_mass_balance_residual_m3_h"
                    ]
                ),
                "max_abs_pressure_law_residual_pa": (
                    None
                    if network is None
                    else network[
                        "max_abs_pressure_law_residual_pa"
                    ]
                ),
            }
        )

    unresolved_corner_count = sum(
        corner["status"] != "solved"
        for corner in corners
    )
    all_corners_solved = (
        nominal["status"] == "solved"
        and unresolved_corner_count == 0
    )

    operating_envelope = None
    edge_flow_ranges = None
    if all_corners_solved:
        operating_envelope = {
            "airflow_m3_h": _metric_envelope(
                [
                    float(point["airflow_m3_h"])
                    for point in solved_points
                ],
                "m3/h",
            ),
            "system_pressure_pa": _metric_envelope(
                [
                    float(point["system_pressure_pa"])
                    for point in solved_points
                ],
                "Pa",
            ),
        }
        edge_flow_ranges = _edge_airflow_corner_ranges(
            study,
            solved_networks,
        )

    equivalent_envelope = {
        "lower": round(min(equivalent_resistances), 9),
        "upper": round(max(equivalent_resistances), 9),
        "unit": "Pa/(m3/s)^2",
    }

    fixed_record = _input_record(
        "fixed_pressure_pa",
        study.fixed_pressure_pa,
    )
    edge_records = [
        _edge_input_record(
            base_edges[item.edge_name],
            item,
        )
        for item in uncertainty_items
    ]

    missing = []
    if study.fan_curve_provenance is None:
        missing.append("fan_curve")
    if (
        study.fixed_pressure_pa.uncertainty_abs > 0
        and study.fixed_pressure_pa.provenance is None
    ):
        missing.append("fixed_pressure_pa")
    for item in uncertainty_items:
        if item.uncertainty_abs > 0 and item.provenance is None:
            missing.append(f"edge:{item.edge_name}")

    nominal_point = nominal["fan_operating_point"]
    return {
        "analysis": study.name,
        "status": (
            "complete" if all_corners_solved else "indeterminate"
        ),
        "fan_curve": study.fan_curve.name,
        "loop_network": study.loop_network.name,
        "fan_discharge_node": study.fan_discharge_node,
        "fan_suction_node": study.fan_suction_node,
        "input_intervals": {
            "fixed_pressure_pa": {
                "nominal": study.fixed_pressure_pa.value,
                "lower": study.fixed_pressure_pa.lower,
                "upper": study.fixed_pressure_pa.upper,
                "unit": "Pa",
            },
            "edge_resistance_pa_per_m3_s_squared": {
                record["edge"]: {
                    "nominal": record["value"],
                    "lower": record["lower"],
                    "upper": record["upper"],
                    "unit": record["unit"],
                }
                for record in edge_records
            },
        },
        "nominal_status": nominal["status"],
        "nominal_operating_point": nominal_point,
        "nominal_equivalent_loop_resistance_pa_per_m3_s_squared": (
            nominal[
                "equivalent_loop_resistance_pa_per_m3_s_squared"
            ]
        ),
        "nominal_fan_loop_result": nominal,
        "corner_count": len(corners),
        "solved_corner_count": len(solved_points),
        "unresolved_corner_count": unresolved_corner_count,
        "corners": corners,
        "equivalent_loop_resistance_envelope": equivalent_envelope,
        "operating_point_envelope": operating_envelope,
        "edge_airflow_corner_ranges": edge_flow_ranges,
        "traceability": {
            "complete": not missing,
            "missing_provenance": missing,
            "fan_curve_provenance": _provenance_record(
                study.fan_curve_provenance
            ),
            "inputs": [fixed_record, *edge_records],
        },
        "message": (
            "All evaluated uncertainty corners intersect the supplied "
            "fan curve; evaluated-corner operating ranges are reported."
            if all_corners_solved
            else "At least one evaluated uncertainty corner has no "
            "fan intersection inside the supplied fan-curve range; "
            "the operating-point envelope and branch-flow ranges are "
            "withheld."
        ),
        "engineering_note": (
            "This is deterministic corner analysis over user-supplied "
            "absolute bounds on fixed pressure and selected fixed "
            "quadratic loop-edge resistances. Each corner re-derives "
            "the passive two-terminal equivalent resistance, solves "
            "the fan intersection without extrapolation, and re-solves "
            "the full loop at the operating airflow. Equivalent-resistance "
            "and operating-point ranges are min/max across evaluated "
            "corners. Internal edge-flow ranges are diagnostic corner "
            "ranges only and are not claimed as guaranteed continuous-"
            "interval extrema. Geometry-derived resistances remain frozen "
            "at their nominal derivation before the explicit resistance "
            "uncertainty is applied. No fan-curve uncertainty, probability "
            "distribution, covariance, variable-friction iteration, "
            "damper/control action, leakage, system effect, acoustics, "
            "stall/surge assessment, compressibility, transients, or "
            "manufacturer acceptance is inferred."
        ),
    }
