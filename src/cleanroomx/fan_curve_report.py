from __future__ import annotations

from .fan_curve import FanOperatingPointCase


def markdown_fan_operating_point_report(
    case: FanOperatingPointCase,
    result: dict,
) -> str:
    lines = [
        f"# CleanroomX Fan Operating Point Report — {result['case']}",
        "",
        f"- Status: **{result['status']}**.",
        f"- Fan curve: **{result['fan_curve']}**.",
        f"- System curve: **{result['system_curve']}**.",
        f"- Supplied fan airflow range: **{result['fan_curve_airflow_range_m3_h'][0]}–{result['fan_curve_airflow_range_m3_h'][1]} m³/h**.",
        f"- Fixed system pressure: **{result['fixed_pressure_pa']} Pa**.",
        f"- Quadratic resistance: **{result['resistance_pa_per_m3_s_squared']} Pa/(m³/s)²**.",
        "",
        "## Fan curve points",
        "",
        "| Airflow m³/h | Static pressure Pa |",
        "|---:|---:|",
    ]
    for point in case.fan_curve.points:
        lines.append(
            f"| {round(point.airflow_m3_h, 3)} | "
            f"{round(point.static_pressure_pa, 4)} |"
        )

    lines.extend(["", "## Operating point", ""])
    operating_point = result["operating_point"]
    if operating_point is None:
        lines.append(f"**No in-range operating point.** {result['reason']}")
    else:
        lines.extend(
            [
                f"- Airflow: **{operating_point['airflow_m3_h']} m³/h** "
                f"({operating_point['airflow_m3_s']} m³/s).",
                f"- Static pressure: **{operating_point['static_pressure_pa']} Pa**.",
                f"- Fan/system pressure residual: **{operating_point['pressure_residual_pa']} Pa**.",
                f"- Air power at the intersection: **{operating_point['air_power_kw']} kW**.",
                f"- Interpolated fan segment: **{operating_point['fan_curve_segment']}**.",
            ]
        )

    lines.extend(
        [
            "",
            "## Boundary margins",
            "",
            f"- Fan minus system pressure at minimum supplied flow: **{result['fan_minus_system_pressure_at_min_flow_pa']} Pa**.",
            f"- Fan minus system pressure at maximum supplied flow: **{result['fan_minus_system_pressure_at_max_flow_pa']} Pa**.",
            "",
            "## Engineering boundary",
            "",
            result["scope_note"],
            "",
        ]
    )
    return "\n".join(lines)
