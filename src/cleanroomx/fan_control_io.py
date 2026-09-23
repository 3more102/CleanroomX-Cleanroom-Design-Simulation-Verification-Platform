from __future__ import annotations

import json
from pathlib import Path

from .fan_control import FanControlState, FanControlStudy
from .fan_curve import FanCurve, FanCurvePoint, SystemCurve


def fan_control_study_from_dict(data: dict) -> FanControlStudy:
    system_data = data["system_curve"]
    states = []
    for state_data in data["states"]:
        fan_data = state_data["fan_curve"]
        states.append(
            FanControlState(
                name=state_data["name"],
                control_signal_percent=state_data["control_signal_percent"],
                fan_curve=FanCurve(
                    name=fan_data["name"],
                    points=tuple(
                        FanCurvePoint(**point)
                        for point in fan_data["points"]
                    ),
                ),
            )
        )

    return FanControlStudy(
        name=data["name"],
        system_curve=SystemCurve(
            name=system_data["name"],
            fixed_pressure_pa=system_data.get("fixed_pressure_pa", 0.0),
            resistance_pa_per_m3_s_squared=system_data[
                "resistance_pa_per_m3_s_squared"
            ],
        ),
        states=tuple(states),
        target_airflow_m3_h=data.get("target_airflow_m3_h"),
        target_tolerance_m3_h=data.get("target_tolerance_m3_h", 0.0),
    )


def load_fan_control_study(path: str | Path) -> FanControlStudy:
    return fan_control_study_from_dict(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )
