from __future__ import annotations

from pathlib import Path

from .json_integrity import load_json_file

from .fan_curve import FanCurve, FanCurvePoint, FanOperatingPointStudy, SystemCurve


def fan_operating_point_study_from_dict(data: dict) -> FanOperatingPointStudy:
    fan_data = data["fan_curve"]
    system_data = data["system_curve"]
    return FanOperatingPointStudy(
        name=data["name"],
        fan_curve=FanCurve(
            name=fan_data["name"],
            points=tuple(FanCurvePoint(**point) for point in fan_data["points"]),
        ),
        system_curve=SystemCurve(
            name=system_data["name"],
            fixed_pressure_pa=system_data.get("fixed_pressure_pa", 0.0),
            resistance_pa_per_m3_s_squared=system_data[
                "resistance_pa_per_m3_s_squared"
            ],
        ),
    )


def load_fan_operating_point_study(path: str | Path) -> FanOperatingPointStudy:
    return fan_operating_point_study_from_dict(
        load_json_file(path)
    )
