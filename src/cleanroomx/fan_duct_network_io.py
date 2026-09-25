from __future__ import annotations

import json
from pathlib import Path

from .input_contracts import strict_input_fields
from .fan_curve import FanCurve, FanCurvePoint
from .fan_duct_network import FanDuctNetworkStudy
from .hvac_io import duct_network_from_dict


@strict_input_fields(
    "name",
    "fan_curve",
    "duct_network",
    "reference_system_airflow_m3_h",
    "fixed_pressure_pa",
    context="fan/duct-network input",
)
def fan_duct_network_study_from_dict(data: dict) -> FanDuctNetworkStudy:
    fan_data = data["fan_curve"]
    return FanDuctNetworkStudy(
        name=data["name"],
        fan_curve=FanCurve(
            name=fan_data["name"],
            points=tuple(
                FanCurvePoint(**point)
                for point in fan_data["points"]
            ),
        ),
        duct_network=duct_network_from_dict(data["duct_network"]),
        reference_system_airflow_m3_h=data[
            "reference_system_airflow_m3_h"
        ],
        fixed_pressure_pa=data.get("fixed_pressure_pa", 0.0),
    )


def load_fan_duct_network_study(
    path: str | Path,
) -> FanDuctNetworkStudy:
    return fan_duct_network_study_from_dict(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )
