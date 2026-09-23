from __future__ import annotations

from dataclasses import asdict

from .hvac_models import AirState
from .psychrometrics import (
    dew_point_c,
    humidity_ratio_kg_kg_da,
    moist_air_cp_kj_kg_da_k,
    moist_air_enthalpy_kj_kg_da,
    moist_air_specific_volume_m3_kg_da,
)
from .psychrometric_uncertainty_models import UncertainAirState
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
        "provenance": (
            asdict(item.provenance) if item.provenance is not None else None
        ),
    }


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
            "The configured available capacity covers the complete conservative "
            "requirement interval.",
        )
    if lower_required_kw > available_kw:
        return (
            "fail",
            "The complete conservative requirement interval exceeds the configured "
            "available capacity.",
        )
    return (
        "indeterminate",
        "The configured available capacity lies inside the conservative requirement "
        "interval.",
    )


def _nominal_state(state: AirState | UncertainAirState) -> AirState:
    return state.nominal_state if isinstance(state, UncertainAirState) else state


def _corner_states(
    state: AirState | UncertainAirState,
) -> tuple[AirState, ...]:
    return (
        state.corner_states()
        if isinstance(state, UncertainAirState)
        else (state,)
    )


def _derived_interval(
    nominal: float,
    values: list[float],
    unit: str,
) -> dict:
    return {
        "nominal": round(nominal, 6),
        "lower": round(min(values), 6),
        "upper": round(max(values), 6),
        "unit": unit,
    }


def _psychrometric_state_result(
    state: AirState | UncertainAirState,
) -> dict:
    nominal_state = _nominal_state(state)
    corners = _corner_states(state)
    metrics = {
        "humidity_ratio_g_kg_da": (
            lambda item: humidity_ratio_kg_kg_da(item) * 1000.0,
            "g/kg dry air",
        ),
        "enthalpy_kj_kg_da": (
            moist_air_enthalpy_kj_kg_da,
            "kJ/kg dry air",
        ),
        "specific_volume_m3_kg_da": (
            moist_air_specific_volume_m3_kg_da,
            "m3/kg dry air",
        ),
        "dew_point_c": (dew_point_c, "C"),
    }

    derived = {}
    for name, (function, unit) in metrics.items():
        values = [function(item) for item in corners]
        derived[name] = _derived_interval(
            function(nominal_state),
            values,
            unit,
        )

    if isinstance(state, UncertainAirState):
        inputs = {
            "dry_bulb_c": _interval(state.dry_bulb_c),
            "relative_humidity_percent": _interval(
                state.relative_humidity_percent
            ),
            "pressure_kpa": _interval(state.pressure_kpa),
        }
    else:
        inputs = {
            "dry_bulb_c": {
                "nominal": state.dry_bulb_c,
                "lower": state.dry_bulb_c,
                "upper": state.dry_bulb_c,
                "unit": "C",
            },
            "relative_humidity_percent": {
                "nominal": state.relative_humidity_percent,
                "lower": state.relative_humidity_percent,
                "upper": state.relative_humidity_percent,
                "unit": "%",
            },
            "pressure_kpa": {
                "nominal": state.pressure_kpa,
                "lower": state.pressure_kpa,
                "upper": state.pressure_kpa,
                "unit": "kPa",
            },
        }

    return {
        "inputs": inputs,
        "derived": derived,
        "corner_count": len(corners),
    }


def _state_traceability(
    prefix: str,
    state: AirState | UncertainAirState | None,
) -> list[dict]:
    if not isinstance(state, UncertainAirState):
        return []

    records = []
    for name, item in (
        ("dry_bulb_c", state.dry_bulb_c),
        ("relative_humidity_percent", state.relative_humidity_percent),
        ("pressure_kpa", state.pressure_kpa),
    ):
        if item.uncertainty_abs > 0 or item.provenance is not None:
            records.append(_input_record(f"{prefix}.{name}", item))
    return records


