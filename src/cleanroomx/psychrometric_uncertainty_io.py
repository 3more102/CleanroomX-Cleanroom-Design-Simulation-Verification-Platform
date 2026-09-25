from __future__ import annotations

from pathlib import Path

from .strict_json import load_strict_json

from .psychrometric_uncertainty_models import UncertainAirState
from .uncertainty_models import Provenance, UncertainValue


def _value_from_dict(data: dict, unit: str) -> UncertainValue:
    provenance_data = data.get("provenance")
    provenance = (
        Provenance(**provenance_data) if provenance_data is not None else None
    )
    return UncertainValue(
        value=data["value"],
        unit=unit,
        uncertainty_abs=data.get("uncertainty_abs", 0.0),
        provenance=provenance,
    )


def psychrometric_uncertainty_from_dict(data: dict) -> UncertainAirState:
    pressure = data.get(
        "pressure_kpa",
        {"value": 101.325, "uncertainty_abs": 0.0},
    )
    return UncertainAirState(
        name=data["name"],
        dry_bulb_c=_value_from_dict(data["dry_bulb_c"], "C"),
        relative_humidity_percent=_value_from_dict(
            data["relative_humidity_percent"],
            "%",
        ),
        pressure_kpa=_value_from_dict(pressure, "kPa"),
    )


def load_psychrometric_uncertainty(path: str | Path) -> UncertainAirState:
    data = load_strict_json(path)
    return psychrometric_uncertainty_from_dict(data)
