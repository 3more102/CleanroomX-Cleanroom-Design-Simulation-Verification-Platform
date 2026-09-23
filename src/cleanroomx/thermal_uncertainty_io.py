from __future__ import annotations

import json
from pathlib import Path

from .hvac_models import AirState
from .thermal_uncertainty_models import UncertainThermalDesign
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


def thermal_uncertainty_from_dict(data: dict) -> UncertainThermalDesign:
    outdoor = data.get("outdoor_air")
    supply_temp = data.get("supply_air_temp_c")
    return UncertainThermalDesign(
        name=data["name"],
        room_air=AirState(**data["room_air"]),
        outdoor_air=AirState(**outdoor) if outdoor is not None else None,
        cleanroom_airflow_m3_h=_value_from_dict(
            data["cleanroom_airflow_m3_h"], "m3/h"
        ),
        internal_sensible_kw=_value_from_dict(
            data["internal_sensible_kw"], "kW"
        ),
        internal_latent_kw=_value_from_dict(
            data["internal_latent_kw"], "kW"
        ),
        makeup_airflow_m3_h=_value_from_dict(
            data.get(
                "makeup_airflow_m3_h",
                {"value": 0.0, "uncertainty_abs": 0.0},
            ),
            "m3/h",
        ),
        supply_air_temp_c=(
            _value_from_dict(supply_temp, "C")
            if supply_temp is not None
            else None
        ),
        capacity_margin_percent=data.get("capacity_margin_percent", 0.0),
        available_cooling_capacity_kw=data.get(
            "available_cooling_capacity_kw"
        ),
        available_heating_capacity_kw=data.get(
            "available_heating_capacity_kw"
        ),
    )


def load_thermal_uncertainty(path: str | Path) -> UncertainThermalDesign:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return thermal_uncertainty_from_dict(data)
