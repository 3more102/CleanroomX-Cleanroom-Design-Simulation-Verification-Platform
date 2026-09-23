from __future__ import annotations

from dataclasses import asdict
from itertools import product
from math import prod

from .fan_loop_network import FanLoopNetworkStudy, solve_fan_loop_network
from .fan_loop_uncertainty_models import FanLoopNetworkUncertaintyStudy
from .loop_network import LoopedFlowNetwork, QuadraticFlowEdge
from .uncertainty_models import UncertainValue


def _input_record(name: str, item: UncertainValue) -> dict:
    return {
        "name": name,
        "value": item.value,
        "unit": item.unit,
        "uncertainty_abs": item.uncertainty_abs,
        "lower": item.lower,
        "upper": item.upper,
        "provenance": (
            asdict(item.provenance) if item.provenance is not None else None
        ),
    }


def _edge_at_resistance(
    edge: QuadraticFlowEdge,
    resistance_pa_per_m3_s_squared: float,
) -> QuadraticFlowEdge:
    if resistance_pa_per_m3_s_squared == edge.resistance_pa_per_m3_s_squared:
        return edge

    evidence: dict = {
        "base_resistance_basis": edge.resistance_basis,
        "base_resistance_pa_per_m3_s_squared": (
            edge.resistance_pa_per_m3_s_squared
        ),
        "uncertainty_adjusted_resistance_pa_per_m3_s_squared": (
            resistance_pa_per_m3_s_squared
        ),
    }
    if edge.resistance_evidence is not None:
        evidence["base_resistance_evidence"] = edge.resistance_evidence

    return QuadraticFlowEdge(
        name=edge.name,
        start_node=edge.start_node,
        end_node=edge.end_node,
        resistance_pa_per_m3_s_squared=resistance_pa_per_m3_s_squared,
        resistance_basis="uncertainty_adjusted",
        resistance_evidence=evidence,
    )


