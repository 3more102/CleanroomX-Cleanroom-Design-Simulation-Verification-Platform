from __future__ import annotations

import json
from pathlib import Path

from .fan_curve import FanCurve, FanCurvePoint, SystemCurve
from .fan_speed import FanSpeedSweepStudy


def fan_speed_sweep_study_from_dict(data: dict) -> FanSpeedSweepStudy:
    fan_data = data["reference_fan_curve"]
    system_data = data["system_curve"]
    return FanSpeedSweepStudy(
        name=data["name"],
        reference_fan_curve=FanCurve(
            name=fan_data["name"],
            points=tuple(
                FanCurvePoint(**point) for point in fan_data["points"]
            ),
        ),
        system_curve=SystemCurve(
            name=system_data["name"],
            fixed_pressure_pa=system_data.get("fixed_pressure_pa", 0.0),
            resistance_pa_per_m3_s_squared=system_data[
                "resistance_pa_per_m3_s_squared"
            ],
        ),
        speed_ratios=tuple(data["speed_ratios"]),
        reference_speed_rpm=data.get("reference_speed_rpm"),
    )


def load_fan_speed_sweep_study(path: str | Path) -> FanSpeedSweepStudy:
    return fan_speed_sweep_study_from_dict(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )
