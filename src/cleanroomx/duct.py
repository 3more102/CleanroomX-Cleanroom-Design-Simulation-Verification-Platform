from __future__ import annotations

import math
from dataclasses import dataclass


def _positive(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{field_name} must be finite and > 0")
    return value


def _nonnegative(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{field_name} must be finite and >= 0")
    return value


@dataclass(frozen=True)
class DuctSection:
    name: str
    length_m: float
    airflow_m3_h: float
    friction_factor: float
    air_density_kg_m3: float
    local_loss_coefficient: float = 0.0
    diameter_m: float | None = None
    width_m: float | None = None
    height_m: float | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("duct-section name cannot be empty")
        object.__setattr__(self, "length_m", _nonnegative(self.length_m, "length_m"))
        object.__setattr__(
            self, "airflow_m3_h", _positive(self.airflow_m3_h, "airflow_m3_h")
        )
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
                self, "diameter_m", _positive(self.diameter_m, "diameter_m")
            )
        else:
            if self.width_m is None or self.height_m is None:
                raise ValueError("rectangular duct requires both width_m and height_m")
            object.__setattr__(self, "width_m", _positive(self.width_m, "width_m"))
            object.__setattr__(
                self, "height_m", _positive(self.height_m, "height_m")
            )

        if self.length_m == 0 and self.local_loss_coefficient == 0:
            raise ValueError(
                "duct section must have positive length_m or local_loss_coefficient"
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
        return 2.0 * self.width_m * self.height_m / (
            self.width_m + self.height_m
        )


@dataclass(frozen=True)
class DuctPath:
    name: str
    sections: tuple[DuctSection, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("duct-path name cannot be empty")
        if not self.sections:
            raise ValueError("duct path must contain at least one section")
        names = [section.name for section in self.sections]
        if len(names) != len(set(names)):
            raise ValueError("duct-section names must be unique within a path")


@dataclass(frozen=True)
class DuctNetwork:
    paths: tuple[DuctPath, ...]

    def __post_init__(self) -> None:
        if not self.paths:
            raise ValueError("duct network must contain at least one path")
        names = [path.name for path in self.paths]
        if len(names) != len(set(names)):
            raise ValueError("duct-path names must be unique")


def analyze_duct_section(section: DuctSection) -> dict:
    airflow_m3_s = section.airflow_m3_h / 3600.0
    velocity_m_s = airflow_m3_s / section.area_m2
    velocity_pressure_pa = 0.5 * section.air_density_kg_m3 * velocity_m_s**2
    friction_pressure_drop_pa = (
        section.friction_factor
        * (section.length_m / section.hydraulic_diameter_m)
        * velocity_pressure_pa
    )
    local_pressure_drop_pa = (
        section.local_loss_coefficient * velocity_pressure_pa
    )
    total_pressure_drop_pa = friction_pressure_drop_pa + local_pressure_drop_pa

    return {
        "name": section.name,
        "shape": section.shape,
        "length_m": round(section.length_m, 4),
        "airflow_m3_h": round(section.airflow_m3_h, 3),
        "airflow_m3_s": round(airflow_m3_s, 6),
        "area_m2": round(section.area_m2, 6),
        "hydraulic_diameter_m": round(section.hydraulic_diameter_m, 6),
        "velocity_m_s": round(velocity_m_s, 4),
        "air_density_kg_m3": round(section.air_density_kg_m3, 4),
        "friction_factor": round(section.friction_factor, 6),
        "local_loss_coefficient": round(section.local_loss_coefficient, 6),
        "velocity_pressure_pa": round(velocity_pressure_pa, 4),
        "friction_pressure_drop_pa": round(friction_pressure_drop_pa, 4),
        "local_pressure_drop_pa": round(local_pressure_drop_pa, 4),
        "total_pressure_drop_pa": round(total_pressure_drop_pa, 4),
    }


def analyze_duct_path(path: DuctPath) -> dict:
    sections = [analyze_duct_section(section) for section in path.sections]
    total_pressure_drop_pa = sum(
        section["total_pressure_drop_pa"] for section in sections
    )
    return {
        "name": path.name,
        "sections": sections,
        "total_pressure_drop_pa": round(total_pressure_drop_pa, 4),
    }


def analyze_duct_network(network: DuctNetwork) -> dict:
    paths = [analyze_duct_path(path) for path in network.paths]
    critical = max(paths, key=lambda path: path["total_pressure_drop_pa"])
    return {
        "paths": paths,
        "critical_path": critical["name"],
        "critical_path_pressure_drop_pa": critical["total_pressure_drop_pa"],
        "scope_note": (
            "Path losses use Darcy-Weisbach straight-duct friction plus explicit local "
            "loss coefficients. Airflow, density, friction factor, geometry, and fitting "
            "coefficients are project inputs. The model compares user-defined paths; it "
            "does not solve branch airflow, fan curves, system effect, leakage, acoustic "
            "performance, or control interactions."
        ),
    }
