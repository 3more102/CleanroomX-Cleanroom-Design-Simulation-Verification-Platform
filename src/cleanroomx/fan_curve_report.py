from __future__ import annotations

from .markdown import markdown_text


def markdown_fan_operating_point_report(result: dict) -> str:
    lines = [
        f"# CleanroomX Fan/System Operating-Point Report — {markdown_text(result['study'])}",
        "",
        f"- Fan curve: **{result['fan_curve']}**",
        f"- System curve: **{result['system_curve']}**",
        f"- Status: **{result['status'].upper()}**",
        "",
        "## System model",
        "",
        f"- Fixed pressure: **{result['system_model']['fixed_pressure_pa']} Pa**",
        "- Quadratic resistance: "
        f"**{result['system_model']['resistance_pa_per_m3_s_squared']} Pa/(m³/s)²**",
        "",
    ]

    point = result["operating_point"]
    if point is not None:
        segment = point["interpolation_segment"]
        lines.extend(
            [
                "## Operating point",
                "",
                f"- Airflow: **{point['airflow_m3_h']} m³/h** "
                f"({point['airflow_m3_s']} m³/s)",
                f"- Fan pressure: **{point['fan_pressure_pa']} Pa**",
                f"- System pressure: **{point['system_pressure_pa']} Pa**",
                f"- Pressure residual: **{point['pressure_residual_pa']} Pa**",
                f"- Air power: **{point['air_power_kw']} kW**",
                "- Interpolation segment: "
                f"**{segment['low_airflow_m3_h']}–{segment['high_airflow_m3_h']} m³/h**",
                "",
            ]
        )
    else:
        lines.extend(["## Operating point", "", result["message"], ""])

    lines.extend(
        [
            "## Supplied fan-curve checks",
            "",
            "| Airflow (m³/h) | Fan pressure (Pa) | System pressure (Pa) | Fan-system margin (Pa) |",
            "|---:|---:|---:|---:|",
        ]
    )
    for row in result["curve_point_checks"]:
        lines.append(
            f"| {row['airflow_m3_h']} | {row['fan_pressure_pa']} | "
            f"{row['system_pressure_pa']} | {row['pressure_margin_pa']} |"
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
