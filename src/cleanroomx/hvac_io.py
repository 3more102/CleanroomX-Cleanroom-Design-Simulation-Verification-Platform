from __future__ import annotations

import json
from pathlib import Path

from .hvac_models import (
    AirBalanceDesign,
    AirState,
    FanSystem,
    FilterUnit,
    HVACProject,
    HVACRoom,
    ThermalDesign,
    ThermalLoads,
)


def thermal_design_from_dict(data: dict) -> ThermalDesign:
    outdoor = data.get("outdoor_air")
    return ThermalDesign(
        room_air=AirState(**data["room_air"]),
        outdoor_air=AirState(**outdoor) if outdoor is not None else None,
        makeup_air_m3_h=data.get("makeup_air_m3_h", 0.0),
        supply_air_temp_c=data.get("supply_air_temp_c"),
        capacity_margin_percent=data.get("capacity_margin_percent", 0.0),
        loads=ThermalLoads(**data.get("loads", {})),
    )


def hvac_project_from_dict(data: dict) -> HVACProject:
    rooms = tuple(
        HVACRoom(
            name=item["name"],
            cleanroom_airflow_m3_h=item["cleanroom_airflow_m3_h"],
            thermal_design=thermal_design_from_dict(item["thermal_design"]),
            air_balance=AirBalanceDesign(**item.get("air_balance", {})),
        )
        for item in data["rooms"]
    )
    filter_data = data.get("filter_unit")
    filter_unit = FilterUnit(**filter_data) if filter_data is not None else None
    fan_data = data.get("fan_system")
    fan_system = FanSystem(**fan_data) if fan_data is not None else None
    return HVACProject(
        name=data["name"],
        rooms=rooms,
        filter_unit=filter_unit,
        fan_system=fan_system,
    )


def load_hvac_project(path: str | Path) -> HVACProject:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return hvac_project_from_dict(data)
