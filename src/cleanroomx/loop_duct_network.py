from __future__ import annotations

import math
from dataclasses import dataclass

from .duct import DuctSection
from .loop_network import LoopedFlowNetwork, QuadraticFlowEdge, solve_looped_network


def _positive(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{field_name} must be finite and > 0")
    return value


@dataclass(frozen=True)
class GeometryDerivedLoopEdge:
    name: str
    start_node: str
    end_node: str
    reference_airflow_m3_h: float
    sections: tuple[DuctSection, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("geometry-derived loop edge name cannot be empty")
        if not self.start_node.strip() or not self.end_node.strip():
            raise ValueError("geometry-derived loop edge node names cannot be empty")
        if self.start_node == self.end_node:
            raise ValueError("geometry-derived loop edge cannot connect a node to itself")
        object.__setattr__(
            self,
            "reference_airflow_m3_h",
            _positive(self.reference_airflow_m3_h, "reference_airflow_m3_h"),
        )
        if not self.sections:
            raise ValueError("geometry-derived loop edge requires at least one duct section")
        names = [section.name for section in self.sections]
        if len(names) != len(set(names)):
            raise ValueError(
                "duct-section names must be unique within a geometry-derived loop edge"
            )
        for section in self.sections:
            if not math.isclose(
                section.airflow_m3_h,
                self.reference_airflow_m3_h,
                rel_tol=0.0,
                abs_tol=1e-9,
            ):
                raise ValueError(
                    "each duct section airflow_m3_h must equal the edge "
                    "reference_airflow_m3_h"
                )


@dataclass(frozen=True)
class GeometryDerivedLoopNetwork:
    name: str
    node_injections_m3_h: dict[str, float]
    edges: tuple[GeometryDerivedLoopEdge, ...]
    reference_node: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("geometry-derived loop-network name cannot be empty")
        if not self.edges:
            raise ValueError("geometry-derived loop network requires at least one edge")
        names = [edge.name for edge in self.edges]
        if len(names) != len(set(names)):
            raise ValueError("geometry-derived loop edge names must be unique")


def derive_edge_resistance(edge: GeometryDerivedLoopEdge) -> tuple[QuadraticFlowEdge, dict]:
    total_resistance = 0.0
    section_results: list[dict] = []

    for section in edge.sections:
        friction = section.friction_analysis()
        friction_factor = friction["friction_factor"]
        loss_multiplier = (
            friction_factor * section.length_m / section.hydraulic_diameter_m
            + section.local_loss_coefficient
        )
        resistance = (
            0.5
            * section.air_density_kg_m3
            * loss_multiplier
            / section.area_m2**2
        )
        if not math.isfinite(resistance) or resistance < 0:
            raise ValueError(
                f"derived resistance for section {section.name!r} must be finite and >= 0"
            )
        total_resistance += resistance
        reference_airflow_m3_s = edge.reference_airflow_m3_h / 3600.0
        section_results.append(
            {
                "name": section.name,
                "shape": section.shape,
                "length_m": round(section.length_m, 6),
                "area_m2": round(section.area_m2, 9),
                "hydraulic_diameter_m": round(section.hydraulic_diameter_m, 9),
                "air_density_kg_m3": round(section.air_density_kg_m3, 6),
                "local_loss_coefficient": round(
                    section.local_loss_coefficient, 9
                ),
                "friction_factor": round(friction_factor, 9),
                "friction_factor_method": friction["method"],
                "reynolds_number": (
                    None
                    if friction["reynolds_number"] is None
                    else round(friction["reynolds_number"], 6)
                ),
                "absolute_roughness_m": friction["absolute_roughness_m"],
                "relative_roughness": (
                    None
                    if friction["relative_roughness"] is None
                    else round(friction["relative_roughness"], 12)
                ),
                "kinematic_viscosity_m2_s": friction[
                    "kinematic_viscosity_m2_s"
                ],
                "quadratic_resistance_pa_per_m3_s_squared": round(
                    resistance, 12
                ),
                "reference_pressure_drop_pa": round(
                    resistance * reference_airflow_m3_s**2, 9
                ),
            }
        )

    fixed_edge = QuadraticFlowEdge(
        name=edge.name,
        start_node=edge.start_node,
        end_node=edge.end_node,
        resistance_pa_per_m3_s_squared=total_resistance,
    )
    reference_airflow_m3_s = edge.reference_airflow_m3_h / 3600.0
    evidence = {
        "name": edge.name,
        "start_node": edge.start_node,
        "end_node": edge.end_node,
        "reference_airflow_m3_h": round(edge.reference_airflow_m3_h, 9),
        "derived_resistance_pa_per_m3_s_squared": round(total_resistance, 12),
        "reference_pressure_drop_pa": round(
            total_resistance * reference_airflow_m3_s**2, 9
        ),
        "sections": section_results,
        "basis_note": (
            "The quadratic edge resistance is derived from the configured duct "
            "geometry, density, local-loss coefficients, and Darcy friction factors. "
            "Automatic Darcy friction, when selected, is resolved at the declared "
            "reference airflow and then held fixed during loop balancing."
        ),
    }
    return fixed_edge, evidence


def derive_fixed_loop_network(
    network: GeometryDerivedLoopNetwork,
) -> tuple[LoopedFlowNetwork, list[dict]]:
    fixed_edges: list[QuadraticFlowEdge] = []
    evidence: list[dict] = []
    for edge in network.edges:
        fixed_edge, edge_evidence = derive_edge_resistance(edge)
        fixed_edges.append(fixed_edge)
        evidence.append(edge_evidence)

    fixed_network = LoopedFlowNetwork(
        name=network.name,
        node_injections_m3_h=dict(network.node_injections_m3_h),
        edges=tuple(fixed_edges),
        reference_node=network.reference_node,
    )
    return fixed_network, evidence


def analyze_geometry_derived_loop_network(
    network: GeometryDerivedLoopNetwork,
    *,
    mass_balance_tolerance_m3_h: float = 1e-6,
    max_iterations: int = 100,
) -> dict:
    fixed_network, derivation = derive_fixed_loop_network(network)
    result = solve_looped_network(
        fixed_network,
        mass_balance_tolerance_m3_h=mass_balance_tolerance_m3_h,
        max_iterations=max_iterations,
    )

    derivation_by_name = {item["name"]: item for item in derivation}
    enriched_edges = []
    for solved_edge in result["edges"]:
        basis = derivation_by_name[solved_edge["name"]]
        reference_airflow = basis["reference_airflow_m3_h"]
        solved_airflow = solved_edge["airflow_m3_h"]
        enriched = dict(solved_edge)
        enriched["reference_airflow_m3_h"] = reference_airflow
        enriched["absolute_solved_to_reference_flow_ratio"] = round(
            abs(solved_airflow) / reference_airflow, 9
        )
        enriched["resistance_derivation"] = basis
        enriched_edges.append(enriched)

    output = dict(result)
    output["workflow"] = "geometry_derived_fixed_resistance_loop"
    output["edges"] = enriched_edges
    output["scope_note"] = (
        "Loop edge resistance is derived from explicit duct geometry, air density, "
        "local-loss coefficients, and Darcy friction inputs. If automatic Darcy "
        "friction is used, it is evaluated only at the declared reference airflow "
        "and then frozen. The pressure-node solve remains the v0.23 fixed-resistance "
        "steady-state model; it does not iterate Reynolds-dependent friction, infer "
        "dampers or leakage, couple a fan curve, or model transients."
    )
    return output
