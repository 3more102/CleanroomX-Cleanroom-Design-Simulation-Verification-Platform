from __future__ import annotations


def _format_interval(item: dict, unit: str) -> str:
    return (
        f"{item['nominal']} {unit} "
        f"({item['lower']} to {item['upper']} {unit})"
    )


def markdown_thermal_uncertainty_report(result: dict) -> str:
    traceability = result["traceability"]
    thermal_airflow = result["thermal_airflow_for_internal_sensible_m3_h"]

    lines = [
        f"# CleanroomX Thermal Uncertainty Report — {result['case']}",
        "",
        "## Endpoint-scenario envelope",
        "",
        f"- Method: **{result['method']}**.",
        f"- Endpoint scenarios evaluated: **{result['scenario_count']}**.",
        (
            "- Inputs with non-zero uncertainty: **"
            + (
                ", ".join(result["uncertain_dimensions"])
                if result["uncertain_dimensions"]
                else "none"
            )
            + "**."
        ),
        "",
        "| Output | Nominal and endpoint envelope |",
        "|---|---|",
        (
            "| Preliminary cooling capacity | "
            + _format_interval(
                result["preliminary_cooling_capacity_kw"],
                "kW",
            )
            + " |"
        ),
        (
            "| Preliminary heating capacity | "
            + _format_interval(
                result["preliminary_heating_capacity_kw"],
                "kW",
            )
            + " |"
        ),
        (
            "| Governing supply airflow | "
            + _format_interval(
                result["governing_supply_airflow_m3_h"],
                "m³/h",
            )
            + " |"
        ),
        (
            "| Makeup-air total load | "
            + _format_interval(result["makeup_air_total_kw"], "kW")
            + " |"
        ),
        (
            "| Net room + makeup load | "
            + _format_interval(result["net_room_plus_makeup_kw"], "kW")
            + " |"
        ),
        "",
        (
            "Governing airflow bases encountered: **"
            + ", ".join(result["governing_airflow_bases"])
            + "**."
        ),
        "",
        "## Internal sensible-load airflow",
        "",
        (
            f"- Status: **{thermal_airflow['status']}**."
        ),
        (
            f"- Nominal: **{thermal_airflow['nominal']} m³/h**."
            if thermal_airflow["nominal"] is not None
            else "- Nominal: **not defined**."
        ),
        (
            f"- Endpoint envelope: **{thermal_airflow['lower']} to "
            f"{thermal_airflow['upper']} m³/h**."
            if thermal_airflow["lower"] is not None
            else "- Endpoint envelope: **not defined**."
        ),
        "",
        "## Input provenance",
        "",
        f"- Complete: **{'yes' if traceability['complete'] else 'no'}**.",
        (
            f"- Inputs with provenance: **{traceability['inputs_with_provenance']}/"
            f"{traceability['input_count']}**."
        ),
        "",
        "| Input | Nominal | ± uncertainty | Endpoint interval | Source | Reference |",
        "|---|---:|---:|---:|---|---|",
    ]

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
