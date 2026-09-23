from __future__ import annotations

from dataclasses import asdict

from .psychrometrics import (
    moist_air_cp_kj_kg_da_k,
    moist_air_enthalpy_kj_kg_da,
    moist_air_specific_volume_m3_kg_da,
)
from .thermal_uncertainty_models import UncertainThermalDesign
from .uncertainty_models import UncertainValue


def _interval(item: UncertainValue) -> dict:
    return {
        "nominal": round(item.value, 6),
        "lower": round(item.lower, 6),
        "upper": round(item.upper, 6),
        "unit": item.unit,
    }


def _input_record(name: str, item: UncertainValue) -> dict:
    return {
        "name": name,
        "value": item.value,
        "unit": item.unit,
        "uncertainty_abs": item.uncertainty_abs,
        "lower": item.lower,
        "upper": item.upper,
        "provenance": asdict(item.provenance) if item.provenance is not None else None,
    }


def _scaled_interval(lower: float, upper: float, factor: float) -> tuple[float, float]:
    a = lower * factor
    b = upper * factor
    return (min(a, b), max(a, b))


def _capacity_status(
    lower_required_kw: float,
    upper_required_kw: float,
    available_kw: float | None,
) -> tuple[str, str]:
    if available_kw is None:
        return "not_checked", "No available equipment capacity was configured."
    if upper_required_kw <= available_kw:
        return (
            "pass",
            "The configured available capacity covers the complete conservative requirement interval.",
        )
    if lower_required_kw > available_kw:
        return (
            "fail",
            "The complete conservative requirement interval exceeds the configured available capacity.",
        )
    return (
        "indeterminate",
        "The configured available capacity lies inside the conservative requirement interval.",
    )


