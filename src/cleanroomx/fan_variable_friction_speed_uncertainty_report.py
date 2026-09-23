from __future__ import annotations


def markdown_fan_variable_friction_speed_uncertainty_report(
    result: dict,
) -> str:
    lines = [
        "# CleanroomX Fan-Speed / Variable-Friction Uncertainty Study — "
        f"{result['study']}",
        "",
        f"- Reference fan curve: **{result['reference_fan_curve']}**",
        f"- Loop network: **{result['loop_network']}**",
        f"- Overall status: **{result['status'].upper()}**",
        f"- Speed cases: **{result['speed_case_count']}**",
        "- Uncertainty corners per speed: "
        f"**{result['uncertainty_corner_count_per_speed']}**",
        "- Total speed × corner cases: "
        f"**{result['total_speed_corner_case_count']}**",
        "- Speed cases with incomplete uncertainty envelopes: "
        f"**{result['unresolved_speed_case_count']}**",
    ]
    if result["reference_speed_rpm"] is not None:
        lines.append(
            f"- Reference fan speed: **{result['reference_speed_rpm']} rpm**"
        )

    lines.extend(
        [
            "",
            "## Speed × uncertainty summary",
            "",
            "| Speed ratio | Speed rpm | Status | Corners solved | Airflow envelope m³/h | System-pressure envelope Pa | Provenance complete |",
            "|---:|---:|---|---:|---|---|---|",
        ]
    )
    for case in result["speed_cases"]:
        envelope = case["operating_point_envelope"]
        if envelope is None:
            airflow = pressure = "—"
        else:
            airflow = (
                f"{envelope['airflow_m3_h']['lower']}–"
                f"{envelope['airflow_m3_h']['upper']}"
            )
            pressure = (
                f"{envelope['system_pressure_pa']['lower']}–"
                f"{envelope['system_pressure_pa']['upper']}"
            )
        rpm = "—" if case["speed_rpm"] is None else case["speed_rpm"]
        lines.append(
            f"| {case['speed_ratio']} | {rpm} | {case['status']} | "
            f"{case['solved_corner_count']}/{case['corner_count']} | "
            f"{airflow} | {pressure} | "
            f"{case['traceability']['complete']} |"
        )

    unresolved = [
        case for case in result["speed_cases"] if case["status"] != "complete"
    ]
    if unresolved:
        lines.extend(["", "## Incomplete speed cases", ""])
        for case in unresolved:
            lines.append(
                f"- **{case['speed_ratio']}x**: nominal state "
                f"`{case['nominal_status']}`, unresolved uncertainty corners "
                f"**{case['unresolved_corner_count']}**."
            )

    lines.extend(["", "## Engineering note", "", result["scope_note"], ""])
    return "\n".join(lines)
