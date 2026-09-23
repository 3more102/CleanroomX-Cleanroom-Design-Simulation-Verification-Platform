from __future__ import annotations

import json
from pathlib import Path

from .fan_curve import (
    FanCurvePoint,
    FanOperatingPointCase,
    FanStaticPressureCurve,
    QuadraticSystemCurve,
)


def fan_operating_point_case_from_dict(data: dict) -> FanOperatingPointCase:
    fan_data = data["fan_curve"]
    system_data = data["system_curve"]
    return FanOperatingPointCase(
        name=data["name"],
        fan_curve=FanStaticPressureCurve(
            name=fan_data["name"],
            points=tuple(FanCurvePoint(**point) for point in fan_data["points"]),
        ),
        system_curve=QuadraticSystemCurve(**system_data),
    )


def load_fan_operating_point_case(path: str | Path) -> FanOperatingPointCase:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return fan_operating_point_case_from_dict(data)
