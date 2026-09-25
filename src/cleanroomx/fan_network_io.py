from __future__ import annotations

import json
from pathlib import Path

from .input_contracts import strict_input_fields
from .duct_flow import ParallelFlowPath, ParallelFlowSection
from .fan_curve import FanCurve, FanCurvePoint
from .fan_network import FanDrivenParallelNetworkStudy


@strict_input_fields(
    "name",
    "fan_curve",
    "fixed_pressure_pa",
    "paths",
    context="fan/parallel-network input",
)
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
        json.loads(Path(path).read_text(encoding="utf-8"))
    )
