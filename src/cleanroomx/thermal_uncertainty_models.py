from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import product

from .hvac_models import AirState
from .uncertainty_models import UncertainValue


def _optional_positive(value: float | None, field_name: str) -> float | None:
    if value is None:
        return None
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{field_name} must be finite and > 0 when provided")
    return value


def _nonnegative(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{field_name} must be finite and >= 0")
    return value


def _expect_unit(item: UncertainValue, expected: str, field_name: str) -> None:
    if item.unit != expected:
        raise ValueError(
            f"{field_name} unit must be {expected!r}, got {item.unit!r}"
        )


def _bounds(item: UncertainValue) -> tuple[float, ...]:
    if item.lower == item.upper:
        return (item.lower,)
    return (item.lower, item.upper)


@dataclass(frozen=True)
class UncertainAirState:
    dry_bulb_c: UncertainValue
    relative_humidity_percent: UncertainValue
    pressure_kpa: UncertainValue = field(
        default_factory=lambda: UncertainValue(101.325, "kPa")
    )

    def __post_init__(self) -> None:
        _expect_unit(self.dry_bulb_c, "C", "dry_bulb_c")
        _expect_unit(
            self.relative_humidity_percent,
            "%",
            "relative_humidity_percent",
        )
        _expect_unit(self.pressure_kpa, "kPa", "pressure_kpa")

        if self.dry_bulb_c.lower < -45.0 or self.dry_bulb_c.upper > 60.0:
            raise ValueError(
                "dry_bulb_c uncertainty interval must remain between -45 and 60 C"
            )
        if (
            self.relative_humidity_percent.lower <= 0.0
            or self.relative_humidity_percent.upper > 100.0
        ):
            raise ValueError(
                "relative_humidity_percent uncertainty interval must remain > 0 and <= 100"
            )
        if self.pressure_kpa.lower <= 0.0:
            raise ValueError(
                "pressure_kpa lower uncertainty bound must remain > 0"
            )

    @property
    def nominal_state(self) -> AirState:
        return AirState(
            self.dry_bulb_c.value,
            self.relative_humidity_percent.value,
            self.pressure_kpa.value,
        )

    @property
    def dry_bulb_lower_c(self) -> float:
        return self.dry_bulb_c.lower

    def corner_states(self) -> tuple[AirState, ...]:
        return tuple(
            AirState(t, rh, pressure)
            for t, rh, pressure in product(
                _bounds(self.dry_bulb_c),
                _bounds(self.relative_humidity_percent),
                _bounds(self.pressure_kpa),
            )
        )


AirStateInput = AirState | UncertainAirState


@dataclass(frozen=True)
class UncertainThermalDesign:
    name: str
    room_air: AirStateInput
    cleanroom_airflow_m3_h: UncertainValue
    internal_sensible_kw: UncertainValue
    internal_latent_kw: UncertainValue
    outdoor_air: AirStateInput | None = None
    makeup_airflow_m3_h: UncertainValue = field(
        default_factory=lambda: UncertainValue(0.0, "m3/h")
    )
    supply_air_temp_c: UncertainValue | None = None
    capacity_margin_percent: float = 0.0
    available_cooling_capacity_kw: float | None = None
    available_heating_capacity_kw: float | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("thermal uncertainty analysis name cannot be empty")

        _expect_unit(
            self.cleanroom_airflow_m3_h,
            "m3/h",
            "cleanroom_airflow_m3_h",
        )
        _expect_unit(self.internal_sensible_kw, "kW", "internal_sensible_kw")
        _expect_unit(self.internal_latent_kw, "kW", "internal_latent_kw")
        _expect_unit(
            self.makeup_airflow_m3_h,
            "m3/h",
            "makeup_airflow_m3_h",
        )

        if self.cleanroom_airflow_m3_h.lower <= 0:
            raise ValueError(
                "cleanroom_airflow_m3_h lower uncertainty bound must remain > 0"
            )
        if self.internal_sensible_kw.lower < 0:
            raise ValueError(
                "internal_sensible_kw lower uncertainty bound must remain >= 0"
            )
        if self.internal_latent_kw.lower < 0:
            raise ValueError(
                "internal_latent_kw lower uncertainty bound must remain >= 0"
            )
        if self.makeup_airflow_m3_h.lower < 0:
            raise ValueError(
                "makeup_airflow_m3_h lower uncertainty bound must remain >= 0"
            )
        if self.makeup_airflow_m3_h.upper > 0 and self.outdoor_air is None:
            raise ValueError(
                "outdoor_air is required when makeup_airflow_m3_h can be > 0"
            )

        if self.supply_air_temp_c is not None:
            _expect_unit(self.supply_air_temp_c, "C", "supply_air_temp_c")
            room_lower = (
                self.room_air.dry_bulb_lower_c
                if isinstance(self.room_air, UncertainAirState)
                else self.room_air.dry_bulb_c
            )
            if (
                self.internal_sensible_kw.upper > 0
                and self.supply_air_temp_c.upper >= room_lower
            ):
                raise ValueError(
                    "supply_air_temp_c upper uncertainty bound must remain below the "
                    "lowest room dry-bulb temperature when sensible load can be positive"
                )

        object.__setattr__(
            self,
            "capacity_margin_percent",
            _nonnegative(self.capacity_margin_percent, "capacity_margin_percent"),
        )
        object.__setattr__(
            self,
            "available_cooling_capacity_kw",
            _optional_positive(
                self.available_cooling_capacity_kw,
                "available_cooling_capacity_kw",
            ),
        )
        object.__setattr__(
            self,
            "available_heating_capacity_kw",
            _optional_positive(
                self.available_heating_capacity_kw,
                "available_heating_capacity_kw",
            ),
        )
