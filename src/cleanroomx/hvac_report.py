from __future__ import annotations


def markdown_hvac_report(result: dict) -> str:
    lines = [f"# CleanroomX HVAC Report — {result['project']}", ""]
    lines.extend(
        [
            "## Airflow and preliminary capacity",
            "",
            "| Room | Cleanroom m³/h | Governing m³/h | Basis | Net surplus m³/h | Balance | Cooling kW | Heating kW | Filter units |",
            "|---|---:|---:|---|---:|---|---:|---:|---:|",
        ]
    )
    for room in result["rooms"]:
        thermal = room["thermal"]
        balance = room["air_balance"]
        units = room["filter_units"] if room["filter_units"] is not None else "—"
        balance_status = "PASS" if balance["passes_minimum_surplus"] else "FAIL"
        lines.append(
            f"| {room['name']} | {room['cleanroom_airflow_m3_h']} | "
            f"{room['governing_airflow_m3_h']} | {thermal['governing_airflow_basis']} | "
            f"{balance['net_surplus_m3_h']} | {balance_status} | "
            f"{thermal['preliminary_cooling_capacity_kw']} | "
            f"{thermal['preliminary_heating_capacity_kw']} | {units} |"
        )

    lines.extend(["", "## Air-balance details", ""])
    for room in result["rooms"]:
        balance = room["air_balance"]
        lines.append(
            f"- **{room['name']}:** supply {balance['supply_airflow_m3_h']} m³/h, "
            f"return {balance['return_airflow_m3_h']} m³/h, exhaust "
            f"{balance['exhaust_airflow_m3_h']} m³/h, transfer-in "
            f"{balance['transfer_in_airflow_m3_h']} m³/h, transfer-out "
            f"{balance['transfer_out_airflow_m3_h']} m³/h, net surplus "
            f"{balance['net_surplus_m3_h']} m³/h."
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

    duct = result.get("supply_duct_network")
    if duct is not None:
        lines.extend(
            [
                "",
                "## Supply duct pressure-loss screening",
                "",
                f"- Critical path: **{duct['critical_path']}**.",
                f"- Critical-path duct loss: **{duct['critical_path_pressure_loss_pa']} Pa**.",
                f"- Air density: **{duct['air_density_kg_m3']} kg/m³**.",
                f"- Dynamic viscosity: **{duct['dynamic_viscosity_pa_s']} Pa·s**.",
                "",
                "| Path | Total pressure loss (Pa) |",
                "|---|---:|",
            ]
        )
        for path in duct["paths"]:
            lines.append(
                f"| {path['name']} | {path['total_pressure_loss_pa']} |"
            )

        for path in duct["paths"]:
            lines.extend(
                [
                    "",
                    f"### Duct path — {path['name']}",
                    "",
                    "| Section | Shape | Flow m³/h | Velocity m/s | Re | Darcy f | Friction Pa | Local Pa | Total Pa |",
                    "|---|---|---:|---:|---:|---:|---:|---:|---:|",
                ]
            )
            for section in path["sections"]:
                lines.append(
                    f"| {section['name']} | {section['shape']} | "
                    f"{section['airflow_m3_h']} | {section['velocity_m_s']} | "
                    f"{section['reynolds_number']} | {section['darcy_friction_factor']} | "
                    f"{section['friction_pressure_loss_pa']} | "
                    f"{section['local_pressure_loss_pa']} | "
                    f"{section['total_pressure_loss_pa']} |"
                )
        lines.extend(["", duct["engineering_note"]])

    if result["supply_fan"] is not None:
        fan = result["supply_fan"]
        lines.extend(
            [
                "",
                "## Preliminary supply-fan duty",
                "",
                f"- Airflow: **{fan['airflow_m3_h']} m³/h**.",
                f"- Duct-pressure source: **{fan['duct_pressure_source']}**.",
                f"- Total entered/calculated static pressure: **{fan['total_static_pressure_pa']} Pa**.",
                f"- Estimated electrical input: **{fan['estimated_electrical_input_kw']} kW**.",
                f"- {fan['scope_note']}",
            ]
        )

    lines.extend(
        [
            "",
            f"Total governing airflow: **{result['total_governing_airflow_m3_h']} m³/h**.",
            f"Total return airflow: **{result['total_return_airflow_m3_h']} m³/h**.",
            f"Total exhaust airflow: **{result['total_exhaust_airflow_m3_h']} m³/h**.",
            f"Total net surplus: **{result['total_net_surplus_m3_h']} m³/h**.",
            f"All minimum airflow-surplus checks pass: **{result['all_air_balances_pass']}**.",
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
