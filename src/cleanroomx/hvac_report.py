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

    if result["duct_network"] is not None:
        network = result["duct_network"]
        lines.extend(
            [
                "",
                "## Duct critical-path pressure loss",
                "",
                "| Path | Calculated pressure drop Pa |",
                "|---|---:|",
            ]
        )
        for path in network["paths"]:
            lines.append(
                f"| {path['name']} | {path['total_pressure_drop_pa']} |"
            )
        lines.extend(
            [
                "",
                f"Critical path: **{network['critical_path']}**.",
                f"Critical-path duct pressure drop: **{network['critical_path_pressure_drop_pa']} Pa**.",
                "",
                network["scope_note"],
            ]
        )

    if result["branch_flow_network"] is not None:
        network = result["branch_flow_network"]
        lines.extend(
            [
                "",
                "## Branch-flow supply network",
                "",
                f"- Source node: **{network['source_node']}**.",
                f"- Solved source airflow: **{network['source_airflow_m3_h']} m³/h**.",
                f"- Critical terminal: **{network['critical_terminal']}**.",
                f"- Critical-path pressure drop: **{network['critical_path_pressure_drop_pa']} Pa**.",
                "",
                "| Branch | From | To | Solved airflow m³/h | Pressure drop Pa |",
                "|---|---|---|---:|---:|",
            ]
        )
        for item in network["branches"]:
            lines.append(
                f"| {item['name']} | {item['upstream_node']} | "
                f"{item['downstream_node']} | {item['airflow_m3_h']} | "
                f"{item['total_pressure_drop_pa']} |"
            )
        lines.extend(
            [
                "",
                "| Terminal | Demand m³/h | Source-to-terminal pressure drop Pa |",
                "|---|---:|---:|",
            ]
        )
        for terminal in network["terminals"]:
            lines.append(
                f"| {terminal['node']} | {terminal['airflow_m3_h']} | "
                f"{terminal['total_pressure_drop_pa']} |"
            )
        lines.extend(["", network["scope_note"]])

    if result["supply_fan"] is not None:
        fan = result["supply_fan"]
        lines.extend(
            [
                "",
                "## Preliminary supply-fan duty",
                "",
                f"- Airflow: **{fan['airflow_m3_h']} m³/h**.",
                f"- Total entered/computed static pressure: **{fan['total_static_pressure_pa']} Pa**.",
                f"- Duct pressure source: **{fan['duct_pressure_drop_source']}**.",
                f"- Estimated electrical input: **{fan['estimated_electrical_input_kw']} kW**.",
                f"- {fan['scope_note']}",
            ]
        )

    if result.get("fan_curve_duty_check") is not None:
        check = result["fan_curve_duty_check"]
        lines.extend(
            [
                "",
                "## Fan-curve design-duty check",
                "",
                f"- Status: **{check['status'].upper()}**.",
                f"- Required duty: **{check['required_airflow_m3_h']} m³/h at {check['required_pressure_pa']} Pa**.",
            ]
        )
        if check["available_fan_pressure_pa"] is not None:
            lines.extend(
                [
                    f"- Interpolated fan pressure: **{check['available_fan_pressure_pa']} Pa**.",
                    f"- Pressure margin: **{check['pressure_margin_pa']} Pa**.",
                ]
            )
        lines.extend(["", check["message"], "", check["scope_note"]])

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
