from __future__ import annotations

import math
from dataclasses import dataclass

from .duct import DuctSection
from .loop_network import LoopedFlowNetwork, QuadraticFlowEdge, solve_looped_network


@dataclass(frozen=True)
class LoopDuctEdge:
    name: str
    start_node: str
    end_node: str
    sections: tuple[DuctSection, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("loop-duct edge name cannot be empty")
        if not self.start_node.strip() or not self.end_node.strip():
            raise ValueError("loop-duct edge node names cannot be empty")
        if self.start_node == self.end_node:
            raise ValueError("loop-duct edge cannot connect a node to itself")
        if not self.sections:
            raise ValueError("loop-duct edge must contain at least one section")
        names = [section.name for section in self.sections]
        if len(names) != len(set(names)):
            raise ValueError("duct-section names must be unique within a loop edge")

        reference = self.sections[0].airflow_m3_h
        for section in self.sections[1:]:
            if not math.isclose(
                section.airflow_m3_h,
                reference,
                rel_tol=1e-9,
                abs_tol=1e-6,
            ):
                raise ValueError(
                    "all sections in a loop-duct edge must use the same explicit "
                    "reference airflow_m3_h"
                )

    @property
    def reference_airflow_m3_h(self) -> float:
        return self.sections[0].airflow_m3_h


@dataclass(frozen=True)
class GeometryLoopedFlowNetwork:
    name: str
    node_injections_m3_h: dict[str, float]
    edges: tuple[LoopDuctEdge, ...]
    reference_node: str

    def __post_init__(self) -> None:
        if not self.edges:
            raise ValueError("geometry loop network requires at least one edge")
        names = [edge.name for edge in self.edges]
        if len(names) != len(set(names)):
            raise ValueError("loop-duct edge names must be unique")

        validation_network = LoopedFlowNetwork(
            name=self.name,
            node_injections_m3_h=dict(self.node_injections_m3_h),
            edges=tuple(
                QuadraticFlowEdge(
                    name=edge.name,
                    start_node=edge.start_node,
                    end_node=edge.end_node,
                    resistance_pa_per_m3_s_squared=1.0,
                )
                for edge in self.edges
            ),
            reference_node=self.reference_node,
        )
        object.__setattr__(
            self,
            "node_injections_m3_h",
            validation_network.node_injections_m3_h,
        )


def _section_fixed_resistance(section: DuctSection) -> tuple[float, dict]:
    friction = section.friction_analysis()
    friction_factor = friction["friction_factor"]
    resistance_multiplier = (
        friction_factor * section.length_m / section.hydraulic_diameter_m
        + section.local_loss_coefficient
    )
    resistance = (
        0.5
        * section.air_density_kg_m3
        * resistance_multiplier
        / (section.area_m2**2)
    )
    reference_airflow_m3_s = section.airflow_m3_h / 3600.0
    reference_pressure_drop_pa = resistance * reference_airflow_m3_s**2
    return resistance, {
        "name": section.name,
        "shape": section.shape,
        "reference_airflow_m3_h": round(section.airflow_m3_h, 3),
        "area_m2": round(section.area_m2, 9),
        "hydraulic_diameter_m": round(section.hydraulic_diameter_m, 9),
        "air_density_kg_m3": round(section.air_density_kg_m3, 6),
        "friction_factor": round(friction_factor, 9),
        "friction_factor_method": friction["method"],
        "reynolds_number": (
            None
            if friction["reynolds_number"] is None
            else round(friction["reynolds_number"], 3)
        ),
        "absolute_roughness_m": friction["absolute_roughness_m"],
        "relative_roughness": (
            None
            if friction["relative_roughness"] is None
            else round(friction["relative_roughness"], 12)
        ),
        "kinematic_viscosity_m2_s": friction["kinematic_viscosity_m2_s"],
        "local_loss_coefficient": round(section.local_loss_coefficient, 9),
        "quadratic_resistance_pa_per_m3_s_squared": round(resistance, 9),
        "reference_pressure_drop_pa": round(reference_pressure_drop_pa, 6),
    }


def derive_loop_duct_edge_resistance(edge: LoopDuctEdge) -> dict:
    raw_resistance = 0.0
    sections: list[dict] = []
    for section in edge.sections:
        section_resistance, section_result = _section_fixed_resistance(section)
        raw_resistance += section_resistance
        sections.append(section_result)

    if raw_resistance <= 0:
        raise ValueError(
            f"loop-duct edge {edge.name!r} has zero derived quadratic resistance"
        )

    reference_airflow_m3_s = edge.reference_airflow_m3_h / 3600.0
    return {
        "name": edge.name,
        "start_node": edge.start_node,
        "end_node": edge.end_node,
        "reference_airflow_m3_h": round(edge.reference_airflow_m3_h, 3),
        "resistance_pa_per_m3_s_squared": raw_resistance,
        "reference_pressure_drop_pa": round(
            raw_resistance * reference_airflow_m3_s**2,
            6,
        ),
        "sections": sections,
    }


def solve_geometry_looped_network(
    network: GeometryLoopedFlowNetwork,
    *,
    mass_balance_tolerance_m3_h: float = 1e-6,
    max_iterations: int = 100,
) -> dict:
    derived_edges = [
        derive_loop_duct_edge_resistance(edge)
        for edge in network.edges
    ]
    fixed_network = LoopedFlowNetwork(
        name=network.name,
        node_injections_m3_h=dict(network.node_injections_m3_h),
        edges=tuple(
            QuadraticFlowEdge(
                name=edge["name"],
                start_node=edge["start_node"],
                end_node=edge["end_node"],
                resistance_pa_per_m3_s_squared=edge[
                    "resistance_pa_per_m3_s_squared"
                ],
            )
            for edge in derived_edges
        ),
        reference_node=network.reference_node,
    )
    result = solve_looped_network(
        fixed_network,
        mass_balance_tolerance_m3_h=mass_balance_tolerance_m3_h,
        max_iterations=max_iterations,
    )

    derived_by_name = {edge["name"]: edge for edge in derived_edges}
    for solved_edge in result["edges"]:
        basis = derived_by_name[solved_edge["name"]]
        solved_edge["reference_airflow_m3_h"] = basis["reference_airflow_m3_h"]
        solved_edge["reference_pressure_drop_pa"] = basis[
            "reference_pressure_drop_pa"
        ]
        solved_edge["sections"] = basis["sections"]
        solved_edge["resistance_basis"] = (
            "duct_geometry_with_friction_frozen_at_reference_airflow"
        )

    result["resistance_basis"] = (
        "duct_geometry_with_friction_frozen_at_reference_airflow"
    )
    result["scope_note"] = (
        "Each loop-edge quadratic resistance is derived from explicit duct geometry, "
        "air density, local-loss coefficients, and a Darcy friction factor. A supplied "
        "friction factor is held fixed directly; automatic Darcy friction is resolved "
        "at the edge's explicit reference airflow and then held fixed while the loop "
        "network is balanced. The solver does not iterate friction factor with solved "
        "flow, infer roughness or viscosity, model dampers/leakage/controls, couple a "
        "fan curve, or model compressibility/transients."
    )
    return result
