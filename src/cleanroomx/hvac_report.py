from __future__ import annotations


def markdown_hvac_report(result: dict) -> str:
    lines = [f"# CleanroomX HVAC Report — {result['project']}", ""]
    lines.extend(
        [
            "## Airflow and preliminary capacity",
            "",
            "| Room | Cleanroom m³/h | Governing m³/h | Basis | Cooling kW | Heating kW | Filter units | Air-balance residual m³/h |",
            "|---|---:|---:|---|---:|---:|---:|---:|",
        ]
    )
    for room in result["rooms"]:
        thermal = room["thermal"]
        units = room["filter_units"] if room["filter_units"] is not None else "—"
        balance = room.get("air_balance")
        residual = balance["balance_residual_m3_h"] if balance is not None else "—"
        lines.append(
            f"| {room['name']} | {room['cleanroom_airflow_m3_h']} | "
            f"{room['governing_airflow_m3_h']} | {thermal['governing_airflow_basis']} | "
            f"{thermal['preliminary_cooling_capacity_kw']} | "
            f"{thermal['preliminary_heating_capacity_kw']} | {units} | {residual} |"
        )

    balances = [room for room in result["rooms"] if room.get("air_balance") is not None]
    if balances:
        summary = result["air_balance_summary"]
        lines.extend(
            [
                "",
                "## Room air-balance closure",
                "",
                f"Configured rooms: **{summary['rooms_configured']}**; balanced within explicit tolerance: "
                f"**{summary['rooms_balanced']}**; out of balance: **{summary['rooms_out_of_balance']}**.",
                "",
            ]
        )
        for room in balances:
            balance = room["air_balance"]
            lines.append(
                f"- **{room['name']}** — supply {balance['analysis_supply_airflow_m3_h']} m³/h; "
                f"return {balance['return_air_m3_h']} m³/h; exhaust {balance['exhaust_air_m3_h']} m³/h; "
                f"transfer in/out {balance['transfer_in_m3_h']}/{balance['transfer_out_m3_h']} m³/h; "
                f"leakage in/out {balance['leakage_in_m3_h']}/{balance['leakage_out_m3_h']} m³/h; "
                f"residual {balance['balance_residual_m3_h']} m³/h; status `{balance['status']}`."
            )
        lines.extend(
            [
                "",
                "Outdoor/makeup air is treated as a component of total room supply and is not added a second time in the room balance.",
            ]
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
