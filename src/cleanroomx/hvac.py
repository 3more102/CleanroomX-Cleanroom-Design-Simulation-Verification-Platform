from __future__ import annotations

import math

from .airflow import analyze_air_balance
from .duct import analyze_duct_network
from .fan import analyze_supply_fan
from .hvac_models import HVACProject
from .supply_network import solve_supply_network
from .thermal import analyze_thermal_design


def analyze_hvac_project(project: HVACProject) -> dict:
    room_results: list[dict] = []
    governing_airflow_by_room: dict[str, float] = {}
    total_cleanroom_airflow = 0.0
    total_governing_airflow = 0.0
    total_return_airflow = 0.0
    total_exhaust_airflow = 0.0
    total_net_surplus = 0.0
    total_cooling_kw = 0.0
    total_heating_kw = 0.0
    all_air_balances_pass = True

    for room in project.rooms:
        thermal = analyze_thermal_design(
            room.thermal_design,
            room.cleanroom_airflow_m3_h,
        )
        governing_airflow = thermal["governing_supply_airflow_m3_h"]
        governing_airflow_by_room[room.name] = governing_airflow
        air_balance = analyze_air_balance(governing_airflow, room.air_balance)
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
        total_cleanroom_airflow += room.cleanroom_airflow_m3_h
        total_governing_airflow += governing_airflow
        total_return_airflow += room.air_balance.return_airflow_m3_h
        total_exhaust_airflow += room.air_balance.exhaust_airflow_m3_h
        total_net_surplus += air_balance["net_surplus_m3_h"]
        total_cooling_kw += thermal["preliminary_cooling_capacity_kw"]
        total_heating_kw += thermal["preliminary_heating_capacity_kw"]

    supply_network = None
    branch_airflows_m3_h: dict[str, float] | None = None
    fan_design_airflow_m3_h = total_governing_airflow

    if project.supply_network is not None:
        defined_rooms = set(governing_airflow_by_room)
        referenced_rooms = {
            node.room_name
            for node in project.supply_network.nodes
            if node.room_name is not None
        }
        unknown_rooms = sorted(referenced_rooms - defined_rooms)
        if unknown_rooms:
            raise ValueError(
                "supply network references unknown HVAC room(s): "
                + ", ".join(unknown_rooms)
            )
        missing_rooms = sorted(defined_rooms - referenced_rooms)
        if missing_rooms:
            raise ValueError(
                "every HVAC room must be mapped to exactly one supply node when "
                "supply_network is configured; missing: "
                + ", ".join(missing_rooms)
            )

        supply_network = solve_supply_network(
            project.supply_network,
            governing_airflow_by_room,
        )
        branch_airflows_m3_h = {
            branch["name"]: branch["airflow_m3_h"]
            for branch in supply_network["branches"]
        }
        fan_design_airflow_m3_h = supply_network["source_airflow_m3_h"]

    duct_network = (
        analyze_duct_network(project.duct_network, branch_airflows_m3_h)
        if project.duct_network is not None
        else None
    )

    supply_fan = None
    if project.fan_system is not None:
        filter_drop = (
            project.filter_unit.pressure_drop_pa
            if project.filter_unit is not None
            else 0.0
        )
        duct_override = (
            duct_network["critical_path_pressure_drop_pa"]
            if duct_network is not None
            else None
        )
        supply_fan = analyze_supply_fan(
            fan_design_airflow_m3_h,
            project.fan_system,
            terminal_filter_pressure_drop_pa=filter_drop,
            duct_pressure_drop_override_pa=duct_override,
        )

    return {
        "project": project.name,
        "rooms": room_results,
        "total_cleanroom_airflow_m3_h": round(total_cleanroom_airflow, 3),
        "total_governing_airflow_m3_h": round(total_governing_airflow, 3),
        "fan_design_airflow_m3_h": round(fan_design_airflow_m3_h, 3),
        "total_return_airflow_m3_h": round(total_return_airflow, 3),
        "total_exhaust_airflow_m3_h": round(total_exhaust_airflow, 3),
        "total_net_surplus_m3_h": round(total_net_surplus, 3),
        "all_air_balances_pass": all_air_balances_pass,
        "supply_network": supply_network,
        "duct_network": duct_network,
        "supply_fan": supply_fan,
        "total_preliminary_cooling_capacity_kw": round(total_cooling_kw, 4),
        "total_preliminary_heating_capacity_kw": round(total_heating_kw, 4),
        "engineering_note": (
            "Thermal/HVAC results are preliminary calculations from explicit project "
            "inputs. A configured rooted supply network aggregates downstream room "
            "demand but does not perform pressure-driven flow balancing. Cleanroom "
            "airflow remains requirement-driven; no ISO class is mapped to a fixed ACH, "
            "pressure offset, airflow surplus, filter pressure drop, duct friction "
            "factor, fitting loss coefficient, or fan duty."
        ),
    }
