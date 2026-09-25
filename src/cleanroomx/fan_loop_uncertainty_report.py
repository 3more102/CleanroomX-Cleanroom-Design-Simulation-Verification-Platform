from __future__ import annotations

from .markdown import markdown_text


def _fmt(value: object) -> str:
    return "—" if value is None else str(value)


def markdown_fan_loop_network_uncertainty_report(result: dict) -> str:
    lines = [
        f"# CleanroomX Fan/Loop-Network Uncertainty Report — {markdown_text(result['analysis'])}",
        "",
        f"- Status: **{result['status'].upper()}**",
        f"- Fan curve: **{result['fan_curve']}**",
        f"- Fan discharge node: **{result['fan_discharge_node']}**",
        f"- Fan suction node: **{result['fan_suction_node']}**",
        f"- Solved corners: **{result['solved_corner_count']}/{result['corner_count']}**",
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
            "No nominal intersection exists inside the supplied fan-curve range."
        )
    else:
        lines.extend(
            [
                f"- Airflow: **{nominal['airflow_m3_h']} m³/h**",
                f"- System pressure: **{nominal['system_pressure_pa']} Pa**",
                "- Equivalent loop resistance: "
                f"**{result['nominal_equivalent_loop_resistance_pa_per_m3_s_squared']} "
                "Pa/(m³/s)²**",
            ]
        )

    lines.extend(["", "## Bounded corner envelope", ""])
    envelope = result["operating_point_envelope"]
    resistance_envelope = result["equivalent_loop_resistance_envelope"]
    if envelope is None:
        lines.append(result["message"])
    else:
        lines.extend(
            [
                "- Airflow: "
                f"**{envelope['airflow_m3_h']['lower']} to "
                f"{envelope['airflow_m3_h']['upper']} m³/h**",
                "- System pressure: "
                f"**{envelope['system_pressure_pa']['lower']} to "
                f"{envelope['system_pressure_pa']['upper']} Pa**",
                "- Equivalent loop resistance across corners: "
                f"**{resistance_envelope['lower']} to "
                f"{resistance_envelope['upper']} Pa/(m³/s)²**",
            ]
        )

    lines.extend(
        [
            "",
            "## Corner results",
            "",
            "| Fixed pressure Pa | Equivalent R Pa/(m³/s)² | Status | Airflow m³/h | Pressure Pa |",
            "|---:|---:|---|---:|---:|",
        ]
    )
    for corner in result["corners"]:
        point = corner["operating_point"]
        lines.append(
            f"| {corner['fixed_pressure_pa']} | "
            f"{corner['equivalent_loop_resistance_pa_per_m3_s_squared']} | "
            f"{corner['status']} | "
            f"{_fmt(None if point is None else point['airflow_m3_h'])} | "
            f"{_fmt(None if point is None else point['system_pressure_pa'])} |"
        )

    traceability = result["traceability"]
    lines.extend(
        [
            "",
            "## Traceability",
            "",
            f"- Provenance complete for bounded inputs: "
            f"**{'yes' if traceability['complete'] else 'no'}**",
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
