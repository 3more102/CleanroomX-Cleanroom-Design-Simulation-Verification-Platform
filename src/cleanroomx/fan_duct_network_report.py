from __future__ import annotations

from .markdown import markdown_text


def markdown_fan_duct_network_report(result: dict) -> str:
    lines = [
        f"# CleanroomX Fan/Duct-Network Report — {markdown_text(result['study'])}",
        "",
        f"- Fan curve: **{markdown_text(result['fan_curve'])}**",
        f"- Status: **{result['status'].upper()}**",
        "- Reference system airflow: "
        f"**{result['reference_system_airflow_m3_h']} m³/h**",
        f"- Fixed pressure component: **{result['fixed_pressure_pa']} Pa**",
        f"- Critical path: **{markdown_text(result['critical_path'])}**",
        "- Critical-path quadratic resistance: "
        f"**{result['critical_path_quadratic_resistance_pa_per_m3_s_squared']} "
        "Pa/(m³/s)²**",
        "- Critical-path pressure drop at reference airflow: "
        f"**{result['critical_path_reference_pressure_drop_pa']} Pa**",
        "",
        "## Fan operating point",
        "",
    ]

    point = result["operating_point"]
    if point is None:
        lines.append(result["fan_solver"]["message"])
        lines.append("")
    else:
        lines.extend(
            [
                f"- Airflow: **{point['airflow_m3_h']} m³/h** "
                f"({point['airflow_m3_s']} m³/s)",
                f"- Fan pressure: **{point['fan_pressure_pa']} Pa**",
                f"- System pressure: **{point['system_pressure_pa']} Pa**",
                "- Fan-system pressure residual: "
                f"**{point['pressure_residual_pa']} Pa**",
                f"- Air power: **{point['air_power_kw']} kW**",
                "",
            ]
        )

    lines.extend(
        [
            "## Duct paths",
            "",
            "| Path | R (Pa/(m³/s)²) | Reference drop (Pa) | "
            "Operating drop (Pa) |",
            "|---|---:|---:|---:|",
        ]
    )
    for path in result["paths"]:
        operating_drop = path.get("operating_pressure_drop_pa", "n/a")
        lines.append(
            f"| {markdown_text(path['name'])} | "
            f"{path['quadratic_resistance_pa_per_m3_s_squared']} | "
            f"{path['reference_pressure_drop_pa']} | "
            f"{operating_drop} |"
        )

    for path in result["paths"]:
        lines.extend(
            [
                "",
                f"### {markdown_text(path['name'])} sections",
                "",
                "| Section | Reference flow (m³/h) | Flow ratio | "
                "R contribution (Pa/(m³/s)²) | Reference drop (Pa) | "
                "Operating flow (m³/h) | Operating drop (Pa) |",
                "|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for section in path["sections"]:
            lines.append(
                f"| {markdown_text(section['name'])} | "
                f"{section['reference_airflow_m3_h']} | "
                f"{section['flow_ratio_to_system']} | "
                f"{section['quadratic_resistance_pa_per_m3_s_squared']} | "
                f"{section['reference_pressure_drop_pa']} | "
                f"{section.get('operating_airflow_m3_h', 'n/a')} | "
                f"{section.get('operating_pressure_drop_pa', 'n/a')} |"
            )

    lines.extend(
        [
            "",
            "## Engineering note",
            "",
            result["scope_note"],
            "",
        ]
    )
    return "\n".join(lines)
