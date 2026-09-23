from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RecoverySample:
    time_minutes: float
    concentration_per_m3: float
    uncertainty_abs_per_m3: float | None = None
    uncertainty_percent: float | None = None

    def __post_init__(self) -> None:
        time = float(self.time_minutes)
        concentration = float(self.concentration_per_m3)
        absolute = (
            None
            if self.uncertainty_abs_per_m3 is None
            else float(self.uncertainty_abs_per_m3)
        )
        percent = (
            None if self.uncertainty_percent is None else float(self.uncertainty_percent)
        )
        if time < 0:
            raise ValueError("time_minutes must be >= 0")
        if concentration < 0:
            raise ValueError("concentration_per_m3 must be >= 0")
        if absolute is not None and percent is not None:
            raise ValueError(
                "provide either uncertainty_abs_per_m3 or uncertainty_percent, not both"
            )
        if absolute is not None and absolute < 0:
            raise ValueError("uncertainty_abs_per_m3 must be >= 0")
        if percent is not None and percent < 0:
            raise ValueError("uncertainty_percent must be >= 0")
        object.__setattr__(self, "time_minutes", time)
        object.__setattr__(self, "concentration_per_m3", concentration)
        object.__setattr__(self, "uncertainty_abs_per_m3", absolute)
        object.__setattr__(self, "uncertainty_percent", percent)


@dataclass(frozen=True)
class RecoveryTestSpec:
    name: str
    particle_size_um: float
    target_concentration_per_m3: float
    samples: tuple[RecoverySample, ...]
    max_recovery_time_minutes: float | None = None
    instrument_id: str | None = None
    instrument_serial_number: str | None = None
    calibration_certificate_id: str | None = None
    calibration_date: str | None = None
    calibration_due_date: str | None = None
    sample_location: str | None = None
    occupancy_state: str | None = None
    method_reference: str | None = None
    data_source: str | None = None
    analyst: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("recovery-test name cannot be empty")

        particle_size = float(self.particle_size_um)
        target = float(self.target_concentration_per_m3)
        if particle_size <= 0:
            raise ValueError("particle_size_um must be > 0")
        if target <= 0:
            raise ValueError("target_concentration_per_m3 must be > 0")
        if len(self.samples) < 2:
            raise ValueError("recovery test requires at least two samples")

        previous_time: float | None = None
        for sample in self.samples:
            if previous_time is not None and sample.time_minutes <= previous_time:
                raise ValueError("recovery sample times must be strictly increasing")
            previous_time = sample.time_minutes

        max_time = self.max_recovery_time_minutes
        if max_time is not None:
            max_time = float(max_time)
            if max_time <= 0:
                raise ValueError("max_recovery_time_minutes must be > 0 when provided")

        object.__setattr__(self, "particle_size_um", particle_size)
        object.__setattr__(self, "target_concentration_per_m3", target)
        object.__setattr__(self, "max_recovery_time_minutes", max_time)
