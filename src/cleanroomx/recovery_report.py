from __future__ import annotations


def markdown_recovery_report(result: dict) -> str:
    lines = [f"# CleanroomX Recovery Test Report — {result['test']}", ""]
    lines.extend(
        [
            "## Result",
            "",
            f"- Particle size: **{result['particle_size_um']} µm**",
            f"- Target concentration: **{result['target_concentration_per_m3']} particles/m³**",
            f"- Target reached: **{'yes' if result['reached_target'] else 'no'}**",
            f"- Observed recovery time: **{result['observed_recovery_time_minutes'] if result['observed_recovery_time_minutes'] is not None else 'not reached'} min**",
            f"- Configured maximum recovery time: **{result['max_recovery_time_minutes'] if result['max_recovery_time_minutes'] is not None else 'not configured'}**",
            f"- Criterion status: **{result['criterion_status'].upper()}**",
            "",
            result["criterion_message"],
            "",
        ]
    )

    metadata = result["metadata"]
    if any(value is not None for value in metadata.values()):
        lines.extend(["## Traceability", ""])
        for key, value in metadata.items():
            if value is not None:
                lines.append(f"- {key.replace('_', ' ').title()}: {value}")
        lines.append("")

    lines.extend(
        [
            "## Samples",
            "",
            "| Time (min) | Concentration (particles/m³) | At/below target |",
            "|---:|---:|---|",
        ]
    )
    for sample in result["samples"]:
        lines.append(
            f"| {sample['time_minutes']} | {sample['concentration_per_m3']} | "
            f"{'yes' if sample['at_or_below_target'] else 'no'} |"
        )

    fit = result["log_linear_fit"]
    lines.extend(["", "## Log-linear diagnostic", ""])
    if not fit["available"]:
        lines.append(fit["reason"])
    else:
        lines.extend(
            [
                f"- ln(C) slope: {fit['slope_ln_concentration_per_min']} 1/min",
                f"- R²: {fit['r_squared']}",
                f"- Estimated effective ACH: {fit['estimated_effective_ach_1_h']}",
                f"- Fitted target crossing: {fit['fitted_target_crossing_time_minutes']} min",
                "",
                fit["screening_note"],
            ]
        )

    lines.extend(["", "## Engineering note", "", result["engineering_note"], ""])
    return "\n".join(lines)
