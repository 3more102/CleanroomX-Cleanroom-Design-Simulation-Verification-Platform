from __future__ import annotations

from pathlib import Path

from .json_integrity import load_json_file

from .fan_curve import FanCurve, FanCurvePoint
from .fan_loop_uncertainty_models import FanLoopNetworkUncertaintyStudy
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
    loop_network = looped_flow_network_from_dict(data["loop_network"])
    edges_by_name = {edge.name: edge for edge in loop_network.edges}

    edge_uncertainty: dict[str, UncertainValue] = {}
    for edge_name, spec in data.get("edge_resistance_uncertainty", {}).items():
        if edge_name not in edges_by_name:
            raise ValueError(
                "edge resistance uncertainty references unknown edge "
                f"{edge_name!r}"
            )
        if isinstance(spec, (int, float)):
            uncertainty_abs = float(spec)
            provenance = None
        elif isinstance(spec, dict):
            if "value" in spec:
                raise ValueError(
                    "edge_resistance_uncertainty must not repeat the nominal "
                    "resistance; the loop-network edge is the nominal source"
                )
            uncertainty_abs = spec.get("uncertainty_abs", 0.0)
            provenance = _provenance_from_dict(spec.get("provenance"))
        else:
            raise ValueError(
                f"edge resistance uncertainty for {edge_name!r} must be "
                "a number or object"
            )

        edge_uncertainty[edge_name] = UncertainValue(
            value=edges_by_name[
                edge_name
            ].resistance_pa_per_m3_s_squared,
            unit="Pa/(m3/s)^2",
            uncertainty_abs=uncertainty_abs,
            provenance=provenance,
        )

    return FanLoopNetworkUncertaintyStudy(
        name=data["name"],
        fan_curve=FanCurve(
            name=fan_data["name"],
            points=tuple(
                FanCurvePoint(**point) for point in fan_data["points"]
            ),
        ),
        loop_network=loop_network,
        fan_discharge_node=data["fan_discharge_node"],
        fan_suction_node=data["fan_suction_node"],
        fixed_pressure_pa=_uncertain_value(
            data.get("fixed_pressure_pa", 0.0),
            "Pa",
        ),
        edge_resistance_pa_per_m3_s_squared=edge_uncertainty,
        fan_curve_provenance=_provenance_from_dict(
            fan_data.get("provenance")
        ),
        max_corner_cases=data.get("max_corner_cases", 256),
    )


def load_fan_loop_network_uncertainty(
    path: str | Path,
) -> FanLoopNetworkUncertaintyStudy:
    return fan_loop_network_uncertainty_from_dict(
        load_json_file(path)
    )
