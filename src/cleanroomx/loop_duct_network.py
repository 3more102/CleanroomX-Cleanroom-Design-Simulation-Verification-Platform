from __future__ import annotations

import math
from dataclasses import dataclass

from .loop_network import LoopedFlowNetwork, QuadraticFlowEdge, solve_looped_network


def _finite(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite")
    return value


def _positive(value: float, field_name: str) -> float:
    value = _finite(value, field_name)
    if value <= 0:
        raise ValueError(f"{field_name} must be > 0")
    return value


def _nonnegative(value: float, field_name: str) -> float:
    value = _finite(value, field_name)
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return value


@dataclass(frozen=True)
class FixedFrictionDuctSection:
    name: str
    length_m: float
    friction_factor: float
    air_density_kg_m3: float
    local_loss_coefficient: float = 0.0
    diameter_m: float | None = None
    width_m: float | None = None
    height_m: float | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("loop-duct section name cannot be empty")
        object.__setattr__(self, "length_m", _nonnegative(self.length_m, "length_m"))
        object.__setattr__(
            self,
            "friction_factor",
            _nonnegative(self.friction_factor, "friction_factor"),
        )
        object.__setattr__(
            self,
            "air_density_kg_m3",
            _positive(self.air_density_kg_m3, "air_density_kg_m3"),
        )
        object.__setattr__(
            self,
            "local_loss_coefficient",
            _nonnegative(self.local_loss_coefficient, "local_loss_coefficient"),
        )

        circular = self.diameter_m is not None
        rectangular = self.width_m is not None or self.height_m is not None
        if circular == rectangular:
            raise ValueError(
                "provide either diameter_m or both width_m and height_m, but not both"
            )
        if circular:
            object.__setattr__(
                self,
                "diameter_m",
                _positive(self.diameter_m, "diameter_m"),
            )
        else:
            if self.width_m is None or self.height_m is None:
                raise ValueError("rectangular duct requires width_m and height_m")
            object.__setattr__(self, "width_m", _positive(self.width_m, "width_m"))
            object.__setattr__(
                self,
                "height_m",
                _positive(self.height_m, "height_m"),
            )

        if self.dimensionless_loss_coefficient <= 0:
            raise ValueError(
                "loop-duct section must have positive fixed loss from friction and/or local K"
            )

    @property
    def shape(self) -> str:
        return "circular" if self.diameter_m is not None else "rectangular"

    @property
    def area_m2(self) -> float:
        if self.diameter_m is not None:
            return math.pi * self.diameter_m**2 / 4.0
        assert self.width_m is not None and self.height_m is not None
        return self.width_m * self.height_m

    @property
    def hydraulic_diameter_m(self) -> float:
        if self.diameter_m is not None:
            return self.diameter_m
        assert self.width_m is not None and self.height_m is not None
        return (
            2.0
            * self.width_m
            * self.height_m
            / (self.width_m + self.height_m)
        )

    @property
    def dimensionless_loss_coefficient(self) -> float:
        return (
            self.friction_factor * self.length_m / self.hydraulic_diameter_m
            + self.local_loss_coefficient
        )

    @property
    def resistance_pa_per_m3_s_squared(self) -> float:
        return (
            0.5
            * self.air_density_kg_m3
            * self.dimensionless_loss_coefficient
            / self.area_m2**2
        )

    def solved_evidence(self, airflow_m3_s: float) -> dict:
        airflow_m3_s = _finite(airflow_m3_s, "airflow_m3_s")
        magnitude = abs(airflow_m3_s)
        velocity_m_s = magnitude / self.area_m2
        velocity_pressure_pa = 0.5 * self.air_density_kg_m3 * velocity_m_s**2
        friction_pressure_drop_pa = (
            self.friction_factor
            * self.length_m
            / self.hydraulic_diameter_m
            * velocity_pressure_pa
        )
        local_pressure_drop_pa = (
            self.local_loss_coefficient * velocity_pressure_pa
        )
        total_pressure_drop_pa = (
            friction_pressure_drop_pa + local_pressure_drop_pa
        )
        signed_pressure_drop_pa = (
            math.copysign(total_pressure_drop_pa, airflow_m3_s)
            if airflow_m3_s != 0
            else 0.0
        )
        return {
            "name": self.name,
            "shape": self.shape,
            "length_m": round(self.length_m, 6),
            "diameter_m": self.diameter_m,
            "width_m": self.width_m,
            "height_m": self.height_m,
            "area_m2": round(self.area_m2, 9),
            "hydraulic_diameter_m": round(self.hydraulic_diameter_m, 9),
            "friction_factor": round(self.friction_factor, 9),
            "air_density_kg_m3": round(self.air_density_kg_m3, 9),
            "local_loss_coefficient": round(self.local_loss_coefficient, 9),
            "dimensionless_loss_coefficient": round(
                self.dimensionless_loss_coefficient, 9
            ),
            "resistance_pa_per_m3_s_squared": round(
                self.resistance_pa_per_m3_s_squared, 9
            ),
            "airflow_m3_s": round(airflow_m3_s, 12),
            "airflow_m3_h": round(airflow_m3_s * 3600.0, 6),
            "velocity_m_s": round(velocity_m_s, 9),
            "velocity_pressure_pa": round(velocity_pressure_pa, 9),
            "friction_pressure_drop_pa": round(
                friction_pressure_drop_pa, 9
            ),
            "local_pressure_drop_pa": round(local_pressure_drop_pa, 9),
            "total_pressure_drop_pa": round(total_pressure_drop_pa, 9),
            "signed_pressure_drop_pa": round(signed_pressure_drop_pa, 9),
        }


@dataclass(frozen=True)
class GeometryLoopEdge:
    name: str
    start_node: str
    end_node: str
    sections: tuple[FixedFrictionDuctSection, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("loop-duct edge name cannot be empty")
        if not self.start_node.strip() or not self.end_node.strip():
            raise ValueError("loop-duct edge node names cannot be empty")
        if self.start_node == self.end_node:
            raise ValueError("loop-duct edge cannot connect a node to itself")
        if not self.sections:
            raise ValueError("loop-duct edge requires at least one section")
        names = [section.name for section in self.sections]
        if len(names) != len(set(names)):
            raise ValueError("loop-duct section names must be unique within an edge")

    @property
    def resistance_pa_per_m3_s_squared(self) -> float:
        return sum(
            section.resistance_pa_per_m3_s_squared
            for section in self.sections
        )

    def as_quadratic_edge(self) -> QuadraticFlowEdge:
        return QuadraticFlowEdge(
            name=self.name,
            start_node=self.start_node,
            end_node=self.end_node,
            resistance_pa_per_m3_s_squared=(
                self.resistance_pa_per_m3_s_squared
            ),
        )


@dataclass(frozen=True)
class GeometryLoopNetwork:
    name: str
    node_injections_m3_h: dict[str, float]
    edges: tuple[GeometryLoopEdge, ...]
    reference_node: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("loop-duct network name cannot be empty")
        if not self.edges:
            raise ValueError("loop-duct network requires at least one edge")
        edge_names = [edge.name for edge in self.edges]
        if len(edge_names) != len(set(edge_names)):
            raise ValueError("loop-duct edge names must be unique")
        # Reuse the validated fixed-resistance network model for graph,
        # node-reference, injection-balance, and connectivity checks.
        self.as_quadratic_network()

    def as_quadratic_network(self) -> LoopedFlowNetwork:
        return LoopedFlowNetwork(
            name=self.name,
            node_injections_m3_h=dict(self.node_injections_m3_h),
            edges=tuple(edge.as_quadratic_edge() for edge in self.edges),
            reference_node=self.reference_node,
        )


def solve_geometry_looped_network(
    network: GeometryLoopNetwork,
    *,
    mass_balance_tolerance_m3_h: float = 1e-6,
    max_iterations: int = 100,
) -> dict:
    base = solve_looped_network(
        network.as_quadratic_network(),
        mass_balance_tolerance_m3_h=mass_balance_tolerance_m3_h,
        max_iterations=max_iterations,
    )
    solved_by_name = {edge["name"]: edge for edge in base["edges"]}
    enriched_edges = []
    geometry_residuals: list[float] = []

    for edge in network.edges:
        solved = dict(solved_by_name[edge.name])
        airflow_m3_s = float(solved["airflow_m3_s"])
        sections = [
            section.solved_evidence(airflow_m3_s)
            for section in edge.sections
        ]
        signed_section_sum_pa = sum(
            section["signed_pressure_drop_pa"] for section in sections
        )
        geometry_residual_pa = (
            float(solved["pressure_difference_pa"])
            - signed_section_sum_pa
        )
        geometry_residuals.append(abs(geometry_residual_pa))
        solved.update(
            {
                "resistance_source": "explicit_geometry_fixed_friction",
                "section_count": len(sections),
                "sections": sections,
                "section_pressure_drop_sum_pa": round(
                    signed_section_sum_pa, 9
                ),
                "geometry_pressure_residual_pa": round(
                    geometry_residual_pa, 9
                ),
            }
        )
        enriched_edges.append(solved)

    return {
        **base,
        "edges": enriched_edges,
        "max_abs_geometry_pressure_residual_pa": round(
            max(geometry_residuals, default=0.0), 9
        ),
        "scope_note": (
            "This workflow derives each loop-edge fixed quadratic resistance from "
            "explicit duct geometry, air density, a user-supplied fixed Darcy friction "
            "factor, and explicit local-loss coefficients, then reuses the connected "
            "steady-state loop solver. It does not iterate friction factor with solved "
            "Reynolds number, infer roughness, size ducts, solve fan operating points, "
            "model dampers or controls, leakage, compressibility, or transients."
        ),
    }
