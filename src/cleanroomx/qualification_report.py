from __future__ import annotations

from .markdown import markdown_text


def _fmt(value: float) -> str:
    return f"{value:.6g}"


def markdown_qualification_report(result: dict) -> str:
    lines = [
        f"# CleanroomX Qualification Uncertainty Report — {markdown_text(result['analysis'])}",
        "",
        f"- Overall status: **{result['overall_status'].upper()}**",
        f"- Method: **{markdown_text(result['method'])}**",
        "",
    ]

    if result["measurements"]:
        lines.extend(
            [
                "## Measurement checks",
                "",
                "| Check | Interval | Requirement | Status | Reference |",
                "|---|---:|---:|---|---|",
            ]
        )
        for item in result["measurements"]:
            req = item["requirement"]
            symbol = "≥" if req["kind"] == "minimum" else "≤"
            lines.append(
                f"| {markdown_text(item['name'])} | {_fmt(item['interval']['lower'])} to "
                f"{_fmt(item['interval']['upper'])} {markdown_text(item['unit'])} | "
                f"{symbol} {_fmt(req['limit'])} {markdown_text(req['unit'])} | "
                f"{item['status'].upper()} | {markdown_text(req['reference'] or '—')} |"
            )
        lines.append("")

    if result["pressure_cascades"]:
        lines.extend(
            [
                "## Pressure-cascade checks",
                "",
                "| Check | Nominal ΔP | Conservative interval | Minimum | Status | Reference |",
                "|---|---:|---:|---:|---|---|",
            ]
        )
        for item in result["pressure_cascades"]:
            req = item["requirement"]
            lines.append(
                f"| {markdown_text(item['name'])} | {_fmt(item['nominal_delta_pa'])} Pa | "
                f"{_fmt(item['interval_pa']['lower'])} to {_fmt(item['interval_pa']['upper'])} Pa | "
                f"{_fmt(req['limit'])} Pa | {item['status'].upper()} | "
                f"{markdown_text(req['reference'] or '—')} |"
            )
        lines.append("")

    traceability = result["traceability"]
    lines.extend(
        [
            "## Traceability",
            "",
            f"- Inputs with provenance: **{traceability['inputs_with_provenance']}/{traceability['input_count']}**",
            f"- Complete: **{'yes' if traceability['complete'] else 'no'}**",
        ]
    )
    if traceability["missing_provenance"]:
        lines.append("- Missing provenance: " + ", ".join(markdown_text(name) for name in traceability["missing_provenance"]))
    lines.extend(["", "## Engineering note", "", result["engineering_note"], ""])
    return "\n".join(lines)
