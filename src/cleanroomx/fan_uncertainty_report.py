from __future__ import annotations


def _fmt(value: object) -> str:
    return "—" if value is None else str(value)


def markdown_fan_system_uncertainty_report(result: dict) -> str:
    lines = [
        f"# CleanroomX Fan/System Uncertainty Report — {result['analysis']}",
        "",
        f"- Status: **{result['status'].upper()}**",
        f"- Fan curve: **{result['fan_curve']}**",
        f"- System curve: **{result['system_curve']}**",
        f"- Solved corners: **{result['solved_corner_count']}/{result['corner_count']}**",
        "",
        "## Input intervals",
        "",
    ]

    fixed = result["input_intervals"]["fixed_pressure_pa"]
    resistance = result["input_intervals"]["resistance_pa_per_m3_s_squared"]
    lines.extend(
        [
            f"- Fixed pressure: **{fixed['lower']} to {fixed['upper']} Pa** "
            f"(nominal {fixed['nominal']} Pa)",
            "- Quadratic resistance: "
            f"**{resistance['lower']} to {resistance['upper']} Pa/(m³/s)²** "
            f"(nominal {resistance['nominal']})",
            "",
            "## Nominal operating point",
            "",
        ]
    )

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
                f"- Air power: **{nominal['air_power_kw']} kW**",
            ]
        )

    lines.extend(["", "## Bounded operating-point envelope", ""])
    envelope = result["operating_point_envelope"]
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
                "- Air power: "
                f"**{envelope['air_power_kw']['lower']} to "
                f"{envelope['air_power_kw']['upper']} kW**",
            ]
        )

    lines.extend(
        [
            "",
            "## Corner results",
            "",
            "| Fixed pressure Pa | R Pa/(m³/s)² | Status | Airflow m³/h | Pressure Pa |",
            "|---:|---:|---|---:|---:|",
        ]
    )
    for corner in result["corners"]:
        point = corner["operating_point"]
        lines.append(
            f"| {corner['fixed_pressure_pa']} | "
            f"{corner['resistance_pa_per_m3_s_squared']} | "
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
            f"- Provenance complete: **{'yes' if traceability['complete'] else 'no'}**",
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
