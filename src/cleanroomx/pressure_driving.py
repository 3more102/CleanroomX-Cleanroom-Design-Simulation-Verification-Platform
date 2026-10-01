from __future__ import annotations

from dataclasses import dataclass
import math


STANDARD_GRAVITY_M_S2 = 9.80665
DRY_AIR_GAS_CONSTANT_J_KG_K = 287.05


def _finite(value: float, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a finite number")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite")
    return value


def _positive(value: float, field_name: str) -> float:
    value = _finite(value, field_name)
    if value <= 0.0:
        raise ValueError(f"{field_name} must be > 0")
    return value


def _nonnegative(value: float, field_name: str) -> float:
    value = _finite(value, field_name)
    if value < 0.0:
        raise ValueError(f"{field_name} must be >= 0")
    return value


def _finite_result(value: float, context: str) -> float:
    if not math.isfinite(value):
        raise ValueError(
            "pressure-driving calculation became non-finite: " + context
        )
    return value


def dry_air_density_kg_m3(
    absolute_pressure_pa: float,
    temperature_k: float,
    *,
    gas_constant_j_kg_k: float = DRY_AIR_GAS_CONSTANT_J_KG_K,
) -> float:
    """Return dry-air density from the ideal-gas relation rho=P/(R*T)."""
    pressure = _positive(absolute_pressure_pa, "absolute_pressure_pa")
    temperature = _positive(temperature_k, "temperature_k")
    gas_constant = _positive(gas_constant_j_kg_k, "gas_constant_j_kg_k")
    return _finite_result(
        pressure / (gas_constant * temperature),
        "dry-air density",
    )


@dataclass(frozen=True)
class WindPressureInput:
    """Explicit CONTAM-style wind-pressure inputs for one exterior path."""

    air_density_kg_m3: float
    reference_wind_speed_m_s: float
    pressure_coefficient: float
    wind_speed_modifier_coefficient: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "air_density_kg_m3",
            _positive(self.air_density_kg_m3, "wind air_density_kg_m3"),
        )
        object.__setattr__(
            self,
            "reference_wind_speed_m_s",
            _nonnegative(
                self.reference_wind_speed_m_s,
                "wind reference_wind_speed_m_s",
            ),
        )
        coefficient = _finite(
            self.pressure_coefficient,
            "wind pressure_coefficient",
        )
        if not -1.0 <= coefficient <= 1.0:
            raise ValueError(
                "wind pressure_coefficient must be in [-1, 1] "
                "for the CONTAM wall-pressure profile convention"
            )
        object.__setattr__(self, "pressure_coefficient", coefficient)
        object.__setattr__(
            self,
            "wind_speed_modifier_coefficient",
            _positive(
                self.wind_speed_modifier_coefficient,
                "wind wind_speed_modifier_coefficient",
            ),
        )

    @property
    def pressure_pa(self) -> float:
        speed_squared = _finite_result(
            self.reference_wind_speed_m_s * self.reference_wind_speed_m_s,
            "reference wind speed squared",
        )
        dynamic_pressure = _finite_result(
            0.5 * self.air_density_kg_m3 * speed_squared,
            "wind dynamic pressure",
        )
        modified = _finite_result(
            dynamic_pressure * self.wind_speed_modifier_coefficient,
            "terrain/elevation-modified wind dynamic pressure",
        )
        return _finite_result(
            modified * self.pressure_coefficient,
            "surface wind pressure",
        )


@dataclass(frozen=True)
class StackPressureInput:
    """Incompressible hydrostatic pressure terms for one airflow path."""

    start_air_density_kg_m3: float
    end_air_density_kg_m3: float
    start_height_above_node_reference_m: float
    end_height_above_node_reference_m: float
    gravity_m_s2: float = STANDARD_GRAVITY_M_S2

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "start_air_density_kg_m3",
            _positive(
                self.start_air_density_kg_m3,
                "stack start_air_density_kg_m3",
            ),
        )
        object.__setattr__(
            self,
            "end_air_density_kg_m3",
            _positive(
                self.end_air_density_kg_m3,
                "stack end_air_density_kg_m3",
            ),
        )
        object.__setattr__(
            self,
            "start_height_above_node_reference_m",
            _finite(
                self.start_height_above_node_reference_m,
                "stack start_height_above_node_reference_m",
            ),
        )
        object.__setattr__(
            self,
            "end_height_above_node_reference_m",
            _finite(
                self.end_height_above_node_reference_m,
                "stack end_height_above_node_reference_m",
            ),
        )
        object.__setattr__(
            self,
            "gravity_m_s2",
            _positive(self.gravity_m_s2, "stack gravity_m_s2"),
        )

    @property
    def pressure_difference_pa(self) -> float:
        start_hydrostatic = _finite_result(
            -self.start_air_density_kg_m3
            * self.gravity_m_s2
            * self.start_height_above_node_reference_m,
            "start-node hydrostatic pressure",
        )
        end_hydrostatic = _finite_result(
            -self.end_air_density_kg_m3
            * self.gravity_m_s2
            * self.end_height_above_node_reference_m,
            "end-node hydrostatic pressure",
        )
        return _finite_result(
            start_hydrostatic - end_hydrostatic,
            "stack pressure difference",
        )
