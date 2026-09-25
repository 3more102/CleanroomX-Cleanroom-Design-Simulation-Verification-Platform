from __future__ import annotations

from pathlib import Path

from .strict_json import load_strict_json

from .fan_curve import FanCurve, FanCurvePoint
from .fan_duct_network import FanDuctNetworkStudy
from .hvac_io import duct_network_from_dict


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
        load_strict_json(path)
    )
