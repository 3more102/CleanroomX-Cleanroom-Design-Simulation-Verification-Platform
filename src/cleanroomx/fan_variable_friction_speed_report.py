from __future__ import annotations


def markdown_fan_variable_friction_speed_report(result: dict) -> str:
    lines = [
        "# CleanroomX Fan-Speed / Variable-Friction Loop Study — "
        f"{result['study']}",
        "",
        f"- Reference fan curve: **{result['reference_fan_curve']}**",
        f"- Loop network: **{result['loop_network']}**",
        f"- Fan discharge node: **{result['fan_discharge_node']}**",
        f"- Fan suction node: **{result['fan_suction_node']}**",
        f"- Fixed pressure: **{result['fixed_pressure_pa']} Pa**",
        f"- Overall status: **{result['status'].upper()}**",
        f"- Speed cases: **{result['speed_case_count']}**",
        "- Unresolved/non-converged speed cases: "
        f"**{result['unresolved_speed_case_count']}**",
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
            "| Speed ratio | Speed rpm | Status | Scaled range m³/h | "
            "Operating airflow m³/h | Fan pressure Pa | Loop pressure Pa | "
            "Pressure residual Pa | Fluid air power kW | Shaft power kW | "
            "Electrical input kW | Network outer iterations | "
            "Resistance closure | Continuity residual m³/h |",
            "|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )

    for case in result["speed_cases"]:
        point = case["fan_operating_point"]
        check = case["system_pressure_check"]
        diagnostics = case["solver_diagnostics"]
        power = case["power_evidence"]
        rpm = "—" if case["speed_rpm"] is None else case["speed_rpm"]
        curve_range = case["scaled_fan_curve_airflow_range_m3_h"]
        if point is None or check is None:
            airflow = fan_pressure = loop_pressure = pressure_residual = "—"
            fluid_power = shaft_power = electrical_power = "—"
        else:
            airflow = point["airflow_m3_h"]
            fan_pressure = point["fan_pressure_pa"]
            loop_pressure = check["loop_network_pressure_pa"]
            pressure_residual = check["fan_minus_system_pressure_pa"]
            fluid_power = power["fluid_air_power_kw"]
            shaft_power = (
                "—" if power["shaft_power_kw"] is None
                else power["shaft_power_kw"]
            )
            electrical_power = (
                "—" if power["electrical_input_kw"] is None
                else power["electrical_input_kw"]
            )

        outer_iterations = diagnostics.get("network_outer_iterations", "—")
        closure = diagnostics.get(
            "network_max_relative_resistance_closure_error", "—"
        )
        continuity = diagnostics.get(
            "max_abs_mass_balance_residual_m3_h", "—"
        )
        lines.append(
            f"| {case['speed_ratio']} | {rpm} | {case['status']} | "
            f"{curve_range[0]}–{curve_range[1]} | {airflow} | "
            f"{fan_pressure} | {loop_pressure} | {pressure_residual} | "
            f"{fluid_power} | {shaft_power} | {electrical_power} | "
            f"{outer_iterations} | {closure} | {continuity} |"
        )

    unresolved = [
        case for case in result["speed_cases"] if case["status"] != "solved"
    ]
    if unresolved:
        lines.extend(["", "## Unresolved speed cases", ""])
        for case in unresolved:
            diagnostics = case["solver_diagnostics"]
            lines.append(
                f"- **{case['speed_ratio']}x — {case['status']}**: "
                f"{case['solver_message']} "
                f"(termination: {diagnostics['termination_reason']})"
            )

    lines.extend(["", "## Engineering note", "", result["scope_note"], ""])
    return "\n".join(lines)
