from __future__ import annotations


def markdown_fan_loop_damper_report(result: dict) -> str:
    lines = [
        f"# CleanroomX Fan/Loop Damper Study — {result['study']}",
        "",
        f"- Fan curve: **{result['fan_curve']}**",
        f"- Overall status: **{result['status'].upper()}**",
        f"- Configured states: **{result['state_count']}**",
        f"- Solved states: **{result['solved_state_count']}**",
        "",
        "## State summary",
        "",
        "| State | Status | Equivalent loop resistance (Pa/(m³/s)²) | Operating airflow (m³/h) | Fan pressure (Pa) |",
        "|---|---|---:|---:|---:|",
    ]

    for state in result["states"]:
        airflow = (
            "—"
            if state["operating_airflow_m3_h"] is None
            else state["operating_airflow_m3_h"]
        )
        pressure = (
            "—"
            if state["fan_pressure_pa"] is None
            else state["fan_pressure_pa"]
        )
        lines.append(
            f"| {state['state']} | {state['status']} | "
            f"{state['equivalent_loop_resistance_pa_per_m3_s_squared']} | "
            f"{airflow} | {pressure} |"
        )

    for state in result["states"]:
        lines.extend(
            [
                "",
                f"## State — {state['state']}",
                "",
                "### Explicit damper resistance adjustments",
                "",
                "| Edge | Base resistance | Added resistance | Adjusted resistance |",
                "|---|---:|---:|---:|",
            ]
        )
        for row in state["damper_adjustments"]:
            lines.append(
                f"| {row['edge']} | "
                f"{row['base_resistance_pa_per_m3_s_squared']} | "
                f"{row['added_resistance_pa_per_m3_s_squared']} | "
                f"{row['adjusted_resistance_pa_per_m3_s_squared']} |"
            )

        fan_loop = state["fan_loop_result"]
        network = fan_loop["operating_network_solution"]
        if network is None:
            lines.extend(
                [
                    "",
                    "### Operating point",
                    "",
                    fan_loop["message"],
                ]
            )
            continue

        lines.extend(
            [
                "",
                "### Operating edge flows",
                "",
                "| Edge | Airflow (m³/h) | Direction | Pressure difference (Pa) |",
                "|---|---:|---|---:|",
            ]
        )
        for edge in network["edges"]:
            lines.append(
                f"| {edge['name']} | {edge['airflow_m3_h']} | "
                f"{edge['flow_direction']} | {edge['pressure_difference_pa']} |"
            )

    lines.extend(["", "## Engineering note", "", result["scope_note"], ""])
    return "\n".join(lines)
