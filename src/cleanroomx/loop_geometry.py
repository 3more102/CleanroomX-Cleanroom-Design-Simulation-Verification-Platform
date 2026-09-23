from __future__ import annotations

import math
from dataclasses import dataclass

from .duct import DuctSection
from .loop_network import LoopedFlowNetwork, QuadraticFlowEdge, solve_looped_network


@dataclass(frozen=True)
class ReferenceDuctEdge:
    name: str
    start_node: str
    end_node: str
    reference_airflow_m3_h: float
    length_m: float
    air_density_kg_m3: float
    friction_factor: float | None = None
    local_loss_coefficient: float = 0.0
    diameter_m: float | None = None
    width_m: float | None = None
    height_m: float | None = None
    absolute_roughness_m: float | None = None
    kinematic_viscosity_m2_s: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("reference duct-edge name cannot be empty")
        if not isinstance(self.start_node, str) or not self.start_node.strip():
            raise ValueError("reference duct-edge start_node cannot be empty")
        if not isinstance(self.end_node, str) or not self.end_node.strip():
            raise ValueError("reference duct-edge end_node cannot be empty")
        if self.start_node == self.end_node:
            raise ValueError("reference duct edge cannot connect a node to itself")
        # Reuse the canonical duct-section validation, including geometry and
        # manual/automatic Darcy-friction input rules.
        self.as_duct_section()

    def as_duct_section(self) -> DuctSection:
        return DuctSection(
            name=self.name,
            length_m=self.length_m,
            airflow_m3_h=self.reference_airflow_m3_h,
            friction_factor=self.friction_factor,
            air_density_kg_m3=self.air_density_kg_m3,
            local_loss_coefficient=self.local_loss_coefficient,
            diameter_m=self.diameter_m,
            width_m=self.width_m,
            height_m=self.height_m,
            absolute_roughness_m=self.absolute_roughness_m,
            kinematic_viscosity_m2_s=self.kinematic_viscosity_m2_s,
        )


@dataclass(frozen=True)
class ReferenceGeometryLoopNetwork:
    name: str
    node_injections_m3_h: dict[str, float]
    edges: tuple[ReferenceDuctEdge, ...]
    reference_node: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("reference geometry loop-network name cannot be empty")
        if not self.edges:
            raise ValueError("reference geometry loop-network requires at least one edge")


def derive_fixed_resistance(edge: ReferenceDuctEdge) -> dict:
    """Derive one fixed quadratic edge resistance at the declared reference flow."""
    section = edge.as_duct_section()
    reference_airflow_m3_s = section.airflow_m3_h / 3600.0
    velocity_m_s = reference_airflow_m3_s / section.area_m2
    friction = section.friction_analysis()
    friction_factor = friction["friction_factor"]
    velocity_pressure_pa = 0.5 * section.air_density_kg_m3 * velocity_m_s**2
    friction_pressure_drop_pa = (
        friction_factor
        * (section.length_m / section.hydraulic_diameter_m)
        * velocity_pressure_pa
    )
    local_pressure_drop_pa = (
        section.local_loss_coefficient * velocity_pressure_pa
    )
    reference_pressure_drop_pa = (
        friction_pressure_drop_pa + local_pressure_drop_pa
    )
    resistance = reference_pressure_drop_pa / reference_airflow_m3_s**2
    if not math.isfinite(resistance) or resistance <= 0:
        raise ValueError(
            f"edge {edge.name!r} must derive a finite resistance > 0; "
            "provide positive friction/local loss at the reference airflow"
        )

    return {
        "name": edge.name,
        "start_node": edge.start_node,
        "end_node": edge.end_node,
        "reference_airflow_m3_h": round(section.airflow_m3_h, 6),
        "reference_airflow_m3_s": round(reference_airflow_m3_s, 12),
        "shape": section.shape,
        "area_m2": round(section.area_m2, 9),
        "hydraulic_diameter_m": round(section.hydraulic_diameter_m, 9),
        "velocity_m_s": round(velocity_m_s, 9),
        "air_density_kg_m3": round(section.air_density_kg_m3, 9),
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
        "kinematic_viscosity_m2_s": friction["kinematic_viscosity_m2_s"],
        "local_loss_coefficient": round(section.local_loss_coefficient, 9),
        "friction_pressure_drop_pa": round(friction_pressure_drop_pa, 9),
        "local_pressure_drop_pa": round(local_pressure_drop_pa, 9),
        "reference_pressure_drop_pa": round(reference_pressure_drop_pa, 9),
        "derived_resistance_pa_per_m3_s_squared": round(resistance, 12),
    }


def build_fixed_resistance_network(
    network: ReferenceGeometryLoopNetwork,
) -> tuple[LoopedFlowNetwork, list[dict]]:
    derivations = [derive_fixed_resistance(edge) for edge in network.edges]
    fixed_network = LoopedFlowNetwork(
        name=network.name,
        node_injections_m3_h=dict(network.node_injections_m3_h),
        edges=tuple(
            QuadraticFlowEdge(
                name=item["name"],
                start_node=item["start_node"],
                end_node=item["end_node"],
                resistance_pa_per_m3_s_squared=item[
                    "derived_resistance_pa_per_m3_s_squared"
                ],
            )
            for item in derivations
        ),
        reference_node=network.reference_node,
    )
    return fixed_network, derivations


def analyze_reference_geometry_loop(
    network: ReferenceGeometryLoopNetwork,
    *,
    mass_balance_tolerance_m3_h: float = 1e-6,
    max_iterations: int = 100,
) -> dict:
    fixed_network, derivations = build_fixed_resistance_network(network)
    loop_solution = solve_looped_network(
        fixed_network,
        mass_balance_tolerance_m3_h=mass_balance_tolerance_m3_h,
        max_iterations=max_iterations,
    )
    return {
        "network": network.name,
        "status": loop_solution["status"],
        "reference_node": network.reference_node,
        "derived_edges": derivations,
        "loop_solution": loop_solution,
        "scope_note": (
            "Each edge resistance is derived once from explicit duct geometry, density, "
            "local-loss inputs, and a declared positive reference airflow. Darcy friction "
            "is either supplied directly or resolved from explicit roughness and kinematic "
            "viscosity at that reference airflow. The resulting resistance is then held "
            "fixed while the v0.23 loop solver balances the network. This workflow does "
            "not iterate Reynolds number or friction factor at solved edge flow, infer "
            "fittings/material properties, model leakage/dampers/controls, couple a fan "
            "curve, or represent transient/compressible behavior."
        ),
    }
