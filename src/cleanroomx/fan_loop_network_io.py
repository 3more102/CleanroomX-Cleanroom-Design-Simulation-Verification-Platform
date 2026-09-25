from __future__ import annotations

from pathlib import Path

from .json_integrity import load_json_file

from .fan_curve import FanCurve, FanCurvePoint
from .fan_loop_network import FanLoopNetworkStudy
from .loop_network_io import looped_flow_network_from_dict


def fan_loop_network_study_from_dict(data: dict) -> FanLoopNetworkStudy:
    fan_data = data["fan_curve"]
    return FanLoopNetworkStudy(
        name=data["name"],
        fan_curve=FanCurve(
            name=fan_data["name"],
            points=tuple(FanCurvePoint(**point) for point in fan_data["points"]),
        ),
        loop_network=looped_flow_network_from_dict(data["loop_network"]),
        fan_discharge_node=data["fan_discharge_node"],
        fan_suction_node=data["fan_suction_node"],
        fixed_pressure_pa=data.get("fixed_pressure_pa", 0.0),
    )


def load_fan_loop_network_study(path: str | Path) -> FanLoopNetworkStudy:
    return fan_loop_network_study_from_dict(
        load_json_file(path)
    )
