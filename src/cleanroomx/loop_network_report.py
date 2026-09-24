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
        "- Net node-injection pressure power: "
        f"**{result['pressure_power']['net_node_injection_power_w']} W**",
        "- Total edge pressure-power dissipation: "
        f"**{result['pressure_power']['total_edge_dissipation_w']} W**",
        "- Pressure-power balance residual: "
        f"**{result['pressure_power']['balance_residual_w']} W**",
        "",
        "## Nodes",
        "",
        "| Node | Relative pressure (Pa) | Specified injection (m³/h) | Net edge outflow (m³/h) | Continuity residual (m³/h) | Specified pressure power (W) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for node in result["nodes"]:
        lines.append(
            f"| {node['name']} | {node['relative_pressure_pa']} | "
            f"{node['specified_injection_m3_h']} | "
            f"{node['net_edge_outflow_m3_h']} | "
            f"{node['mass_balance_residual_m3_h']} | "
            f"{node['specified_pressure_power_w']} |"
        )

    lines.extend(
        [
            "",
            "## Edges",
            "",
            "| Edge | Declared start | Declared end | Solved airflow (m³/h) | Actual direction | Pressure difference (Pa) | R [Pa/(m³/s)²] | R basis | Pressure-law residual (Pa) | Dissipated pressure power (W) |",
            "|---|---|---|---:|---|---:|---:|---|---:|---:|",
        ]
    )
    for edge in result["edges"]:
        lines.append(
            f"| {edge['name']} | {edge['start_node']} | {edge['end_node']} | "
            f"{edge['airflow_m3_h']} | {edge['flow_direction']} | "
            f"{edge['pressure_difference_pa']} | "
            f"{edge['resistance_pa_per_m3_s_squared']} | "
            f"{edge.get('resistance_basis', 'explicit')} | "
            f"{edge['pressure_law_residual_pa']} | "
            f"{edge['dissipated_pressure_power_w']} |"
        )

    derived_edges = [
        edge for edge in result["edges"]
        if edge.get("resistance_basis") == "duct_geometry"
        and edge.get("resistance_evidence") is not None
    ]
    if derived_edges:
        lines.extend(
            [
                "",
                "## Geometry-derived resistance evidence",
                "",
                "| Edge | Shape | Area (m²) | Dh (m) | Darcy f | Friction method | Local K | Reference airflow (m³/h) | R [Pa/(m³/s)²] |",
                "|---|---|---:|---:|---:|---|---:|---:|---:|",
            ]
        )
        for edge in derived_edges:
            evidence = edge["resistance_evidence"]
            reference_airflow = (
                "—"
                if evidence["reference_airflow_m3_h"] is None
                else evidence["reference_airflow_m3_h"]
            )
            lines.append(
                f"| {edge['name']} | {evidence['shape']} | "
                f"{evidence['area_m2']:.9g} | "
                f"{evidence['hydraulic_diameter_m']:.9g} | "
                f"{evidence['friction_factor']:.9g} | "
                f"{evidence['friction_factor_method']} | "
                f"{evidence['local_loss_coefficient']:.9g} | "
                f"{reference_airflow} | "
                f"{edge['resistance_pa_per_m3_s_squared']} |"
            )

    lines.extend(["", "## Engineering note", "", result["scope_note"], ""])
    return "\n".join(lines)