def analyze_thermal_uncertainty(design: UncertainThermalDesign) -> dict:
    sensible = design.internal_sensible_kw
    latent = design.internal_latent_kw
    makeup = design.makeup_airflow_m3_h

    internal_nominal = sensible.value + latent.value
    internal_lower = sensible.lower + latent.lower
    internal_upper = sensible.upper + latent.upper

    makeup_nominal = 0.0
    makeup_lower = 0.0
    makeup_upper = 0.0
    makeup_kw_per_m3_h = 0.0

    if design.outdoor_air is not None and makeup.upper > 0:
        outdoor_h = moist_air_enthalpy_kj_kg_da(design.outdoor_air)
        room_h = moist_air_enthalpy_kj_kg_da(design.room_air)
        outdoor_specific_volume = moist_air_specific_volume_m3_kg_da(
            design.outdoor_air
        )
        makeup_kw_per_m3_h = (
            (outdoor_h - room_h) / 3600.0 / outdoor_specific_volume
        )
        makeup_nominal = makeup.value * makeup_kw_per_m3_h
        makeup_lower, makeup_upper = _scaled_interval(
            makeup.lower,
            makeup.upper,
            makeup_kw_per_m3_h,
        )

    net_nominal = internal_nominal + makeup_nominal
    net_lower = internal_lower + makeup_lower
    net_upper = internal_upper + makeup_upper

    multiplier = 1.0 + design.capacity_margin_percent / 100.0
    cooling_nominal = max(net_nominal, 0.0) * multiplier
    cooling_lower = max(net_lower, 0.0) * multiplier
    cooling_upper = max(net_upper, 0.0) * multiplier
    heating_nominal = max(-net_nominal, 0.0) * multiplier
    heating_lower = max(-net_upper, 0.0) * multiplier
    heating_upper = max(-net_lower, 0.0) * multiplier

    thermal_airflow = None
    if design.supply_air_temp_c is not None:
        cp = moist_air_cp_kj_kg_da_k(design.room_air)
        room_specific_volume = moist_air_specific_volume_m3_kg_da(design.room_air)

        def airflow_for(sensible_kw: float, supply_temp_c: float) -> float:
            if sensible_kw == 0:
                return 0.0
            delta_t = design.room_air.dry_bulb_c - supply_temp_c
            dry_air_kg_s = sensible_kw / (cp * delta_t)
            return dry_air_kg_s * room_specific_volume * 3600.0

        thermal_airflow = {
            "nominal": round(
                airflow_for(sensible.value, design.supply_air_temp_c.value), 6
            ),
            "lower": round(
                airflow_for(sensible.lower, design.supply_air_temp_c.lower), 6
            ),
            "upper": round(
                airflow_for(sensible.upper, design.supply_air_temp_c.upper), 6
            ),
            "unit": "m3/h",
        }

    airflow_candidates = [
        (
            "cleanroom_airflow",
            design.cleanroom_airflow_m3_h.value,
            design.cleanroom_airflow_m3_h.lower,
            design.cleanroom_airflow_m3_h.upper,
        ),
        (
            "makeup_air",
            makeup.value,
            makeup.lower,
            makeup.upper,
        ),
    ]
    if thermal_airflow is not None:
        airflow_candidates.append(
            (
                "internal_sensible_load",
                thermal_airflow["nominal"],
                thermal_airflow["lower"],
                thermal_airflow["upper"],
            )
        )

    nominal_basis, nominal_governing, _, _ = max(
        airflow_candidates, key=lambda item: item[1]
    )
    governing_lower = max(item[2] for item in airflow_candidates)
    governing_upper = max(item[3] for item in airflow_candidates)

    cooling_status, cooling_message = _capacity_status(
        cooling_lower,
        cooling_upper,
        design.available_cooling_capacity_kw,
    )
    heating_status, heating_message = _capacity_status(
        heating_lower,
        heating_upper,
        design.available_heating_capacity_kw,
    )
    checked_statuses = [
        status
        for status in (cooling_status, heating_status)
        if status != "not_checked"
    ]
    if "fail" in checked_statuses:
        overall_status = "fail"
    elif "indeterminate" in checked_statuses:
        overall_status = "indeterminate"
    elif checked_statuses:
        overall_status = "pass"
    else:
        overall_status = "not_checked"

    inputs = [
        _input_record("cleanroom_airflow_m3_h", design.cleanroom_airflow_m3_h),
        _input_record("internal_sensible_kw", sensible),
        _input_record("internal_latent_kw", latent),
        _input_record("makeup_airflow_m3_h", makeup),
    ]
    if design.supply_air_temp_c is not None:
        inputs.append(_input_record("supply_air_temp_c", design.supply_air_temp_c))
    missing = [item["name"] for item in inputs if item["provenance"] is None]

    return {
        "analysis": design.name,
        "method": "conservative_interval_fixed_air_states",
        "loads_kw": {
            "internal_total": {
                "nominal": round(internal_nominal, 6),
                "lower": round(internal_lower, 6),
                "upper": round(internal_upper, 6),
            },
            "makeup_air_total": {
                "nominal": round(makeup_nominal, 6),
                "lower": round(makeup_lower, 6),
                "upper": round(makeup_upper, 6),
                "kw_per_m3_h": round(makeup_kw_per_m3_h, 9),
            },
            "net_room_plus_makeup": {
                "nominal": round(net_nominal, 6),
                "lower": round(net_lower, 6),
                "upper": round(net_upper, 6),
            },
        },
        "cooling_capacity_kw": {
            "nominal": round(cooling_nominal, 6),
            "lower": round(cooling_lower, 6),
            "upper": round(cooling_upper, 6),
            "available": design.available_cooling_capacity_kw,
            "status": cooling_status,
            "message": cooling_message,
        },
        "heating_capacity_kw": {
            "nominal": round(heating_nominal, 6),
            "lower": round(heating_lower, 6),
            "upper": round(heating_upper, 6),
            "available": design.available_heating_capacity_kw,
            "status": heating_status,
            "message": heating_message,
        },
        "airflow_m3_h": {
            "cleanroom": _interval(design.cleanroom_airflow_m3_h),
            "makeup": _interval(makeup),
            "thermal_for_internal_sensible": thermal_airflow,
            "governing": {
                "nominal": round(nominal_governing, 6),
                "lower": round(governing_lower, 6),
                "upper": round(governing_upper, 6),
                "nominal_basis": nominal_basis,
                "unit": "m3/h",
            },
        },
        "capacity_margin_percent": design.capacity_margin_percent,
        "overall_status": overall_status,
        "traceability": {
            "input_count": len(inputs),
            "inputs_with_provenance": len(inputs) - len(missing),
            "complete": not missing,
            "missing_provenance": missing,
            "inputs": inputs,
        },
        "engineering_note": (
            "Deterministic bounds are propagated for explicit sensible/latent loads, "
            "cleanroom airflow, makeup airflow, and optional supply-air temperature. "
            "Room and outdoor psychrometric states are held fixed in this workflow. "
            "This is conservative engineering screening, not a statistical uncertainty "
            "budget, weather/load simulation, or equipment selection procedure."
        ),
    }
