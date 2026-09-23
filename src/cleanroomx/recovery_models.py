from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RecoverySample:
    time_minutes: float
    concentration_per_m3: float

    def __post_init__(self) -> None:
        time = float(self.time_minutes)
        concentration = float(self.concentration_per_m3)
        if time < 0:
            raise ValueError("time_minutes must be >= 0")
        if concentration <= 0:
            raise ValueError("concentration_per_m3 must be > 0")
        object.__setattr__(self, "time_minutes", time)
        object.__setattr__(self, "concentration_per_m3", concentration)


@dataclass(frozen=True)
class RecoveryTestSpec:
    name: str
    target_concentration_per_m3: float
    samples: tuple[RecoverySample, ...]
    max_recovery_time_minutes: float | None = None
    design_ach: float | None = None
    removal_efficiency: float = 1.0

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("recovery-test name cannot be empty")

        target = float(self.target_concentration_per_m3)
        if target <= 0:
            raise ValueError("target_concentration_per_m3 must be > 0")
        object.__setattr__(self, "target_concentration_per_m3", target)

        if len(self.samples) < 2:
            raise ValueError("recovery test requires at least two samples")
        if self.samples[0].time_minutes != 0.0:
            raise ValueError("first recovery sample must be at time_minutes = 0")
        for previous, current in zip(self.samples, self.samples[1:]):
            if current.time_minutes <= previous.time_minutes:
                raise ValueError("recovery sample times must be strictly increasing")

        if self.max_recovery_time_minutes is not None:
            maximum = float(self.max_recovery_time_minutes)
            if maximum <= 0:
                raise ValueError("max_recovery_time_minutes must be > 0 when provided")
            object.__setattr__(self, "max_recovery_time_minutes", maximum)

        if self.design_ach is not None:
            ach = float(self.design_ach)
            if ach <= 0:
                raise ValueError("design_ach must be > 0 when provided")
            object.__setattr__(self, "design_ach", ach)

        efficiency = float(self.removal_efficiency)
        if not 0.0 < efficiency <= 1.0:
            raise ValueError("removal_efficiency must be > 0 and <= 1")
        object.__setattr__(self, "removal_efficiency", efficiency)
