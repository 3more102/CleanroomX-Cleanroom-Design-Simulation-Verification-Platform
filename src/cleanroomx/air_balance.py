from __future__ import annotations

from .hvac_models import AirBalanceDesign


def analyze_air_balance(
    design: AirBalanceDesign,
    supply_airflow_m3_h: float,
) -> dict:
    """Evaluate a steady-state volumetric room-air balance.

    Supply airflow is the total air delivered to the room. Outdoor/makeup air is a
    component of that supply and is therefore not added again here.
    """
    supply = float(supply_airflow_m3_h)
    if supply <= 0:
        raise ValueError("supply_airflow_m3_h must be > 0")

    mechanical_outflow = design.return_air_m3_h + design.exhaust_air_m3_h
    mechanical_surplus = supply - mechanical_outflow

    passive_inflow = design.transfer_in_m3_h + design.leakage_in_m3_h
    passive_outflow = design.transfer_out_m3_h + design.leakage_out_m3_h
    passive_net_outflow = passive_outflow - passive_inflow

    total_inflow = supply + passive_inflow
    total_outflow = mechanical_outflow + passive_outflow
    residual = total_inflow - total_outflow
    tolerance = design.balance_tolerance_m3_h

    if abs(residual) <= tolerance:
        status = "balanced"
    elif residual > 0:
        status = "unaccounted_outflow_required"
    else:
        status = "unaccounted_inflow_required"

    return {
        "analysis_supply_airflow_m3_h": round(supply, 3),
        "return_air_m3_h": round(design.return_air_m3_h, 3),
        "exhaust_air_m3_h": round(design.exhaust_air_m3_h, 3),
        "transfer_in_m3_h": round(design.transfer_in_m3_h, 3),
        "transfer_out_m3_h": round(design.transfer_out_m3_h, 3),
        "leakage_in_m3_h": round(design.leakage_in_m3_h, 3),
        "leakage_out_m3_h": round(design.leakage_out_m3_h, 3),
        "mechanical_surplus_m3_h": round(mechanical_surplus, 3),
        "passive_net_outflow_m3_h": round(passive_net_outflow, 3),
        "total_inflow_m3_h": round(total_inflow, 3),
        "total_outflow_m3_h": round(total_outflow, 3),
        "balance_residual_m3_h": round(residual, 3),
        "required_unmodeled_outflow_m3_h": round(max(residual, 0.0), 3),
        "required_unmodeled_inflow_m3_h": round(max(-residual, 0.0), 3),
        "balance_tolerance_m3_h": round(tolerance, 3),
        "status": status,
        "scope_note": (
            "Steady-state volumetric balance only. Pressure is not calculated from the "
            "airflow surplus; leakage paths and transfer flows must be supplied explicitly "
            "or determined by a separate pressure/network model."
        ),
    }
