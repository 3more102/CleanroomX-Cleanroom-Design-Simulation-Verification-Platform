from __future__ import annotations


def markdown_fan_speed_control_report(result: dict) -> str:
    reference_speed = (
        "not supplied"
        if result["reference_speed_rpm"] is None
        else f"{result['reference_speed_rpm']} rpm"
    )
    requirement = (
        "not configured"
        if result["required_airflow_m3_h"] is None
        else f"{result['required_airflow_m3_h']} m³/h"
    )
    lines = [
        f"# CleanroomX Fan-Speed Control Study — {result['study']}",
        "",
        f"- Reference fan curve: **{result['reference_fan_curve']}**",
        f"- System curve: **{result['system_curve']}**",
        f"- Reference speed: **{reference_speed}**",
        f"- Required airflow: **{requirement}**",
        f"- Study status: **{result['status'].upper()}**",
        f"- Solved scenarios: **{result['solved_scenario_count']}/{result['scenario_count']}**",
        "",
        "## Speed scenarios",
        "",
        "| Speed ratio | Speed % | Speed rpm | Status | Operating airflow m³/h | System pressure Pa | Meets required airflow |",
        "|---:|---:|---:|---|---:|---:|---|",
    ]

    for item in result["scenarios"]:
        point = item["operating_point"]
        airflow = "—" if point is None else point["airflow_m3_h"]
        pressure = "—" if point is None else point["system_pressure_pa"]
        rpm = "—" if item["speed_rpm"] is None else item["speed_rpm"]
        meets = (
            "—"
            if item["meets_required_airflow"] is None
            else ("yes" if item["meets_required_airflow"] else "no")
        )
        lines.append(
            f"| {item['speed_ratio']} | {item['speed_percent']} | {rpm} | "
            f"{item['status']} | {airflow} | {pressure} | {meets} |"
        )

    if result["target_summary"] is not None:
        target = result["target_summary"]
        lines.extend(
            [
                "",
                "## Airflow target screening",
                "",
                f"- Status: **{target['status'].upper()}**",
                f"- Required airflow: **{target['required_airflow_m3_h']} m³/h**",
            ]
        )
        if target["lowest_tested_speed_ratio_meeting_requirement"] is not None:
            lines.append(
                "- Lowest tested speed meeting the target: "
                f"**{target['lowest_tested_speed_ratio_meeting_requirement']}x "
                f"({target['lowest_tested_speed_percent_meeting_requirement']}%)**"
            )
            if target["lowest_tested_speed_rpm_meeting_requirement"] is not None:
                lines.append(
                    "- Corresponding tested speed: "
                    f"**{target['lowest_tested_speed_rpm_meeting_requirement']} rpm**"
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
