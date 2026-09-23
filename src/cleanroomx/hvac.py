from __future__ import annotations

import math

from .hvac_models import HVACProject
from .thermal import analyze_thermal_design


def analyze_hvac_project(project: HVACProject) -> dict:
    room_results: list[dict] = []
    total_cleanroom_airflow = 0.0
    total_governing_airflow = 0.0
    total_cooling_kw = 0.0
    total_heating_kw = 0.0

    for room in project.rooms:
        thermal = analyze_thermal_design(
            room.thermal_design,
            room.cleanroom_airflow_m3_h,
        )
        governing_airflow = thermal["governing_supply_airflow_m3_h"]
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
                "thermal": thermal,
            }
        )
        total_cleanroom_airflow += room.cleanroom_airflow_m3_h
        total_governing_airflow += governing_airflow
        total_cooling_kw += thermal["preliminary_cooling_capacity_kw"]
        total_heating_kw += thermal["preliminary_heating_capacity_kw"]

    return {
        "project": project.name,
        "rooms": room_results,
        "total_cleanroom_airflow_m3_h": round(total_cleanroom_airflow, 3),
        "total_governing_airflow_m3_h": round(total_governing_airflow, 3),
        "total_preliminary_cooling_capacity_kw": round(total_cooling_kw, 4),
        "total_preliminary_heating_capacity_kw": round(total_heating_kw, 4),
        "engineering_note": (
            "Thermal/HVAC results are preliminary calculations from explicit project "
            "inputs. Cleanroom airflow is supplied independently; no ISO class is mapped "
            "to a fixed ACH or airflow."
        ),
    }
