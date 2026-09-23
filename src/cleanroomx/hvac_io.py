from __future__ import annotations

import json
from pathlib import Path

from .branch_network import BranchDuct, BranchFlowNetwork, TerminalDemand
from .duct import DuctNetwork, DuctPath, DuctSection
from .fan_curve import FanCurve, FanCurvePoint
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


def duct_network_from_dict(data: dict) -> DuctNetwork:
    return DuctNetwork(
        paths=tuple(
            DuctPath(
                name=path["name"],
                sections=tuple(
                    DuctSection(**section) for section in path["sections"]
                ),
            )
            for path in data["paths"]
        )
    )



def branch_flow_network_from_dict(data: dict) -> BranchFlowNetwork:
    return BranchFlowNetwork(
        source_node=data["source_node"],
        branches=tuple(BranchDuct(**branch) for branch in data["branches"]),
        terminal_demands=tuple(
            TerminalDemand(**terminal) for terminal in data["terminal_demands"]
        ),
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
    fan_curve_data = data.get("fan_curve")
    fan_curve = (
        FanCurve(
            name=fan_curve_data["name"],
            points=tuple(FanCurvePoint(**point) for point in fan_curve_data["points"]),
        )
        if fan_curve_data is not None
        else None
    )
    duct_data = data.get("duct_network")
    duct_network = (
        duct_network_from_dict(duct_data) if duct_data is not None else None
    )
    branch_flow_data = data.get("branch_flow_network")
    branch_flow_network = (
        branch_flow_network_from_dict(branch_flow_data)
        if branch_flow_data is not None
        else None
    )
    return HVACProject(
        name=data["name"],
        rooms=rooms,
        filter_unit=filter_unit,
        fan_system=fan_system,
        duct_network=duct_network,
        branch_flow_network=branch_flow_network,
        fan_curve=fan_curve,
    )


def load_hvac_project(path: str | Path) -> HVACProject:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return hvac_project_from_dict(data)
