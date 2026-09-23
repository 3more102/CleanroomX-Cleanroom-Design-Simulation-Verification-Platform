from __future__ import annotations

import math
from dataclasses import dataclass


def _efficiency(value: float | None, field_name: str) -> float | None:
    if value is None:
        return None
    value = float(value)
    if not math.isfinite(value) or value <= 0.0 or value > 1.0:
        raise ValueError(f"{field_name} must be finite and in (0, 1]")
    return value


def _nonnegative(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{field_name} must be finite and >= 0")
    return value


@dataclass(frozen=True)
class FanPowerEfficiencies:
    """Optional explicit efficiency chain for fan power evidence.

    No default efficiencies are supplied. Fan efficiency alone permits shaft
    power. Electrical input and specific fan power require explicit fan,
    motor, and VFD efficiencies.
    """

    fan_efficiency: float | None = None
    motor_efficiency: float | None = None
    vfd_efficiency: float | None = None

    def __post_init__(self) -> None:
        fan = _efficiency(self.fan_efficiency, "fan_efficiency")
        motor = _efficiency(self.motor_efficiency, "motor_efficiency")
        vfd = _efficiency(self.vfd_efficiency, "vfd_efficiency")
        if fan is None and (motor is not None or vfd is not None):
            raise ValueError(
                "fan_efficiency is required when motor or VFD efficiency is supplied"
            )
        if vfd is not None and motor is None:
            raise ValueError(
                "motor_efficiency is required when vfd_efficiency is supplied"
            )
        object.__setattr__(self, "fan_efficiency", fan)
        object.__setattr__(self, "motor_efficiency", motor)
        object.__setattr__(self, "vfd_efficiency", vfd)

    def to_dict(self) -> dict:
        return {
            "fan_efficiency": self.fan_efficiency,
            "motor_efficiency": self.motor_efficiency,
            "vfd_efficiency": self.vfd_efficiency,
        }


def fan_power_efficiencies_from_dict(
    data: dict | None,
) -> FanPowerEfficiencies | None:
    if data is None:
        return None
    if not isinstance(data, dict):
        raise ValueError("power_efficiencies must be an object when provided")
    allowed = {"fan_efficiency", "motor_efficiency", "vfd_efficiency"}
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(
            "unsupported power efficiency option(s): "
            + ", ".join(sorted(unknown))
        )
    return FanPowerEfficiencies(**data)


def analyze_fan_pressure_power(
    airflow_m3_h: float,
    pressure_pa: float,
    efficiencies: FanPowerEfficiencies | None = None,
) -> dict:
    airflow = _nonnegative(airflow_m3_h, "airflow_m3_h")
    pressure = _nonnegative(pressure_pa, "pressure_pa")
    airflow_m3_s = airflow / 3600.0
    fluid_power_w = airflow_m3_s * pressure

    fan_efficiency = (
        None if efficiencies is None else efficiencies.fan_efficiency
    )
    motor_efficiency = (
        None if efficiencies is None else efficiencies.motor_efficiency
    )
    vfd_efficiency = (
        None if efficiencies is None else efficiencies.vfd_efficiency
    )

    shaft_power_w = (
        fluid_power_w / fan_efficiency
        if fan_efficiency is not None
        else None
    )
    electrical_input_w = (
        shaft_power_w / motor_efficiency / vfd_efficiency
        if (
            shaft_power_w is not None
            and motor_efficiency is not None
            and vfd_efficiency is not None
        )
        else None
    )
    specific_fan_power_w_per_m3_s = (
        electrical_input_w / airflow_m3_s
        if electrical_input_w is not None and airflow_m3_s > 0.0
        else None
    )

    return {
        "airflow_m3_h": round(airflow, 6),
        "airflow_m3_s": round(airflow_m3_s, 12),
        "pressure_pa": round(pressure, 9),
        "fluid_air_power_w": round(fluid_power_w, 9),
        "fluid_air_power_kw": round(fluid_power_w / 1000.0, 9),
        "efficiencies": (
            None if efficiencies is None else efficiencies.to_dict()
        ),
        "shaft_power_kw": (
            None if shaft_power_w is None else round(shaft_power_w / 1000.0, 9)
        ),
        "electrical_input_kw": (
            None
            if electrical_input_w is None
            else round(electrical_input_w / 1000.0, 9)
        ),
        "specific_fan_power_w_per_m3_s": (
            None
            if specific_fan_power_w_per_m3_s is None
            else round(specific_fan_power_w_per_m3_s, 9)
        ),
        "scope_note": (
            "Fluid air power is Q*deltaP. Shaft power is reported only when "
            "explicit fan efficiency is supplied. Electrical input and "
            "specific fan power are reported only when explicit fan, motor, "
            "and VFD efficiencies are all supplied. No efficiency is inferred."
        ),
    }
