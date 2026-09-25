from __future__ import annotations

from pathlib import Path

from .json_integrity import load_json_file

from .duct_flow import ParallelFlowPath, ParallelFlowSection
from .fan_curve import FanCurve, FanCurvePoint
from .fan_network import FanDrivenParallelNetworkStudy


def fan_driven_parallel_network_study_from_dict(
    data: dict,
) -> FanDrivenParallelNetworkStudy:
    fan_data = data["fan_curve"]
    return FanDrivenParallelNetworkStudy(
        name=data["name"],
        fan_curve=FanCurve(
            name=fan_data["name"],
            points=tuple(FanCurvePoint(**point) for point in fan_data["points"]),
        ),
        fixed_pressure_pa=data.get("fixed_pressure_pa", 0.0),
        paths=tuple(
            ParallelFlowPath(
                name=path["name"],
                sections=tuple(
                    ParallelFlowSection(**section) for section in path["sections"]
                ),
            )
            for path in data["paths"]
        ),
    )


def load_fan_driven_parallel_network_study(
    path: str | Path,
) -> FanDrivenParallelNetworkStudy:
    return fan_driven_parallel_network_study_from_dict(
        load_json_file(path)
    )
