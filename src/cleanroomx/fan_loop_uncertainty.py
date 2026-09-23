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


def _unique_bounds(item: UncertainValue) -> tuple[float, ...]:
    return tuple(sorted({item.lower, item.upper}))


def _network_with_resistances(
    study: FanLoopNetworkUncertaintyStudy,
    resistance_by_edge: dict[str, float],
) -> LoopedFlowNetwork:
    network = study.fan_loop_study.loop_network
    edges = tuple(
        QuadraticFlowEdge(
            name=edge.name,
            start_node=edge.start_node,
            end_node=edge.end_node,
            resistance_pa_per_m3_s_squared=resistance_by_edge[edge.name],
            resistance_basis=edge.resistance_basis,
            resistance_evidence=edge.resistance_evidence,
        )
        for edge in network.edges
    )
    return LoopedFlowNetwork(
        name=network.name,
        node_injections_m3_h=network.node_injections_m3_h,
        edges=edges,
        reference_node=network.reference_node,
    )


def _corner_study(
    study: FanLoopNetworkUncertaintyStudy,
    fixed_pressure_pa: float,
    resistance_by_edge: dict[str, float],
) -> FanLoopNetworkStudy:
    base = study.fan_loop_study
    return FanLoopNetworkStudy(
        name=base.name,
        fan_curve=base.fan_curve,
        loop_network=_network_with_resistances(study, resistance_by_edge),
        fan_discharge_node=base.fan_discharge_node,
        fan_suction_node=base.fan_suction_node,
        fixed_pressure_pa=fixed_pressure_pa,
    )


def _metric_envelope(points: list[dict], key: str, unit: str) -> dict:
    values = [float(point[key]) for point in points]
    return {
        "lower": round(min(values), 6),
        "upper": round(max(values), 6),
        "unit": unit,
    }


