from __future__ import annotations

import json
from pathlib import Path

from .hvac_models import ThermalLoads
from .thermal_uncertainty import ThermalUncertaintyCase
from .uncertainty_models import Provenance, UncertainValue


def _uncertain_value(data: dict | float | int, unit: str) -> UncertainValue:
    if isinstance(data, (int, float)):
        return UncertainValue(float(data), unit)

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


def thermal_uncertainty_case_from_dict(data: dict) -> ThermalUncertaintyCase:
    thermal = data["thermal_design"]
    room = thermal["room_air"]
    outdoor = thermal.get("outdoor_air")
    supply = thermal.get("supply_air_temp_c")

    return ThermalUncertaintyCase(
        name=data["name"],
        cleanroom_airflow_m3_h=_uncertain_value(
            data["cleanroom_airflow_m3_h"],
            "m3/h",
        ),
        room_dry_bulb_c=_uncertain_value(room["dry_bulb_c"], "degC"),
        room_relative_humidity_percent=_uncertain_value(
            room["relative_humidity_percent"],
            "%RH",
        ),
        room_pressure_kpa=_uncertain_value(
            room.get("pressure_kpa", 101.325),
            "kPa",
        ),
        makeup_air_m3_h=_uncertain_value(
            thermal.get("makeup_air_m3_h", 0.0),
            "m3/h",
        ),
        outdoor_dry_bulb_c=(
            _uncertain_value(outdoor["dry_bulb_c"], "degC")
            if outdoor is not None
            else None
        ),
        outdoor_relative_humidity_percent=(
            _uncertain_value(outdoor["relative_humidity_percent"], "%RH")
            if outdoor is not None
            else None
        ),
        outdoor_pressure_kpa=(
            _uncertain_value(outdoor.get("pressure_kpa", 101.325), "kPa")
            if outdoor is not None
            else None
        ),
        supply_air_temp_c=(
            _uncertain_value(supply, "degC") if supply is not None else None
        ),
        loads=ThermalLoads(**thermal.get("loads", {})),
        capacity_margin_percent=thermal.get("capacity_margin_percent", 0.0),
    )


def load_thermal_uncertainty_case(path: str | Path) -> ThermalUncertaintyCase:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return thermal_uncertainty_case_from_dict(data)
