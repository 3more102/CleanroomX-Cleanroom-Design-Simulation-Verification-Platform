from __future__ import annotations


def markdown_fan_speed_sweep_report(result: dict) -> str:
    lines = [
        f"# CleanroomX Fan Affinity-Law Speed Sweep — {result['study']}",
        "",
        f"- Reference fan curve: **{result['reference_fan_curve']}**",
        f"- System curve: **{result['system_curve']}**",
        f"- Study status: **{result['status'].upper()}**",
    ]

    if result["reference_speed_rpm"] is not None:
        lines.append(
            f"- Reference fan speed: **{result['reference_speed_rpm']} rpm**"
        )

    lines.extend(
        [
            "",
            "## Speed cases",
            "",
            "| Speed ratio | Speed (%) | Speed (rpm) | Fan-law power ratio | Status | Operating airflow (m³/h) | Operating pressure (Pa) | Air power (kW) |",
            "|---:|---:|---:|---:|---|---:|---:|---:|",
        ]
    )

    for case in result["cases"]:
        point = case["operating_point"]
        speed_rpm = "—" if case["speed_rpm"] is None else case["speed_rpm"]
        if point is None:
            airflow = pressure = air_power = "—"
        else:
            airflow = point["airflow_m3_h"]
            pressure = point["fan_pressure_pa"]
            air_power = point["air_power_kw"]
        lines.append(
            f"| {case['speed_ratio']} | {case['speed_percent']} | {speed_rpm} | "
            f"{case['fan_law_power_ratio_to_reference']} | {case['status']} | "
            f"{airflow} | {pressure} | {air_power} |"
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
