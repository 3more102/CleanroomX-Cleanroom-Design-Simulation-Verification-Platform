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
