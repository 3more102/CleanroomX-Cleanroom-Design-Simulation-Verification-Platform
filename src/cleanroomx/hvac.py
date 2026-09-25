from __future__ import annotations

import math

from .airflow import _format_air_balance_calculation, calculate_air_balance
from .branch_network import (
    _format_branch_flow_network_calculation,
    calculate_branch_flow_network,
)
from .duct import _format_duct_network_calculation, calculate_duct_network
from .fan import _format_supply_fan_calculation, calculate_supply_fan
from .fan_curve import check_fan_duty_against_curve
from .hvac_models import HVACProject
from .thermal import _format_thermal_design_calculation, calculate_thermal_design


def analyze_hvac_project(project: HVACProject) -> dict:
    room_results: list[dict] = []
    cleanroom_airflows: list[float] = []
    governing_airflows: list[float] = []
    return_airflows: list[float] = []
    exhaust_airflows: list[float] = []
    net_surpluses: list[float] = []
    cooling_capacities_kw: list[float] = []
    heating_capacities_kw: list[float] = []
    all_air_balances_pass = True

    for room in project.rooms:
        thermal_calculation = calculate_thermal_design(
            room.thermal_design,
            room.cleanroom_airflow_m3_h,
        )
        thermal = _format_thermal_design_calculation(thermal_calculation)
        governing_airflow = thermal_calculation["governing_supply_airflow_m3_h"]
        air_balance_calculation = calculate_air_balance(
            governing_airflow, room.air_balance
        )
        air_balance = _format_air_balance_calculation(air_balance_calculation)
        all_air_balances_pass = (
            all_air_balances_pass
            and air_balance["passes_minimum_surplus"]
        )

        filter_units = None
        design_airflow_per_filter = None
        delivered_airflow = None

        if project.filter_unit is not None:
            design_airflow_per_filter = project.filter_unit.design_airflow_m3_h
            filter_units = math.ceil(governing_airflow / design_airflow_per_filter)
            delivered_airflow = filter_units * design_airflow_per_filter

        room_results.append(
            {
                "name": room.name,
                "cleanroom_airflow_m3_h": round(room.cleanroom_airflow_m3_h, 3),
                "governing_airflow_m3_h": round(governing_airflow, 3),
                "filter_units": filter_units,
                "design_airflow_per_filter_m3_h": (
                    round(design_airflow_per_filter, 3)
                    if design_airflow_per_filter is not None
                    else None
                ),
                "delivered_airflow_m3_h": (
                    round(delivered_airflow, 3)
                    if delivered_airflow is not None
                    else None
                ),
                "air_balance": air_balance,
                "thermal": thermal,
            }
        )
        cleanroom_airflows.append(room.cleanroom_airflow_m3_h)
        governing_airflows.append(governing_airflow)
        return_airflows.append(room.air_balance.return_airflow_m3_h)
        exhaust_airflows.append(room.air_balance.exhaust_airflow_m3_h)
        net_surpluses.append(air_balance_calculation["net_surplus_m3_h"])
        cooling_capacities_kw.append(
            thermal_calculation["preliminary_cooling_capacity_kw"]
        )
        heating_capacities_kw.append(
            thermal_calculation["preliminary_heating_capacity_kw"]
        )

    total_cleanroom_airflow = math.fsum(cleanroom_airflows)
    total_governing_airflow = math.fsum(governing_airflows)
    total_return_airflow = math.fsum(return_airflows)
    total_exhaust_airflow = math.fsum(exhaust_airflows)
    total_net_surplus = math.fsum(net_surpluses)
    total_cooling_kw = math.fsum(cooling_capacities_kw)
    total_heating_kw = math.fsum(heating_capacities_kw)

    duct_calculation = (
        calculate_duct_network(project.duct_network)
        if project.duct_network is not None
        else None
    )
    duct_network = (
        _format_duct_network_calculation(duct_calculation)
        if duct_calculation is not None
        else None
    )
    branch_flow_calculation = (
        calculate_branch_flow_network(project.branch_flow_network)
        if project.branch_flow_network is not None
        else None
    )
    branch_flow_network = (
        _format_branch_flow_network_calculation(branch_flow_calculation)
        if branch_flow_calculation is not None
        else None
    )

    if branch_flow_calculation is not None:
        source_airflow = branch_flow_calculation["source_airflow_m3_h"]
        if not math.isclose(
            source_airflow,
            total_governing_airflow,
            rel_tol=1e-3,
            abs_tol=1.0,
        ):
            raise ValueError(
                "branch_flow_network source airflow must match total governing "
                f"HVAC airflow; network={source_airflow} m3/h, "
                f"HVAC={round(total_governing_airflow, 3)} m3/h"
            )

    supply_fan = None
    fan_curve_duty_check = None
    if project.fan_system is not None:
        filter_drop = (
            project.filter_unit.pressure_drop_pa
            if project.filter_unit is not None
            else 0.0
        )
        if branch_flow_calculation is not None:
            duct_override = branch_flow_calculation[
                "critical_path_pressure_drop_pa"
            ]
            duct_source = "computed_branch_flow_network"
        elif duct_calculation is not None:
            duct_override = duct_calculation["critical_path_pressure_drop_pa"]
            duct_source = "computed_duct_network"
        else:
            duct_override = None
            duct_source = None
        fan_calculation = calculate_supply_fan(
            total_governing_airflow,
            project.fan_system,
            terminal_filter_pressure_drop_pa=filter_drop,
            duct_pressure_drop_override_pa=duct_override,
            duct_pressure_drop_source=duct_source,
        )
        supply_fan = _format_supply_fan_calculation(fan_calculation)
        if project.fan_curve is not None:
            fan_curve_duty_check = check_fan_duty_against_curve(
                project.fan_curve,
                total_governing_airflow,
                fan_calculation["total_static_pressure_pa"],
            )

    return {
        "project": project.name,
        "rooms": room_results,
        "total_cleanroom_airflow_m3_h": round(total_cleanroom_airflow, 3),
        "total_governing_airflow_m3_h": round(total_governing_airflow, 3),
        "total_return_airflow_m3_h": round(total_return_airflow, 3),
        "total_exhaust_airflow_m3_h": round(total_exhaust_airflow, 3),
        "total_net_surplus_m3_h": round(total_net_surplus, 3),
        "all_air_balances_pass": all_air_balances_pass,
        "duct_network": duct_network,
        "branch_flow_network": branch_flow_network,
        "supply_fan": supply_fan,
        "fan_curve_duty_check": fan_curve_duty_check,
        "total_preliminary_cooling_capacity_kw": round(total_cooling_kw, 4),
        "total_preliminary_heating_capacity_kw": round(total_heating_kw, 4),
        "engineering_note": (
            "Thermal/HVAC results are preliminary calculations from explicit project "
            "inputs. Cleanroom airflow is supplied independently; no ISO class is mapped "
            "to a fixed ACH, pressure offset, airflow surplus, filter pressure drop, "
            "duct friction factor, fitting loss coefficient, branch terminal demand, fan duty, or fan curve."
        ),
    }
