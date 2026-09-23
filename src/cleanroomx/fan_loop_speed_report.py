from __future__ import annotations


def markdown_fan_loop_speed_report(result: dict) -> str:
    lines = [
        f"# CleanroomX Fan-Speed / Loop-Network Study — {result['study']}",
        "",
        f"- Reference fan curve: **{result['reference_fan_curve']}**",
        f"- Loop network: **{result['loop_network']}**",
        f"- Fan discharge node: **{result['fan_discharge_node']}**",
        f"- Fan suction node: **{result['fan_suction_node']}**",
        f"- Fixed pressure: **{result['fixed_pressure_pa']} Pa**",
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
            "| Speed ratio | Speed rpm | Status | Airflow m³/h | Fan pressure Pa | "
            "Equivalent R Pa/(m³/s)² | Continuity residual m³/h | Fan-system residual Pa |",
            "|---:|---:|---|---:|---:|---:|---:|---:|",
        ]
    )
    for case in result["speed_cases"]:
        point = case["fan_operating_point"]
        network = case["operating_network_solution"]
        pressure_check = case["system_pressure_check"]
        rpm = "—" if case["speed_rpm"] is None else case["speed_rpm"]
        if point is None:
            airflow = fan_pressure = continuity = system_residual = "—"
        else:
            airflow = point["airflow_m3_h"]
            fan_pressure = point["fan_pressure_pa"]
            continuity = network["max_abs_mass_balance_residual_m3_h"]
            system_residual = pressure_check["fan_minus_system_pressure_pa"]
        lines.append(
            f"| {case['speed_ratio']} | {rpm} | {case['status']} | {airflow} | "
            f"{fan_pressure} | "
            f"{case['equivalent_loop_resistance_pa_per_m3_s_squared']} | "
            f"{continuity} | {system_residual} |"
        )

    unresolved = [
        case for case in result["speed_cases"]
        if case["fan_operating_point"] is None
    ]
    if unresolved:
        lines.extend(["", "## Unresolved speed cases", ""])
        for case in unresolved:
            lines.append(
                f"- **{case['speed_ratio']}x** — {case['solver_message']}"
            )

    lines.extend(["", "## Engineering note", "", result["scope_note"], ""])
    return "\n".join(lines)
