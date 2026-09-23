from __future__ import annotations

from dataclasses import asdict
from itertools import product
from math import prod

from .fan_loop_network import FanLoopNetworkStudy, solve_fan_loop_network
from .fan_loop_uncertainty_models import FanLoopUncertaintyStudy
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


def _adjusted_edge(
    edge: QuadraticFlowEdge,
    multiplier: float,
) -> QuadraticFlowEdge:
    if multiplier == 1.0:
        return edge
    evidence = {
        "base_resistance_basis": edge.resistance_basis,
        "base_resistance_pa_per_m3_s_squared": (
            edge.resistance_pa_per_m3_s_squared
        ),
        "uncertainty_resistance_multiplier": multiplier,
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
        resistance_basis="uncertainty_adjusted",
        resistance_evidence=evidence,
    )


def _network_with_multipliers(
    study: FanLoopUncertaintyStudy,
    multipliers: dict[str, float],
) -> LoopedFlowNetwork:
    return LoopedFlowNetwork(
        name=study.loop_network.name,
        node_injections_m3_h=study.loop_network.node_injections_m3_h,
        edges=tuple(
            _adjusted_edge(edge, multipliers.get(edge.name, 1.0))
            for edge in study.loop_network.edges
        ),
        reference_node=study.loop_network.reference_node,
    )


def _solve_case(
    study: FanLoopUncertaintyStudy,
    fixed_pressure_pa: float,
    multipliers: dict[str, float],
) -> dict:
    return solve_fan_loop_network(
        FanLoopNetworkStudy(
            name=study.name,
            fan_curve=study.fan_curve,
            loop_network=_network_with_multipliers(study, multipliers),
            fan_discharge_node=study.fan_discharge_node,
            fan_suction_node=study.fan_suction_node,
            fixed_pressure_pa=fixed_pressure_pa,
        )
    )


def _metric_range(points: list[dict], key: str, unit: str) -> dict:
    values = [float(point[key]) for point in points]
    return {
        "lower": round(min(values), 6),
        "upper": round(max(values), 6),
        "unit": unit,
    }


def _edge_airflow_corner_ranges(
    study: FanLoopUncertaintyStudy,
    solved_networks: list[dict],
) -> list[dict]:
    rows = []
    for edge in study.loop_network.edges:
        values = []
        for network in solved_networks:
            match = next(item for item in network["edges"] if item["name"] == edge.name)
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


