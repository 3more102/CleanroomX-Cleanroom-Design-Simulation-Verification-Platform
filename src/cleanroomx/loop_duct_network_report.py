from __future__ import annotations


def markdown_loop_duct_network_report(result: dict) -> str:
    lines = [
        f"# CleanroomX Geometry-Derived Looped-Network Report — {result['network']}",
        "",
        "## Solver summary",
        "",
        f"- Status: **{result['status'].upper()}**",
        f"- Resistance basis: **{result['resistance_basis']}**",
        f"- Reference node: **{result['reference_node']} = 0 Pa**",
        f"- Newton iterations: **{result['iterations']}**",
        f"- Maximum node continuity residual: **{result['max_abs_mass_balance_residual_m3_h']} m³/h**",
        f"- Maximum edge pressure-law residual: **{result['max_abs_pressure_law_residual_pa']} Pa**",
        "",
        "## Geometry-derived edges",
        "",
        "| Edge | Reference airflow (m³/h) | Friction method | f | Re | Derived R [Pa/(m³/s)²] | Reference ΔP (Pa) | Solved airflow (m³/h) | Actual direction | Solved ΔP (Pa) |",
        "|---|---:|---|---:|---:|---:|---:|---:|---|---:|",
    ]
    for edge in result["edges"]:
        reynolds = (
            "—"
            if edge["reynolds_number"] is None
            else str(edge["reynolds_number"])
        )
        lines.append(
            f"| {edge['name']} | {edge['reference_airflow_m3_h']} | "
            f"{edge['friction_factor_method']} | {edge['friction_factor']} | "
            f"{reynolds} | {edge['resistance_pa_per_m3_s_squared']} | "
            f"{edge['reference_pressure_drop_pa']} | {edge['airflow_m3_h']} | "
            f"{edge['flow_direction']} | {edge['pressure_difference_pa']} |"
        )

    lines.extend(
        [
            "",
            "## Nodes",
            "",
            "| Node | Relative pressure (Pa) | Specified injection (m³/h) | Continuity residual (m³/h) |",
            "|---|---:|---:|---:|",
        ]
    )
    for node in result["nodes"]:
        lines.append(
            f"| {node['name']} | {node['relative_pressure_pa']} | "
            f"{node['specified_injection_m3_h']} | "
            f"{node['mass_balance_residual_m3_h']} |"
        )

    lines.extend(["", "## Engineering note", "", result["scope_note"], ""])
    return "\n".join(lines)
