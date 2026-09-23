from __future__ import annotations


def markdown_recovery_uncertainty_report(
    result: dict,
) -> str:
    lines = [
        "# CleanroomX Recovery Uncertainty Report — "
        f"{result['analysis']}",
        "",
        "## Result",
        "",
        (
            "- Particle size: "
            f"**{result['particle_size_um']} µm**"
        ),
        (
            "- Target concentration: "
            f"**{result['target_concentration_per_m3']} "
            "particles/m³**"
        ),
        (
            "- Maximum recovery time: **"
            f"{result['max_recovery_time_minutes'] "
            "if result['max_recovery_time_minutes'] "
            "is not None else 'not configured'}**"
        ),
        (
            "- Recovery observation: **"
            f"{result['target_recovery_status'].upper()}**"
        ),
        (
            "- First possible recovery sample: **"
            f"{result['first_possible_recovery_time_minutes'] "
            "if result['first_possible_recovery_time_minutes'] "
            "is not None else 'not observed'} min**"
        ),
        (
            "- First definite recovery sample: **"
            f"{result['first_definite_recovery_time_minutes'] "
            "if result['first_definite_recovery_time_minutes'] "
            "is not None else 'not observed'} min**"
        ),
        (
            "- Criterion status: **"
            f"{result['criterion_status'].upper()}**"
        ),
        "",
        result["criterion_message"],
        "",
        "## Samples",
        "",
        (
            "| Time (min) | Nominal concentration | "
            "± uncertainty | Interval | Target status |"
        ),
        "|---:|---:|---:|---:|---|",
    ]

    for sample in result["samples"]:
        interval = sample[
            "concentration_interval_per_m3"
        ]
        lines.append(
            f"| {sample['time_minutes']} | "
            f"{sample['concentration_per_m3']} | "
            f"{sample['concentration_uncertainty_abs']} | "
            f"{interval['lower']}–{interval['upper']} | "
            f"{sample['target_status']} |"
        )

    trace = result["traceability"]
    lines.extend(
        [
            "",
            "## Traceability",
            "",
            (
                "- Inputs with provenance: **"
                f"{trace['inputs_with_provenance']}/"
                f"{trace['input_count']}**"
            ),
            (
                "- Complete: **"
                f"{'yes' if trace['complete'] else 'no'}**"
            ),
        ]
    )
    if trace["missing_provenance"]:
        lines.append(
            "- Missing provenance: "
            + ", ".join(trace["missing_provenance"])
        )

    metadata = result["metadata"]
    if any(
        value is not None for value in metadata.values()
    ):
        lines.extend(["", "## Test metadata", ""])
        for key, value in metadata.items():
            if value is not None:
                lines.append(
                    f"- {key.replace('_', ' ').title()}: "
                    f"{value}"
                )

    lines.extend(
        [
            "",
            "## Engineering note",
            "",
            result["engineering_note"],
            "",
        ]
    )
    return "\n".join(lines)
