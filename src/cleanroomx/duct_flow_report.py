from __future__ import annotations

from .markdown import markdown_text


def markdown_parallel_flow_report(result: dict) -> str:
    lines = [f"# CleanroomX Parallel Branch-Flow Report — {markdown_text(result['network'])}", ""]
    lines.extend(
        [
            "## Solution",
            "",
            f"- Specified total airflow: **{result['total_airflow_m3_h']} m³/h**",
            f"- Solved total airflow: **{result['solved_total_airflow_m3_h']} m³/h**",
            f"- Common parallel-path pressure drop: **{result['common_pressure_drop_pa']} Pa**",
            f"- Mass-balance error: **{result['mass_balance_error_m3_h']} m³/h**",
            f"- Maximum equal-pressure residual: **{result['max_abs_pressure_balance_error_pa']} Pa**",
            "",
            "| Path | Solved airflow (m³/h) | Flow fraction | Resistance [Pa/(m³/s)²] | Pressure drop (Pa) | Pressure residual (Pa) |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for path in result["paths"]:
        lines.append(
            f"| {markdown_text(path['name'])} | {path['airflow_m3_h']} | "
            f"{path['airflow_fraction']} | "
            f"{path['resistance_pa_per_m3_s_squared']} | "
            f"{path['pressure_drop_pa']} | "
            f"{path['pressure_balance_error_pa']} |"
        )

    for path in result["paths"]:
        lines.extend(
            [
                "",
                f"## Path — {markdown_text(path['name'])}",
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

    lines.extend(["", "## Engineering note", "", result["scope_note"], ""])
    return "\n".join(lines)
