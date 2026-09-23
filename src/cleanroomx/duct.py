from __future__ import annotations

import math
from dataclasses import dataclass

from .friction import resolve_darcy_friction_factor


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
    friction_factor: float | None
    air_density_kg_m3: float
    local_loss_coefficient: float = 0.0
    diameter_m: float | None = None
    width_m: float | None = None
    height_m: float | None = None
    absolute_roughness_m: float | None = None
    kinematic_viscosity_m2_s: float | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("duct-section name cannot be empty")
        object.__setattr__(self, "length_m", _nonnegative(self.length_m, "length_m"))
        object.__setattr__(
            self, "airflow_m3_h", _positive(self.airflow_m3_h, "airflow_m3_h")
        )
        if self.friction_factor is not None:
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

        auto_inputs = (
            self.absolute_roughness_m is not None,
            self.kinematic_viscosity_m2_s is not None,
        )
        if self.friction_factor is None:
            if not all(auto_inputs):
                raise ValueError(
                    "automatic friction requires absolute_roughness_m and "
                    "kinematic_viscosity_m2_s"
                )
            object.__setattr__(
                self,
                "absolute_roughness_m",
                _nonnegative(self.absolute_roughness_m, "absolute_roughness_m"),
            )
            object.__setattr__(
                self,
                "kinematic_viscosity_m2_s",
                _positive(
                    self.kinematic_viscosity_m2_s,
                    "kinematic_viscosity_m2_s",
                ),
            )
            if self.absolute_roughness_m >= self.hydraulic_diameter_m:
                raise ValueError(
                    "absolute_roughness_m must be smaller than hydraulic diameter"
                )
        elif any(auto_inputs):
            raise ValueError(
                "provide either friction_factor or automatic-friction inputs, not both"
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

    def friction_analysis(self) -> dict:
        if self.friction_factor is not None:
            return {
                "friction_factor": self.friction_factor,
                "method": "user_input",
                "reynolds_number": None,
                "absolute_roughness_m": None,
                "relative_roughness": None,
                "kinematic_viscosity_m2_s": None,
            }

        assert self.absolute_roughness_m is not None
        assert self.kinematic_viscosity_m2_s is not None
        airflow_m3_s = self.airflow_m3_h / 3600.0
        velocity_m_s = airflow_m3_s / self.area_m2
        return resolve_darcy_friction_factor(
            velocity_m_s=velocity_m_s,
            hydraulic_diameter_m=self.hydraulic_diameter_m,
            kinematic_viscosity_m2_s=self.kinematic_viscosity_m2_s,
            absolute_roughness_m=self.absolute_roughness_m,
            circular_geometry=self.shape == "circular",
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
        "friction_factor": round(friction_factor, 6),
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
            else round(friction["relative_roughness"], 9)
        ),
        "kinematic_viscosity_m2_s": friction["kinematic_viscosity_m2_s"],
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
            "loss coefficients. Friction factor may be supplied directly or calculated "
            "from explicit roughness and kinematic viscosity at the section airflow. "
            "Airflow, density, geometry, and fitting coefficients remain project inputs. "
            "The model compares user-defined paths; it "
            "does not solve branch airflow, fan curves, system effect, leakage, acoustic "
            "performance, or control interactions."
        ),
    }
