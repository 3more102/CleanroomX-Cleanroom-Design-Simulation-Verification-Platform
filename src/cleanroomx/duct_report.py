from __future__ import annotations


def markdown_duct_report(result: dict) -> str:
    lines = [f"# CleanroomX Duct Network Report — {result['name']}", ""]
    lines.extend(
        [
            f"- Critical path: **{result['critical_path_name']}**",
            f"- Critical-path pressure drop: **{result['critical_path_pressure_drop_pa']} Pa**",
            "",
            "## Paths",
            "",
            "| Path | Segments | Total pressure drop (Pa) |",
            "|---|---:|---:|",
        ]
    )
    for path in result["paths"]:
        lines.append(
            f"| {path['name']} | {path['segment_count']} | {path['total_pressure_drop_pa']} |"
        )

    for path in result["paths"]:
        lines.extend(
            [
                "",
                f"## {path['name']}",
                "",
                "| Segment | Shape | Flow (m³/h) | Velocity (m/s) | Straight ΔP (Pa) | Local ΔP (Pa) | Total ΔP (Pa) |",
                "|---|---|---:|---:|---:|---:|---:|",
            ]
        )
        for segment in path["segments"]:
            lines.append(
                f"| {segment['name']} | {segment['shape']} | {segment['airflow_m3_h']} | "
                f"{segment['velocity_m_s']} | {segment['straight_pressure_drop_pa']} | "
                f"{segment['local_pressure_drop_pa']} | {segment['total_pressure_drop_pa']} |"
            )

    lines.extend(["", "## Engineering scope", "", result["scope_note"], ""])
    return "\n".join(lines)
