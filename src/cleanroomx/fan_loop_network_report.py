from __future__ import annotations


def markdown_fan_driven_loop_network_report(result: dict) -> str:
    equivalent = result["equivalent_loop_network"]
    lines = [
        f"# CleanroomX Fan/Loop-Network Report — {result['study']}",
        "",
        "## Study summary",
        "",
        f"- Status: **{result['status'].upper()}**",
        f"- Fan curve: **{result['fan_curve']}**",
        f"- Source node: **{result['source_node']}**",
        f"- Sink node: **{result['sink_node']}**",
        f"- Fixed pressure term: **{result['fixed_pressure_pa']} Pa**",
        f"- Network reference airflow: **{equivalent['reference_airflow_m3_h']} m³/h**",
        f"- Reference loop pressure: **{equivalent['reference_network_pressure_pa']} Pa**",
        f"- Equivalent loop resistance: **{equivalent['equivalent_network_resistance_pa_per_m3_s_squared']} Pa/(m³/s)²**",
        "",
        "## Fan-curve checks",
        "",
        "| Airflow (m³/h) | Fan pressure (Pa) | Equivalent system pressure (Pa) | Margin (Pa) |",
        "|---:|---:|---:|---:|",
    ]
    for point in result["fan_curve_point_checks"]:
        lines.append(
            f"| {point['airflow_m3_h']} | {point['fan_pressure_pa']} | "
            f"{point['system_pressure_pa']} | {point['pressure_margin_pa']} |"
        )

    operating = result["fan_operating_point"]
    if operating is None:
        lines.extend(
            [
                "",
                "## Operating point",
                "",
                "No intersection was found inside the supplied fan-curve range.",
                "",
                "## Engineering note",
                "",
                result["scope_note"],
                "",
            ]
        )
        return "\n".join(lines)

    check = result["system_pressure_check"]
    lines.extend(
        [
            "",
            "## Operating point",
            "",
            f"- Airflow: **{operating['airflow_m3_h']} m³/h**",
            f"- Fan pressure: **{check['fan_pressure_pa']} Pa**",
            f"- Loop-network pressure: **{check['loop_network_pressure_pa']} Pa**",
            f"- Total system pressure: **{check['total_system_pressure_pa']} Pa**",
            f"- Fan − system residual: **{check['fan_minus_system_pressure_pa']} Pa**",
            f"- Loop − equivalent-network residual: **{check['loop_minus_equivalent_pressure_pa']} Pa**",
            "",
            "## Operating network nodes",
            "",
            "| Node | Relative pressure (Pa) | Injection (m³/h) | Continuity residual (m³/h) |",
            "|---|---:|---:|---:|",
        ]
    )
    for node in result["operating_network_solution"]["nodes"]:
        lines.append(
            f"| {node['name']} | {node['relative_pressure_pa']} | "
            f"{node['specified_injection_m3_h']} | "
            f"{node['mass_balance_residual_m3_h']} |"
        )

    lines.extend(
        [
            "",
            "## Operating network edges",
            "",
            "| Edge | Airflow (m³/h) | Direction | Pressure difference (Pa) | R basis | R [Pa/(m³/s)²] |",
            "|---|---:|---|---:|---|---:|",
        ]
    )
    for edge in result["operating_network_solution"]["edges"]:
        lines.append(
            f"| {edge['name']} | {edge['airflow_m3_h']} | "
            f"{edge['flow_direction']} | {edge['pressure_difference_pa']} | "
            f"{edge.get('resistance_basis', 'explicit')} | "
            f"{edge['resistance_pa_per_m3_s_squared']} |"
        )

    lines.extend(["", "## Engineering note", "", result["scope_note"], ""])
    return "\n".join(lines)
