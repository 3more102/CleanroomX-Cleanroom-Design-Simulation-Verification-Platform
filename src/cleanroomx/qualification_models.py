from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

from .uncertainty_models import UncertainValue

RequirementKind = Literal["minimum", "maximum"]


@dataclass(frozen=True)
class QualificationRequirement:
    kind: RequirementKind
    limit: float
    unit: str
    reference: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in ("minimum", "maximum"):
            raise ValueError("requirement kind must be 'minimum' or 'maximum'")
        limit = float(self.limit)
        if not math.isfinite(limit):
            raise ValueError("requirement limit must be finite")
        if not self.unit.strip():
            raise ValueError("requirement unit cannot be empty")
        if self.reference is not None and not self.reference.strip():
            raise ValueError("requirement reference cannot be empty when provided")
        object.__setattr__(self, "limit", limit)


@dataclass(frozen=True)
class MeasurementCheck:
    name: str
    observed: UncertainValue
    requirement: QualificationRequirement

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("measurement-check name cannot be empty")
        if self.observed.unit != self.requirement.unit:
            raise ValueError(
                f"measurement unit {self.observed.unit!r} does not match "
                f"requirement unit {self.requirement.unit!r}"
            )


@dataclass(frozen=True)
class PressureCascadeCheck:
    name: str
    higher_pressure: UncertainValue
    lower_pressure: UncertainValue
    min_delta_pa: float
    requirement_reference: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("pressure-cascade check name cannot be empty")
        if self.higher_pressure.unit != "Pa" or self.lower_pressure.unit != "Pa":
            raise ValueError("pressure-cascade inputs must use 'Pa'")
        minimum = float(self.min_delta_pa)
        if not math.isfinite(minimum) or minimum <= 0:
            raise ValueError("min_delta_pa must be finite and > 0")
        if self.requirement_reference is not None and not self.requirement_reference.strip():
            raise ValueError("requirement_reference cannot be empty when provided")
        object.__setattr__(self, "min_delta_pa", minimum)


@dataclass(frozen=True)
class QualificationUncertaintySpec:
    name: str
    measurements: tuple[MeasurementCheck, ...] = field(default_factory=tuple)
    pressure_cascades: tuple[PressureCascadeCheck, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("qualification analysis name cannot be empty")
        if not self.measurements and not self.pressure_cascades:
            raise ValueError("qualification analysis requires at least one check")
