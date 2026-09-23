from __future__ import annotations


def markdown_recovery_report(result: dict) -> str:
    lines = [f"# CleanroomX Recovery Test Report — {result['name']}", ""]
    lines.extend(
        [
            "## Summary",
            "",
            f"- Initial concentration: **{result['initial_concentration_per_m3']} particles/m³**.",
            f"- Target concentration: **{result['target_concentration_per_m3']} particles/m³**.",
            f"- Final measured concentration: **{result['final_concentration_per_m3']} particles/m³**.",
            f"- Observed first target crossing: **{result['observed_recovery_time_minutes']} min**.",
        ]
    )
    if result["max_recovery_time_minutes"] is not None:
        lines.append(
            f"- Configured maximum recovery time: **{result['max_recovery_time_minutes']} min**; "
            f"pass: **{result['passes_max_recovery_time']}**."
        )

    fit = result["fit"]
    lines.extend(
        [
            "",
            "## Log-linear fit",
            "",
            f"- Effective removal rate: **{fit['fitted_effective_removal_rate_per_h']} 1/h**.",
            f"- Fitted half-life: **{fit['fitted_half_life_minutes']} min**.",
            f"- R² on ln(concentration): **{fit['r_squared_log_concentration']}**.",
        ]
    )

    model = result["screening_model"]
    if model["design_ach"] is not None:
        lines.extend(
            [
                "",
                "## Screening-model comparison",
                "",
                f"- Design ACH: **{model['design_ach']} 1/h**.",
                f"- Removal efficiency: **{model['removal_efficiency']}**.",
                f"- Predicted recovery time: **{model['predicted_recovery_time_minutes']} min**.",
                f"- Observed minus predicted: **{model['observed_minus_predicted_minutes']} min**.",
            ]
        )

    lines.extend(
        [
            "",
            "## Samples",
            "",
            "| Time min | Concentration particles/m³ |",
            "|---:|---:|",
        ]
    )
    for sample in result["samples"]:
        lines.append(
            f"| {sample['time_minutes']} | {sample['concentration_per_m3']} |"
        )

    lines.extend(
        ["", "## Engineering note", "", result["engineering_note"], ""]
    )
    return "\n".join(lines)
