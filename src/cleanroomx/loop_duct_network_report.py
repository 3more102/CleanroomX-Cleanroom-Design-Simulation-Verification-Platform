from __future__ import annotations


def markdown_geometry_derived_loop_report(result: dict) -> str:
    lines = [
        f"# CleanroomX Geometry-Derived Looped-Network Report — {result['network']}",
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
            f"{node['specified_injection_m3_h']} | {node['net_edge_outflow_m3_h']} | "
            f"{node['mass_balance_residual_m3_h']} |"
        )

    lines.extend(
        [
            "",
            "## Geometry-derived edges",
            "",
            "| Edge | Solved airflow (m³/h) | Reference airflow (m³/h) | |Q solved| / Q ref | Derived R [Pa/(m³/s)²] | Pressure difference (Pa) |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for edge in result["edges"]:
        lines.append(
            f"| {edge['name']} | {edge['airflow_m3_h']} | "
            f"{edge['reference_airflow_m3_h']} | "
            f"{edge['absolute_solved_to_reference_flow_ratio']} | "
            f"{edge['resistance_pa_per_m3_s_squared']} | "
            f"{edge['pressure_difference_pa']} |"
        )

    lines.extend(
        [
            "",
            "## Resistance derivation evidence",
            "",
            "| Edge | Section | Shape | Darcy f | Method | Reynolds number | Section R [Pa/(m³/s)²] | Reference ΔP (Pa) |",
            "|---|---|---|---:|---|---:|---:|---:|",
        ]
    )
    for edge in result["edges"]:
        basis = edge["resistance_derivation"]
        for section in basis["sections"]:
            lines.append(
                f"| {edge['name']} | {section['name']} | {section['shape']} | "
                f"{section['friction_factor']} | {section['friction_factor_method']} | "
                f"{section['reynolds_number']} | "
                f"{section['quadratic_resistance_pa_per_m3_s_squared']} | "
                f"{section['reference_pressure_drop_pa']} |"
            )

    lines.extend(["", "## Engineering note", "", result["scope_note"], ""])
    return "\n".join(lines)
