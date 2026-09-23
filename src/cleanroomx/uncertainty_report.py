from __future__ import annotations


def markdown_uncertainty_report(result: dict) -> str:
    volume = result["volume_m3"]
    ach = result["ach_1_h"]
    requirement = result["requirement"]
    traceability = result["traceability"]

    lines = [f"# CleanroomX Uncertainty Report — {result['room']}", ""]
    lines.extend(
        [
            "## Conservative intervals",
            "",
            f"- Volume: **{volume['nominal']} m³** ({volume['lower']} to {volume['upper']} m³)",
            f"- Supply ACH: **{ach['nominal']} 1/h** ({ach['lower']} to {ach['upper']} 1/h)",
            f"- Configured minimum ACH: **{requirement['min_ach'] if requirement['min_ach'] is not None else 'not configured'}**",
            f"- Requirement status: **{requirement['status'].upper()}**",
            "",
            requirement["message"],
            "",
            "## Input provenance",
            "",
            f"- Complete: **{'yes' if traceability['complete'] else 'no'}**",
            f"- Inputs with provenance: **{traceability['inputs_with_provenance']}/{traceability['input_count']}**",
            "",
            "| Input | Nominal | ± uncertainty | Interval | Source | Reference |",
            "|---|---:|---:|---:|---|---|",
        ]
    )

    for item in traceability["inputs"]:
        provenance = item["provenance"] or {}
        source = provenance.get("source_name") or "missing"
        reference = provenance.get("reference") or "—"
        lines.append(
            f"| {item['name']} | {item['value']} {item['unit']} | "
            f"{item['uncertainty_abs']} {item['unit']} | "
            f"{item['lower']} to {item['upper']} {item['unit']} | "
            f"{source} | {reference} |"
        )

    if traceability["missing_provenance"]:
        lines.extend(
            [
                "",
                "Missing provenance: "
                + ", ".join(traceability["missing_provenance"])
                + ".",
            ]
        )

    lines.extend(["", "## Engineering note", "", result["engineering_note"], ""])
    return "\n".join(lines)
