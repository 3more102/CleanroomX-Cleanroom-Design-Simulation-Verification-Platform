from __future__ import annotations

from dataclasses import dataclass, field


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
class PressureZone:
    name: str
    observed_pressure_pa: float

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("pressure zone name cannot be empty")


@dataclass(frozen=True)
class PressureRequirement:
    high_zone: str
    low_zone: str
    min_delta_pa: float

    def __post_init__(self) -> None:
        if not self.high_zone.strip() or not self.low_zone.strip():
            raise ValueError("pressure requirement zone names cannot be empty")
        if self.high_zone == self.low_zone:
            raise ValueError("pressure requirement zones must be different")
        if self.min_delta_pa <= 0:
            raise ValueError("min_delta_pa must be positive")


@dataclass(frozen=True)
class PressureCascadeSpec:
    name: str
    zones: tuple[PressureZone, ...]
    requirements: tuple[PressureRequirement, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("pressure cascade name cannot be empty")
        if len(self.zones) < 2:
            raise ValueError("pressure cascade requires at least two zones")
        if not self.requirements:
            raise ValueError("pressure cascade requires at least one pressure requirement")

        zone_names = [zone.name for zone in self.zones]
        if len(zone_names) != len(set(zone_names)):
            raise ValueError("pressure zone names must be unique")

        known = set(zone_names)
        seen_edges: set[tuple[str, str]] = set()
        for requirement in self.requirements:
            if requirement.high_zone not in known or requirement.low_zone not in known:
                raise ValueError(
                    f"pressure requirement references unknown zone: "
                    f"{requirement.high_zone} -> {requirement.low_zone}"
                )
            edge = (requirement.high_zone, requirement.low_zone)
            if edge in seen_edges:
                raise ValueError(f"duplicate pressure requirement: {edge[0]} -> {edge[1]}")
            seen_edges.add(edge)
