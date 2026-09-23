from __future__ import annotations


def markdown_recovery_report(result: dict) -> str:
    lines = [f"# CleanroomX Recovery Test Report — {result['test']}", ""]
    lines.extend(
        [
            "## Result",
            "",
            f"- Particle size: **{result['particle_size_um']} µm**",
            f"- Target concentration: **{result['target_concentration_per_m3']} particles/m³**",
            f"- Target state: **{result.get('target_state', 'reached' if result['reached_target'] else 'not_reached').upper()}**",
            f"- Definitely reached: **{'yes' if result['reached_target'] else 'no'}**",
            f"- Definite recovery time: **{result['observed_recovery_time_minutes'] if result['observed_recovery_time_minutes'] is not None else 'not demonstrated'} min**",
            f"- First possible recovery sample: **{result.get('possible_recovery_time_minutes') if result.get('possible_recovery_time_minutes') is not None else 'none'} min**",
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
            "| Time (min) | Concentration (particles/m³) | ± uncertainty | Interval | Target relation |",
            "|---:|---:|---:|---:|---|",
        ]
    )
    for sample in result["samples"]:
        interval = sample.get("concentration_interval_per_m3", {})
        uncertainty = sample.get("concentration_uncertainty_per_m3", 0.0)
        relation = sample.get(
            "target_relation",
            "at_or_below" if sample["at_or_below_target"] else "above",
        )
        lines.append(
            f"| {sample['time_minutes']} | {sample['concentration_per_m3']} | "
            f"{uncertainty} | {interval.get('lower_bound', sample['concentration_per_m3'])} "
            f"to {interval.get('upper_bound', sample['concentration_per_m3'])} | "
            f"{relation} |"
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
