from __future__ import annotations


def markdown_fan_control_report(result: dict) -> str:
    lines = [
        f"# CleanroomX Fan-Control Study — {result['study']}",
        "",
        f"- System curve: **{result['system_curve']}**",
        f"- Analysis status: **{result['analysis_status'].upper()}**",
        f"- Target status: **{result['target_status'].upper()}**",
        f"- Unresolved control states: **{result['unresolved_state_count']}**",
    ]

    monotonic = result["response_monotonic_non_decreasing"]
    if monotonic is None:
        monotonic_text = "not evaluated (fewer than two solved states)"
    else:
        monotonic_text = "yes" if monotonic else "no"
    lines.append(
        f"- Solved airflow non-decreasing with control signal: **{monotonic_text}**"
    )

    if result["target_band_m3_h"] is not None:
        low, high = result["target_band_m3_h"]
        lines.extend(
            [
                f"- Target airflow: **{result['target_airflow_m3_h']} m³/h**",
                f"- Target tolerance: **±{result['target_tolerance_m3_h']} m³/h**",
                f"- Target band: **{low}–{high} m³/h**",
            ]
        )

    lines.extend(
        [
            "",
            "## Control states",
            "",
            "| State | Control signal (%) | Solve status | Airflow (m³/h) | System pressure (Pa) | Target check |",
            "|---|---:|---|---:|---:|---|",
        ]
    )

    for item in result["states"]:
        point = item["fan_operating_point"]["operating_point"]
        airflow = "—" if point is None else point["airflow_m3_h"]
        pressure = "—" if point is None else point["system_pressure_pa"]
        lines.append(
            f"| {item['state']} | {item['control_signal_percent']} | "
            f"{item['status']} | {airflow} | {pressure} | "
            f"{item['target_status']} |"
        )

    closest = result["closest_solved_state"]
    if closest is not None:
        lines.extend(
            [
                "",
                "## Closest solved state",
                "",
                f"- State: **{closest['state']}**",
                f"- Control signal: **{closest['control_signal_percent']}%**",
                f"- Airflow: **{closest['airflow_m3_h']} m³/h**",
                f"- Error from target: **{closest['airflow_error_m3_h']} m³/h**",
                f"- Target check: **{closest['target_status']}**",
            ]
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
