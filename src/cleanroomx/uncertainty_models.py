from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Provenance:
    source_type: str
    source_name: str
    reference: str | None = None
    revision: str | None = None
    date: str | None = None
    uncertainty_basis: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        if not self.source_type.strip():
            raise ValueError("source_type cannot be empty")
        if not self.source_name.strip():
            raise ValueError("source_name cannot be empty")


@dataclass(frozen=True)
class UncertainValue:
    value: float
    unit: str
    uncertainty_abs: float = 0.0
    provenance: Provenance | None = None

    def __post_init__(self) -> None:
        value = float(self.value)
        uncertainty = float(self.uncertainty_abs)
        if not math.isfinite(value):
            raise ValueError("value must be finite")
        if not math.isfinite(uncertainty) or uncertainty < 0:
            raise ValueError("uncertainty_abs must be finite and >= 0")
        if not self.unit.strip():
            raise ValueError("unit cannot be empty")
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "uncertainty_abs", uncertainty)

    @property
    def lower(self) -> float:
        return self.value - self.uncertainty_abs

    @property
    def upper(self) -> float:
        return self.value + self.uncertainty_abs


@dataclass(frozen=True)
class UncertainRoom:
    name: str
    length_m: UncertainValue
    width_m: UncertainValue
    height_m: UncertainValue
    supply_airflow_m3_h: UncertainValue
    min_ach: float | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("room name cannot be empty")

        expected_units = {
            "length_m": "m",
            "width_m": "m",
            "height_m": "m",
            "supply_airflow_m3_h": "m3/h",
        }
        for field_name, expected_unit in expected_units.items():
            item = getattr(self, field_name)
            if item.unit != expected_unit:
                raise ValueError(
                    f"{field_name} unit must be {expected_unit!r}, got {item.unit!r}"
                )
            if item.lower <= 0:
                raise ValueError(
                    f"{field_name} lower uncertainty bound must remain > 0"
                )

        if self.min_ach is not None:
            minimum = float(self.min_ach)
            if not math.isfinite(minimum) or minimum <= 0:
                raise ValueError("min_ach must be finite and > 0 when provided")
            object.__setattr__(self, "min_ach", minimum)
