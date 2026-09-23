from __future__ import annotations

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
class DuctSection:
    name: str
    length_m: float
    hydraulic_diameter_m: float
    cross_section_area_m2: float
    airflow_m3_h: float
    darcy_friction_factor: float
    minor_loss_coefficient: float = 0.0
    additional_pressure_drop_pa: float = 0.0
    air_density_kg_m3: float = 1.2

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("duct-section name cannot be empty")
        for field_name in (
            "length_m",
            "hydraulic_diameter_m",
            "cross_section_area_m2",
            "airflow_m3_h",
            "darcy_friction_factor",
            "air_density_kg_m3",
        ):
            object.__setattr__(
                self,
                field_name,
                _positive(getattr(self, field_name), field_name),
            )
        for field_name in (
            "minor_loss_coefficient",
            "additional_pressure_drop_pa",
        ):
            object.__setattr__(
                self,
                field_name,
                _nonnegative(getattr(self, field_name), field_name),
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
    name: str
    paths: tuple[DuctPath, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("duct-network name cannot be empty")
        if not self.paths:
            raise ValueError("duct network must contain at least one path")
        names = [path.name for path in self.paths]
        if len(names) != len(set(names)):
            raise ValueError("duct-path names must be unique")
