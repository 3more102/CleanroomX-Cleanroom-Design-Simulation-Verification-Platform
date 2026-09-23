from __future__ import annotations


def markdown_damper_study_report(result: dict) -> str:
    lines = [
        f"# CleanroomX Damper Case Study — {result['study']}",
        "",
        f"- Status: **{result['status'].upper()}**",
        f"- Base network: **{result['network']}**",
        f"- Baseline pressure span: **{result['baseline_pressure_span_pa']} Pa**",
        f"- Cases: **{len(result['cases'])}**",
        "",
        "## Case summary",
        "",
        "| Case | Pressure span (Pa) | Change vs baseline (Pa) |",
        "|---|---:|---:|",
    ]
    for case in result["cases"]:
        lines.append(
            f"| {case['name']} | {case['pressure_span_pa']} | "
            f"{case['pressure_span_change_pa']} |"
        )

    for case in result["cases"]:
        lines.extend(
            [
                "",
                f"## Case — {case['name']}",
                "",
                "### Damper settings",
                "",
                "| Edge | Position (%) | Label | Base R [Pa/(m³/s)²] | Added damper R [Pa/(m³/s)²] | Total R [Pa/(m³/s)²] | Solved airflow (m³/h) | Damper ΔP (Pa) |",
                "|---|---:|---|---:|---:|---:|---:|---:|",
            ]
        )
        for setting in case["settings"]:
            position = (
                "—"
                if setting["position_percent"] is None
                else setting["position_percent"]
            )
            label = setting["setting_label"] or "—"
            lines.append(
                f"| {setting['edge_name']} | {position} | {label} | "
                f"{setting['base_resistance_pa_per_m3_s_squared']} | "
                f"{setting['added_resistance_pa_per_m3_s_squared']} | "
                f"{setting['total_resistance_pa_per_m3_s_squared']} | "
                f"{setting['solved_airflow_m3_h']} | "
                f"{setting['damper_pressure_difference_pa']} |"
            )

        lines.extend(
            [
                "",
                "### Edge airflow comparison",
                "",
                "| Edge | Baseline airflow (m³/h) | Case airflow (m³/h) | Change (m³/h) | Case direction |",
                "|---|---:|---:|---:|---|",
            ]
        )
        for edge in case["flow_changes"]:
            lines.append(
                f"| {edge['edge_name']} | {edge['baseline_airflow_m3_h']} | "
                f"{edge['case_airflow_m3_h']} | {edge['airflow_change_m3_h']} | "
                f"{edge['case_flow_direction']} |"
            )

        network = case["network_solution"]
        lines.extend(
            [
                "",
                f"- Maximum continuity residual: **{network['max_abs_mass_balance_residual_m3_h']} m³/h**",
                f"- Maximum pressure-law residual: **{network['max_abs_pressure_law_residual_pa']} Pa**",
            ]
        )

    lines.extend(["", "## Engineering note", "", result["scope_note"], ""])
    return "\n".join(lines)
