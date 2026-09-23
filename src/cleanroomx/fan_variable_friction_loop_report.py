from __future__ import annotations


def markdown_fan_variable_friction_loop_report(result: dict) -> str:
    diagnostics = result["solver_diagnostics"]
    lines = [
        f"# CleanroomX Fan / Variable-Friction Loop Report — {result['study']}",
        "",
        f"- Fan curve: **{result['fan_curve']}**",
        f"- Status: **{result['status'].upper()}**",
        f"- Fan discharge node: **{result['fan_discharge_node']}**",
        f"- Fan suction node: **{result['fan_suction_node']}**",
        f"- Fixed pressure: **{result['fixed_pressure_pa']} Pa**",
        "- Fan-curve airflow range: "
        f"**{result['fan_curve_airflow_range_m3_h'][0]}–"
        f"{result['fan_curve_airflow_range_m3_h'][1]} m³/h**",
        "",
        "## Solver diagnostics",
        "",
        f"- Converged: **{diagnostics['converged']}**",
        f"- Termination reason: **{diagnostics['termination_reason']}**",
        "- Operating-point pressure tolerance: "
        f"**{diagnostics['operating_pressure_tolerance_pa']} Pa**",
        f"- Operating iterations: **{diagnostics['operating_iterations']}**",
    ]

    point = result["fan_operating_point"]
    if point is None:
        lines.extend(["", "## Operating point", "", result["message"]])
    else:
        network = result["operating_network_solution"]
        check = result["system_pressure_check"]
        variable = network["variable_friction"]
        lines.extend(
            [
                "",
                "## Operating point",
                "",
                f"- Airflow: **{point['airflow_m3_h']} m³/h**",
                f"- Fan pressure: **{point['fan_pressure_pa']} Pa**",
                "- Variable-friction loop pressure: "
                f"**{check['loop_network_pressure_pa']} Pa**",
                f"- Total system pressure: **{check['total_system_pressure_pa']} Pa**",
                "- Fan-system pressure residual: "
                f"**{check['fan_minus_system_pressure_pa']} Pa**",
                f"- Fluid air power: **{point['air_power_kw']} kW**",
                "- Network outer iterations: "
                f"**{variable['outer_iterations']}**",
                "- Maximum relative resistance closure error: "
                f"**{variable['max_relative_resistance_closure_error']}**",
                "- Maximum continuity residual: "
                f"**{network['max_abs_mass_balance_residual_m3_h']} m³/h**",
                "- Maximum edge pressure-law residual: "
                f"**{network['max_abs_pressure_law_residual_pa']} Pa**",
                "",
                "### Operating loop edges",
                "",
                "| Edge | Basis | Airflow (m³/h) | Direction | Resistance Pa/(m³/s)² |",
                "|---|---|---:|---|---:|",
            ]
        )
        for edge in network["edges"]:
            lines.append(
                f"| {edge['name']} | {edge['resistance_basis']} | "
                f"{edge['airflow_m3_h']} | {edge['flow_direction']} | "
                f"{edge['resistance_pa_per_m3_s_squared']} |"
            )

        lines.extend(
            [
                "",
                "### Variable-friction edge closure",
                "",
                "| Edge | State | Airflow (m³/h) | Used R | Target R | Relative change | Reynolds |",
                "|---|---|---:|---:|---:|---:|---:|",
            ]
        )
        for row in variable["edge_closure"]:
            target_r = (
                "—"
                if row["target_resistance_pa_per_m3_s_squared"] is None
                else row["target_resistance_pa_per_m3_s_squared"]
            )
            reynolds = (
                "—"
                if row["target_reynolds_number"] is None
                else row["target_reynolds_number"]
            )
            lines.append(
                f"| {row['name']} | {row['state']} | {row['airflow_m3_h']} | "
                f"{row['used_resistance_pa_per_m3_s_squared']} | {target_r} | "
                f"{row['relative_resistance_change']} | {reynolds} |"
            )

    lines.extend(
        [
            "",
            "## Supplied fan-curve checks",
            "",
            "| Airflow (m³/h) | Fan pressure (Pa) | Loop pressure (Pa) | Total system pressure (Pa) | Margin (Pa) | Network outer iterations |",
            "|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in result["fan_curve_point_checks"]:
        lines.append(
            f"| {row['airflow_m3_h']} | {row['fan_pressure_pa']} | "
            f"{row['loop_network_pressure_pa']} | {row['system_pressure_pa']} | "
            f"{row['pressure_margin_pa']} | {row['network_outer_iterations']} |"
        )

    lines.extend(["", "## Engineering note", "", result["scope_note"], ""])
    return "\n".join(lines)