def _makeup_load_values(
    design: UncertainThermalDesign,
) -> tuple[float, float, float]:
    makeup = design.makeup_airflow_m3_h
    if design.outdoor_air is None or makeup.upper <= 0:
        return 0.0, 0.0, 0.0

    def load(
        flow_m3_h: float,
        room: AirState,
        outdoor: AirState,
    ) -> float:
        dry_air_kg_s = (
            flow_m3_h
            / 3600.0
            / moist_air_specific_volume_m3_kg_da(outdoor)
        )
        return dry_air_kg_s * (
            moist_air_enthalpy_kj_kg_da(outdoor)
            - moist_air_enthalpy_kj_kg_da(room)
        )

    nominal = load(
        makeup.value,
        _nominal_state(design.room_air),
        _nominal_state(design.outdoor_air),
    )
    values = [
        load(flow, room, outdoor)
        for flow in {makeup.lower, makeup.upper}
        for room in _corner_states(design.room_air)
        for outdoor in _corner_states(design.outdoor_air)
    ]
    return nominal, min(values), max(values)


def _thermal_airflow_interval(
    design: UncertainThermalDesign,
) -> dict | None:
    if design.supply_air_temp_c is None:
        return None

    sensible = design.internal_sensible_kw
    supply = design.supply_air_temp_c

    def airflow(
        sensible_kw: float,
        supply_temp_c: float,
        room: AirState,
    ) -> float:
        if sensible_kw == 0:
            return 0.0
        delta_t = room.dry_bulb_c - supply_temp_c
        if delta_t <= 0:
            raise ValueError(
                "supply-air temperature must remain below room dry-bulb "
                "temperature for positive sensible load"
            )
        dry_air_kg_s = sensible_kw / (
            moist_air_cp_kj_kg_da_k(room) * delta_t
        )
        return (
            dry_air_kg_s
            * moist_air_specific_volume_m3_kg_da(room)
            * 3600.0
        )

    nominal = airflow(
        sensible.value,
        supply.value,
        _nominal_state(design.room_air),
    )
    values = [
        airflow(load, temperature, room)
        for load in {sensible.lower, sensible.upper}
        for temperature in {supply.lower, supply.upper}
        for room in _corner_states(design.room_air)
    ]
    return {
        "nominal": round(nominal, 6),
        "lower": round(min(values), 6),
        "upper": round(max(values), 6),
        "unit": "m3/h",
    }


def analyze_thermal_uncertainty(
    design: UncertainThermalDesign,
) -> dict:
    sensible = design.internal_sensible_kw
    latent = design.internal_latent_kw
    makeup = design.makeup_airflow_m3_h

    internal_nominal = sensible.value + latent.value
    internal_lower = sensible.lower + latent.lower
    internal_upper = sensible.upper + latent.upper

    (
        makeup_nominal,
        makeup_lower,
        makeup_upper,
    ) = _makeup_load_values(design)
    makeup_kw_per_m3_h = (
        makeup_nominal / makeup.value if makeup.value else 0.0
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

    thermal_airflow = _thermal_airflow_interval(design)

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
        airflow_candidates,
        key=lambda item: item[1],
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
        _input_record(
            "cleanroom_airflow_m3_h",
            design.cleanroom_airflow_m3_h,
        ),
        _input_record("internal_sensible_kw", sensible),
        _input_record("internal_latent_kw", latent),
        _input_record("makeup_airflow_m3_h", makeup),
    ]
    if design.supply_air_temp_c is not None:
        inputs.append(
            _input_record(
                "supply_air_temp_c",
                design.supply_air_temp_c,
            )
        )
    inputs.extend(_state_traceability("room_air", design.room_air))
    inputs.extend(_state_traceability("outdoor_air", design.outdoor_air))
    missing = [
        item["name"]
        for item in inputs
        if item["provenance"] is None
    ]

    return {
        "analysis": design.name,
        "method": "conservative_interval_corner_enumeration",
        "psychrometric_states": {
            "room_air": _psychrometric_state_result(design.room_air),
            "outdoor_air": (
                _psychrometric_state_result(design.outdoor_air)
                if design.outdoor_air is not None
                else None
            ),
        },
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
                "kw_per_m3_h_at_nominal_states": round(
                    makeup_kw_per_m3_h,
                    9,
                ),
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
            "Deterministic bounds are propagated for explicit loads, airflow, "
            "optional supply-air temperature, and configured room/outdoor dry-bulb "
            "temperature, relative humidity, and pressure. Psychrometric and "
            "dependent load/airflow bounds are obtained by complete endpoint-corner "
            "enumeration of the supplied intervals. This is conservative engineering "
            "screening, not a statistical uncertainty budget, correlated-variable "
            "model, hourly weather/load simulation, or equipment selection procedure."
        ),
    }
