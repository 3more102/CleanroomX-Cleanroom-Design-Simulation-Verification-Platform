from __future__ import annotations


def _fmt_counts(counts: dict) -> str:
    if not counts:
        return "—"
    return ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))


def markdown_dossier_report(result: dict) -> str:
    summary = result["executive_summary"]
    lines = [f"# CleanroomX Engineering Dossier — {result['dossier']}", ""]

    metadata = result["metadata"]
    if any(value is not None for value in metadata.values()):
        lines.extend(["## Dossier metadata", ""])
        for key, value in metadata.items():
            if value is not None:
                lines.append(f"- {key.replace('_', ' ').title()}: {value}")
        lines.append("")

    lines.extend(
        [
            "## Executive summary",
            "",
            f"- Dossier state: **{summary['state'].upper()}**",
            f"- Attention items: **{summary['adverse_item_count']}**",
            f"- Unchecked items: **{summary['unresolved_item_count']}**",
            "",
            "| Component | Status | Detail |",
            "|---|---|---|",
        ]
    )
    for name, component in summary["components"].items():
        detail = _fmt_counts(component.get("counts", {}))
        if name == "hvac" and component["status"] != "not_included":
            detail = f"failed_air_balances={component['failed_air_balances']}"
        lines.append(f"| {name} | {component['status']} | {detail} |")

    verification = result["verification"]
    if verification is not None:
        lines.extend(["", "## Room and pressure-cascade verification", ""])
        for room in verification["rooms"]:
            fail_count = sum(item["status"] == "fail" for item in room["findings"])
            unchecked = sum(
                item["status"] == "not_checked" for item in room["findings"]
            )
            lines.append(
                f"- **{room['room']}** — ACH {room['ach']:.3f} 1/h; "
                f"failures {fail_count}; unchecked {unchecked}."
            )
        if verification["pressure_cascade"]:
            cascade_failures = sum(
                item["status"] == "fail" for item in verification["pressure_cascade"]
            )
            lines.append(
                f"- Pressure-cascade links: {len(verification['pressure_cascade'])}; "
                f"failures: {cascade_failures}."
            )

    hvac = result["hvac"]
    if hvac is not None:
        lines.extend(
            [
                "",
                "## HVAC / duct screening",
                "",
                f"- Governing airflow: **{hvac['total_governing_airflow_m3_h']} m³/h**",
                f"- Preliminary cooling capacity: **{hvac['total_preliminary_cooling_capacity_kw']} kW**",
                f"- Preliminary heating capacity: **{hvac['total_preliminary_heating_capacity_kw']} kW**",
                f"- All airflow-surplus checks pass: **{hvac['all_air_balances_pass']}**",
            ]
        )
        if hvac.get("duct_network") is not None:
            network = hvac["duct_network"]
            lines.append(
                f"- Critical duct path: **{network['critical_path']}** at "
                f"**{network['critical_path_pressure_drop_pa']} Pa**"
            )
        if hvac.get("branch_flow_network") is not None:
            network = hvac["branch_flow_network"]
            lines.append(
                f"- Critical branch-flow terminal: **{network['critical_terminal']}** at "
                f"**{network['critical_path_pressure_drop_pa']} Pa**"
            )
        if hvac.get("supply_fan") is not None:
            fan = hvac["supply_fan"]
            lines.append(
                f"- Preliminary fan electrical input: "
                f"**{fan['estimated_electrical_input_kw']} kW**"
            )
        if hvac.get("fan_curve_duty_check") is not None:
            check = hvac["fan_curve_duty_check"]
            lines.append(
                f"- Fan-curve duty check: **{check['status']}** at "
                f"**{check['required_airflow_m3_h']} m³/h / "
                f"{check['required_pressure_pa']} Pa**"
            )
            if check["available_fan_pressure_pa"] is not None:
                lines.append(
                    f"- Interpolated fan pressure: "
                    f"**{check['available_fan_pressure_pa']} Pa**; "
                    f"margin **{check['pressure_margin_pa']} Pa**"
                )
            else:
                low, high = check["fan_curve_airflow_range_m3_h"]
                lines.append(
                    f"- Supplied fan-curve airflow range: **{low} to {high} m³/h**; "
                    "no extrapolation performed."
                )

    if result["recovery_tests"]:
        lines.extend(
            [
                "",
                "## Recovery qualification",
                "",
                "| Test | Status | Observed recovery min | Target particles/m³ |",
                "|---|---|---:|---:|",
            ]
        )
        for item in result["recovery_tests"]:
            observed = (
                "—"
                if item["observed_recovery_time_minutes"] is None
                else item["observed_recovery_time_minutes"]
            )
            lines.append(
                f"| {item['test']} | {item['criterion_status']} | {observed} | "
                f"{item['target_concentration_per_m3']} |"
            )

    if result["qualification_analyses"]:
        lines.extend(
            [
                "",
                "## Uncertainty-aware qualification",
                "",
                "| Analysis | Overall status | Provenance complete |",
                "|---|---|---|",
            ]
        )
        for item in result["qualification_analyses"]:
            lines.append(
                f"| {item['analysis']} | {item['overall_status']} | "
                f"{'yes' if item['traceability']['complete'] else 'no'} |"
            )

    if result["uncertainty_rooms"]:
        lines.extend(
            [
                "",
                "## Uncertainty / provenance screening",
                "",
                "| Room | Requirement status | ACH interval 1/h | Provenance complete |",
                "|---|---|---|---|",
            ]
        )
        for item in result["uncertainty_rooms"]:
            ach = item["ach_1_h"]
            lines.append(
                f"| {item['room']} | {item['requirement']['status']} | "
                f"{ach['lower']} to {ach['upper']} | "
                f"{'yes' if item['traceability']['complete'] else 'no'} |"
            )

    if result["thermal_uncertainty_analyses"]:
        lines.extend(
            [
                "",
                "## Thermal/HVAC uncertainty screening",
                "",
                "| Analysis | Status | Cooling interval kW | Heating interval kW | Provenance complete |",
                "|---|---|---:|---:|---|",
            ]
        )
        for item in result["thermal_uncertainty_analyses"]:
            cooling = item["cooling_capacity_kw"]
            heating = item["heating_capacity_kw"]
            lines.append(
                f"| {item['analysis']} | {item['overall_status']} | "
                f"{cooling['lower']} to {cooling['upper']} | "
                f"{heating['lower']} to {heating['upper']} | "
                f"{'yes' if item['traceability']['complete'] else 'no'} |"
            )

    if result["fan_operating_point_studies"]:
        lines.extend(
            [
                "",
                "## Fan/system operating-point studies",
                "",
                "| Study | Status | Airflow m³/h | Pressure Pa |",
                "|---|---|---:|---:|",
            ]
        )
        for item in result["fan_operating_point_studies"]:
            point = item["operating_point"]
            airflow = "—" if point is None else point["airflow_m3_h"]
            pressure = "—" if point is None else point["system_pressure_pa"]
            lines.append(
                f"| {item['study']} | {item['status']} | {airflow} | {pressure} |"
            )

    lines.extend(
        [
            "",
            "## Source-file fingerprints",
            "",
            "| Kind | Path | SHA-256 |",
            "|---|---|---|",
        ]
    )
    for source in result["source_files"]:
        lines.append(
            f"| {source['kind']} | {source['path']} | `{source['sha256']}` |"
        )

    lines.extend(
        [
            "",
            "## Scope note",
            "",
            summary["scope_note"],
            "",
        ]
    )
    return "\n".join(lines)
