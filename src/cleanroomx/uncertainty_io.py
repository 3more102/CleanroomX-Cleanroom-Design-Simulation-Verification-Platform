from __future__ import annotations

from pathlib import Path

from .jsonio import load_strict_json

from .uncertainty_models import Provenance, UncertainRoom, UncertainValue


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


def uncertain_room_from_dict(data: dict) -> UncertainRoom:
    return UncertainRoom(
        name=data["name"],
        length_m=_value_from_dict(data["length_m"], "m"),
        width_m=_value_from_dict(data["width_m"], "m"),
        height_m=_value_from_dict(data["height_m"], "m"),
        supply_airflow_m3_h=_value_from_dict(
            data["supply_airflow_m3_h"], "m3/h"
        ),
        min_ach=data.get("min_ach"),
    )


def load_uncertain_room(path: str | Path) -> UncertainRoom:
    data = load_strict_json(path)
    return uncertain_room_from_dict(data)
