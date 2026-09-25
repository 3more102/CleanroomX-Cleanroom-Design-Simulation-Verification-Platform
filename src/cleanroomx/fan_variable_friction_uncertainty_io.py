from __future__ import annotations

import json
from pathlib import Path

from .input_contracts import strict_input_fields
from .fan_curve import FanCurve, FanCurvePoint
from .fan_variable_friction_uncertainty import (
    FanCurveScenario,
    FanVariableFrictionLoopUncertaintyStudy,
)
from .loop_network_io import looped_flow_network_from_dict
from .pressure_power import fan_power_efficiencies_from_dict
from .uncertainty_models import Provenance, UncertainValue


_SOLVER_KEYS = {
    "resistance_relative_tolerance",
    "relaxation",
    "near_zero_airflow_m3_h",
    "max_outer_iterations",
    "mass_balance_tolerance_m3_h",
    "max_newton_iterations",
    "operating_pressure_tolerance_pa",
    "max_operating_iterations",
}


def _provenance_from_dict(data: dict | None) -> Provenance | None:
    return None if data is None else Provenance(**data)


def _uncertain_value(
    data: float | int | dict,
    unit: str,
) -> UncertainValue:
    if isinstance(data, (int, float)):
        return UncertainValue(float(data), unit)
    if not isinstance(data, dict):
        raise ValueError("uncertain value must be a number or object")
    return UncertainValue(
        value=data["value"],
        unit=unit,
        uncertainty_abs=data.get("uncertainty_abs", 0.0),
        provenance=_provenance_from_dict(data.get("provenance")),
    )


def _fan_curve_scenarios(
    data: dict,
    nominal_fan_curve: FanCurve,
) -> tuple[FanCurveScenario, ...]:
    specs = data.get("fan_curve_scenarios", [])
    if not isinstance(specs, list):
        raise ValueError("fan_curve_scenarios must be an array when provided")

    scenarios = []
    for spec in specs:
        if not isinstance(spec, dict):
            raise ValueError("fan_curve_scenarios entries must be objects")
        name = spec.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("fan_curve_scenarios entry requires a non-empty name")
        points = spec.get("points")
        if not isinstance(points, list):
            raise ValueError(
                f"fan_curve_scenarios entry {name!r} requires a points array"
            )
        scenarios.append(
            FanCurveScenario(
                name=name,
                fan_curve=FanCurve(
                    name=f"{nominal_fan_curve.name} — {name}",
                    points=tuple(FanCurvePoint(**point) for point in points),
                ),
                provenance=_provenance_from_dict(spec.get("provenance")),
            )
        )
    return tuple(scenarios)


def _fan_curve_airflow_uncertainty(
    data: dict,
    fan_curve: FanCurve,
) -> dict[int, UncertainValue]:
    specs = data.get("fan_curve_airflow_uncertainty", [])
    if not isinstance(specs, list):
        raise ValueError(
            "fan_curve_airflow_uncertainty must be an array when provided"
        )

    result: dict[int, UncertainValue] = {}
    for spec in specs:
        if not isinstance(spec, dict):
            raise ValueError(
                "fan_curve_airflow_uncertainty entries must be objects"
            )
        if "point_index" not in spec:
            raise ValueError(
                "fan_curve_airflow_uncertainty entry requires point_index"
            )
        point_index = spec["point_index"]
        if (
            isinstance(point_index, bool)
            or not isinstance(point_index, int)
            or point_index < 0
            or point_index >= len(fan_curve.points)
        ):
            raise ValueError(
                "fan_curve_airflow_uncertainty point_index must identify "
                "an existing supplied fan-curve point"
            )
        if point_index in result:
            raise ValueError(
                "fan_curve_airflow_uncertainty contains duplicate point_index "
                f"{point_index}"
            )
        if "value" in spec or "airflow_m3_h" in spec:
            raise ValueError(
                "fan_curve_airflow_uncertainty must not repeat the nominal "
                "airflow_m3_h; the fan curve is the nominal source"
            )
        point = fan_curve.points[point_index]
        result[point_index] = UncertainValue(
            value=point.airflow_m3_h,
            unit="m3/h",
            uncertainty_abs=spec.get("uncertainty_abs", 0.0),
            provenance=_provenance_from_dict(spec.get("provenance")),
        )
    return result


