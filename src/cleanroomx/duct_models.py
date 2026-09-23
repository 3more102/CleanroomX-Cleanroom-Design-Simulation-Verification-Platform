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


def _efficiency(value: float, field_name: str) -> float:
    value = float(value)
    if not 0 < value <= 1:
        raise ValueError(f"{field_name} must be > 0 and <= 1")
    return value


@dataclass(frozen=True)
class DuctSection:
    name: str
    length_m: float
    cross_section_area_m2: float
    hydraulic_diameter_m: float
    airflow_m3_h: float
    friction_factor: float
    local_loss_coefficient: float = 0.0

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("duct-section name cannot be empty")
        for field_name in (
            "length_m",
            "cross_section_area_m2",
            "hydraulic_diameter_m",
            "airflow_m3_h",
        ):
            object.__setattr__(
                self, field_name, _positive(getattr(self, field_name), field_name)
            )
        object.__setattr__(
            self,
            "friction_factor",
            _nonnegative(self.friction_factor, "friction_factor"),
        )
        object.__setattr__(
            self,
            "local_loss_coefficient",
            _nonnegative(self.local_loss_coefficient, "local_loss_coefficient"),
        )


@dataclass(frozen=True)
class DuctPath:
    name: str
    sections: tuple[DuctSection, ...]
    fixed_pressure_drop_pa: float = 0.0

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("duct-path name cannot be empty")
        if not self.sections:
            raise ValueError("duct path must contain at least one section")
        names = [section.name for section in self.sections]
        if len(names) != len(set(names)):
            raise ValueError("duct-section names must be unique within a path")
        object.__setattr__(
            self,
            "fixed_pressure_drop_pa",
            _nonnegative(self.fixed_pressure_drop_pa, "fixed_pressure_drop_pa"),
        )


@dataclass(frozen=True)
class DuctNetwork:
    name: str
    air_density_kg_m3: float
    fan_airflow_m3_h: float
    fan_efficiency: float
    motor_efficiency: float
    paths: tuple[DuctPath, ...]
    coil_pressure_drop_pa: float = 0.0
    terminal_filter_pressure_drop_pa: float = 0.0
    other_system_pressure_drop_pa: float = 0.0
    static_margin_pa: float = 0.0

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("duct-network name cannot be empty")
        if not self.paths:
            raise ValueError("duct network must contain at least one path")
        names = [path.name for path in self.paths]
        if len(names) != len(set(names)):
            raise ValueError("duct-path names must be unique")
        object.__setattr__(
            self,
            "air_density_kg_m3",
            _positive(self.air_density_kg_m3, "air_density_kg_m3"),
        )
        object.__setattr__(
            self,
            "fan_airflow_m3_h",
            _positive(self.fan_airflow_m3_h, "fan_airflow_m3_h"),
        )
        object.__setattr__(
            self, "fan_efficiency", _efficiency(self.fan_efficiency, "fan_efficiency")
        )
        object.__setattr__(
            self,
            "motor_efficiency",
            _efficiency(self.motor_efficiency, "motor_efficiency"),
        )
        for field_name in (
            "coil_pressure_drop_pa",
            "terminal_filter_pressure_drop_pa",
            "other_system_pressure_drop_pa",
            "static_margin_pa",
        ):
            object.__setattr__(
                self, field_name, _nonnegative(getattr(self, field_name), field_name)
            )
