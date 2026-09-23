from __future__ import annotations

import json
from pathlib import Path

from .fan_curve import FanCurve, FanCurvePoint
from .fan_variable_friction_uncertainty import (
    FanVariableFrictionLoopUncertaintyStudy,
)
from .loop_network_io import looped_flow_network_from_dict
from .pressure_power import fan_power_efficiencies_from_dict
from .uncertainty_models import Provenance, UncertainValue


_SOLVER_KEYS = {
    "resistance_relative_tolerance",
    "relaxation",
    "near_zero_airflow_m3_h",
    "max_outer_iterations",
    "mass_balance_tolerance_m3_h",
    "max_newton_iterations",
    "operating_pressure_tolerance_pa",
    "max_operating_iterations",
}


def _provenance_from_dict(data: dict | None) -> Provenance | None:
    return None if data is None else Provenance(**data)


def _uncertain_value(
    data: float | int | dict,
    unit: str,
) -> UncertainValue:
    if isinstance(data, (int, float)):
        return UncertainValue(float(data), unit)
    if not isinstance(data, dict):
        raise ValueError("uncertain value must be a number or object")
    return UncertainValue(
        value=data["value"],
        unit=unit,
        uncertainty_abs=data.get("uncertainty_abs", 0.0),
        provenance=_provenance_from_dict(data.get("provenance")),
    )


def fan_variable_friction_loop_uncertainty_from_dict(
    data: dict,
) -> FanVariableFrictionLoopUncertaintyStudy:
    fan_data = data["fan_curve"]
    loop_network = looped_flow_network_from_dict(data["loop_network"])
    edges_by_name = {edge.name: edge for edge in loop_network.edges}

    edge_uncertainty: dict[str, UncertainValue] = {}
    for edge_name, spec in data.get(
        "edge_local_loss_uncertainty", {}
    ).items():
        edge = edges_by_name.get(edge_name)
        if edge is None:
            raise ValueError(
                "edge local-loss uncertainty references unknown edge "
                f"{edge_name!r}"
            )
        evidence = edge.resistance_evidence
        if evidence is None or "local_loss_coefficient" not in evidence:
            raise ValueError(
                f"edge {edge_name!r} has no local-loss geometry evidence"
            )
        if isinstance(spec, (int, float)):
            uncertainty_abs = float(spec)
            provenance = None
        elif isinstance(spec, dict):
            if "value" in spec:
                raise ValueError(
                    "edge_local_loss_uncertainty must not repeat the nominal "
                    "local-loss coefficient; the loop-network geometry is "
                    "the nominal source"
                )
            uncertainty_abs = spec.get("uncertainty_abs", 0.0)
            provenance = _provenance_from_dict(spec.get("provenance"))
        else:
            raise ValueError(
                f"edge local-loss uncertainty for {edge_name!r} must be "
                "a number or object"
            )
        edge_uncertainty[edge_name] = UncertainValue(
            value=evidence["local_loss_coefficient"],
            unit="1",
            uncertainty_abs=uncertainty_abs,
            provenance=provenance,
        )

    solver = data.get("solver", {})
    if not isinstance(solver, dict):
        raise ValueError("solver must be an object when provided")
    unknown = set(solver) - _SOLVER_KEYS
    if unknown:
        raise ValueError(
            "unsupported fan/variable-friction uncertainty solver option(s): "
            + ", ".join(sorted(unknown))
        )

    return FanVariableFrictionLoopUncertaintyStudy(
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
        edge_local_loss_coefficient=edge_uncertainty,
        fan_curve_provenance=_provenance_from_dict(
            fan_data.get("provenance")
        ),
        max_corner_cases=data.get("max_corner_cases", 256),
        power_efficiencies=fan_power_efficiencies_from_dict(
            data.get("power_efficiencies")
        ),
        **solver,
    )


def load_fan_variable_friction_loop_uncertainty(
    path: str | Path,
) -> FanVariableFrictionLoopUncertaintyStudy:
    return fan_variable_friction_loop_uncertainty_from_dict(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )
