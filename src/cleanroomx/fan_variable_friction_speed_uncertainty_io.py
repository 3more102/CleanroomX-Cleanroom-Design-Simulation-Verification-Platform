from __future__ import annotations

import json
from pathlib import Path

from .fan_variable_friction_speed_uncertainty import (
    FanVariableFrictionSpeedUncertaintyStudy,
)
from .fan_variable_friction_uncertainty_io import (
    fan_variable_friction_loop_uncertainty_from_dict,
)


def fan_variable_friction_speed_uncertainty_from_dict(
    data: dict,
) -> FanVariableFrictionSpeedUncertaintyStudy:
    if "reference_fan_curve" not in data:
        raise ValueError("reference_fan_curve is required")
    base_data = {
        "name": data["name"],
        "fan_discharge_node": data["fan_discharge_node"],
        "fan_suction_node": data["fan_suction_node"],
        "fixed_pressure_pa": data.get("fixed_pressure_pa", 0.0),
        "fan_curve": data["reference_fan_curve"],
        "loop_network": data["loop_network"],
        "edge_local_loss_uncertainty": data.get("edge_local_loss_uncertainty", {}),
        "edge_absolute_roughness_uncertainty": data.get(
            "edge_absolute_roughness_uncertainty", {}
        ),
        "edge_kinematic_viscosity_uncertainty": data.get(
            "edge_kinematic_viscosity_uncertainty", {}
        ),
        "edge_air_density_uncertainty": data.get("edge_air_density_uncertainty", {}),
        "max_corner_cases": data.get("max_corner_cases", 256),
        "solver": data.get("solver", {}),
        "power_efficiencies": data.get("power_efficiencies"),
    }
    base = fan_variable_friction_loop_uncertainty_from_dict(base_data)
    return FanVariableFrictionSpeedUncertaintyStudy(
        name=data["name"],
        reference_fan_curve=base.fan_curve,
        loop_network=base.loop_network,
        fan_discharge_node=base.fan_discharge_node,
        fan_suction_node=base.fan_suction_node,
        speed_ratios=tuple(data["speed_ratios"]),
        fixed_pressure_pa=base.fixed_pressure_pa,
        edge_local_loss_coefficient=base.edge_local_loss_coefficient,
        edge_absolute_roughness_m=base.edge_absolute_roughness_m,
        edge_kinematic_viscosity_m2_s=base.edge_kinematic_viscosity_m2_s,
        edge_air_density_kg_m3=base.edge_air_density_kg_m3,
        fan_curve_provenance=base.fan_curve_provenance,
        reference_speed_rpm=data.get("reference_speed_rpm"),
        max_corner_cases=base.max_corner_cases,
        max_total_cases=data.get("max_total_cases", 1024),
        power_efficiencies=base.power_efficiencies,
        resistance_relative_tolerance=base.resistance_relative_tolerance,
        relaxation=base.relaxation,
        near_zero_airflow_m3_h=base.near_zero_airflow_m3_h,
        max_outer_iterations=base.max_outer_iterations,
        mass_balance_tolerance_m3_h=base.mass_balance_tolerance_m3_h,
        max_newton_iterations=base.max_newton_iterations,
        operating_pressure_tolerance_pa=base.operating_pressure_tolerance_pa,
        max_operating_iterations=base.max_operating_iterations,
    )


def load_fan_variable_friction_speed_uncertainty(
    path: str | Path,
) -> FanVariableFrictionSpeedUncertaintyStudy:
    return fan_variable_friction_speed_uncertainty_from_dict(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )
