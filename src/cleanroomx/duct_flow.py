from __future__ import annotations

import math
from dataclasses import dataclass


def _positive(value: float, field_name: str) -> float:
    value = float(value)
    if value <= 0:
        raise ValueError(f"{field_name} must be > 0")
    return value


def _nonnegative(value: float, field_name: str) -> float:
    value = float(value)
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return value


@dataclass(frozen=True)
class ParallelFlowSection:
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
            raise ValueError("parallel-flow section name cannot be empty")
        object.__setattr__(self, "length_m", _nonnegative(self.length_m, "length_m"))
        object.__setattr__(
            self, "friction_factor", _nonnegative(self.friction_factor, "friction_factor")
        )
        object.__setattr__(
            self, "air_density_kg_m3", _positive(self.air_density_kg_m3, "air_density_kg_m3")
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
            object.__setattr__(self, "diameter_m", _positive(self.diameter_m, "diameter_m"))
        else:
            if self.width_m is None or self.height_m is None:
                raise ValueError("rectangular duct requires both width_m and height_m")
            object.__setattr__(self, "width_m", _positive(self.width_m, "width_m"))
            object.__setattr__(self, "height_m", _positive(self.height_m, "height_m"))

        if self.resistance_multiplier <= 0:
            raise ValueError(
                "section must have positive friction or local resistance for flow solving"
            )

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
        return 2.0 * self.width_m * self.height_m / (self.width_m + self.height_m)

    @property
    def resistance_multiplier(self) -> float:
        friction = 0.0
        if self.length_m > 0 and self.friction_factor > 0:
            friction = self.friction_factor * self.length_m / self.hydraulic_diameter_m
        return friction + self.local_loss_coefficient

    @property
    def resistance_pa_per_m3_s_squared(self) -> float:
        return (
            0.5
            * self.air_density_kg_m3
            * self.resistance_multiplier
            / self.area_m2**2
        )


@dataclass(frozen=True)
class ParallelFlowPath:
    name: str
    sections: tuple[ParallelFlowSection, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("parallel-flow path name cannot be empty")
        if not self.sections:
            raise ValueError("parallel-flow path must contain at least one section")
        names = [section.name for section in self.sections]
        if len(names) != len(set(names)):
            raise ValueError("section names must be unique within a parallel-flow path")

    @property
    def resistance_pa_per_m3_s_squared(self) -> float:
        return sum(
            section.resistance_pa_per_m3_s_squared for section in self.sections
        )


@dataclass(frozen=True)
class ParallelFlowNetwork:
    name: str
    total_airflow_m3_h: float
    paths: tuple[ParallelFlowPath, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("parallel-flow network name cannot be empty")
        object.__setattr__(
            self,
            "total_airflow_m3_h",
            _positive(self.total_airflow_m3_h, "total_airflow_m3_h"),
        )
        if len(self.paths) < 2:
            raise ValueError("parallel-flow network requires at least two paths")
        names = [path.name for path in self.paths]
        if len(names) != len(set(names)):
            raise ValueError("parallel-flow path names must be unique")


def _section_result(section: ParallelFlowSection, airflow_m3_s: float) -> dict:
    velocity = airflow_m3_s / section.area_m2
    velocity_pressure = 0.5 * section.air_density_kg_m3 * velocity**2
    friction_multiplier = (
        section.friction_factor * section.length_m / section.hydraulic_diameter_m
        if section.length_m > 0
        else 0.0
    )
    friction_loss = friction_multiplier * velocity_pressure
    local_loss = section.local_loss_coefficient * velocity_pressure
    return {
        "name": section.name,
        "airflow_m3_h": round(airflow_m3_s * 3600.0, 3),
        "velocity_m_s": round(velocity, 4),
        "velocity_pressure_pa": round(velocity_pressure, 4),
        "friction_pressure_drop_pa": round(friction_loss, 4),
        "local_pressure_drop_pa": round(local_loss, 4),
        "total_pressure_drop_pa": round(friction_loss + local_loss, 4),
    }


def solve_parallel_branch_flows(network: ParallelFlowNetwork) -> dict:
    total_airflow_m3_s = network.total_airflow_m3_h / 3600.0
    resistances = [
        path.resistance_pa_per_m3_s_squared for path in network.paths
    ]
    if any(resistance <= 0 for resistance in resistances):
        raise ValueError("all parallel-flow paths must have positive resistance")

    conductance_sum = sum(1.0 / math.sqrt(resistance) for resistance in resistances)
    common_pressure_drop_pa = (total_airflow_m3_s / conductance_sum) ** 2

    path_results = []
    solved_total = 0.0
    for path, resistance in zip(network.paths, resistances):
        airflow_m3_s = math.sqrt(common_pressure_drop_pa / resistance)
        solved_total += airflow_m3_s
        sections = [_section_result(section, airflow_m3_s) for section in path.sections]
        path_results.append(
            {
                "name": path.name,
                "resistance_pa_per_m3_s_squared": round(resistance, 6),
                "airflow_m3_h": round(airflow_m3_s * 3600.0, 3),
                "airflow_fraction": round(airflow_m3_s / total_airflow_m3_s, 6),
                "pressure_drop_pa": round(
                    sum(section["total_pressure_drop_pa"] for section in sections), 4
                ),
                "sections": sections,
            }
        )

    return {
        "network": network.name,
        "total_airflow_m3_h": round(network.total_airflow_m3_h, 3),
        "solved_total_airflow_m3_h": round(solved_total * 3600.0, 3),
        "common_pressure_drop_pa": round(common_pressure_drop_pa, 4),
        "paths": path_results,
        "mass_balance_error_m3_h": round(
            (solved_total - total_airflow_m3_s) * 3600.0, 9
        ),
        "scope_note": (
            "This solver distributes a specified total airflow across parallel paths "
            "that share common upstream/downstream pressure nodes. Every section in a "
            "path carries the same path airflow, and friction factors, air density, and "
            "local loss coefficients are held constant, so path loss follows R*Q^2. "
            "It does not solve arbitrary looped networks, fan curves, variable friction "
            "factor, damper controls, leakage, or transient behavior."
        ),
    }
