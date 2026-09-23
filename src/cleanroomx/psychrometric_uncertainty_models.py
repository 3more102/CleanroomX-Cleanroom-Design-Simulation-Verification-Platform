from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product

from .hvac_models import AirState
from .psychrometrics import saturation_vapor_pressure_kpa
from .uncertainty_models import UncertainValue


def _expect_unit(item: UncertainValue, expected: str, field_name: str) -> None:
    if item.unit != expected:
        raise ValueError(
            f"{field_name} unit must be {expected!r}, got {item.unit!r}"
        )


@dataclass(frozen=True)
class UncertainAirState:
    name: str
    dry_bulb_c: UncertainValue
    relative_humidity_percent: UncertainValue
    pressure_kpa: UncertainValue = field(
        default_factory=lambda: UncertainValue(101.325, "kPa")
    )

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("air-state uncertainty analysis name cannot be empty")

        _expect_unit(self.dry_bulb_c, "C", "dry_bulb_c")
        _expect_unit(
            self.relative_humidity_percent,
            "%",
            "relative_humidity_percent",
        )
        _expect_unit(self.pressure_kpa, "kPa", "pressure_kpa")

        if self.dry_bulb_c.lower < -45.0 or self.dry_bulb_c.upper > 60.0:
            raise ValueError(
                "dry_bulb_c uncertainty interval must remain within -45 to 60 C"
            )
        if (
            self.relative_humidity_percent.lower <= 0.0
            or self.relative_humidity_percent.upper > 100.0
        ):
            raise ValueError(
                "relative_humidity_percent uncertainty interval must remain > 0 and <= 100"
            )
        if self.pressure_kpa.lower <= 0.0:
            raise ValueError("pressure_kpa lower uncertainty bound must remain > 0")

        highest_vapor_pressure = (
            self.relative_humidity_percent.upper
            / 100.0
            * saturation_vapor_pressure_kpa(self.dry_bulb_c.upper)
        )
        if highest_vapor_pressure >= self.pressure_kpa.lower:
            raise ValueError(
                "uncertainty box permits water-vapor partial pressure at or above total pressure"
            )

    @property
    def nominal_state(self) -> AirState:
        return AirState(
            dry_bulb_c=self.dry_bulb_c.value,
            relative_humidity_percent=self.relative_humidity_percent.value,
            pressure_kpa=self.pressure_kpa.value,
        )

    def corner_states(self) -> tuple[AirState, ...]:
        states = []
        seen: set[tuple[float, float, float]] = set()
        for temperature, rh, pressure in product(
            (self.dry_bulb_c.lower, self.dry_bulb_c.upper),
            (
                self.relative_humidity_percent.lower,
                self.relative_humidity_percent.upper,
            ),
            (self.pressure_kpa.lower, self.pressure_kpa.upper),
        ):
            key = (temperature, rh, pressure)
            if key in seen:
                continue
            seen.add(key)
            states.append(
                AirState(
                    dry_bulb_c=temperature,
                    relative_humidity_percent=rh,
                    pressure_kpa=pressure,
                )
            )
        return tuple(states)
