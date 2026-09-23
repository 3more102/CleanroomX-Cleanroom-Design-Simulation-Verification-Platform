from __future__ import annotations

import json
from pathlib import Path

from .fan_variable_friction_speed_uncertainty import (
    FanVariableFrictionSpeedUncertaintyStudy,
)
from .fan_variable_friction_uncertainty_io import (
    fan_variable_friction_loop_uncertainty_from_dict,
)


_SPEED_ONLY_KEYS = {
    "speed_ratios",
    "reference_speed_rpm",
    "max_total_cases",
}


def fan_variable_friction_speed_uncertainty_from_dict(
    data: dict,
) -> FanVariableFrictionSpeedUncertaintyStudy:
    if "reference_fan_curve" not in data:
        raise ValueError("reference_fan_curve is required")

    base_data = dict(data)
    base_data["fan_curve"] = base_data.pop("reference_fan_curve")
    for key in _SPEED_ONLY_KEYS:
        base_data.pop(key, None)

    base_study = fan_variable_friction_loop_uncertainty_from_dict(
        base_data
    )
    return FanVariableFrictionSpeedUncertaintyStudy(
        name=data["name"],
        base_uncertainty_study=base_study,
        speed_ratios=tuple(data["speed_ratios"]),
        reference_speed_rpm=data.get("reference_speed_rpm"),
        max_total_cases=data.get("max_total_cases", 1024),
    )


def load_fan_variable_friction_speed_uncertainty(
    path: str | Path,
) -> FanVariableFrictionSpeedUncertaintyStudy:
    return fan_variable_friction_speed_uncertainty_from_dict(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )
