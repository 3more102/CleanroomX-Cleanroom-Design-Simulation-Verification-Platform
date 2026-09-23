from __future__ import annotations

import math
from dataclasses import dataclass

from .duct import DuctSection
from .loop_network import LoopedFlowNetwork, QuadraticFlowEdge, solve_looped_network


@dataclass(frozen=True)
class ReferenceDuctSection:
    name: str
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
            raise ValueError("reference duct-section name cannot be empty")

    def at_airflow(self, airflow_m3_h: float) -> DuctSection:
        return DuctSection(
            name=self.name,
            length_m=self.length_m,
            airflow_m3_h=airflow_m3_h,
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
class ReferenceDuctEdge:
    name: str
    start_node: str
    end_node: str
    reference_airflow_m3_h: float
    sections: tuple[ReferenceDuctSection, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("reference duct-edge name cannot be empty")
        if not isinstance(self.start_node, str) or not self.start_node.strip():
            raise ValueError("reference duct-edge start_node cannot be empty")
        if not isinstance(self.end_node, str) or not self.end_node.strip():
            raise ValueError("reference duct-edge end_node cannot be empty")
        if self.start_node == self.end_node:
            raise ValueError("reference duct edge cannot connect a node to itself")
        if not self.sections:
            raise ValueError("reference duct edge requires at least one section")
        names = [section.name for section in self.sections]
        if len(names) != len(set(names)):
            raise ValueError("reference duct-section names must be unique within an edge")
        for section in self.sections:
            section.at_airflow(self.reference_airflow_m3_h)


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


def _derive_section(
    section_spec: ReferenceDuctSection,
    reference_airflow_m3_h: float,
) -> tuple[float, dict]:
    section = section_spec.at_airflow(reference_airflow_m3_h)
    airflow_m3_s = section.airflow_m3_h / 3600.0
    velocity_m_s = airflow_m3_s / section.area_m2
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
    pressure_drop_pa = friction_pressure_drop_pa + local_pressure_drop_pa
    resistance = pressure_drop_pa / airflow_m3_s**2
    if not math.isfinite(resistance) or resistance <= 0:
        raise ValueError(
            f"section {section.name!r} must derive a finite resistance > 0; "
            "provide positive friction/local loss at the reference airflow"
        )

    evidence = {
        "name": section.name,
        "shape": section.shape,
        "length_m": round(section.length_m, 9),
        "diameter_m": section.diameter_m,
        "width_m": section.width_m,
        "height_m": section.height_m,
        "area_m2": round(section.area_m2, 12),
        "hydraulic_diameter_m": round(section.hydraulic_diameter_m, 12),
        "reference_airflow_m3_h": round(section.airflow_m3_h, 9),
        "reference_airflow_m3_s": round(airflow_m3_s, 12),
        "reference_velocity_m_s": round(velocity_m_s, 12),
        "air_density_kg_m3": round(section.air_density_kg_m3, 9),
        "friction_factor": round(friction_factor, 12),
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
        "local_loss_coefficient": round(section.local_loss_coefficient, 12),
        "reference_velocity_pressure_pa": round(velocity_pressure_pa, 12),
        "reference_friction_pressure_drop_pa": round(
            friction_pressure_drop_pa, 12
        ),
        "reference_local_pressure_drop_pa": round(local_pressure_drop_pa, 12),
        "reference_pressure_drop_pa": round(pressure_drop_pa, 12),
        "derived_resistance_pa_per_m3_s_squared": round(resistance, 12),
    }
    return resistance, evidence


def _derive_edge(
    edge: ReferenceDuctEdge,
) -> tuple[float, dict, list[float]]:
    section_results = [
        _derive_section(section, edge.reference_airflow_m3_h)
        for section in edge.sections
    ]
    section_resistances = [item[0] for item in section_results]
    section_evidence = [item[1] for item in section_results]
    resistance = sum(section_resistances)
    reference_pressure_drop_pa = sum(
        item["reference_pressure_drop_pa"] for item in section_evidence
    )
    return (
        resistance,
        {
            "name": edge.name,
            "start_node": edge.start_node,
            "end_node": edge.end_node,
            "reference_airflow_m3_h": round(edge.reference_airflow_m3_h, 9),
            "reference_pressure_drop_pa": round(reference_pressure_drop_pa, 12),
            "derived_resistance_pa_per_m3_s_squared": round(resistance, 12),
            "section_count": len(section_evidence),
            "sections": section_evidence,
        },
        section_resistances,
    )


def derive_reference_edge_resistance(edge: ReferenceDuctEdge) -> dict:
    """Return auditable fixed-resistance evidence for one geometry-defined edge."""
    return _derive_edge(edge)[1]


def solve_reference_geometry_loop(
    network: ReferenceGeometryLoopNetwork,
    *,
    mass_balance_tolerance_m3_h: float = 1e-6,
    max_iterations: int = 100,
) -> dict:
    derived = {
        edge.name: _derive_edge(edge)
        for edge in network.edges
    }
    fixed_network = LoopedFlowNetwork(
        name=network.name,
        node_injections_m3_h=dict(network.node_injections_m3_h),
        edges=tuple(
            QuadraticFlowEdge(
                name=edge.name,
                start_node=edge.start_node,
                end_node=edge.end_node,
                resistance_pa_per_m3_s_squared=derived[edge.name][0],
            )
            for edge in network.edges
        ),
        reference_node=network.reference_node,
    )
    base = solve_looped_network(
        fixed_network,
        mass_balance_tolerance_m3_h=mass_balance_tolerance_m3_h,
        max_iterations=max_iterations,
    )

    enriched_edges = []
    geometry_residuals: list[float] = []
    for solved_edge in base["edges"]:
        edge_result = dict(solved_edge)
        _, reference_evidence, section_resistances = derived[solved_edge["name"]]
        airflow_m3_s = float(solved_edge["airflow_m3_s"])
        signed_section_sum_pa = 0.0
        section_outputs = []
        for reference_section, section_resistance in zip(
            reference_evidence["sections"], section_resistances
        ):
            signed_drop_pa = (
                section_resistance * airflow_m3_s * abs(airflow_m3_s)
            )
            signed_section_sum_pa += signed_drop_pa
            section_output = dict(reference_section)
            section_output.update(
                {
                    "solved_airflow_m3_h": round(airflow_m3_s * 3600.0, 6),
                    "solved_velocity_m_s": round(
                        abs(airflow_m3_s) / float(reference_section["area_m2"]),
                        12,
                    ),
                    "solved_signed_pressure_drop_pa": round(signed_drop_pa, 12),
                    "solved_pressure_drop_magnitude_pa": round(
                        abs(signed_drop_pa), 12
                    ),
                }
            )
            section_outputs.append(section_output)

        geometry_residual_pa = (
            float(solved_edge["pressure_difference_pa"])
            - signed_section_sum_pa
        )
        geometry_residuals.append(abs(geometry_residual_pa))
        edge_result.update(
            {
                "resistance_source": "reference_geometry_fixed_resistance",
                "reference_airflow_m3_h": reference_evidence[
                    "reference_airflow_m3_h"
                ],
                "reference_pressure_drop_pa": reference_evidence[
                    "reference_pressure_drop_pa"
                ],
                "section_count": reference_evidence["section_count"],
                "sections": section_outputs,
                "section_pressure_drop_sum_pa": round(
                    signed_section_sum_pa, 12
                ),
                "geometry_pressure_residual_pa": round(
                    geometry_residual_pa, 12
                ),
            }
        )
        enriched_edges.append(edge_result)

    return {
        **base,
        "edges": enriched_edges,
        "max_abs_geometry_pressure_residual_pa": round(
            max(geometry_residuals, default=0.0), 12
        ),
        "scope_note": (
            "Each loop-edge resistance is derived once from explicit duct geometry, "
            "air density, local-loss inputs, and a declared positive reference airflow. "
            "Darcy friction is either supplied directly or resolved from explicit "
            "roughness and kinematic viscosity at that reference airflow. The resolved "
            "section factors and derived edge resistance are then held fixed while the "
            "connected loop solver balances flow. This workflow does not iterate "
            "Reynolds number or friction factor at solved edge flow, infer fitting or "
            "material properties, model leakage/dampers/controls, couple a fan curve, "
            "or represent transient/compressible behavior."
        ),
    }
