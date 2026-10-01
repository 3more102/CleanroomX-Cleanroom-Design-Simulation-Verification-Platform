from __future__ import annotations

import math

from .hvac_models import AirState
from .numeric import finite_float, nonnegative_float

MOLECULAR_MASS_RATIO_WATER_TO_DRY_AIR = 0.621945
DRY_AIR_GAS_CONSTANT_KJ_KG_K = 0.287042


def _saturation_vapor_pressure_iapws_kpa(temperature_c: float) -> float:
    """Return saturation pressure in kPa using the ASHRAE/IAPWS phase model."""
    temperature_k = temperature_c + 273.15

    if temperature_c < 0.0:
        # IAPWS R14-08(2011), ice-Ih sublimation curve as reproduced by
        # ASHRAE Handbook—Fundamentals 2025, Chapter 1.
        theta = temperature_k / 273.16
        coefficients = (-21.2144006, 27.3203819, -6.10598130)
        exponents = (0.00333333333, 1.20666667, 1.70333333)
        ln_pressure_ratio = sum(
            coefficient * (theta**exponent - 1.0)
            for coefficient, exponent in zip(coefficients, exponents)
        ) / theta
        return 0.611657 * math.exp(ln_pressure_ratio)

    # IAPWS-IF97 Region 4 saturation-pressure equation, as reproduced by
    # ASHRAE Handbook—Fundamentals 2025, Chapter 1.
    n1 = 0.11670521452767e4
    n2 = -0.72421316703206e6
    n3 = -0.17073846940092e2
    n4 = 0.12020824702470e5
    n5 = -0.32325550322333e7
    n6 = 0.14915108613530e2
    n7 = -0.48232657361591e4
    n8 = 0.40511340542057e6
    n9 = -0.23855557567849
    n10 = 0.65017534844798e3

    theta = temperature_k + n9 / (temperature_k - n10)
    a = theta**2 + n1 * theta + n2
    b = n3 * theta**2 + n4 * theta + n5
    c = n6 * theta**2 + n7 * theta + n8
    discriminant = b**2 - 4.0 * a * c
    if discriminant <= 0.0:
        raise ValueError("IAPWS saturation-pressure equation left its valid domain")
    pressure_mpa = (
        2.0 * c / (-b + math.sqrt(discriminant))
    ) ** 4
    return pressure_mpa * 1000.0


def saturation_vapor_pressure_kpa(dry_bulb_c: float) -> float:
    """Return phase-aware saturation vapor pressure in kPa.

    CleanroomX supports AirState dry-bulb temperatures from -45 to 60 C.
    Below 0 C the IAPWS ice-Ih sublimation correlation is used; at and above
    0 C the IAPWS-IF97 Region 4 liquid-water saturation correlation is used.
    """
    t = finite_float(dry_bulb_c, "dry_bulb_c")
    if not -45.0 <= t <= 60.0:
        raise ValueError("dry_bulb_c must be between -45 and 60 C")
    return _saturation_vapor_pressure_iapws_kpa(t)


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
    """Solve dew point from the same phase-aware saturation model."""
    target_pressure_kpa = vapor_pressure_kpa(state)
    lower_c = -100.0
    upper_c = state.dry_bulb_c

    if target_pressure_kpa < _saturation_vapor_pressure_iapws_kpa(lower_c):
        raise ValueError(
            "dew point is below -100 C, outside the supported IAPWS inversion range"
        )

    # Relative humidity is constrained to <= 100%, so dew point cannot exceed
    # dry-bulb temperature under this model. Bisection is deterministic and
    # avoids mixing a separate dew-point approximation with the saturation model.
    for _ in range(100):
        midpoint_c = 0.5 * (lower_c + upper_c)
        midpoint_pressure_kpa = _saturation_vapor_pressure_iapws_kpa(midpoint_c)
        if midpoint_pressure_kpa < target_pressure_kpa:
            lower_c = midpoint_c
        else:
            upper_c = midpoint_c

    return 0.5 * (lower_c + upper_c)


def dry_air_mass_flow_kg_s(airflow_m3_h: float, state: AirState) -> float:
    airflow_m3_h = nonnegative_float(airflow_m3_h, "airflow_m3_h")
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
