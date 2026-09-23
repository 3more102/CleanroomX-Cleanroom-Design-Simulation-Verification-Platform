from __future__ import annotations

import math
from dataclasses import dataclass

from .uncertainty_models import Provenance


@dataclass(frozen=True)
class UncertainRecoverySample:
    time_minutes: float
    concentration_per_m3: float
    concentration_uncertainty_abs: float = 0.0
    provenance: Provenance | None = None

    def __post_init__(self) -> None:
        time = float(self.time_minutes)
        concentration = float(self.concentration_per_m3)
        uncertainty = float(self.concentration_uncertainty_abs)
        if not math.isfinite(time) or time < 0:
            raise ValueError("time_minutes must be finite and >= 0")
        if not math.isfinite(concentration) or concentration < 0:
            raise ValueError("concentration_per_m3 must be finite and >= 0")
        if not math.isfinite(uncertainty) or uncertainty < 0:
            raise ValueError(
                "concentration_uncertainty_abs must be finite and >= 0"
            )
        object.__setattr__(self, "time_minutes", time)
        object.__setattr__(self, "concentration_per_m3", concentration)
        object.__setattr__(self, "concentration_uncertainty_abs", uncertainty)

    @property
    def lower_concentration_per_m3(self) -> float:
        return max(
            0.0,
            self.concentration_per_m3 - self.concentration_uncertainty_abs,
        )

    @property
    def upper_concentration_per_m3(self) -> float:
        return self.concentration_per_m3 + self.concentration_uncertainty_abs


@dataclass(frozen=True)
class RecoveryUncertaintySpec:
    name: str
    particle_size_um: float
    target_concentration_per_m3: float
    samples: tuple[UncertainRecoverySample, ...]
    max_recovery_time_minutes: float | None = None
    instrument_id: str | None = None
    sample_location: str | None = None
    occupancy_state: str | None = None
    method_reference: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("recovery analysis name cannot be empty")

        particle_size = float(self.particle_size_um)
        target = float(self.target_concentration_per_m3)
        if not math.isfinite(particle_size) or particle_size <= 0:
            raise ValueError("particle_size_um must be finite and > 0")
        if not math.isfinite(target) or target <= 0:
            raise ValueError(
                "target_concentration_per_m3 must be finite and > 0"
            )
        if len(self.samples) < 2:
            raise ValueError(
                "recovery analysis requires at least two samples"
            )

        previous: float | None = None
        for sample in self.samples:
            if previous is not None and sample.time_minutes <= previous:
                raise ValueError(
                    "recovery sample times must be strictly increasing"
                )
            previous = sample.time_minutes

        maximum = self.max_recovery_time_minutes
        if maximum is not None:
            maximum = float(maximum)
            if not math.isfinite(maximum) or maximum <= 0:
                raise ValueError(
                    "max_recovery_time_minutes must be finite and > 0"
                )

        object.__setattr__(self, "particle_size_um", particle_size)
        object.__setattr__(
            self, "target_concentration_per_m3", target
        )
        object.__setattr__(
            self, "max_recovery_time_minutes", maximum
        )
