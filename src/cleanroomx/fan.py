from __future__ import annotations

from .hvac_models import FanSystem


def analyze_supply_fan(
    airflow_m3_h: float,
    system: FanSystem,
    terminal_filter_pressure_drop_pa: float = 0.0,
    duct_pressure_drop_pa: float | None = None,
) -> dict:
    """Return preliminary supply-fan duty and electrical input power."""
    airflow_m3_h = float(airflow_m3_h)
    filter_drop = float(terminal_filter_pressure_drop_pa)
    duct_drop = (
        system.duct_pressure_drop_pa
        if duct_pressure_drop_pa is None
        else float(duct_pressure_drop_pa)
    )
    if airflow_m3_h <= 0:
        raise ValueError("airflow_m3_h must be > 0")
    if filter_drop < 0:
        raise ValueError("terminal_filter_pressure_drop_pa must be >= 0")
    if duct_drop < 0:
        raise ValueError("duct_pressure_drop_pa must be >= 0")

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
        "airflow_m3_h": round(airflow_m3_h, 3),
        "airflow_m3_s": round(airflow_m3_s, 6),
        "pressure_components_pa": {
            "duct": round(duct_drop, 3),
            "coil": round(system.coil_pressure_drop_pa, 3),
            "terminal_filter": round(filter_drop, 3),
            "other": round(system.other_pressure_drop_pa, 3),
        },
        "duct_pressure_drop_source": (
            "fan_system_input"
            if duct_pressure_drop_pa is None
            else "duct_network_critical_path"
        ),
        "configured_duct_pressure_drop_pa": round(system.duct_pressure_drop_pa, 3),
        "total_static_pressure_pa": round(total_static_pa, 3),
        "fan_efficiency": system.fan_efficiency,
        "motor_efficiency": system.motor_efficiency,
        "air_power_kw": round(air_power_w / 1000.0, 4),
        "shaft_power_kw": round(shaft_power_w / 1000.0, 4),
        "estimated_electrical_input_kw": round(input_power_w / 1000.0, 4),
        "scope_note": (
            "Preliminary steady-state fan power only. Pressure drops and efficiencies "
            "are explicit design inputs. System effect, velocity pressure, dirty-filter "
            "allowance, VFD/control losses, altitude correction, redundancy, and final "
            "manufacturer selection are not inferred."
        ),
    }
