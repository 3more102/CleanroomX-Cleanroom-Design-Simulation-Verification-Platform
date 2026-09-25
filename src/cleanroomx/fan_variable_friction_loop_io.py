from __future__ import annotations

import json
from pathlib import Path

from .fan_curve import FanCurve, FanCurvePoint
from .fan_variable_friction_loop import FanVariableFrictionLoopStudy
from .loop_network_io import looped_flow_network_from_dict
from .pressure_power import fan_power_efficiencies_from_dict


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


def fan_variable_friction_loop_study_from_dict(
    data: dict,
) -> FanVariableFrictionLoopStudy:
    fan_data = data["fan_curve"]
    solver = data.get("solver", {})
    if not isinstance(solver, dict):
        raise ValueError("solver must be an object when provided")
    unknown = set(solver) - _SOLVER_KEYS
    if unknown:
        raise ValueError(
            "unsupported fan/variable-friction solver option(s): "
            + ", ".join(sorted(unknown))
        )

    return FanVariableFrictionLoopStudy(
        name=data["name"],
        fan_curve=FanCurve(
            name=fan_data["name"],
            points=tuple(
                FanCurvePoint(**point) for point in fan_data["points"]
            ),
        ),
        loop_network=looped_flow_network_from_dict(data["loop_network"]),
        fan_discharge_node=data["fan_discharge_node"],
        fan_suction_node=data["fan_suction_node"],
        fixed_pressure_pa=data.get("fixed_pressure_pa", 0.0),
        power_efficiencies=fan_power_efficiencies_from_dict(
            data.get("power_efficiencies")
        ),
        **solver,
    )


def load_fan_variable_friction_loop_study(
    path: str | Path,
) -> FanVariableFrictionLoopStudy:
    return fan_variable_friction_loop_study_from_dict(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )
