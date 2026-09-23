from __future__ import annotations

from .loop_network_report import markdown_looped_network_report


def markdown_reference_geometry_loop_report(result: dict) -> str:
    lines = [
        f"# CleanroomX Reference-Geometry Loop Report — {result['network']}",
        "",
        "## Reference resistance derivation",
        "",
        "| Edge | Reference flow (m³/h) | Shape | Velocity (m/s) | Darcy f | Method | Reference ΔP (Pa) | Derived R [Pa/(m³/s)²] |",
        "|---|---:|---|---:|---:|---|---:|---:|",
    ]
    for edge in result["derived_edges"]:
        lines.append(
            f"| {edge['name']} | {edge['reference_airflow_m3_h']} | "
            f"{edge['shape']} | {edge['velocity_m_s']} | "
            f"{edge['friction_factor']} | {edge['friction_factor_method']} | "
            f"{edge['reference_pressure_drop_pa']} | "
            f"{edge['derived_resistance_pa_per_m3_s_squared']} |"
        )

    solver_lines = markdown_looped_network_report(result["loop_solution"]).splitlines()
    if solver_lines and solver_lines[0].startswith("# "):
        solver_lines[0] = "## Fixed-resistance loop solution"
    solver_lines = [
        ("### " + line[3:]) if line.startswith("## ") else line
        for line in solver_lines
    ]
    lines.extend(["", *solver_lines, "", "## Integration boundary", "", result["scope_note"], ""])
    return "\n".join(lines)