def _fan_curve_pressure_uncertainty(
    data: dict,
    fan_curve: FanCurve,
) -> dict[float, UncertainValue]:
    specs = data.get("fan_curve_pressure_uncertainty", [])
    if not isinstance(specs, list):
        raise ValueError(
            "fan_curve_pressure_uncertainty must be an array when provided"
        )

    points_by_airflow = {
        float(point.airflow_m3_h): point for point in fan_curve.points
    }
    result: dict[float, UncertainValue] = {}
    for spec in specs:
        if not isinstance(spec, dict):
            raise ValueError(
                "fan_curve_pressure_uncertainty entries must be objects"
            )
        if "airflow_m3_h" not in spec:
            raise ValueError(
                "fan_curve_pressure_uncertainty entry requires airflow_m3_h"
            )
        if "value" in spec or "pressure_pa" in spec:
            raise ValueError(
                "fan_curve_pressure_uncertainty must not repeat the nominal "
                "pressure_pa; the fan curve is the nominal source"
            )
        airflow = float(spec["airflow_m3_h"])
        point = points_by_airflow.get(airflow)
        if point is None:
            raise ValueError(
                "fan_curve_pressure_uncertainty references unknown supplied "
                f"airflow point {airflow!r} m3/h"
            )
        if airflow in result:
            raise ValueError(
                "fan_curve_pressure_uncertainty contains duplicate airflow "
                f"point {airflow!r} m3/h"
            )
        result[airflow] = UncertainValue(
            value=point.pressure_pa,
            unit="Pa",
            uncertainty_abs=spec.get("uncertainty_abs", 0.0),
            provenance=_provenance_from_dict(spec.get("provenance")),
        )
    return result


def _edge_parameter_uncertainty(
    data: dict,
    edges_by_name: dict,
    *,
    block_key: str,
    evidence_key: str,
    unit: str,
    label: str,
) -> dict[str, UncertainValue]:
    result: dict[str, UncertainValue] = {}
    for edge_name, spec in data.get(block_key, {}).items():
        edge = edges_by_name.get(edge_name)
        if edge is None:
            raise ValueError(
                f"edge {label} uncertainty references unknown edge "
                f"{edge_name!r}"
            )
        evidence = edge.resistance_evidence
        if evidence is None or evidence.get(evidence_key) is None:
            raise ValueError(
                f"edge {edge_name!r} has no {label} geometry evidence"
            )
        if isinstance(spec, (int, float)):
            uncertainty_abs = float(spec)
            provenance = None
        elif isinstance(spec, dict):
            if "value" in spec:
                raise ValueError(
                    f"{block_key} must not repeat the nominal {label}; "
                    "the loop-network geometry is the nominal source"
                )
            uncertainty_abs = spec.get("uncertainty_abs", 0.0)
            provenance = _provenance_from_dict(spec.get("provenance"))
        else:
            raise ValueError(
                f"edge {label} uncertainty for {edge_name!r} must be "
                "a number or object"
            )
        result[edge_name] = UncertainValue(
            value=evidence[evidence_key],
            unit=unit,
            uncertainty_abs=uncertainty_abs,
            provenance=provenance,
        )
    return result


