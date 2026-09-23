from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from itertools import product
from math import prod

from .fan_curve import FanCurve
from .fan_variable_friction_loop import (
    FanVariableFrictionLoopStudy,
    solve_fan_variable_friction_loop,
)
from .loop_network import LoopedFlowNetwork, QuadraticFlowEdge
from .loop_resistance import LoopedDuctResistanceInput, derive_loop_edge_resistance
from .pressure_power import FanPowerEfficiencies
from .uncertainty_models import Provenance, UncertainValue


@dataclass(frozen=True)
class FanVariableFrictionLoopUncertaintyStudy:
    name: str
    fan_curve: FanCurve
    loop_network: LoopedFlowNetwork
    fan_discharge_node: str
    fan_suction_node: str
    fixed_pressure_pa: UncertainValue
    edge_local_loss_coefficient: dict[str, UncertainValue]
    fan_curve_provenance: Provenance | None = None
    max_corner_cases: int = 256
    power_efficiencies: FanPowerEfficiencies | None = None
    resistance_relative_tolerance: float = 1e-6
    relaxation: float = 0.5
    near_zero_airflow_m3_h: float = 1e-6
    max_outer_iterations: int = 50
    mass_balance_tolerance_m3_h: float = 1e-6
    max_newton_iterations: int = 100
    operating_pressure_tolerance_pa: float = 1e-6
    max_operating_iterations: int = 80

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError(
                "fan/variable-friction uncertainty study name cannot be empty"
            )
        if self.fixed_pressure_pa.unit != "Pa":
            raise ValueError("fixed_pressure_pa unit must be 'Pa'")
        if self.fixed_pressure_pa.lower < 0:
            raise ValueError(
                "fixed_pressure_pa lower uncertainty bound must remain >= 0"
            )
        if (
            isinstance(self.max_corner_cases, bool)
            or not isinstance(self.max_corner_cases, int)
            or self.max_corner_cases <= 0
        ):
            raise ValueError("max_corner_cases must be an integer > 0")

        edges_by_name = {edge.name: edge for edge in self.loop_network.edges}
        normalized: dict[str, UncertainValue] = {}
        for edge_name, item in self.edge_local_loss_coefficient.items():
            edge = edges_by_name.get(edge_name)
            if edge is None:
                raise ValueError(
                    "edge local-loss uncertainty references unknown edge "
                    f"{edge_name!r}"
                )
            evidence = edge.resistance_evidence
            if (
                edge.resistance_basis != "duct_geometry"
                or evidence is None
                or evidence.get("absolute_roughness_m") is None
                or evidence.get("kinematic_viscosity_m2_s") is None
            ):
                raise ValueError(
                    f"edge local-loss uncertainty for {edge_name!r} requires "
                    "an automatic-friction duct_geometry edge"
                )
            if item.unit != "1":
                raise ValueError(
                    f"edge local-loss uncertainty for {edge_name!r} "
                    "must use unit '1'"
                )
            if item.lower < 0:
                raise ValueError(
                    f"edge local-loss lower uncertainty bound for "
                    f"{edge_name!r} must remain >= 0"
                )
            nominal = float(evidence["local_loss_coefficient"])
            if not math.isclose(
                item.value,
                nominal,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                raise ValueError(
                    f"edge local-loss uncertainty nominal for {edge_name!r} "
                    "must match the loop-network geometry evidence"
                )
            normalized[edge_name] = item
        object.__setattr__(self, "edge_local_loss_coefficient", normalized)

        FanVariableFrictionLoopStudy(
            name=self.name,
            fan_curve=self.fan_curve,
            loop_network=self.loop_network,
            fan_discharge_node=self.fan_discharge_node,
            fan_suction_node=self.fan_suction_node,
            fixed_pressure_pa=self.fixed_pressure_pa.value,
            power_efficiencies=self.power_efficiencies,
            resistance_relative_tolerance=self.resistance_relative_tolerance,
            relaxation=self.relaxation,
            near_zero_airflow_m3_h=self.near_zero_airflow_m3_h,
            max_outer_iterations=self.max_outer_iterations,
            mass_balance_tolerance_m3_h=self.mass_balance_tolerance_m3_h,
            max_newton_iterations=self.max_newton_iterations,
            operating_pressure_tolerance_pa=self.operating_pressure_tolerance_pa,
            max_operating_iterations=self.max_operating_iterations,
        )


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


def _rectangular_dimensions(
    area_m2: float,
    hydraulic_diameter_m: float,
) -> tuple[float, float]:
    area = float(area_m2)
    hydraulic_diameter = float(hydraulic_diameter_m)
    side_sum = 2.0 * area / hydraulic_diameter
    discriminant = side_sum**2 - 4.0 * area
    tolerance = 1e-12 * max(side_sum**2, 4.0 * area, 1.0)
    if discriminant < -tolerance:
        raise ValueError(
            "stored rectangular duct evidence is geometrically inconsistent"
        )
    root = math.sqrt(max(discriminant, 0.0))
    width = 0.5 * (side_sum + root)
    height = 0.5 * (side_sum - root)
    if width <= 0 or height <= 0:
        raise ValueError(
            "stored rectangular duct evidence has invalid dimensions"
        )
    return width, height


def _edge_at_local_loss(
    edge: QuadraticFlowEdge,
    local_loss_coefficient: float,
) -> QuadraticFlowEdge:
    evidence = edge.resistance_evidence
    if evidence is None:
        raise ValueError(
            f"edge {edge.name!r} has no duct-geometry resistance evidence"
        )
    common = {
        "length_m": evidence["length_m"],
        "air_density_kg_m3": evidence["air_density_kg_m3"],
        "local_loss_coefficient": local_loss_coefficient,
        "absolute_roughness_m": evidence["absolute_roughness_m"],
        "kinematic_viscosity_m2_s": evidence["kinematic_viscosity_m2_s"],
        "reference_airflow_m3_h": evidence["reference_airflow_m3_h"],
    }
    shape = evidence["shape"]
    if shape == "circular":
        common["diameter_m"] = evidence["hydraulic_diameter_m"]
    elif shape == "rectangular":
        width, height = _rectangular_dimensions(
            evidence["area_m2"],
            evidence["hydraulic_diameter_m"],
        )
        common["width_m"] = width
        common["height_m"] = height
    else:
        raise ValueError(f"unsupported stored duct shape {shape!r}")

    rebuilt = derive_loop_edge_resistance(
        LoopedDuctResistanceInput(**common)
    )
    rebuilt["uncertainty_base_local_loss_coefficient"] = evidence[
        "local_loss_coefficient"
    ]
    rebuilt["uncertainty_adjusted_local_loss_coefficient"] = (
        local_loss_coefficient
    )
    return QuadraticFlowEdge(
        name=edge.name,
        start_node=edge.start_node,
        end_node=edge.end_node,
        resistance_pa_per_m3_s_squared=rebuilt[
            "resistance_pa_per_m3_s_squared"
        ],
        resistance_basis="duct_geometry",
        resistance_evidence=rebuilt,
    )


def _network_at_corner(
    study: FanVariableFrictionLoopUncertaintyStudy,
    edge_local_losses: dict[str, float],
) -> LoopedFlowNetwork:
    return LoopedFlowNetwork(
        name=study.loop_network.name,
        node_injections_m3_h=study.loop_network.node_injections_m3_h,
        edges=tuple(
            _edge_at_local_loss(edge, edge_local_losses[edge.name])
            if edge.name in edge_local_losses
            else edge
            for edge in study.loop_network.edges
        ),
        reference_node=study.loop_network.reference_node,
    )


def _solve_case(
    study: FanVariableFrictionLoopUncertaintyStudy,
    fixed_pressure_pa: float,
    edge_local_losses: dict[str, float],
) -> dict:
    return solve_fan_variable_friction_loop(
        FanVariableFrictionLoopStudy(
            name=study.name,
            fan_curve=study.fan_curve,
            loop_network=_network_at_corner(study, edge_local_losses),
            fan_discharge_node=study.fan_discharge_node,
            fan_suction_node=study.fan_suction_node,
            fixed_pressure_pa=fixed_pressure_pa,
            power_efficiencies=study.power_efficiencies,
            resistance_relative_tolerance=study.resistance_relative_tolerance,
            relaxation=study.relaxation,
            near_zero_airflow_m3_h=study.near_zero_airflow_m3_h,
            max_outer_iterations=study.max_outer_iterations,
            mass_balance_tolerance_m3_h=study.mass_balance_tolerance_m3_h,
            max_newton_iterations=study.max_newton_iterations,
            operating_pressure_tolerance_pa=(
                study.operating_pressure_tolerance_pa
            ),
            max_operating_iterations=study.max_operating_iterations,
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
    study: FanVariableFrictionLoopUncertaintyStudy,
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


def analyze_fan_variable_friction_loop_uncertainty(
    study: FanVariableFrictionLoopUncertaintyStudy,
) -> dict:
    nominal = _solve_case(
        study,
        study.fixed_pressure_pa.value,
        {
            name: item.value
            for name, item in study.edge_local_loss_coefficient.items()
        },
    )

    fixed_values = sorted(
        {study.fixed_pressure_pa.lower, study.fixed_pressure_pa.upper}
    )
    uncertain_edge_names = sorted(study.edge_local_loss_coefficient)
    edge_value_sets = [
        sorted(
            {
                study.edge_local_loss_coefficient[name].lower,
                study.edge_local_loss_coefficient[name].upper,
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
            "fan/variable-friction uncertainty corner count "
            f"{corner_count} is exceeding "
            f"max_corner_cases={study.max_corner_cases}"
        )

    corners = []
    solved_points = []
    solved_networks = []
    for fixed_pressure in fixed_values:
        for values in edge_combinations:
            edge_local_losses = dict(zip(uncertain_edge_names, values))
            result = _solve_case(
                study,
                fixed_pressure,
                edge_local_losses,
            )
            point = result["fan_operating_point"]
            network = result["operating_network_solution"]
            edge_airflows = None
            if result["status"] == "solved" and point is not None and network is not None:
                solved_points.append(point)
                solved_networks.append(network)
                edge_airflows = {
                    edge["name"]: edge["airflow_m3_h"]
                    for edge in network["edges"]
                }

            corners.append(
                {
                    "fixed_pressure_pa": round(fixed_pressure, 6),
                    "edge_local_loss_coefficient": {
                        name: round(value, 9)
                        for name, value in edge_local_losses.items()
                    },
                    "status": result["status"],
                    "operating_point": point,
                    "edge_airflows_m3_h": edge_airflows,
                    "solver_diagnostics": result["solver_diagnostics"],
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
            "fan_pressure_pa": _metric_envelope(
                solved_points,
                "fan_pressure_pa",
                "Pa",
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

    fixed_record = _input_record(
        "fixed_pressure_pa",
        study.fixed_pressure_pa,
    )
    edge_records = [
        _input_record(f"edge_local_loss:{name}", item)
        for name, item in study.edge_local_loss_coefficient.items()
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
            "edge_local_loss_coefficient": {
                name: {
                    "nominal": item.value,
                    "lower": item.lower,
                    "upper": item.upper,
                    "unit": "1",
                }
                for name, item in study.edge_local_loss_coefficient.items()
            },
        },
        "nominal_status": nominal["status"],
        "nominal_operating_point": nominal["fan_operating_point"],
        "nominal_result": nominal,
        "corner_count": len(corners),
        "solved_corner_count": len(solved_points),
        "unresolved_corner_count": unresolved_corner_count,
        "corners": corners,
        "operating_point_envelope": operating_point_envelope,
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
            "All evaluated uncertainty corners converged and intersect the "
            "supplied fan curve; reported operating-point values are min/max "
            "across those solved corners."
            if all_corners_solved
            else "At least one evaluated uncertainty corner is unresolved "
            "because the fan curve has no bounded intersection or the "
            "variable-friction/network solver did not converge. No complete "
            "operating-point or edge-flow corner range is reported."
        ),
        "engineering_note": (
            "This is deterministic corner analysis for user-supplied "
            "absolute bounds on fixed pressure and selected automatic-friction "
            "duct local-loss coefficients. Every corner rebuilds the affected "
            "geometry-edge evidence and re-solves the complete Darcy-friction "
            "network at every fan/system airflow evaluated by the bounded "
            "operating-point search. Reported min/max values are ranges across "
            "evaluated corners only and are not claimed as guaranteed extrema "
            "for all interior combinations. No probability distribution, "
            "covariance, fan-curve uncertainty, geometry tolerance inference, "
            "damper/control inference, leakage, system effect, acoustics, "
            "stall/surge assessment, motor/VFD limits, compressibility, "
            "transients, or manufacturer acceptance is inferred."
        ),
    }
