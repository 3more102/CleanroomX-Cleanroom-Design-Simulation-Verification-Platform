from __future__ import annotations


def markdown_looped_network_report(result: dict) -> str:
    lines = [
        f"# CleanroomX Looped-Network Flow Report — {result['network']}",
        "",
        "## Solver summary",
        "",
        f"- Status: **{result['status'].upper()}**",
        f"- Reference node: **{result['reference_node']} = 0 Pa**",
        f"- Newton iterations: **{result['iterations']}**",
        f"- Mass-balance tolerance: **{result['mass_balance_tolerance_m3_h']} m³/h**",
        f"- Maximum node continuity residual: **{result['max_abs_mass_balance_residual_m3_h']} m³/h**",
        f"- Maximum edge pressure-law residual: **{result['max_abs_pressure_law_residual_pa']} Pa**",
        "",
        "## Nodes",
        "",
        "| Node | Relative pressure (Pa) | Specified injection (m³/h) | Net edge outflow (m³/h) | Continuity residual (m³/h) |",
        "|---|---:|---:|---:|---:|",
    ]
    for node in result["nodes"]:
        lines.append(
            f"| {node['name']} | {node['relative_pressure_pa']} | "
            f"{node['specified_injection_m3_h']} | "
            f"{node['net_edge_outflow_m3_h']} | "
            f"{node['mass_balance_residual_m3_h']} |"
        )

    lines.extend(
        [
            "",
            "## Edges",
            "",
            "| Edge | Declared start | Declared end | Solved airflow (m³/h) | Actual direction | Pressure difference (Pa) | R [Pa/(m³/s)²] | Pressure-law residual (Pa) |",
            "|---|---|---|---:|---|---:|---:|---:|",
        ]
    )
    for edge in result["edges"]:
        lines.append(
            f"| {edge['name']} | {edge['start_node']} | {edge['end_node']} | "
            f"{edge['airflow_m3_h']} | {edge['flow_direction']} | "
            f"{edge['pressure_difference_pa']} | "
            f"{edge['resistance_pa_per_m3_s_squared']} | "
            f"{edge['pressure_law_residual_pa']} |"
        )

    lines.extend(["", "## Engineering note", "", result["scope_note"], ""])
    return "\n".join(lines)