def analyze_fan_loop_network_uncertainty(
    study: FanLoopNetworkUncertaintyStudy,
) -> dict:
    nominal = solve_fan_loop_network(study.fan_loop_study)

    edge_names = tuple(edge.name for edge in study.fan_loop_study.loop_network.edges)
    fixed_values = _unique_bounds(study.fixed_pressure_pa)
    edge_value_options = [
        _unique_bounds(study.edge_resistances[name])
        for name in edge_names
    ]
    corner_count = prod(
        [len(fixed_values), *(len(values) for values in edge_value_options)]
    )
    if corner_count > study.max_corner_cases:
        raise ValueError(
            f"fan/loop uncertainty expands to {corner_count} corner cases, "
            f"exceeding max_corner_cases={study.max_corner_cases}"
        )

    corners: list[dict] = []
    solved_points: list[dict] = []
    solved_equivalent_resistances: list[float] = []

    for values in product(fixed_values, *edge_value_options):
        fixed_pressure = values[0]
        resistance_by_edge = dict(zip(edge_names, values[1:]))
        result = solve_fan_loop_network(
            _corner_study(study, fixed_pressure, resistance_by_edge)
        )
        point = result["fan_operating_point"]
        network_solution = result["operating_network_solution"]
        edge_airflows = None
        if network_solution is not None:
            edge_airflows = {
                edge["name"]: edge["airflow_m3_h"]
                for edge in network_solution["edges"]
            }

        corner = {
            "fixed_pressure_pa": round(fixed_pressure, 6),
            "edge_resistance_pa_per_m3_s_squared": {
                name: round(resistance_by_edge[name], 6)
                for name in edge_names
            },
            "equivalent_loop_resistance_pa_per_m3_s_squared": round(
                result["equivalent_loop_resistance_pa_per_m3_s_squared"], 9
            ),
            "status": result["status"],
            "operating_point": point,
            "operating_edge_airflows_m3_h": edge_airflows,
        }
        corners.append(corner)
        if point is not None:
            solved_points.append(point)
            solved_equivalent_resistances.append(
                result["equivalent_loop_resistance_pa_per_m3_s_squared"]
            )

    unresolved_corner_count = sum(
        corner["status"] != "solved" for corner in corners
    )
    all_corners_solved = (
        unresolved_corner_count == 0 and nominal["status"] == "solved"
    )

    envelope = None
    equivalent_resistance_envelope = None
    if all_corners_solved:
        envelope = {
            "airflow_m3_h": _metric_envelope(
                solved_points, "airflow_m3_h", "m3/h"
            ),
            "system_pressure_pa": _metric_envelope(
                solved_points, "system_pressure_pa", "Pa"
            ),
        }
        equivalent_resistance_envelope = {
            "lower": round(min(solved_equivalent_resistances), 6),
            "upper": round(max(solved_equivalent_resistances), 6),
            "unit": "Pa/(m3/s)^2",
        }

    fixed_record = _input_record("fixed_pressure_pa", study.fixed_pressure_pa)
    edge_records = [
        _input_record(f"edge:{name}", study.edge_resistances[name])
        for name in edge_names
    ]
    tracked_inputs = [
        fixed_record,
        *[
            item
            for item in edge_records
            if item["uncertainty_abs"] > 0
        ],
    ]
    missing = [
        item["name"]
        for item in tracked_inputs
        if item["provenance"] is None
    ]
    if study.fan_curve_provenance is None:
        missing.insert(0, "fan_curve")

    traceability = {
        "complete": not missing,
        "missing_provenance": missing,
        "fan_curve_provenance": (
            asdict(study.fan_curve_provenance)
            if study.fan_curve_provenance is not None
            else None
        ),
        "fixed_pressure": fixed_record,
        "edge_resistances": edge_records,
    }

    input_intervals = {
        "fixed_pressure_pa": {
            "nominal": study.fixed_pressure_pa.value,
            "lower": study.fixed_pressure_pa.lower,
            "upper": study.fixed_pressure_pa.upper,
            "unit": "Pa",
        },
        "edge_resistance_pa_per_m3_s_squared": {
            name: {
                "nominal": study.edge_resistances[name].value,
                "lower": study.edge_resistances[name].lower,
                "upper": study.edge_resistances[name].upper,
                "unit": "Pa/(m3/s)^2",
            }
            for name in edge_names
        },
    }

    return {
        "analysis": study.name,
        "status": "complete" if all_corners_solved else "indeterminate",
        "fan_curve": study.fan_loop_study.fan_curve.name,
        "fan_discharge_node": study.fan_loop_study.fan_discharge_node,
        "fan_suction_node": study.fan_loop_study.fan_suction_node,
        "input_intervals": input_intervals,
        "nominal_status": nominal["status"],
        "nominal_operating_point": nominal["fan_operating_point"],
        "nominal_equivalent_loop_resistance_pa_per_m3_s_squared": nominal[
            "equivalent_loop_resistance_pa_per_m3_s_squared"
        ],
        "corner_count": len(corners),
        "solved_corner_count": len(solved_points),
        "unresolved_corner_count": unresolved_corner_count,
        "corners": corners,
        "operating_point_envelope": envelope,
        "equivalent_loop_resistance_envelope": equivalent_resistance_envelope,
        "traceability": traceability,
        "message": (
            "The nominal case and every configured lower/upper corner intersect "
            "the supplied fan curve; the reported operating-point envelope is "
            "the min/max across solved corner cases."
            if all_corners_solved
            else "The nominal case or at least one configured lower/upper corner "
            "has no intersection inside the supplied fan-curve range; no complete "
            "operating-point envelope is reported."
        ),
        "engineering_note": (
            "This is deterministic corner analysis for user-supplied absolute "
            "bounds on fixed pressure and fixed quadratic loop-edge resistances. "
            "The fan curve is held fixed and is interpolated only inside supplied "
            "data; no fan-curve extrapolation is performed. Corner edge-flow values "
            "are diagnostic solved-case evidence and are not claimed as conservative "
            "continuous-interval bounds for every interior uncertainty combination. "
            "Geometry-derived or automatic-friction resistances remain frozen at "
            "their nominal derivation basis before the configured resistance bounds "
            "are applied. No probability distribution, covariance, variable-friction "
            "iteration, damper/control action, leakage, system-effect correction, "
            "stall/surge assessment, motor/VFD limit, compressibility, or transient "
            "behavior is inferred."
        ),
    }
