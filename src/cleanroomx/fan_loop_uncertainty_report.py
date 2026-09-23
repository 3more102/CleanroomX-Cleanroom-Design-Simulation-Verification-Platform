from __future__ import annotations


def _fmt(value: object) -> str:
    return "—" if value is None else str(value)


def markdown_fan_loop_network_uncertainty_report(
    result: dict,
) -> str:
    lines = [
        (
            "# CleanroomX Fan/Loop-Network Uncertainty Report — "
            f"{result['analysis']}"
        ),
        "",
        f"- Status: **{result['status'].upper()}**",
        f"- Fan curve: **{result['fan_curve']}**",
        f"- Loop network: **{result['loop_network']}**",
        f"- Fan discharge node: **{result['fan_discharge_node']}**",
        f"- Fan suction node: **{result['fan_suction_node']}**",
        (
            "- Solved corners: "
            f"**{result['solved_corner_count']}/{result['corner_count']}**"
        ),
        "",
        "## Input intervals",
        "",
    ]

    fixed = result["input_intervals"]["fixed_pressure_pa"]
    lines.append(
        f"- Fixed pressure: **{fixed['lower']} to {fixed['upper']} Pa** "
        f"(nominal {fixed['nominal']} Pa)"
    )
    for name, interval in result["input_intervals"][
        "edge_resistance_pa_per_m3_s_squared"
    ].items():
        lines.append(
            f"- Edge `{name}` resistance: **{interval['lower']} to "
            f"{interval['upper']} Pa/(m³/s)²** "
            f"(nominal {interval['nominal']})"
        )

    lines.extend(["", "## Nominal operating point", ""])
    nominal = result["nominal_operating_point"]
    if nominal is None:
        lines.append(
            "No nominal intersection exists inside the supplied "
            "fan-curve range."
        )
    else:
        lines.extend(
            [
                f"- Airflow: **{nominal['airflow_m3_h']} m³/h**",
                (
                    "- System pressure: "
                    f"**{nominal['system_pressure_pa']} Pa**"
                ),
                (
                    "- Equivalent loop resistance: "
                    f"**{result['nominal_equivalent_loop_resistance_pa_per_m3_s_squared']} "
                    "Pa/(m³/s)²**"
                ),
            ]
        )

    lines.extend(["", "## Evaluated-corner envelope", ""])
    envelope = result["operating_point_envelope"]
    resistance_envelope = result[
        "equivalent_loop_resistance_envelope"
    ]
    lines.extend(
        [
            (
                "- Equivalent loop resistance across evaluated corners: "
                f"**{resistance_envelope['lower']} to "
                f"{resistance_envelope['upper']} Pa/(m³/s)²**"
            ),
        ]
    )
    if envelope is None:
        lines.append(result["message"])
    else:
        lines.extend(
            [
                (
                    "- Airflow: "
                    f"**{envelope['airflow_m3_h']['lower']} to "
                    f"{envelope['airflow_m3_h']['upper']} m³/h**"
                ),
                (
                    "- System pressure: "
                    f"**{envelope['system_pressure_pa']['lower']} to "
                    f"{envelope['system_pressure_pa']['upper']} Pa**"
                ),
            ]
        )

    lines.extend(
        [
            "",
            "## Corner results",
            "",
            (
                "| Fixed pressure Pa | Edge resistances | "
                "Equivalent R Pa/(m³/s)² | Status | "
                "Airflow m³/h | Pressure Pa |"
            ),
            "|---:|---|---:|---|---:|---:|",
        ]
    )
    for corner in result["corners"]:
        point = corner["operating_point"]
        edge_text = ", ".join(
            f"{name}={value}"
            for name, value in corner[
                "edge_resistance_pa_per_m3_s_squared"
            ].items()
        ) or "nominal"
        lines.append(
            f"| {corner['fixed_pressure_pa']} | {edge_text} | "
            f"{corner['equivalent_loop_resistance_pa_per_m3_s_squared']} | "
            f"{corner['status']} | "
            f"{_fmt(None if point is None else point['airflow_m3_h'])} | "
            f"{_fmt(None if point is None else point['system_pressure_pa'])} |"
        )

    edge_ranges = result["edge_airflow_corner_ranges"]
    if edge_ranges is not None:
        lines.extend(
            [
                "",
                "## Evaluated corner branch-flow ranges",
                "",
                (
                    "These are diagnostic min/max values across evaluated "
                    "corners only; they are not asserted continuous-interval "
                    "bounds."
                ),
                "",
                "| Edge | Lower m³/h | Upper m³/h | Direction reversal |",
                "|---|---:|---:|---|",
            ]
        )
        for row in edge_ranges:
            lines.append(
                f"| {row['edge']} | "
                f"{row['lower_airflow_m3_h']} | "
                f"{row['upper_airflow_m3_h']} | "
                f"{'yes' if row['direction_reversal_across_corners'] else 'no'} |"
            )

    traceability = result["traceability"]
    lines.extend(
        [
            "",
            "## Traceability",
            "",
            (
                "- Provenance complete for bounded inputs: "
                f"**{'yes' if traceability['complete'] else 'no'}**"
            ),
        ]
    )
    if traceability["missing_provenance"]:
        lines.append(
            "- Missing provenance: "
            + ", ".join(traceability["missing_provenance"])
            + "."
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
