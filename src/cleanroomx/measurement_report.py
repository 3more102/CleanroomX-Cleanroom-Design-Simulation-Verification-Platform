from __future__ import annotations


def markdown_measurement_report(result: dict) -> str:
    interval = result["coverage_interval"]
    lines = [
        f"# CleanroomX Measurement Uncertainty Report — {result['measurand']}",
        "",
        "## Result",
        "",
        f"- Measured value: **{result['value']} {result['unit']}**",
        (
            "- Combined standard uncertainty: "
            f"**{result['combined_standard_uncertainty']} {result['unit']}**"
        ),
        f"- Coverage factor: **{result['coverage_factor']}**",
        f"- Expanded uncertainty: **{result['expanded_uncertainty']} {result['unit']}**",
        (
            "- Expanded-uncertainty interval: "
            f"**[{interval['lower_bound']}, {interval['upper_bound']}] {result['unit']}**"
        ),
        f"- Criterion status: **{result['criterion_status'].upper()}**",
        "",
        result["criterion_message"],
        "",
    ]

    requirement = result["requirement"]
    if requirement is not None:
        lines.extend(["## Requirement", ""])
        lines.append(f"- Kind: {requirement['kind']}")
        if requirement["lower_limit"] is not None:
            lines.append(f"- Lower limit: {requirement['lower_limit']} {result['unit']}")
        if requirement["upper_limit"] is not None:
            lines.append(f"- Upper limit: {requirement['upper_limit']} {result['unit']}")
        if requirement["reference"]:
            lines.append(f"- Reference: {requirement['reference']}")
        lines.append("")

    provenance = result["provenance"]
    if any(value is not None for value in provenance.values()):
        lines.extend(["## Traceability / provenance", ""])
        for key, value in provenance.items():
            if value is not None:
                lines.append(f"- {key.replace('_', ' ').title()}: {value}")
        lines.append("")

    lines.extend(
        [
            "## Uncertainty budget",
            "",
            "| Component | Type | Standard uncertainty | Sensitivity coefficient | Standard contribution | Source |",
            "|---|---|---:|---:|---:|---|",
        ]
    )
    for component in result["components"]:
        lines.append(
            "| "
            f"{component['name']} | "
            f"{component['evaluation_type'] or ''} | "
            f"{component['standard_uncertainty']} | "
            f"{component['sensitivity_coefficient']} | "
            f"{component['standard_contribution']} | "
            f"{component['source'] or ''} |"
        )

    lines.extend(["", "## Engineering note", "", result["engineering_note"], ""])
    return "\n".join(lines)
