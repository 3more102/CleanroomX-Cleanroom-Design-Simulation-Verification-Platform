from __future__ import annotations

from .markdown import markdown_text


def markdown_consistency_report(result: dict) -> str:
    lines = [
        "# CleanroomX Cross-Module Consistency Report",
        "",
        f"- Verification project: **{markdown_text(result['verification_project'])}**",
        f"- HVAC project: **{markdown_text(result['hvac_project'])}**",
        f"- Status: **{result['status'].upper()}**",
        (
            "- Room airflow absolute consistency tolerance: "
            f"**{result['room_airflow_abs_tolerance_m3_h']} m³/h**"
        ),
        (
            "- Require identical room sets: "
            f"**{result['require_same_room_set']}**"
        ),
        "",
        "## Shared-room airflow checks",
        "",
    ]

    if result["room_airflow_checks"]:
        lines.extend(
            [
                "| Room | Verification supply m³/h | HVAC cleanroom m³/h | Difference m³/h | Absolute difference m³/h | Status |",
                "|---|---:|---:|---:|---:|---|",
            ]
        )
        for item in result["room_airflow_checks"]:
            lines.append(
                f"| {markdown_text(item['room'])} | "
                f"{item['verification_supply_airflow_m3_h']} | "
                f"{item['hvac_cleanroom_airflow_m3_h']} | "
                f"{item['difference_m3_h']} | "
                f"{item['absolute_difference_m3_h']} | "
                f"{item['status']} |"
            )
    else:
        lines.append(
            "No exact room-name matches were found, so airflow values were not comparable."
        )

    lines.extend(["", "## Room-scope differences", ""])
    lines.append(
        "- Verification-only rooms: "
        + (
            ", ".join(markdown_text(name) for name in result["verification_only_rooms"])
            if result["verification_only_rooms"]
            else "none"
        )
    )
    lines.append(
        "- HVAC-only rooms: "
        + (
            ", ".join(markdown_text(name) for name in result["hvac_only_rooms"])
            if result["hvac_only_rooms"]
            else "none"
        )
    )

    lines.extend(
        [
            "",
            "## Scope note",
            "",
            result["scope_note"],
            "",
        ]
    )
    return "\n".join(lines)
