from __future__ import annotations


def markdown_loop_damper_study_report(result: dict) -> str:
    baseline = result["baseline_solution"]
    lines = [
        f"# CleanroomX Loop Damper-Resistance Study — {result['study']}",
        "",
        f"- Base network: **{result['base_network']}**",
        f"- Status: **{result['status'].upper()}**",
        "- Baseline maximum continuity residual: "
        f"**{baseline['max_abs_mass_balance_residual_m3_h']} m³/h**",
        "- Baseline maximum pressure-law residual: "
        f"**{baseline['max_abs_pressure_law_residual_pa']} Pa**",
        "",
        "## Baseline edge flows",
        "",
        "| Edge | Airflow (m³/h) | Actual direction | "
        "Resistance [Pa/(m³/s)²] | Basis |",
        "|---|---:|---|---:|---|",
    ]
    for edge in baseline["edges"]:
        lines.append(
            f"| {edge['name']} | {edge['airflow_m3_h']} | "
            f"{edge['flow_direction']} | "
            f"{edge['resistance_pa_per_m3_s_squared']} | "
            f"{edge['resistance_basis']} |"
        )

    for case in result["cases"]:
        solution = case["network_solution"]
        lines.extend(
            [
                "",
                f"## Case — {case['name']}",
                "",
                f"- Status: **{case['status'].upper()}**",
                "- Maximum continuity residual: "
                f"**{solution['max_abs_mass_balance_residual_m3_h']} m³/h**",
                "- Maximum pressure-law residual: "
                f"**{solution['max_abs_pressure_law_residual_pa']} Pa**",
                "",
                "### Resistance adjustments",
                "",
                "| Edge | Multiplier | Base R | Adjusted R | Base basis |",
                "|---|---:|---:|---:|---|",
            ]
        )
        for item in case["adjustments"]:
            lines.append(
                f"| {item['edge']} | {item['resistance_multiplier']} | "
                f"{item['base_resistance_pa_per_m3_s_squared']} | "
                f"{item['adjusted_resistance_pa_per_m3_s_squared']} | "
                f"{item['base_resistance_basis']} |"
            )

        lines.extend(
            [
                "",
                "### Flow redistribution",
                "",
                "| Edge | Baseline flow (m³/h) | Case flow (m³/h) | "
                "Delta (m³/h) | Change (%) |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for row in case["flow_changes"]:
            percent = (
                "n/a"
                if row["percent_change"] is None
                else row["percent_change"]
            )
            lines.append(
                f"| {row['edge']} | {row['baseline_airflow_m3_h']} | "
                f"{row['case_airflow_m3_h']} | "
                f"{row['delta_airflow_m3_h']} | {percent} |"
            )

    lines.extend(["", "## Engineering note", "", result["scope_note"], ""])
    return "\n".join(lines)
