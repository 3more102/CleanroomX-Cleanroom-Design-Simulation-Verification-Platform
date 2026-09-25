from __future__ import annotations

from pathlib import Path

from .jsonio import load_strict_json

from .fan_curve import FanCurve, FanCurvePoint
from .fan_loop_speed import FanLoopSpeedStudy
from .loop_network_io import looped_flow_network_from_dict


def fan_loop_speed_study_from_dict(data: dict) -> FanLoopSpeedStudy:
    fan_data = data["reference_fan_curve"]
    return FanLoopSpeedStudy(
        name=data["name"],
        reference_fan_curve=FanCurve(
            name=fan_data["name"],
            points=tuple(FanCurvePoint(**point) for point in fan_data["points"]),
        ),
        loop_network=looped_flow_network_from_dict(data["loop_network"]),
        fan_discharge_node=data["fan_discharge_node"],
        fan_suction_node=data["fan_suction_node"],
        speed_ratios=tuple(data["speed_ratios"]),
        fixed_pressure_pa=data.get("fixed_pressure_pa", 0.0),
        reference_speed_rpm=data.get("reference_speed_rpm"),
    )


def load_fan_loop_speed_study(path: str | Path) -> FanLoopSpeedStudy:
    return fan_loop_speed_study_from_dict(
        load_strict_json(path)
    )
