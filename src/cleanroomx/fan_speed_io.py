from __future__ import annotations

from pathlib import Path

from .jsonio import load_strict_json

from .fan_curve import FanCurve, FanCurvePoint, SystemCurve
from .fan_speed import FanSpeedStudy


def fan_speed_study_from_dict(data: dict) -> FanSpeedStudy:
    fan_data = data["reference_fan_curve"]
    system_data = data["system_curve"]
    return FanSpeedStudy(
        name=data["name"],
        reference_fan_curve=FanCurve(
            name=fan_data["name"],
            points=tuple(
                FanCurvePoint(**point)
                for point in fan_data["points"]
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


def load_fan_speed_study(path: str | Path) -> FanSpeedStudy:
    return fan_speed_study_from_dict(
        load_strict_json(path)
    )
