from __future__ import annotations


def _fmt(value: object) -> str:
    return "—" if value is None else str(value)


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

    uncertainty = result["uncertainty_summary"]
    lines.extend(
        [
            "## Measurement uncertainty",
            "",
            f"- Coverage: **{uncertainty['coverage']}** "
            f"({uncertainty['samples_with_uncertainty']}/{uncertainty['sample_count']} samples)",
            f"- First certainly at/below target: **{_fmt(uncertainty['first_certainly_at_or_below_target_time_minutes'])} min**",
            f"- Nominal recovery-sample uncertainty status: **{_fmt(uncertainty['nominal_recovery_sample_uncertainty_status'])}**",
            f"- Indeterminate samples: **{uncertainty['indeterminate_count']}**",
            "",
            uncertainty["note"],
            "",
        ]
    )

    lines.extend(
        [
            "## Samples",
            "",
            "| Time (min) | Concentration (particles/m³) | Nominal target | Uncertainty lower | Uncertainty upper | Uncertainty status |",
            "|---:|---:|---|---:|---:|---|",
        ]
    )
    for sample in result["samples"]:
        interval = sample["uncertainty"]
        lines.append(
            f"| {sample['time_minutes']} | {sample['concentration_per_m3']} | "
            f"{'at/below' if sample['at_or_below_target'] else 'above'} | "
            f"{_fmt(interval['lower_bound'])} | {_fmt(interval['upper_bound'])} | "
            f"{interval['status']} |"
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
