from __future__ import annotations

import json
from pathlib import Path

from .input_contracts import strict_input_fields
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


@strict_input_fields(
    "name",
    "length_m",
    "width_m",
    "height_m",
    "supply_airflow_m3_h",
    "min_ach",
    context="room-uncertainty input",
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
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return uncertain_room_from_dict(data)
