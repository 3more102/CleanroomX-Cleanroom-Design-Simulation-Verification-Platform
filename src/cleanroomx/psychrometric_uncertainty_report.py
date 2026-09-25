from __future__ import annotations

from .markdown import markdown_text


def _fmt(value: float) -> str:
    return f"{value:.6g}"


def _interval_text(item: dict) -> str:
    return (
        f"{_fmt(item['nominal'])} {markdown_text(item['unit'])} "
        f"({_fmt(item['lower'])} to {_fmt(item['upper'])} {markdown_text(item['unit'])})"
    )


def markdown_psychrometric_uncertainty_report(result: dict) -> str:
    state = result["input_state"]
    properties = result["psychrometric_properties"]
    traceability = result["traceability"]

    lines = [
        f"# CleanroomX Psychrometric Uncertainty Report — {markdown_text(result['analysis'])}",
        "",
        f"- Method: **{result['method']}**",
        f"- Unique evaluated corners: **{result['corner_count']}**",
        "",
        "## Input-state intervals",
        "",
        f"- Dry-bulb temperature: **{_interval_text(state['dry_bulb_c'])}**",
        (
            "- Relative humidity: "
            f"**{_interval_text(state['relative_humidity_percent'])}**"
        ),
        f"- Pressure: **{_interval_text(state['pressure_kpa'])}**",
        "",
        "## Derived psychrometric intervals",
        "",
        "| Property | Nominal | Lower | Upper | Unit |",
        "|---|---:|---:|---:|---|",
    ]

    labels = (
        ("Vapor pressure", "vapor_pressure_kpa"),
        ("Humidity ratio", "humidity_ratio_g_kg_da"),
        ("Moist-air enthalpy", "enthalpy_kj_kg_da"),
        ("Specific volume", "specific_volume_m3_kg_da"),
        ("Dew point", "dew_point_c"),
        ("Moist-air cp", "cp_kj_kg_da_k"),
    )
    for label, key in labels:
        item = properties[key]
        lines.append(
            f"| {label} | {_fmt(item['nominal'])} | {_fmt(item['lower'])} | "
            f"{_fmt(item['upper'])} | {markdown_text(item['unit'])} |"
        )

    lines.extend(
        [
            "",
            "## Input provenance",
            "",
            f"- Complete: **{'yes' if traceability['complete'] else 'no'}**",
            (
                "- Inputs with provenance: "
                f"**{traceability['inputs_with_provenance']}/"
                f"{traceability['input_count']}**"
            ),
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
            f"| {markdown_text(item['name'])} | {_fmt(item['value'])} {markdown_text(item['unit'])} | "
            f"{_fmt(item['uncertainty_abs'])} {markdown_text(item['unit'])} | "
            f"{_fmt(item['lower'])} to {_fmt(item['upper'])} {markdown_text(item['unit'])} | "
            f"{markdown_text(source)} | {markdown_text(reference)} |"
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
