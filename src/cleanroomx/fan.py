from __future__ import annotations

from .hvac_models import FanSystem
from .numeric import nonnegative_float, positive_float


def calculate_supply_fan(
    airflow_m3_h: float,
    system: FanSystem,
    terminal_filter_pressure_drop_pa: float = 0.0,
    duct_pressure_drop_override_pa: float | None = None,
    duct_pressure_drop_source: str | None = None,
) -> dict:
    """Return preliminary supply-fan duty and electrical input power."""
    airflow_m3_h = positive_float(airflow_m3_h, "airflow_m3_h")
    filter_drop = nonnegative_float(
        terminal_filter_pressure_drop_pa, "terminal_filter_pressure_drop_pa"
    )

    if duct_pressure_drop_override_pa is None:
        duct_drop = system.duct_pressure_drop_pa
        duct_drop_source = "fan_system_input"
    else:
        duct_drop = nonnegative_float(
            duct_pressure_drop_override_pa, "duct_pressure_drop_override_pa"
        )
        duct_drop_source = duct_pressure_drop_source or "computed_duct_network"

    total_static_pa = (
        duct_drop
        + system.coil_pressure_drop_pa
        + system.other_pressure_drop_pa
        + filter_drop
    )
    airflow_m3_s = airflow_m3_h / 3600.0
    air_power_w = airflow_m3_s * total_static_pa
    shaft_power_w = air_power_w / system.fan_efficiency
    input_power_w = shaft_power_w / system.motor_efficiency

    return {
        "name": system.name,
        "airflow_m3_h": airflow_m3_h,
        "airflow_m3_s": airflow_m3_s,
        "pressure_components_pa": {
            "duct": duct_drop,
            "coil": system.coil_pressure_drop_pa,
            "terminal_filter": filter_drop,
            "other": system.other_pressure_drop_pa,
        },
        "duct_pressure_drop_source": duct_drop_source,
        "total_static_pressure_pa": total_static_pa,
        "fan_efficiency": system.fan_efficiency,
        "motor_efficiency": system.motor_efficiency,
        "air_power_kw": air_power_w / 1000.0,
        "shaft_power_kw": shaft_power_w / 1000.0,
        "estimated_electrical_input_kw": input_power_w / 1000.0,
        "scope_note": (
            "Preliminary steady-state fan power only. Pressure drops and efficiencies "
            "are explicit design inputs or, for duct loss, an optional computed critical "
            "path. System effect, velocity pressure at fan boundaries, dirty-filter "
            "allowance, VFD/control losses, altitude correction, redundancy, and final "
            "manufacturer selection are not inferred."
        ),
    }


def _format_supply_fan_calculation(calculation: dict) -> dict:
    components = calculation["pressure_components_pa"]
    return {
        "name": calculation["name"],
        "airflow_m3_h": round(calculation["airflow_m3_h"], 3),
        "airflow_m3_s": round(calculation["airflow_m3_s"], 6),
        "pressure_components_pa": {
            "duct": round(components["duct"], 3),
            "coil": round(components["coil"], 3),
            "terminal_filter": round(components["terminal_filter"], 3),
            "other": round(components["other"], 3),
        },
        "duct_pressure_drop_source": calculation["duct_pressure_drop_source"],
        "total_static_pressure_pa": round(calculation["total_static_pressure_pa"], 3),
        "fan_efficiency": calculation["fan_efficiency"],
        "motor_efficiency": calculation["motor_efficiency"],
        "air_power_kw": round(calculation["air_power_kw"], 4),
        "shaft_power_kw": round(calculation["shaft_power_kw"], 4),
        "estimated_electrical_input_kw": round(
            calculation["estimated_electrical_input_kw"], 4
        ),
        "scope_note": calculation["scope_note"],
    }


def analyze_supply_fan(
    airflow_m3_h: float,
    system: FanSystem,
    terminal_filter_pressure_drop_pa: float = 0.0,
    duct_pressure_drop_override_pa: float | None = None,
    duct_pressure_drop_source: str | None = None,
) -> dict:
    """Return preliminary supply-fan duty and electrical input power."""
    return _format_supply_fan_calculation(
        calculate_supply_fan(
            airflow_m3_h,
            system,
            terminal_filter_pressure_drop_pa=terminal_filter_pressure_drop_pa,
            duct_pressure_drop_override_pa=duct_pressure_drop_override_pa,
            duct_pressure_drop_source=duct_pressure_drop_source,
        )
    )
