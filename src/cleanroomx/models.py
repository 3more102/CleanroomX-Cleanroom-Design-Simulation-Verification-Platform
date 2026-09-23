from __future__ import annotations

from dataclasses import dataclass, field
import math


@dataclass(frozen=True)
class ParticleRequirement:
    size_um: float
    max_concentration_per_m3: float
    observed_concentration_per_m3: float

    def __post_init__(self) -> None:
        if self.size_um <= 0:
            raise ValueError("particle size must be positive")
        if self.max_concentration_per_m3 < 0:
            raise ValueError("particle concentration limit cannot be negative")
        if self.observed_concentration_per_m3 < 0:
            raise ValueError("observed particle concentration cannot be negative")


@dataclass(frozen=True)
class RoomSpec:
    name: str
    length_m: float
    width_m: float
    height_m: float
    supply_airflow_m3_h: float
    min_ach: float | None = None
    min_pressure_pa: float | None = None
    observed_pressure_pa: float | None = None
    particle_requirements: tuple[ParticleRequirement, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("room name cannot be empty")
        for label, value in (
            ("length_m", self.length_m),
            ("width_m", self.width_m),
            ("height_m", self.height_m),
            ("supply_airflow_m3_h", self.supply_airflow_m3_h),
        ):
            if value <= 0:
                raise ValueError(f"{label} must be positive")
        if self.min_ach is not None and self.min_ach <= 0:
            raise ValueError("min_ach must be positive when provided")


@dataclass(frozen=True)
class ZonePressure:
    name: str
    observed_pressure_pa: float

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("zone name cannot be empty")
        if not math.isfinite(self.observed_pressure_pa):
            raise ValueError("observed_pressure_pa must be finite")


@dataclass(frozen=True)
class PressureRelationship:
    higher_zone: str
    lower_zone: str
    min_delta_pa: float

    def __post_init__(self) -> None:
        if not self.higher_zone.strip() or not self.lower_zone.strip():
            raise ValueError("pressure relationship zone names cannot be empty")
        if self.higher_zone == self.lower_zone:
            raise ValueError("pressure relationship must connect two different zones")
        if not math.isfinite(self.min_delta_pa) or self.min_delta_pa < 0:
            raise ValueError("min_delta_pa must be a finite value >= 0")


@dataclass(frozen=True)
class PressureCascadeSpec:
    name: str
    zones: tuple[ZonePressure, ...]
    relationships: tuple[PressureRelationship, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("cascade name cannot be empty")
        if len(self.zones) < 2:
            raise ValueError("pressure cascade requires at least two zones")

        zone_names = [zone.name for zone in self.zones]
        if len(set(zone_names)) != len(zone_names):
            raise ValueError("zone names must be unique")
        known = set(zone_names)

        seen_edges: set[tuple[str, str]] = set()
        for relationship in self.relationships:
            if relationship.higher_zone not in known:
                raise ValueError(f"unknown higher_zone: {relationship.higher_zone}")
            if relationship.lower_zone not in known:
                raise ValueError(f"unknown lower_zone: {relationship.lower_zone}")
            edge = (relationship.higher_zone, relationship.lower_zone)
            if edge in seen_edges:
                raise ValueError(
                    f"duplicate pressure relationship: {relationship.higher_zone} -> {relationship.lower_zone}"
                )
            seen_edges.add(edge)
