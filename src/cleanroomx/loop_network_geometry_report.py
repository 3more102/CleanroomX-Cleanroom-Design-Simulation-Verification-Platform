from __future__ import annotations

from .loop_network_report import markdown_looped_network_report


def markdown_geometry_looped_network_report(result: dict) -> str:
    base_lines = markdown_looped_network_report(result).splitlines()
    try:
        insertion_index = base_lines.index("## Engineering note")
    except ValueError:
        insertion_index = len(base_lines)

    lines = [
        "",
        "## Geometry-derived fixed-resistance basis",
        "",
        "| Edge | Reference airflow (m³/h) | Derived R [Pa/(m³/s)²] | Reference pressure drop (Pa) |",
        "|---|---:|---:|---:|",
    ]
    for edge in result["edges"]:
        lines.append(
            f"| {edge['name']} | {edge['reference_airflow_m3_h']} | "
            f"{edge['resistance_pa_per_m3_s_squared']} | "
            f"{edge['reference_pressure_drop_pa']} |"
        )

    for edge in result["edges"]:
        lines.extend(
            [
                "",
                f"### {edge['name']} sections",
                "",
                "| Section | Shape | Reference airflow (m³/h) | Darcy f | Method | Reynolds number | Section R [Pa/(m³/s)²] | Reference drop (Pa) |",
                "|---|---|---:|---:|---|---:|---:|---:|",
            ]
        )
        for section in edge["sections"]:
            reynolds = (
                "—"
                if section["reynolds_number"] is None
                else section["reynolds_number"]
            )
            lines.append(
                f"| {section['name']} | {section['shape']} | "
                f"{section['reference_airflow_m3_h']} | "
                f"{section['friction_factor']} | "
                f"{section['friction_factor_method']} | {reynolds} | "
                f"{section['quadratic_resistance_pa_per_m3_s_squared']} | "
                f"{section['reference_pressure_drop_pa']} |"
            )

    return "\n".join(
        base_lines[:insertion_index]
        + lines
        + [""]
        + base_lines[insertion_index:]
    )
