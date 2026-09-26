from __future__ import annotations

from .markdown import markdown_text


def markdown_design_requirements_report(result: dict) -> str:
    lines = [
        f"# CleanroomX Design Requirements — {markdown_text(result['project'])}",
        "",
        f"Status: **{markdown_text(result['status']).upper()}**",
        "",
    ]
    for room in result["rooms"]:
        lines.extend([
            f"## {markdown_text(room['name'])}",
            "",
            f"- Classification: **{markdown_text(room['classification'] or 'not configured')}**",
            f"- Intended process: **{markdown_text(room['intended_process'] or 'not configured')}**",
            f"- Operating mode: **{markdown_text(room['operating_mode'] or 'not configured')}**",
            f"- Filtration requirement: **{markdown_text(room['filtration_requirement'] or 'not configured')}**",
            f"- Supply/return strategy: **{markdown_text(room['supply_return_strategy'] or 'not configured')}**",
            "",
            "| Target | Value | Unit | Status | Source | Equation |",
            "|---|---:|---|---|---|---|",
        ])
        for target in room["targets"]:
            value = "—" if target["value"] is None else target["value"]
            lines.append(
                f"| {markdown_text(target['name'])} | {value} | {markdown_text(target['unit'] or '')} | "
                f"{markdown_text(target['status'])} | {markdown_text(target['source'])} | {markdown_text(target['equation'])} |"
            )
        if room["warnings"]:
            lines.extend(["", "Warnings:"])
            lines.extend(f"- {markdown_text(item)}" for item in room["warnings"])
        lines.append("")
    lines.extend(["## Engineering boundary", "", markdown_text(result["engineering_note"]), ""])
    return "\n".join(lines)


def markdown_air_system_design_report(result: dict) -> str:
    lines = [
        f"# CleanroomX Air System Design — {markdown_text(result['design'])}",
        "",
        f"Status: **{markdown_text(result['status']).upper()}**",
        "",
        "| Room | Strategy | Governing airflow m³/h | Basis | Return m³/h | Exhaust m³/h | Makeup m³/h | Minimum surplus m³/h | Achieved surplus m³/h | Margin m³/h |",
        "|---|---|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for room in result["rooms"]:
        lines.append(
            f"| {markdown_text(room['name'])} | {markdown_text(room['strategy'])} | "
            f"{room['governing_airflow_m3_h']} | {markdown_text(room['governing_basis'])} | "
            f"{room['proposed_return_airflow_m3_h']} | {room['exhaust_airflow_m3_h']} | "
            f"{room['preliminary_makeup_airflow_m3_h']} | {room['minimum_surplus_m3_h']} | "
            f"{room['achieved_surplus_m3_h']} | {room['surplus_margin_m3_h']} |"
        )
    lines.extend(["", "## Preliminary equipment counts", ""])
    for room in result["rooms"]:
        counts = room["equipment_counts"]
        lines.append(
            f"- **{markdown_text(room['name'])}:** FFU/filter units {counts['filter_units'] if counts['filter_units'] is not None else '—'}, "
            f"supply terminals {counts['supply_terminals'] if counts['supply_terminals'] is not None else '—'}, "
            f"return grilles {counts['return_grilles'] if counts['return_grilles'] is not None else '—'}, "
            f"exhaust terminals {counts['exhaust_terminals'] if counts['exhaust_terminals'] is not None else '—'}."
        )
    if result["warnings"]:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {markdown_text(item)}" for item in result["warnings"])
    lines.extend(["", "## Engineering boundary", "", markdown_text(result["engineering_note"]), ""])
    return "\n".join(lines)
