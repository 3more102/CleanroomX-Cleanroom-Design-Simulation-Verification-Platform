from __future__ import annotations


def markdown_geometry_loop_report(result: dict) -> str:
    lines = [
        f"# CleanroomX Geometry-Derived Looped-Duct Report — {result['network']}",
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
            "| Edge | Sections | Derived R [Pa/(m³/s)²] | Airflow (m³/h) | Actual direction | Pressure difference (Pa) | Geometry residual (Pa) |",
            "|---|---:|---:|---:|---|---:|---:|",
        ]
    )
    for edge in result["edges"]:
        lines.append(
            f"| {edge['name']} | {edge['section_count']} | "
            f"{edge['resistance_pa_per_m3_s_squared']} | "
            f"{edge['airflow_m3_h']} | {edge['flow_direction']} | "
            f"{edge['pressure_difference_pa']} | "
            f"{edge['geometry_pressure_residual_pa']} |"
        )

    lines.extend(
        [
            "",
            "## Section evidence",
            "",
            "| Edge | Section | Shape | Area (m²) | Dh (m) | Darcy f | K | Section R [Pa/(m³/s)²] | Velocity (m/s) | Friction ΔP (Pa) | Local ΔP (Pa) | Total ΔP magnitude (Pa) |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for edge in result["edges"]:
        for section in edge["sections"]:
            lines.append(
                f"| {edge['name']} | {section['name']} | {section['shape']} | "
                f"{section['area_m2']} | {section['hydraulic_diameter_m']} | "
                f"{section['friction_factor']} | {section['local_loss_coefficient']} | "
                f"{section['resistance_pa_per_m3_s_squared']} | "
                f"{section['velocity_m_s']} | "
                f"{section['friction_pressure_drop_pa']} | "
                f"{section['local_pressure_drop_pa']} | "
                f"{section['total_pressure_drop_pa']} |"
            )

    lines.extend(["", "## Engineering note", "", result["scope_note"], ""])
    return "\n".join(lines)
