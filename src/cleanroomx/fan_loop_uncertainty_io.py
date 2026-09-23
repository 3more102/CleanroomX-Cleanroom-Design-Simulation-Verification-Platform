from __future__ import annotations

import json
from pathlib import Path

from .fan_curve import FanCurve, FanCurvePoint
from .fan_loop_network import FanLoopNetworkStudy
from .fan_loop_uncertainty_models import FanLoopNetworkUncertaintyStudy
from .loop_network_io import looped_flow_network_from_dict
from .uncertainty_models import Provenance, UncertainValue


_RESISTANCE_UNIT = "Pa/(m3/s)^2"


def _provenance_from_dict(data: dict | None) -> Provenance | None:
    return None if data is None else Provenance(**data)


def _uncertain_value(data: float | int | dict, unit: str) -> UncertainValue:
    if isinstance(data, (int, float)):
        return UncertainValue(float(data), unit)
    return UncertainValue(
        value=data["value"],
        unit=unit,
        uncertainty_abs=data.get("uncertainty_abs", 0.0),
        provenance=_provenance_from_dict(data.get("provenance")),
    )


def _edge_uncertainty_value(
    nominal: float,
    data: float | int | dict | None,
) -> UncertainValue:
    if data is None:
        return UncertainValue(nominal, _RESISTANCE_UNIT)
    if isinstance(data, (int, float)):
        return UncertainValue(
            nominal,
            _RESISTANCE_UNIT,
            uncertainty_abs=float(data),
        )
    unsupported = set(data) - {"uncertainty_abs", "provenance"}
    if unsupported:
        raise ValueError(
            "unsupported edge-resistance uncertainty field(s): "
            + ", ".join(sorted(unsupported))
        )
    return UncertainValue(
        nominal,
        _RESISTANCE_UNIT,
        uncertainty_abs=data.get("uncertainty_abs", 0.0),
        provenance=_provenance_from_dict(data.get("provenance")),
    )


def fan_loop_network_uncertainty_from_dict(
    data: dict,
) -> FanLoopNetworkUncertaintyStudy:
    fan_data = data["fan_curve"]
    fan_curve = FanCurve(
        name=fan_data["name"],
        points=tuple(FanCurvePoint(**point) for point in fan_data["points"]),
    )
    loop_network = looped_flow_network_from_dict(data["loop_network"])
    fixed_pressure = _uncertain_value(
        data.get("fixed_pressure_pa", 0.0),
        "Pa",
    )

    uncertainty_specs = data.get("edge_resistance_uncertainty", {})
    if not isinstance(uncertainty_specs, dict):
        raise ValueError("edge_resistance_uncertainty must be an object")
    edge_names = {edge.name for edge in loop_network.edges}
    unknown = sorted(set(uncertainty_specs) - edge_names)
    if unknown:
        raise ValueError(
            "edge_resistance_uncertainty references unknown edge(s): "
            + ", ".join(unknown)
        )

    edge_resistances = {
        edge.name: _edge_uncertainty_value(
            edge.resistance_pa_per_m3_s_squared,
            uncertainty_specs.get(edge.name),
        )
        for edge in loop_network.edges
    }

    base_study = FanLoopNetworkStudy(
        name=data["name"],
        fan_curve=fan_curve,
        loop_network=loop_network,
        fan_discharge_node=data["fan_discharge_node"],
        fan_suction_node=data["fan_suction_node"],
        fixed_pressure_pa=fixed_pressure.value,
    )
    return FanLoopNetworkUncertaintyStudy(
        name=data["name"],
        fan_loop_study=base_study,
        fixed_pressure_pa=fixed_pressure,
        edge_resistances=edge_resistances,
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
