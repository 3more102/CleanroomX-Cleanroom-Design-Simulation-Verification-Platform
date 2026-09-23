from __future__ import annotations

import math

from .hvac_models import AirState

MOLECULAR_MASS_RATIO_WATER_TO_DRY_AIR = 0.621945
DRY_AIR_GAS_CONSTANT_KJ_KG_K = 0.287042


def saturation_vapor_pressure_kpa(dry_bulb_c: float) -> float:
    """Approximate saturation vapor pressure over water in kPa.

    Uses e_w = 6.112 exp(17.62 t / (243.12 + t)) hPa for -45 to 60 C.
    """
    t = float(dry_bulb_c)
    if not -45.0 <= t <= 60.0:
        raise ValueError("dry_bulb_c must be between -45 and 60 C")
    return 0.6112 * math.exp((17.62 * t) / (243.12 + t))


def vapor_pressure_kpa(state: AirState) -> float:
    return (
        state.relative_humidity_percent
        / 100.0
        * saturation_vapor_pressure_kpa(state.dry_bulb_c)
    )


def humidity_ratio_kg_kg_da(state: AirState) -> float:
    p_w = vapor_pressure_kpa(state)
    if p_w >= state.pressure_kpa:
        raise ValueError("water-vapor partial pressure must be below total pressure")
    return MOLECULAR_MASS_RATIO_WATER_TO_DRY_AIR * p_w / (state.pressure_kpa - p_w)


def moist_air_enthalpy_kj_kg_da(state: AirState) -> float:
    w = humidity_ratio_kg_kg_da(state)
    t = state.dry_bulb_c
    return 1.006 * t + w * (2501.0 + 1.86 * t)


def moist_air_specific_volume_m3_kg_da(state: AirState) -> float:
    w = humidity_ratio_kg_kg_da(state)
    t_k = state.dry_bulb_c + 273.15
    return (
        DRY_AIR_GAS_CONSTANT_KJ_KG_K
        * t_k
        * (1.0 + 1.607858 * w)
        / state.pressure_kpa
    )


def moist_air_cp_kj_kg_da_k(state: AirState) -> float:
    w = humidity_ratio_kg_kg_da(state)
    return 1.006 + 1.86 * w


def dew_point_c(state: AirState) -> float:
    p_w_hpa = vapor_pressure_kpa(state) * 10.0
    alpha = math.log(p_w_hpa / 6.112)
    return 243.12 * alpha / (17.62 - alpha)


def dry_air_mass_flow_kg_s(airflow_m3_h: float, state: AirState) -> float:
    if airflow_m3_h < 0:
        raise ValueError("airflow_m3_h must be >= 0")
    return airflow_m3_h / 3600.0 / moist_air_specific_volume_m3_kg_da(state)


def air_state_result(state: AirState) -> dict:
    return {
        "dry_bulb_c": state.dry_bulb_c,
        "relative_humidity_percent": state.relative_humidity_percent,
        "pressure_kpa": state.pressure_kpa,
        "humidity_ratio_g_kg_da": round(humidity_ratio_kg_kg_da(state) * 1000.0, 4),
        "enthalpy_kj_kg_da": round(moist_air_enthalpy_kj_kg_da(state), 4),
        "specific_volume_m3_kg_da": round(
            moist_air_specific_volume_m3_kg_da(state), 6
        ),
        "dew_point_c": round(dew_point_c(state), 3),
    }
