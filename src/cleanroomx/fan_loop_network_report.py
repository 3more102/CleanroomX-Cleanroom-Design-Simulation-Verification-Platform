from __future__ import annotations

from .markdown import markdown_text


def markdown_fan_loop_network_report(result: dict) -> str:
    lines = [
        f"# CleanroomX Fan/Loop-Network Report — {markdown_text(result['study'])}",
        "",
        f"- Fan curve: **{markdown_text(result['fan_curve'])}**",
        f"- Status: **{result['status'].upper()}**",
        f"- Fan discharge node: **{markdown_text(result['fan_discharge_node'])}**",
        f"- Fan suction node: **{markdown_text(result['fan_suction_node'])}**",
        f"- Fixed pressure: **{result['fixed_pressure_pa']} Pa**",
        f"- Reference airflow: **{result['reference_airflow_m3_h']} m³/h**",
        f"- Reference loop pressure: **{result['reference_network_pressure_pa']} Pa**",
        "- Equivalent loop resistance: "
        f"**{result['equivalent_loop_resistance_pa_per_m3_s_squared']} Pa/(m³/s)²**",
        "",
    ]

    point = result["fan_operating_point"]
    if point is None:
        lines.extend(["## Operating point", "", result["message"], ""])
    else:
        check = result["system_pressure_check"]
        network = result["operating_network_solution"]
        lines.extend(
            [
                "## Operating point",
                "",
                f"- Airflow: **{point['airflow_m3_h']} m³/h**",
                f"- Fan pressure: **{point['fan_pressure_pa']} Pa**",
                f"- Loop-network pressure: **{check['loop_network_pressure_pa']} Pa**",
                f"- Total system pressure: **{check['total_system_pressure_pa']} Pa**",
                "- Fan-system residual: "
                f"**{check['fan_minus_system_pressure_pa']} Pa**",
                "- Equivalent-network residual: "
                f"**{check['network_pressure_residual_pa']} Pa**",
                "- Maximum continuity residual: "
                f"**{network['max_abs_mass_balance_residual_m3_h']} m³/h**",
                "- Maximum edge pressure-law residual: "
                f"**{network['max_abs_pressure_law_residual_pa']} Pa**",
                "",
                "## Solved loop edges",
                "",
                "| Edge | Resistance basis | Airflow (m³/h) | Actual direction | Pressure difference (Pa) |",
                "|---|---|---:|---|---:|",
            ]
        )
        for edge in network["edges"]:
            lines.append(
                f"| {markdown_text(edge['name'])} | {edge['resistance_basis']} | "
                f"{edge['airflow_m3_h']} | {edge['flow_direction']} | "
                f"{edge['pressure_difference_pa']} |"
            )

        lines.extend(
            [
                "",
                "## Solved node pressures",
                "",
                "| Node | Relative pressure (Pa) | Injection (m³/h) | Continuity residual (m³/h) |",
                "|---|---:|---:|---:|",
            ]
        )
        for node in network["nodes"]:
            lines.append(
                f"| {markdown_text(node['name'])} | {node['relative_pressure_pa']} | "
                f"{node['specified_injection_m3_h']} | "
                f"{node['mass_balance_residual_m3_h']} |"
            )

    lines.extend(
        [
            "",
            "## Supplied fan-curve checks",
            "",
            "| Airflow (m³/h) | Fan pressure (Pa) | System pressure (Pa) | Margin (Pa) |",
            "|---:|---:|---:|---:|",
        ]
    )
    for row in result["fan_curve_point_checks"]:
        lines.append(
            f"| {row['airflow_m3_h']} | {row['fan_pressure_pa']} | "
            f"{row['system_pressure_pa']} | {row['pressure_margin_pa']} |"
        )

    lines.extend(["", "## Engineering note", "", result["scope_note"], ""])
    return "\n".join(lines)
