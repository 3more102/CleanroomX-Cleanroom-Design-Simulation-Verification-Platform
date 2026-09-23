from __future__ import annotations

import json
from pathlib import Path

from .fan_curve import FanCurve, FanCurvePoint
from .fan_loop_uncertainty_models import (
    EdgeResistanceUncertainty,
    FanLoopNetworkUncertaintyStudy,
)
from .loop_network_io import looped_flow_network_from_dict
from .uncertainty_models import Provenance, UncertainValue


def _provenance_from_dict(data: dict | None) -> Provenance | None:
    return None if data is None else Provenance(**data)


def _uncertain_value(
    data: float | int | dict,
    unit: str,
) -> UncertainValue:
    if isinstance(data, (int, float)):
        return UncertainValue(float(data), unit)
    return UncertainValue(
        value=data["value"],
        unit=unit,
        uncertainty_abs=data.get("uncertainty_abs", 0.0),
        provenance=_provenance_from_dict(data.get("provenance")),
    )


def fan_loop_network_uncertainty_from_dict(
    data: dict,
) -> FanLoopNetworkUncertaintyStudy:
    fan_data = data["fan_curve"]
    edge_uncertainty = data.get(
        "edge_resistance_uncertainty",
        {},
    )
    return FanLoopNetworkUncertaintyStudy(
        name=data["name"],
        fan_curve=FanCurve(
            name=fan_data["name"],
            points=tuple(
                FanCurvePoint(**point)
                for point in fan_data["points"]
            ),
        ),
        loop_network=looped_flow_network_from_dict(
            data["loop_network"]
        ),
        fan_discharge_node=data["fan_discharge_node"],
        fan_suction_node=data["fan_suction_node"],
        fixed_pressure_pa=_uncertain_value(
            data.get("fixed_pressure_pa", 0.0),
            "Pa",
        ),
        edge_resistance_uncertainties=tuple(
            EdgeResistanceUncertainty(
                edge_name=edge_name,
                uncertainty_abs=(
                    float(value)
                    if isinstance(value, (int, float))
                    else float(value.get("uncertainty_abs", 0.0))
                ),
                provenance=(
                    None
                    if isinstance(value, (int, float))
                    else _provenance_from_dict(
                        value.get("provenance")
                    )
                ),
            )
            for edge_name, value in edge_uncertainty.items()
        ),
        fan_curve_provenance=_provenance_from_dict(
            fan_data.get("provenance")
        ),
        max_corner_cases=data.get("max_corner_cases", 256),
    )


def load_fan_loop_network_uncertainty(
    path: str | Path,
) -> FanLoopNetworkUncertaintyStudy:
    return fan_loop_network_uncertainty_from_dict(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )
