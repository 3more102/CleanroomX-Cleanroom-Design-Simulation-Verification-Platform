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
            "| Edge | Declared start | Declared end | Solved airflow (m³/h) | Actual direction | Pressure difference (Pa) | R [Pa/(m³/s)²] | R source | Pressure-law residual (Pa) |",
            "|---|---|---|---:|---|---:|---:|---|---:|",
        ]
    )
    for edge in result["edges"]:
        basis = edge.get("resistance_basis") or {}
        source = basis.get("source", "programmatic")
        lines.append(
            f"| {edge['name']} | {edge['start_node']} | {edge['end_node']} | "
            f"{edge['airflow_m3_h']} | {edge['flow_direction']} | "
            f"{edge['pressure_difference_pa']} | "
            f"{edge['resistance_pa_per_m3_s_squared']} | {source} | "
            f"{edge['pressure_law_residual_pa']} |"
        )

    derived_edges = [
        edge
        for edge in result["edges"]
        if (edge.get("resistance_basis") or {}).get("source") == "duct_geometry"
    ]
    if derived_edges:
        lines.extend(
            [
                "",
                "## Duct-derived resistance evidence",
                "",
                "| Edge | Shape | Reference airflow (m³/h) | Reference drop (Pa) | Darcy f | Friction method | Reynolds number |",
                "|---|---|---:|---:|---:|---|---:|",
            ]
        )
        for edge in derived_edges:
            basis = edge["resistance_basis"]
            reynolds = basis.get("reynolds_number")
            reynolds_text = "" if reynolds is None else str(round(reynolds, 3))
            lines.append(
                f"| {edge['name']} | {basis['shape']} | "
                f"{round(basis['reference_airflow_m3_h'], 3)} | "
                f"{round(basis['reference_pressure_drop_pa'], 4)} | "
                f"{round(basis['friction_factor'], 6)} | "
                f"{basis['friction_factor_method']} | {reynolds_text} |"
            )

    lines.extend(["", "## Engineering note", "", result["scope_note"], ""])
    return "\n".join(lines)
