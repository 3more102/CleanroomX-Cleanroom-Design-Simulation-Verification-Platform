from __future__ import annotations

from .markdown import markdown_text


def _fmt(value: float) -> str:
    return f"{value:.6g}"


def _interval_text(item: dict, unit: str) -> str:
    return (
        f"{_fmt(item['nominal'])} {unit} "
        f"({_fmt(item['lower'])} to {_fmt(item['upper'])} {unit})"
    )


def _append_psychrometric_state(
    lines: list[str],
    label: str,
    state: dict,
) -> None:
    lines.extend(
        [
            f"### {label}",
            "",
            f"- Evaluated state corners: **{state['corner_count']}**",
            "",
            "| Quantity | Nominal | Lower | Upper | Unit |",
            "|---|---:|---:|---:|---|",
        ]
    )
    for name, item in state["inputs"].items():
        lines.append(
            f"| {name} | {_fmt(item['nominal'])} | "
            f"{_fmt(item['lower'])} | {_fmt(item['upper'])} | "
            f"{markdown_text(item['unit'])} |"
        )
    for name, item in state["derived"].items():
        lines.append(
            f"| {name} | {_fmt(item['nominal'])} | "
            f"{_fmt(item['lower'])} | {_fmt(item['upper'])} | "
            f"{markdown_text(item['unit'])} |"
        )
    lines.append("")


def markdown_thermal_uncertainty_report(result: dict) -> str:
    cooling = result["cooling_capacity_kw"]
    heating = result["heating_capacity_kw"]
    airflow = result["airflow_m3_h"]
    traceability = result["traceability"]

    lines = [
        f"# CleanroomX Thermal Uncertainty Report — {markdown_text(result['analysis'])}",
        "",
        f"- Overall capacity status: **{result['overall_status'].upper()}**",
        f"- Method: **{result['method']}**",
        f"- Capacity margin: **{result['capacity_margin_percent']}%**",
        "",
        "## Psychrometric state intervals",
        "",
    ]
    _append_psychrometric_state(
        lines,
        "Room air",
        result["psychrometric_states"]["room_air"],
    )
    outdoor = result["psychrometric_states"]["outdoor_air"]
    if outdoor is not None:
        _append_psychrometric_state(lines, "Outdoor air", outdoor)

    lines.extend(
        [
            "## Capacity intervals",
            "",
            f"- Cooling requirement: **{_interval_text(cooling, 'kW')}**",
            (
                f"- Available cooling capacity: **{cooling['available']} kW**"
                if cooling["available"] is not None
                else "- Available cooling capacity: **not configured**"
            ),
            f"- Cooling status: **{cooling['status'].upper()}** — {cooling['message']}",
            f"- Heating requirement: **{_interval_text(heating, 'kW')}**",
            (
                f"- Available heating capacity: **{heating['available']} kW**"
                if heating["available"] is not None
                else "- Available heating capacity: **not configured**"
            ),
            f"- Heating status: **{heating['status'].upper()}** — {heating['message']}",
            "",
            "## Governing airflow interval",
            "",
            f"- Cleanroom airflow: **{_interval_text(airflow['cleanroom'], 'm³/h')}**",
            f"- Makeup airflow: **{_interval_text(airflow['makeup'], 'm³/h')}**",
        ]
    )

    thermal = airflow["thermal_for_internal_sensible"]
    if thermal is not None:
        lines.append(
            f"- Sensible-load airflow: **{_interval_text(thermal, 'm³/h')}**"
        )
    governing = airflow["governing"]
    lines.extend(
        [
            f"- Governing airflow: **{_interval_text(governing, 'm³/h')}**",
            f"- Nominal governing basis: **{governing['nominal_basis']}**",
            "",
            "## Load intervals",
            "",
            "| Load | Nominal kW | Lower kW | Upper kW |",
            "|---|---:|---:|---:|",
        ]
    )
    for label, key in (
        ("Internal total", "internal_total"),
        ("Makeup-air total", "makeup_air_total"),
        ("Net room + makeup", "net_room_plus_makeup"),
    ):
        item = result["loads_kw"][key]
        lines.append(
            f"| {label} | {_fmt(item['nominal'])} | "
            f"{_fmt(item['lower'])} | {_fmt(item['upper'])} |"
        )

    lines.extend(
        [
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

    lines.extend(
        [
            "",
            "## Engineering note",
            "",
            result["engineering_note"],
            "",
        ]
    )
    return "\n".join(lines)