def _network_at_corner(
    study: FanLoopNetworkUncertaintyStudy,
    edge_resistances: dict[str, float],
) -> LoopedFlowNetwork:
    return LoopedFlowNetwork(
        name=study.loop_network.name,
        node_injections_m3_h=study.loop_network.node_injections_m3_h,
        edges=tuple(
            _edge_at_resistance(
                edge,
                edge_resistances.get(
                    edge.name,
                    edge.resistance_pa_per_m3_s_squared,
                ),
            )
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


def _metric_envelope(points: list[dict], key: str, unit: str) -> dict:
    values = [float(point[key]) for point in points]
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
        values = []
        for network in solved_networks:
            match = next(
                item for item in network["edges"] if item["name"] == edge.name
            )
            values.append(float(match["airflow_m3_h"]))
        lower = min(values)
        upper = max(values)
        rows.append(
            {
                "edge": edge.name,
                "lower_airflow_m3_h": round(lower, 6),
                "upper_airflow_m3_h": round(upper, 6),
                "direction_reversal_across_corners": lower < 0.0 < upper,
            }
        )
    return rows


def analyze_fan_loop_network_uncertainty(
    study: FanLoopNetworkUncertaintyStudy,
) -> dict:
    nominal = solve_fan_loop_network(
        FanLoopNetworkStudy(
            name=study.name,
            fan_curve=study.fan_curve,
            loop_network=study.loop_network,
            fan_discharge_node=study.fan_discharge_node,
            fan_suction_node=study.fan_suction_node,
            fixed_pressure_pa=study.fixed_pressure_pa.value,
        )
    )

    fixed_values = sorted(
        {study.fixed_pressure_pa.lower, study.fixed_pressure_pa.upper}
    )
    uncertain_edge_names = sorted(
        study.edge_resistance_pa_per_m3_s_squared
    )
    edge_value_sets = [
        sorted(
            {
                study.edge_resistance_pa_per_m3_s_squared[name].lower,
                study.edge_resistance_pa_per_m3_s_squared[name].upper,
            }
        )
        for name in uncertain_edge_names
    ]
    edge_combinations = (
        list(product(*edge_value_sets)) if edge_value_sets else [()]
    )

    corner_count = len(fixed_values) * prod(
        len(values) for values in edge_value_sets
    )
    if corner_count > study.max_corner_cases:
        raise ValueError(
            f"fan/loop uncertainty corner count {corner_count} is "
            f"exceeding max_corner_cases={study.max_corner_cases}"
        )

    corners = []
    solved_points = []
    solved_networks = []
    equivalent_resistances = []

    for fixed_pressure in fixed_values:
        for values in edge_combinations:
            edge_resistances = dict(zip(uncertain_edge_names, values))
            result = _solve_case(
                study,
                fixed_pressure,
                edge_resistances,
            )
            equivalent_resistance = float(
                result[
                    "equivalent_loop_resistance_pa_per_m3_s_squared"
                ]
            )
            equivalent_resistances.append(equivalent_resistance)

            point = result["fan_operating_point"]
            network = result["operating_network_solution"]
            edge_airflows = None
            if point is not None and network is not None:
                solved_points.append(point)
                solved_networks.append(network)
                edge_airflows = {
                    edge["name"]: edge["airflow_m3_h"]
                    for edge in network["edges"]
                }

            corners.append(
                {
                    "fixed_pressure_pa": round(fixed_pressure, 6),
                    "edge_resistance_pa_per_m3_s_squared": {
                        name: round(value, 9)
                        for name, value in edge_resistances.items()
                    },
                    "status": result["status"],
                    "equivalent_loop_resistance_pa_per_m3_s_squared": round(
                        equivalent_resistance,
                        9,
                    ),
                    "operating_point": point,
                    "edge_airflows_m3_h": edge_airflows,
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
        corner["status"] != "solved" for corner in corners
    )
    all_corners_solved = (
        nominal["status"] == "solved"
        and unresolved_corner_count == 0
    )

    operating_point_envelope = None
    edge_airflow_corner_ranges = None
    if all_corners_solved:
        operating_point_envelope = {
            "airflow_m3_h": _metric_envelope(
                solved_points,
                "airflow_m3_h",
                "m3/h",
            ),
            "system_pressure_pa": _metric_envelope(
                solved_points,
                "system_pressure_pa",
                "Pa",
            ),
        }
        edge_airflow_corner_ranges = _edge_airflow_corner_ranges(
            study,
            solved_networks,
        )

    equivalent_loop_resistance_envelope = {
        "lower": round(min(equivalent_resistances), 9),
        "upper": round(max(equivalent_resistances), 9),
        "unit": "Pa/(m3/s)^2",
    }

    fixed_record = _input_record(
        "fixed_pressure_pa",
        study.fixed_pressure_pa,
    )
    edge_records = [
        _input_record(f"edge:{name}", item)
        for name, item in (
            study.edge_resistance_pa_per_m3_s_squared.items()
        )
    ]
    missing = [
        record["name"]
        for record in [fixed_record, *edge_records]
        if record["provenance"] is None
    ]
    if study.fan_curve_provenance is None:
        missing.insert(0, "fan_curve")

    return {
        "analysis": study.name,
        "status": "complete" if all_corners_solved else "indeterminate",
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
                name: {
                    "nominal": item.value,
                    "lower": item.lower,
                    "upper": item.upper,
                    "unit": "Pa/(m3/s)^2",
                }
                for name, item in (
                    study.edge_resistance_pa_per_m3_s_squared.items()
                )
            },
        },
        "nominal_operating_point": nominal["fan_operating_point"],
        "nominal_status": nominal["status"],
        "nominal_equivalent_loop_resistance_pa_per_m3_s_squared": (
            nominal[
                "equivalent_loop_resistance_pa_per_m3_s_squared"
            ]
        ),
        "nominal_result": nominal,
        "corner_count": len(corners),
        "solved_corner_count": len(solved_points),
        "unresolved_corner_count": unresolved_corner_count,
        "corners": corners,
        "operating_point_envelope": operating_point_envelope,
        "equivalent_loop_resistance_envelope": (
            equivalent_loop_resistance_envelope
        ),
        "edge_airflow_corner_ranges": edge_airflow_corner_ranges,
        "traceability": {
            "complete": not missing,
            "missing_provenance": missing,
            "fan_curve_provenance": (
                asdict(study.fan_curve_provenance)
                if study.fan_curve_provenance is not None
                else None
            ),
            "inputs": [fixed_record, *edge_records],
        },
        "message": (
            "All evaluated uncertainty corners intersect the supplied fan "
            "curve; reported operating-point values are the min/max across "
            "those solved corners."
            if all_corners_solved
            else "At least one evaluated uncertainty corner has no "
            "intersection inside the supplied fan-curve range; no complete "
            "operating-point or internal edge-flow corner range is reported."
        ),
        "engineering_note": (
            "This is deterministic corner analysis for user-supplied "
            "absolute bounds on fixed pressure and selected loop-edge "
            "quadratic resistance. Every corner re-derives the passive "
            "two-terminal equivalent loop resistance, solves the bounded fan "
            "intersection without extrapolation, and re-solves the full loop "
            "at the operating airflow. Internal edge-flow min/max values, "
            "when reported, are ranges across evaluated corners only and are "
            "not claimed as guaranteed continuous-interval extrema for every "
            "interior uncertainty combination. No probability distribution, "
            "covariance, fan-curve uncertainty, automatic balancing/control, "
            "variable-friction iteration, leakage, system effect, acoustics, "
            "stall/surge assessment, motor/VFD limits, compressibility, "
            "transients, or manufacturer acceptance is inferred."
        ),
    }
