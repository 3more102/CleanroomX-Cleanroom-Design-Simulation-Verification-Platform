from __future__ import annotations


def markdown_fan_speed_report(result: dict) -> str:
    lines = [
        f"# CleanroomX Fan-Speed Study — {result['study']}",
        "",
        f"- Reference fan curve: **{result['reference_fan_curve']}**",
        f"- System curve: **{result['system_curve']}**",
        f"- Overall status: **{result['status'].upper()}**",
        f"- Speed cases: **{result['speed_case_count']}**",
    ]
    if result["reference_speed_rpm"] is not None:
        lines.append(
            f"- Reference fan speed: **{result['reference_speed_rpm']} rpm**"
        )

    lines.extend(
        [
            "",
            "## Speed sweep",
            "",
            "| Speed ratio | Speed rpm | Status | Airflow m³/h | Pressure Pa | Air power kW | Homologous input-power factor |",
            "|---:|---:|---|---:|---:|---:|---:|",
        ]
    )
    for case in result["speed_cases"]:
        point = case["operating_point"]
        rpm = "—" if case["speed_rpm"] is None else case["speed_rpm"]
        if point is None:
            airflow = pressure = air_power = "—"
        else:
            airflow = point["airflow_m3_h"]
            pressure = point["system_pressure_pa"]
            air_power = point["air_power_kw"]
        lines.append(
            f"| {case['speed_ratio']} | {rpm} | {case['status']} | "
            f"{airflow} | {pressure} | {air_power} | "
            f"{case['affinity_scaling']['homologous_input_power_factor']} |"
        )

    unresolved = [
        case for case in result["speed_cases"]
        if case["operating_point"] is None
    ]
    if unresolved:
        lines.extend(["", "## Unresolved speed cases", ""])
        for case in unresolved:
            lines.append(
                f"- **{case['speed_ratio']}x** — {case['solver_message']}"
            )

    lines.extend(
        [
            "",
            "## Engineering note",
            "",
            result["scope_note"],
            "",
        ]
    )
    return "\n".join(lines)
