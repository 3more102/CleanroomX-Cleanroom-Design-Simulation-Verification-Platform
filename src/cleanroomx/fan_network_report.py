from __future__ import annotations

from .markdown import markdown_text


def markdown_fan_driven_parallel_network_report(result: dict) -> str:
    lines = [
        f"# CleanroomX Fan-Driven Parallel Network Report — {markdown_text(result['study'])}",
        "",
        f"- Fan curve: **{result['fan_curve']}**",
        f"- Status: **{result['status'].upper()}**",
        f"- Fixed pressure: **{result['fixed_pressure_pa']} Pa**",
        "- Equivalent parallel-network resistance: "
        f"**{result['equivalent_network_resistance_pa_per_m3_s_squared']} Pa/(m³/s)²**",
        "",
        "## Path resistances",
        "",
        "| Path | Resistance [Pa/(m³/s)²] |",
        "|---|---:|",
    ]
    for path in result["path_resistances"]:
        lines.append(
            f"| {markdown_text(path['name'])} | {path['resistance_pa_per_m3_s_squared']} |"
        )

    point = result["fan_operating_point"]
    if point is None:
        lines.extend(
            [
                "",
                "## Operating point",
                "",
                result["message"],
                "",
            ]
        )
    else:
        pressure = result["system_pressure_check"]
        network = result["network_solution"]
        lines.extend(
            [
                "",
                "## Operating point",
                "",
                f"- Total airflow: **{point['airflow_m3_h']} m³/h**",
                f"- Fan pressure: **{point['fan_pressure_pa']} Pa**",
                f"- Parallel-network pressure: **{pressure['parallel_network_pressure_pa']} Pa**",
                f"- Total system pressure: **{pressure['total_system_pressure_pa']} Pa**",
                "- Fan-system pressure residual: "
                f"**{pressure['fan_minus_system_pressure_pa']} Pa**",
                f"- Mass-balance error: **{network['mass_balance_error_m3_h']} m³/h**",
                "- Maximum equal-pressure residual: "
                f"**{network['max_abs_pressure_balance_error_pa']} Pa**",
                "",
                "## Solved branch flows",
                "",
                "| Path | Airflow (m³/h) | Flow fraction | Pressure drop (Pa) |",
                "|---|---:|---:|---:|",
            ]
        )
        for path in network["paths"]:
            lines.append(
                f"| {markdown_text(path['name'])} | {path['airflow_m3_h']} | "
                f"{path['airflow_fraction']} | {path['pressure_drop_pa']} |"
            )

        for path in network["paths"]:
            lines.extend(
                [
                    "",
                    f"### Path — {markdown_text(path['name'])}",
                    "",
                    "| Section | Airflow (m³/h) | Velocity (m/s) | Friction loss (Pa) | Local loss (Pa) | Total loss (Pa) |",
                    "|---|---:|---:|---:|---:|---:|",
                ]
            )
            for section in path["sections"]:
                lines.append(
                    f"| {markdown_text(section['name'])} | {section['airflow_m3_h']} | "
                    f"{section['velocity_m_s']} | "
                    f"{section['friction_pressure_drop_pa']} | "
                    f"{section['local_pressure_drop_pa']} | "
                    f"{section['total_pressure_drop_pa']} |"
                )

    lines.extend(
        [
            "",
            "## Supplied fan-curve checks",
            "",
            "| Airflow (m³/h) | Fan pressure (Pa) | System pressure (Pa) | Fan-system margin (Pa) |",
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
