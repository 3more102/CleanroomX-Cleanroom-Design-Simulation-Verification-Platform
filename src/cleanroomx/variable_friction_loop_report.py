from __future__ import annotations

from .loop_network_report import markdown_looped_network_report


def markdown_variable_friction_loop_report(result: dict) -> str:
    text = markdown_looped_network_report(result).rstrip()
    info = result["variable_friction"]
    lines = [
        text,
        "",
        "## Variable-friction convergence",
        "",
        f"- Converged: **{info['converged']}**",
        f"- Outer iterations: **{info['outer_iterations']}**",
        "- Automatic-friction edges: "
        f"**{info['automatic_friction_edge_count']}**",
        "- Near-zero frozen edges: "
        f"**{info['near_zero_frozen_edge_count']}**",
        "- Relative resistance tolerance: "
        f"**{info['resistance_relative_tolerance']}**",
        f"- Relaxation: **{info['relaxation']}**",
        "- Maximum relative resistance closure error: "
        f"**{info['max_relative_resistance_closure_error']}**",
        "",
        "### Edge closure",
        "",
        "| Edge | State | Airflow (m³/h) | Used R | Target R | Relative change | Target Darcy f | Target method | Reynolds |",
        "|---|---|---:|---:|---:|---:|---:|---|---:|",
    ]
    for row in info["edge_closure"]:
        target_r = (
            "—"
            if row["target_resistance_pa_per_m3_s_squared"] is None
            else row["target_resistance_pa_per_m3_s_squared"]
        )
        target_f = (
            "—"
            if row["target_friction_factor"] is None
            else row["target_friction_factor"]
        )
        method = (
            "—"
            if row["target_friction_factor_method"] is None
            else row["target_friction_factor_method"]
        )
        reynolds = (
            "—"
            if row["target_reynolds_number"] is None
            else row["target_reynolds_number"]
        )
        lines.append(
            f"| {row['name']} | {row['state']} | "
            f"{row['airflow_m3_h']} | "
            f"{row['used_resistance_pa_per_m3_s_squared']} | "
            f"{target_r} | {row['relative_resistance_change']} | "
            f"{target_f} | {method} | {reynolds} |"
        )

    if info["iteration_history"]:
        lines.extend(
            [
                "",
                "### Outer-iteration history",
                "",
                "| Iteration | Max relative R change | Max continuity residual (m³/h) | Near-zero frozen edges |",
                "|---:|---:|---:|---:|",
            ]
        )
        for row in info["iteration_history"]:
            lines.append(
                f"| {row['outer_iteration']} | "
                f"{row['max_relative_resistance_change']} | "
                f"{row['max_abs_mass_balance_residual_m3_h']} | "
                f"{row['near_zero_frozen_edge_count']} |"
            )

    lines.append("")
    return "\n".join(lines)
