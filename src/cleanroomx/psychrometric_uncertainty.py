from __future__ import annotations

from dataclasses import asdict
from typing import Callable

from .hvac_models import AirState
from .psychrometric_uncertainty_models import UncertainAirState
from .psychrometrics import (
    dew_point_c,
    humidity_ratio_kg_kg_da,
    moist_air_cp_kj_kg_da_k,
    moist_air_enthalpy_kj_kg_da,
    moist_air_specific_volume_m3_kg_da,
    vapor_pressure_kpa,
)
from .uncertainty_models import UncertainValue


def _input_interval(item: UncertainValue) -> dict:
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


def _metric_interval(
    nominal_state: AirState,
    corner_states: tuple[AirState, ...],
    evaluator: Callable[[AirState], float],
    unit: str,
    scale: float = 1.0,
) -> dict:
    nominal = evaluator(nominal_state) * scale
    corners = [evaluator(state) * scale for state in corner_states]
    return {
        "nominal": round(nominal, 6),
        "lower": round(min(corners), 6),
        "upper": round(max(corners), 6),
        "unit": unit,
    }


def analyze_psychrometric_uncertainty(design: UncertainAirState) -> dict:
    nominal_state = design.nominal_state
    corner_states = design.corner_states()

    inputs = [
        _input_record("dry_bulb_c", design.dry_bulb_c),
        _input_record(
            "relative_humidity_percent",
            design.relative_humidity_percent,
        ),
        _input_record("pressure_kpa", design.pressure_kpa),
    ]
    missing = [item["name"] for item in inputs if item["provenance"] is None]

    return {
        "analysis": design.name,
        "method": "deterministic_rectangular_interval_corner_envelope",
        "corner_count": len(corner_states),
        "input_state": {
            "dry_bulb_c": _input_interval(design.dry_bulb_c),
            "relative_humidity_percent": _input_interval(
                design.relative_humidity_percent
            ),
            "pressure_kpa": _input_interval(design.pressure_kpa),
        },
        "psychrometric_properties": {
            "vapor_pressure_kpa": _metric_interval(
                nominal_state,
                corner_states,
                vapor_pressure_kpa,
                "kPa",
            ),
            "humidity_ratio_g_kg_da": _metric_interval(
                nominal_state,
                corner_states,
                humidity_ratio_kg_kg_da,
                "g/kg dry air",
                scale=1000.0,
            ),
            "enthalpy_kj_kg_da": _metric_interval(
                nominal_state,
                corner_states,
                moist_air_enthalpy_kj_kg_da,
                "kJ/kg dry air",
            ),
            "specific_volume_m3_kg_da": _metric_interval(
                nominal_state,
                corner_states,
                moist_air_specific_volume_m3_kg_da,
                "m3/kg dry air",
            ),
            "dew_point_c": _metric_interval(
                nominal_state,
                corner_states,
                dew_point_c,
                "C",
            ),
            "cp_kj_kg_da_k": _metric_interval(
                nominal_state,
                corner_states,
                moist_air_cp_kj_kg_da_k,
                "kJ/(kg dry air K)",
            ),
        },
        "traceability": {
            "input_count": len(inputs),
            "inputs_with_provenance": len(inputs) - len(missing),
            "complete": not missing,
            "missing_provenance": missing,
            "inputs": inputs,
        },
        "engineering_note": (
            "The reported envelopes come from all unique corners of the user-supplied "
            "dry-bulb, relative-humidity, and pressure uncertainty box using the existing "
            "CleanroomX psychrometric equations. No probability distribution, covariance, "
            "sensor accuracy, calibration allowance, or acceptance limit is invented. "
            "This is deterministic screening, not a statistical measurement-uncertainty "
            "budget or psychrometric equipment-selection procedure."
        ),
    }
