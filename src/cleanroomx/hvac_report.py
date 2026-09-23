from __future__ import annotations


def markdown_hvac_report(result: dict) -> str:
    lines = [f"# CleanroomX HVAC Report — {result['project']}", ""]
    lines.extend(
        [
            "## Airflow and preliminary capacity",
            "",
            "| Room | Cleanroom m³/h | Governing m³/h | Basis | Cooling kW | Heating kW | Filter units |",
            "|---|---:|---:|---|---:|---:|---:|",
        ]
    )
    for room in result["rooms"]:
        thermal = room["thermal"]
        units = room["filter_units"] if room["filter_units"] is not None else "—"
        lines.append(
            f"| {room['name']} | {room['cleanroom_airflow_m3_h']} | "
            f"{room['governing_airflow_m3_h']} | {thermal['governing_airflow_basis']} | "
            f"{thermal['preliminary_cooling_capacity_kw']} | "
            f"{thermal['preliminary_heating_capacity_kw']} | {units} |"
        )

    lines.extend(["", "## Psychrometric states", ""])
    for room in result["rooms"]:
        thermal = room["thermal"]
        indoor = thermal["room_air"]
        lines.append(
            f"- **{room['name']} room:** {indoor['dry_bulb_c']} °C, "
            f"{indoor['relative_humidity_percent']}% RH, "
            f"W={indoor['humidity_ratio_g_kg_da']} g/kgda, "
            f"h={indoor['enthalpy_kj_kg_da']} kJ/kgda, "
            f"dew point={indoor['dew_point_c']} °C."
        )
        outdoor = thermal["outdoor_air"]
        if outdoor is not None:
            lines.append(
                f"- **{room['name']} outdoor:** {outdoor['dry_bulb_c']} °C, "
                f"{outdoor['relative_humidity_percent']}% RH, "
                f"W={outdoor['humidity_ratio_g_kg_da']} g/kgda, "
                f"h={outdoor['enthalpy_kj_kg_da']} kJ/kgda."
            )

    lines.extend(
        [
            "",
            f"Total governing airflow: **{result['total_governing_airflow_m3_h']} m³/h**.",
            f"Preliminary cooling capacity: **{result['total_preliminary_cooling_capacity_kw']} kW**.",
            f"Preliminary heating capacity: **{result['total_preliminary_heating_capacity_kw']} kW**.",
            "",
            "## Engineering note",
            "",
            result["engineering_note"],
            "",
        ]
    )
    return "\n".join(lines)
