from __future__ import annotations


def markdown_reference_geometry_loop_report(result: dict) -> str:
    lines = [
        f"# CleanroomX Reference-Geometry Looped-Duct Report — {result['network']}",
        "",
        "## Solver summary",
        "",
        f"- Status: **{result['status'].upper()}**",
        f"- Reference node: **{result['reference_node']} = 0 Pa**",
        f"- Newton iterations: **{result['iterations']}**",
        f"- Mass-balance tolerance: **{result['mass_balance_tolerance_m3_h']} m³/h**",
        f"- Maximum node continuity residual: **{result['max_abs_mass_balance_residual_m3_h']} m³/h**",
        f"- Maximum edge pressure-law residual: **{result['max_abs_pressure_law_residual_pa']} Pa**",
        f"- Maximum geometry pressure residual: **{result['max_abs_geometry_pressure_residual_pa']} Pa**",
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
            "## Geometry-derived edges",
            "",
            "| Edge | Sections | Reference flow (m³/h) | Reference ΔP (Pa) | Derived R [Pa/(m³/s)²] | Solved airflow (m³/h) | Actual direction | Geometry residual (Pa) |",
            "|---|---:|---:|---:|---:|---:|---|---:|",
        ]
    )
    for edge in result["edges"]:
        lines.append(
            f"| {edge['name']} | {edge['section_count']} | "
            f"{edge['reference_airflow_m3_h']} | "
            f"{edge['reference_pressure_drop_pa']} | "
            f"{edge['resistance_pa_per_m3_s_squared']} | "
            f"{edge['airflow_m3_h']} | {edge['flow_direction']} | "
            f"{edge['geometry_pressure_residual_pa']} |"
        )

    lines.extend(
        [
            "",
            "## Section reference evidence",
            "",
            "| Edge | Section | Shape | Reference velocity (m/s) | Darcy f | Method | Re | K | Reference ΔP (Pa) | Section R [Pa/(m³/s)²] | Solved velocity (m/s) | Solved ΔP magnitude (Pa) |",
            "|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for edge in result["edges"]:
        for section in edge["sections"]:
            lines.append(
                f"| {edge['name']} | {section['name']} | {section['shape']} | "
                f"{section['reference_velocity_m_s']} | "
                f"{section['friction_factor']} | "
                f"{section['friction_factor_method']} | "
                f"{section['reynolds_number']} | "
                f"{section['local_loss_coefficient']} | "
                f"{section['reference_pressure_drop_pa']} | "
                f"{section['derived_resistance_pa_per_m3_s_squared']} | "
                f"{section['solved_velocity_m_s']} | "
                f"{section['solved_pressure_drop_magnitude_pa']} |"
            )

    lines.extend(["", "## Engineering note", "", result["scope_note"], ""])
    return "\n".join(lines)
