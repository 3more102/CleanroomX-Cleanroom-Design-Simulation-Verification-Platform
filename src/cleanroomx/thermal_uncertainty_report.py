from __future__ import annotations


def _fmt(value: float) -> str:
    return f"{value:.6g}"


def _interval_text(item: dict, unit: str) -> str:
    return (
        f"{_fmt(item['nominal'])} {unit} "
        f"({_fmt(item['lower'])} to {_fmt(item['upper'])} {unit})"
    )


def markdown_thermal_uncertainty_report(result: dict) -> str:
    cooling = result["cooling_capacity_kw"]
    heating = result["heating_capacity_kw"]
    airflow = result["airflow_m3_h"]
    traceability = result["traceability"]

    lines = [
        f"# CleanroomX Thermal Uncertainty Report — {result['analysis']}",
        "",
        f"- Overall capacity status: **{result['overall_status'].upper()}**",
        f"- Method: **{result['method']}**",
        f"- Capacity margin: **{result['capacity_margin_percent']}%**",
        "",
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
            f"| {item['name']} | {_fmt(item['value'])} {item['unit']} | "
            f"{_fmt(item['uncertainty_abs'])} {item['unit']} | "
            f"{_fmt(item['lower'])} to {_fmt(item['upper'])} {item['unit']} | "
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