def analyze_fan_loop_uncertainty(
    study: FanLoopUncertaintyStudy,
) -> dict:
    nominal_multipliers = {
        edge_name: item.value
        for edge_name, item in study.edge_resistance_multipliers.items()
    }
    nominal = _solve_case(
        study,
        study.fixed_pressure_pa.value,
        nominal_multipliers,
    )

    fixed_values = sorted(
        {study.fixed_pressure_pa.lower, study.fixed_pressure_pa.upper}
    )
    edge_names = sorted(study.edge_resistance_multipliers)
    multiplier_values = [
        sorted(
            {
                study.edge_resistance_multipliers[name].lower,
                study.edge_resistance_multipliers[name].upper,
            }
        )
        for name in edge_names
    ]

    corner_count = len(fixed_values) * prod(
        len(values) for values in multiplier_values
    )
    if corner_count > study.max_corner_cases:
        raise ValueError(
            f"fan/loop uncertainty corner count {corner_count} exceeds "
            f"max_corner_cases={study.max_corner_cases}"
        )

    corners = []
    solved_points = []
    solved_networks = []
    equivalent_resistances = []

    combinations = product(*multiplier_values) if multiplier_values else [()]
    for fixed_pressure in fixed_values:
        for values in combinations:
            multipliers = dict(zip(edge_names, values))
            result = _solve_case(study, fixed_pressure, multipliers)
            equivalent = float(
                result["equivalent_loop_resistance_pa_per_m3_s_squared"]
            )
            equivalent_resistances.append(equivalent)
            network = result["operating_network_solution"]
            point = result["fan_operating_point"]
            if point is not None and network is not None:
                solved_points.append(point)
                solved_networks.append(network)

            corners.append(
                {
                    "fixed_pressure_pa": round(fixed_pressure, 6),
                    "edge_resistance_multipliers": {
                        name: round(value, 9)
                        for name, value in multipliers.items()
                    },
                    "status": result["status"],
                    "equivalent_loop_resistance_pa_per_m3_s_squared": round(
                        equivalent, 9
                    ),
                    "operating_point": point,
                    "max_abs_mass_balance_residual_m3_h": (
                        None
                        if network is None
                        else network["max_abs_mass_balance_residual_m3_h"]
                    ),
                    "max_abs_pressure_law_residual_pa": (
                        None
                        if network is None
                        else network["max_abs_pressure_law_residual_pa"]
                    ),
                }
            )
        combinations = product(*multiplier_values) if multiplier_values else [()]

    unresolved_corner_count = sum(
        corner["status"] != "solved" for corner in corners
    )
    all_corners_solved = (
        unresolved_corner_count == 0 and nominal["status"] == "solved"
    )

    operating_range = None
    edge_flow_ranges = None
    if all_corners_solved:
        operating_range = {
            "airflow_m3_h": _metric_range(
                solved_points, "airflow_m3_h", "m3/h"
            ),
            "system_pressure_pa": _metric_range(
                solved_points, "system_pressure_pa", "Pa"
            ),
        }
        edge_flow_ranges = _edge_airflow_corner_ranges(
            study, solved_networks
        )

    equivalent_corner_range = {
        "lower": round(min(equivalent_resistances), 9),
        "upper": round(max(equivalent_resistances), 9),
        "unit": "Pa/(m3/s)^2",
    }

    fixed_record = _input_record("fixed_pressure_pa", study.fixed_pressure_pa)
    multiplier_records = [
        _input_record(f"edge_multiplier:{name}", item)
        for name, item in study.edge_resistance_multipliers.items()
    ]
    missing = [
        record["name"]
        for record in [fixed_record, *multiplier_records]
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
            "edge_resistance_multipliers": {
                name: {
                    "nominal": item.value,
                    "lower": item.lower,
                    "upper": item.upper,
                    "unit": "ratio",
                }
                for name, item in study.edge_resistance_multipliers.items()
            },
        },
        "nominal_result": nominal,
        "corner_count": len(corners),
        "solved_corner_count": len(solved_points),
        "unresolved_corner_count": unresolved_corner_count,
        "corners": corners,
        "equivalent_loop_resistance_corner_range": equivalent_corner_range,
        "operating_point_corner_range": operating_range,
        "edge_airflow_corner_ranges": edge_flow_ranges,
        "traceability": {
            "complete": not missing,
            "missing_provenance": missing,
            "fan_curve_provenance": (
                asdict(study.fan_curve_provenance)
                if study.fan_curve_provenance is not None
                else None
            ),
            "inputs": [fixed_record, *multiplier_records],
        },
        "message": (
            "All evaluated uncertainty corners intersect the supplied fan curve."
            if all_corners_solved
            else "At least one evaluated uncertainty corner has no fan intersection "
            "inside the supplied fan-curve range; operating-point and edge-flow "
            "corner ranges are withheld."
        ),
        "engineering_note": (
            "This workflow performs deterministic corner analysis over user-supplied "
            "absolute bounds on fixed pressure and selected loop-edge resistance "
            "multipliers. Every corner re-derives the passive two-terminal equivalent "
            "loop resistance, solves the bounded fan intersection without extrapolation, "
            "and re-solves the full loop at the operating airflow. Reported min/max "
            "values are ranges across evaluated corners; for independently uncertain "
            "edge resistances they are not claimed as guaranteed continuous-interval "
            "extrema for internal edge flows. No probability distribution, covariance, "
            "fan-curve uncertainty, automatic balancing/control, variable-friction "
            "iteration, leakage, system effect, acoustics, stall/surge assessment, "
            "compressibility, transients, or manufacturer acceptance is inferred."
        ),
    }
