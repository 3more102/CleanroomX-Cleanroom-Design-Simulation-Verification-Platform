from __future__ import annotations

from .hvac_models import AirBalanceDesign
from .numeric import finite_float, positive_float


def calculate_air_balance(
    supply_airflow_m3_h: float,
    design: AirBalanceDesign,
) -> dict:
    """Evaluate a steady-state room airflow balance from explicit flow inputs."""
    supply_airflow_m3_h = positive_float(
        supply_airflow_m3_h, "supply_airflow_m3_h"
    )

    incoming = finite_float(
        supply_airflow_m3_h + design.transfer_in_airflow_m3_h,
        "incoming_airflow_m3_h",
    )
    mechanically_removed = finite_float(
        design.return_airflow_m3_h + design.exhaust_airflow_m3_h,
        "mechanically_removed_airflow_m3_h",
    )
    outgoing_known = finite_float(
        mechanically_removed + design.transfer_out_airflow_m3_h,
        "known_outgoing_airflow_m3_h",
    )
    net_surplus = finite_float(
        incoming - outgoing_known,
        "net_surplus_m3_h",
    )
    margin = finite_float(
        net_surplus - design.minimum_surplus_m3_h,
        "surplus_margin_m3_h",
    )

    return {
        "supply_airflow_m3_h": supply_airflow_m3_h,
        "return_airflow_m3_h": design.return_airflow_m3_h,
        "exhaust_airflow_m3_h": design.exhaust_airflow_m3_h,
        "transfer_in_airflow_m3_h": design.transfer_in_airflow_m3_h,
        "transfer_out_airflow_m3_h": design.transfer_out_airflow_m3_h,
        "net_surplus_m3_h": net_surplus,
        "minimum_surplus_m3_h": design.minimum_surplus_m3_h,
        "surplus_margin_m3_h": margin,
        "passes_minimum_surplus": margin >= 0,
        "balance_interpretation": (
            "Positive net surplus is airflow available for exfiltration or unmodeled "
            "outflow at steady state; negative net surplus implies infiltration or an "
            "unmodeled inflow is required. This airflow balance does not calculate room "
            "pressure."
        ),
    }


def _format_air_balance_calculation(calculation: dict) -> dict:
    return {
        "supply_airflow_m3_h": round(calculation["supply_airflow_m3_h"], 3),
        "return_airflow_m3_h": round(calculation["return_airflow_m3_h"], 3),
        "exhaust_airflow_m3_h": round(calculation["exhaust_airflow_m3_h"], 3),
        "transfer_in_airflow_m3_h": round(calculation["transfer_in_airflow_m3_h"], 3),
        "transfer_out_airflow_m3_h": round(calculation["transfer_out_airflow_m3_h"], 3),
        "net_surplus_m3_h": round(calculation["net_surplus_m3_h"], 3),
        "minimum_surplus_m3_h": round(calculation["minimum_surplus_m3_h"], 3),
        "surplus_margin_m3_h": round(calculation["surplus_margin_m3_h"], 3),
        "passes_minimum_surplus": calculation["passes_minimum_surplus"],
        "balance_interpretation": calculation["balance_interpretation"],
    }


def analyze_air_balance(
    supply_airflow_m3_h: float,
    design: AirBalanceDesign,
) -> dict:
    """Evaluate a steady-state room airflow balance from explicit flow inputs."""
    return _format_air_balance_calculation(
        calculate_air_balance(supply_airflow_m3_h, design)
    )