@strict_input_fields(
    "name",
    "fan_curve",
    "loop_network",
    "fan_discharge_node",
    "fan_suction_node",
    "fixed_pressure_pa",
    "edge_local_loss_uncertainty",
    "edge_absolute_roughness_uncertainty",
    "edge_kinematic_viscosity_uncertainty",
    "edge_air_density_uncertainty",
    "edge_length_uncertainty",
    "edge_circular_diameter_uncertainty",
    "edge_rectangular_width_uncertainty",
    "edge_rectangular_height_uncertainty",
    "fan_curve_pressure_uncertainty",
    "fan_curve_airflow_uncertainty",
    "fan_curve_scenarios",
    "fan_speed_ratio",
    "max_corner_cases",
    "power_efficiencies",
    "solver",
    context="fan/variable-friction uncertainty input",
)
def fan_variable_friction_loop_uncertainty_from_dict(
    data: dict,
) -> FanVariableFrictionLoopUncertaintyStudy:
    fan_data = data["fan_curve"]
    fan_curve = FanCurve(
        name=fan_data["name"],
        points=tuple(
            FanCurvePoint(**point) for point in fan_data["points"]
        ),
    )
    fan_curve_scenarios = _fan_curve_scenarios(data, fan_curve)
    fan_curve_pressure_uncertainty = _fan_curve_pressure_uncertainty(
        data,
        fan_curve,
    )
    fan_curve_airflow_uncertainty = _fan_curve_airflow_uncertainty(
        data,
        fan_curve,
    )
    loop_network = looped_flow_network_from_dict(data["loop_network"])
    edges_by_name = {edge.name: edge for edge in loop_network.edges}

    edge_local_loss_uncertainty = _edge_parameter_uncertainty(
        data,
        edges_by_name,
        block_key="edge_local_loss_uncertainty",
        evidence_key="local_loss_coefficient",
        unit="1",
        label="local-loss",
    )
    edge_absolute_roughness_uncertainty = _edge_parameter_uncertainty(
        data,
        edges_by_name,
        block_key="edge_absolute_roughness_uncertainty",
        evidence_key="absolute_roughness_m",
        unit="m",
        label="absolute-roughness",
    )
    edge_kinematic_viscosity_uncertainty = _edge_parameter_uncertainty(
        data,
        edges_by_name,
        block_key="edge_kinematic_viscosity_uncertainty",
        evidence_key="kinematic_viscosity_m2_s",
        unit="m2/s",
        label="kinematic-viscosity",
    )
    edge_air_density_uncertainty = _edge_parameter_uncertainty(
        data,
        edges_by_name,
        block_key="edge_air_density_uncertainty",
        evidence_key="air_density_kg_m3",
        unit="kg/m3",
        label="air-density",
    )
    edge_length_uncertainty = _edge_parameter_uncertainty(
        data,
        edges_by_name,
        block_key="edge_length_uncertainty",
        evidence_key="length_m",
        unit="m",
        label="length",
    )
    edge_circular_diameter_uncertainty = _edge_parameter_uncertainty(
        data,
        edges_by_name,
        block_key="edge_circular_diameter_uncertainty",
        evidence_key="hydraulic_diameter_m",
        unit="m",
        label="circular-diameter",
    )
    edge_rectangular_width_uncertainty = _edge_parameter_uncertainty(
        data,
        edges_by_name,
        block_key="edge_rectangular_width_uncertainty",
        evidence_key="width_m",
        unit="m",
        label="rectangular-width",
    )
    edge_rectangular_height_uncertainty = _edge_parameter_uncertainty(
        data,
        edges_by_name,
        block_key="edge_rectangular_height_uncertainty",
        evidence_key="height_m",
        unit="m",
        label="rectangular-height",
    )

    solver = data.get("solver", {})
    if not isinstance(solver, dict):
        raise ValueError("solver must be an object when provided")
    unknown = set(solver) - _SOLVER_KEYS
    if unknown:
        raise ValueError(
            "unsupported fan/variable-friction uncertainty solver option(s): "
            + ", ".join(sorted(unknown))
        )

    return FanVariableFrictionLoopUncertaintyStudy(
        name=data["name"],
        fan_curve=fan_curve,
        loop_network=loop_network,
        fan_discharge_node=data["fan_discharge_node"],
        fan_suction_node=data["fan_suction_node"],
        fixed_pressure_pa=_uncertain_value(
            data.get("fixed_pressure_pa", 0.0),
            "Pa",
        ),
        edge_local_loss_coefficient=edge_local_loss_uncertainty,
        edge_absolute_roughness_m=edge_absolute_roughness_uncertainty,
        edge_kinematic_viscosity_m2_s=(
            edge_kinematic_viscosity_uncertainty
        ),
        edge_air_density_kg_m3=edge_air_density_uncertainty,
        edge_length_m=edge_length_uncertainty,
        edge_circular_diameter_m=edge_circular_diameter_uncertainty,
        edge_rectangular_width_m=edge_rectangular_width_uncertainty,
        edge_rectangular_height_m=edge_rectangular_height_uncertainty,
        fan_curve_pressure_pa=fan_curve_pressure_uncertainty,
        fan_curve_airflow_m3_h=fan_curve_airflow_uncertainty,
        fan_curve_scenarios=fan_curve_scenarios,
        fan_speed_ratio=(
            _uncertain_value(data["fan_speed_ratio"], "1")
            if "fan_speed_ratio" in data
            else None
        ),
        fan_curve_provenance=_provenance_from_dict(
            fan_data.get("provenance")
        ),
        max_corner_cases=data.get("max_corner_cases", 256),
        power_efficiencies=fan_power_efficiencies_from_dict(
            data.get("power_efficiencies")
        ),
        **solver,
    )


def load_fan_variable_friction_loop_uncertainty(
    path: str | Path,
) -> FanVariableFrictionLoopUncertaintyStudy:
    return fan_variable_friction_loop_uncertainty_from_dict(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )
