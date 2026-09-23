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
        elif name == "psychrometric_uncertainty" and component["status"] != "not_included":
            detail = (
                f"analyses={component['analysis_count']}, "
                f"missing_provenance={component['missing_provenance_analyses']}"
            )
        elif name == "fan_system_uncertainty" and component["status"] != "not_included":
            detail = (
                f"analyses={component['analysis_count']}, "
                f"missing_provenance={component['missing_provenance_analyses']}, "
                f"indeterminate={component['counts'].get('indeterminate', 0)}"
            )
        elif name == "fan_loop_uncertainty" and component["status"] != "not_included":
            detail = (
                f"analyses={component['analysis_count']}, "
                f"missing_provenance={component['missing_provenance_analyses']}, "
                f"indeterminate={component['counts'].get('indeterminate', 0)}"
            )
        elif name == "fan_speed_studies" and component["status"] != "not_included":
            detail = (
                f"studies={component['study_count']}, "
                f"speed_cases={component['speed_case_count']}, "
                f"{_fmt_counts(component.get('counts', {}))}"
            )
        elif name == "fan_loop_speed_studies" and component["status"] != "not_included":
            detail = (
                f"studies={component['study_count']}, "
                f"speed_cases={component['speed_case_count']}, "
                f"{_fmt_counts(component.get('counts', {}))}"
            )
        elif (
            name == "fan_variable_friction_loops"
            and component["status"] != "not_included"
        ):
            detail = (
                f"studies={component['study_count']}, "
                f"{_fmt_counts(component.get('counts', {}))}"
            )
        elif (
            name == "fan_variable_friction_speed_studies"
            and component["status"] != "not_included"
        ):
            detail = (
                f"studies={component['study_count']}, "
                f"speed_cases={component['speed_case_count']}, "
                f"{_fmt_counts(component.get('counts', {}))}"
            )
        elif (
            name == "fan_variable_friction_uncertainty"
            and component["status"] != "not_included"
        ):
            detail = (
                f"analyses={component['analysis_count']}, "
                f"corners={component['corner_count']}, "
                f"fan_curve_scenarios={component.get('fan_curve_scenario_count', 0)}, "
                f"missing_provenance={component['missing_provenance_analyses']}, "
                f"indeterminate={component['counts'].get('indeterminate', 0)}"
            )
        elif name == "cross_module_consistency" and component["status"] != "not_included":
            detail = (
                f"shared_rooms={component['shared_room_count']}, "
                f"mismatches={component['mismatch_count']}, "
                f"room_set_mismatch={component['room_set_mismatch']}"
            )
        elif (
            name == "hvac_fan_operating_airflow_consistency"
            and component["status"] != "not_included"
        ):
            detail = (
                f"studies={component['study_count']}, "
                f"solved={component['solved_study_count']}, "
                f"mismatches={component['mismatch_count']}, "
                f"unresolved={component['unresolved_study_count']}"
            )
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
                f"- Fan-curve HVAC duty check: **{check['status']}** at "
                f"**{check['required_airflow_m3_h']} m³/h / {check['required_pressure_pa']} Pa**"
            )
            if check["pressure_margin_pa"] is not None:
                lines.append(
                    f"- Fan-curve pressure margin: **{check['pressure_margin_pa']} Pa**"
                )

    consistency = result.get("consistency_checks", {}).get(
        "verification_hvac_airflow"
    )
    if consistency is not None:
        lines.extend(
            [
                "",
                "## Cross-module verification / HVAC consistency",
                "",
                f"- Status: **{consistency['status']}**",
                (
                    "- Room airflow absolute consistency tolerance: "
                    f"**{consistency['room_airflow_abs_tolerance_m3_h']} m³/h**"
                ),
                (
                    "- Require identical room sets: "
                    f"**{consistency['require_same_room_set']}**"
                ),
                f"- Shared rooms: **{consistency['shared_room_count']}**",
                f"- Airflow mismatches: **{consistency['mismatch_count']}**",
            ]
        )
        if consistency["room_airflow_checks"]:
            lines.extend(
                [
                    "",
                    (
                        "| Room | Verification supply m³/h | HVAC cleanroom m³/h | "
                        "Difference m³/h | Absolute difference m³/h | Status |"
                    ),
                    "|---|---:|---:|---:|---:|---|",
                ]
            )
            for item in consistency["room_airflow_checks"]:
                lines.append(
                    f"| {item['room']} | "
                    f"{item['verification_supply_airflow_m3_h']} | "
                    f"{item['hvac_cleanroom_airflow_m3_h']} | "
                    f"{item['difference_m3_h']} | "
                    f"{item['absolute_difference_m3_h']} | "
                    f"{item['status']} |"
                )
        if consistency["verification_only_rooms"]:
            lines.append(
                "- Verification-only rooms: "
                + ", ".join(consistency["verification_only_rooms"])
            )
        if consistency["hvac_only_rooms"]:
            lines.append(
                "- HVAC-only rooms: "
                + ", ".join(consistency["hvac_only_rooms"])
            )
        lines.extend(["", consistency["scope_note"]])

    if result["recovery_tests"]:
        lines.extend(
            [
                "",
                "## Recovery qualification",
                "",
                "| Test | Status | Nominal recovery min | Confirmed recovery min | Target particles/m³ |",
                "|---|---|---:|---:|---:|",
            ]
        )
        for item in result["recovery_tests"]:
            observed = (
                "—"
                if item["observed_recovery_time_minutes"] is None
                else item["observed_recovery_time_minutes"]
            )
            confirmed = item.get("uncertainty_assessment", {}).get(
                "first_confirmed_recovery_sample_time_minutes"
            )
            confirmed = "—" if confirmed is None else confirmed
            lines.append(
                f"| {item['test']} | {item['criterion_status']} | {observed} | "
                f"{confirmed} | {item['target_concentration_per_m3']} |"
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

    if result["psychrometric_uncertainty_analyses"]:
        lines.extend(
            [
                "",
                "## Psychrometric-state uncertainty screening",
                "",
                "| Analysis | Corners | Humidity ratio g/kg dry air | Enthalpy kJ/kg dry air | Provenance complete |",
                "|---|---:|---:|---:|---|",
            ]
        )
        for item in result["psychrometric_uncertainty_analyses"]:
            humidity = item["psychrometric_properties"]["humidity_ratio_g_kg_da"]
            enthalpy = item["psychrometric_properties"]["enthalpy_kj_kg_da"]
            lines.append(
                f"| {item['analysis']} | {item['corner_count']} | "
                f"{humidity['lower']} to {humidity['upper']} | "
                f"{enthalpy['lower']} to {enthalpy['upper']} | "
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

    if result.get("fan_system_uncertainty_analyses"):
        lines.extend(
            [
                "",
                "## Fan/system bounded uncertainty screening",
                "",
                "| Analysis | Status | Solved corners | Airflow envelope m³/h | Pressure envelope Pa | Provenance complete |",
                "|---|---|---:|---:|---:|---|",
            ]
        )
        for item in result["fan_system_uncertainty_analyses"]:
            envelope = item["operating_point_envelope"]
            airflow = (
                "—"
                if envelope is None
                else f"{envelope['airflow_m3_h']['lower']} to {envelope['airflow_m3_h']['upper']}"
            )
            pressure = (
                "—"
                if envelope is None
                else f"{envelope['system_pressure_pa']['lower']} to {envelope['system_pressure_pa']['upper']}"
            )
            lines.append(
                f"| {item['analysis']} | {item['status']} | "
                f"{item['solved_corner_count']}/{item['corner_count']} | "
                f"{airflow} | {pressure} | "
                f"{'yes' if item['traceability']['complete'] else 'no'} |"
            )

    if result.get("fan_speed_studies"):
        lines.extend(
            [
                "",
                "## Fan affinity-law speed studies",
                "",
                "| Study | Study status | Speed ratio | Speed rpm | Case status | Airflow m³/h | Pressure Pa |",
                "|---|---|---:|---:|---|---:|---:|",
            ]
        )
        for item in result["fan_speed_studies"]:
            for case in item["speed_cases"]:
                point = case["operating_point"]
                speed_rpm = "—" if case["speed_rpm"] is None else case["speed_rpm"]
                airflow = "—" if point is None else point["airflow_m3_h"]
                pressure = "—" if point is None else point["system_pressure_pa"]
                lines.append(
                    f"| {item['study']} | {item['status']} | "
                    f"{case['speed_ratio']} | {speed_rpm} | {case['status']} | "
                    f"{airflow} | {pressure} |"
                )

    if result["fan_duct_network_studies"]:
        lines.extend(
            [
                "",
                "## Fan/duct-network operating-point studies",
                "",
                "| Study | Status | Critical path | Operating airflow m³/h | System pressure Pa |",
                "|---|---|---|---:|---:|",
            ]
        )
        for item in result["fan_duct_network_studies"]:
            point = item["operating_point"]
            airflow = "—" if point is None else point["airflow_m3_h"]
            pressure = "—" if point is None else point["system_pressure_pa"]
            lines.append(
                f"| {item['study']} | {item['status']} | {item['critical_path']} | "
                f"{airflow} | {pressure} |"
            )

    if result["fan_parallel_network_studies"]:
        lines.extend(
            [
                "",
                "## Fan-driven parallel-network studies",
                "",
                "| Study | Status | Equivalent R Pa/(m³/s)² | Operating airflow m³/h | System pressure Pa |",
                "|---|---|---:|---:|---:|",
            ]
        )
        for item in result["fan_parallel_network_studies"]:
            point = item["fan_operating_point"]
            pressure_check = item["system_pressure_check"]
            airflow = "—" if point is None else point["airflow_m3_h"]
            pressure = (
                "—"
                if pressure_check is None
                else pressure_check["total_system_pressure_pa"]
            )
            lines.append(
                f"| {item['study']} | {item['status']} | "
                f"{item['equivalent_network_resistance_pa_per_m3_s_squared']} | "
                f"{airflow} | {pressure} |"
            )

    if result.get("fan_loop_network_studies"):
        lines.extend(["", "## Fan/loop-network operating-point studies", "", "| Study | Status | Equivalent R Pa/(m³/s)² | Operating airflow m³/h | System pressure Pa |", "|---|---|---:|---:|---:|"])
        for item in result["fan_loop_network_studies"]:
            point = item["fan_operating_point"]
            check = item["system_pressure_check"]
            airflow = "—" if point is None else point["airflow_m3_h"]
            pressure = "—" if check is None else check["total_system_pressure_pa"]
            lines.append(f"| {item['study']} | {item['status']} | {item['equivalent_loop_resistance_pa_per_m3_s_squared']} | {airflow} | {pressure} |")

    if result.get("fan_variable_friction_loop_studies"):
        lines.extend(
            [
                "",
                "## Fan / variable-friction loop studies",
                "",
                "| Study | Status | Operating airflow m³/h | System pressure Pa | "
                "Outer iterations | Resistance closure | Continuity residual m³/h | "
                "Edge-law residual Pa | Fan-system residual Pa | Fluid air power kW | "
                "Electrical input kW | Edge dissipation W | Termination |",
                "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
            ]
        )
        for item in result["fan_variable_friction_loop_studies"]:
            point = item.get("fan_operating_point")
            check = item.get("system_pressure_check")
            diagnostics = item.get("solver_diagnostics", {})
            power = item.get("power_evidence")
            airflow = "—" if point is None else point["airflow_m3_h"]
            pressure = (
                "—" if check is None else check["total_system_pressure_pa"]
            )
            residual = (
                "—" if check is None else check["fan_minus_system_pressure_pa"]
            )
            fluid_power = (
                "—" if power is None else power["fluid_air_power_kw"]
            )
            electrical_power = (
                "—"
                if power is None or power["electrical_input_kw"] is None
                else power["electrical_input_kw"]
            )
            edge_dissipation = (
                "—"
                if power is None
                else power["system_components"][
                    "loop_network_edge_dissipation_w"
                ]
            )
            lines.append(
                f"| {item['study']} | {item['status']} | {airflow} | "
                f"{pressure} | {diagnostics.get('network_outer_iterations', '—')} | "
                f"{diagnostics.get('network_max_relative_resistance_closure_error', '—')} | "
                f"{diagnostics.get('max_abs_mass_balance_residual_m3_h', '—')} | "
                f"{diagnostics.get('max_abs_pressure_law_residual_pa', '—')} | "
                f"{residual} | {fluid_power} | {electrical_power} | "
                f"{edge_dissipation} | "
                f"{diagnostics.get('termination_reason', '—')} |"
            )

    if result.get("fan_loop_uncertainty_analyses"):
        lines.extend(
            [
                "",
                "## Fan/loop-network uncertainty analyses",
                "",
                "| Analysis | Status | Corners | Solved | Unresolved | Operating airflow envelope m³/h | Provenance complete |",
                "|---|---|---:|---:|---:|---|---|",
            ]
        )
        for item in result["fan_loop_uncertainty_analyses"]:
            envelope = item.get("operating_point_envelope")
            airflow_envelope = (
                "—"
                if envelope is None
                else (
                    f"{envelope['airflow_m3_h']['lower']}–"
                    f"{envelope['airflow_m3_h']['upper']}"
                )
            )
            lines.append(
                f"| {item['analysis']} | {item['status']} | {item['corner_count']} | "
                f"{item['solved_corner_count']} | {item['unresolved_corner_count']} | "
                f"{airflow_envelope} | {item['traceability']['complete']} |"
            )

    if result.get("fan_variable_friction_uncertainty_analyses"):
        lines.extend(
            [
                "",
                "## Fan / variable-friction loop uncertainty analyses",
                "",
                "| Analysis | Status | Corners | Solved | Unresolved | Whole fan-curve scenarios | Operating airflow envelope m³/h | Airflow excursion from nominal % | Air-power envelope kW | Electrical-input corner range kW | Electrical coverage | SFP corner range W/(m³/s) | SFP coverage | Nominal state | Solver tolerance audit | Fan-curve min headroom m³/h | Boundary evidence | Provenance complete |",
                "|---|---|---:|---:|---:|---|---|---|---|---|---|---|---|---|---|---:|---|---|",
            ]
        )
        for item in result[
            "fan_variable_friction_uncertainty_analyses"
        ]:
            envelope = item.get("operating_point_envelope")
            airflow_envelope = (
                "—"
                if envelope is None
                else (
                    f"{envelope['airflow_m3_h']['lower']}–"
                    f"{envelope['airflow_m3_h']['upper']}"
                )
            )
            air_power = (
                "—"
                if envelope is None or envelope.get("air_power_kw") is None
                else (
                    f"{envelope['air_power_kw']['lower']}–"
                    f"{envelope['air_power_kw']['upper']}"
                )
            )
            excursions = item.get("operating_point_excursions_from_nominal")
            airflow_excursion = "—"
            if excursions is not None:
                airflow_evidence = excursions.get("airflow_m3_h")
                if airflow_evidence is not None:
                    lower_percent = airflow_evidence.get("lower_percent")
                    upper_percent = airflow_evidence.get("upper_percent")
                    if lower_percent is not None and upper_percent is not None:
                        airflow_excursion = (
                            f"{lower_percent}–{upper_percent}"
                        )
            power_ranges = item.get("power_evidence_corner_ranges")
            power_availability = item.get("power_evidence_availability")
            electrical_input = "—"
            specific_fan_power = "—"
            electrical_coverage = "—"
            sfp_coverage = "—"
            if power_availability is not None:
                electrical_evidence = power_availability.get(
                    "electrical_input_kw"
                )
                if electrical_evidence is not None:
                    electrical_coverage = (
                        f"{electrical_evidence['status']} "
                        f"({electrical_evidence['available_corner_count']}/"
                        f"{electrical_evidence['total_corner_count']})"
                    )
                sfp_evidence = power_availability.get(
                    "specific_fan_power_w_per_m3_s"
                )
                if sfp_evidence is not None:
                    sfp_coverage = (
                        f"{sfp_evidence['status']} "
                        f"({sfp_evidence['available_corner_count']}/"
                        f"{sfp_evidence['total_corner_count']})"
                    )
            if power_ranges is not None:
                electrical_range = power_ranges.get("electrical_input_kw")
                if electrical_range is not None:
                    electrical_input = (
                        f"{electrical_range['lower']}–"
                        f"{electrical_range['upper']}"
                    )
                sfp_range = power_ranges.get(
                    "specific_fan_power_w_per_m3_s"
                )
                if sfp_range is not None:
                    specific_fan_power = (
                        f"{sfp_range['lower']}–{sfp_range['upper']}"
                    )
            scenario_names = ", ".join(
                scenario["name"]
                for scenario in item.get("fan_curve_scenarios", [])
            ) or "—"
            solver_tolerance_audit = (
                item.get("solver_quality_summary", {})
                .get("configured_tolerance_assessment", {})
                .get("status", "—")
            )
            boundary_summary = item.get(
                "fan_curve_boundary_clearance_summary"
            )
            fan_curve_headroom = "—"
            boundary_coverage = "—"
            if boundary_summary is not None:
                boundary_coverage = (
                    f"{boundary_summary['solved_corner_count']}/"
                    f"{boundary_summary['corner_count']}"
                )
                boundary_evidence = boundary_summary.get(
                    "minimum_nearest_boundary_headroom_m3_h"
                )
                if boundary_evidence is not None:
                    fan_curve_headroom = boundary_evidence["value"]
            lines.append(
                f"| {item['analysis']} | {item['status']} | "
                f"{item['corner_count']} | {item['solved_corner_count']} | "
                f"{item['unresolved_corner_count']} | {scenario_names} | "
                f"{airflow_envelope} | {airflow_excursion} | {air_power} | "
                f"{electrical_input} | {electrical_coverage} | "
                f"{specific_fan_power} | {sfp_coverage} | "
                f"{item['nominal_status']} | "
                f"{solver_tolerance_audit} | {fan_curve_headroom} | "
                f"{boundary_coverage} | "
                f"{item['traceability']['complete']} |"
            )
            if item["traceability"]["missing_provenance"]:
                lines.append(
                    "- Missing uncertainty provenance for "
                    f"**{item['analysis']}**: "
                    + ", ".join(
                        item["traceability"]["missing_provenance"]
                    )
                )

    if result.get("fan_loop_speed_studies"):
        lines.extend(
            [
                "",
                "## Fan-speed / loop-network studies",
                "",
                "| Study | Speed ratio | Speed rpm | Status | Operating airflow m³/h | System pressure Pa | Continuity residual m³/h | Fan-system residual Pa |",
                "|---|---:|---:|---|---:|---:|---:|---:|",
            ]
        )
        for study in result["fan_loop_speed_studies"]:
            for case in study.get("speed_cases", []):
                point = case.get("fan_operating_point")
                network = case.get("operating_network_solution")
                check = case.get("system_pressure_check")
                airflow = "—" if point is None else point["airflow_m3_h"]
                pressure = "—" if point is None else point["system_pressure_pa"]
                continuity = (
                    "—"
                    if network is None
                    else network["max_abs_mass_balance_residual_m3_h"]
                )
                residual = (
                    "—"
                    if check is None
                    else check["fan_minus_system_pressure_pa"]
                )
                rpm = "—" if case.get("speed_rpm") is None else case["speed_rpm"]
                lines.append(
                    f"| {study['study']} | {case['speed_ratio']} | {rpm} | "
                    f"{case['status']} | {airflow} | {pressure} | "
                    f"{continuity} | {residual} |"
                )

    if result.get("fan_variable_friction_speed_studies"):
        lines.extend(
            [
                "",
                "## Fan-speed / variable-friction loop studies",
                "",
                "| Study | Speed ratio | Speed rpm | Status | Operating airflow m³/h | "
                "System pressure Pa | Outer iterations | Resistance closure | "
                "Continuity residual m³/h | Edge-law residual Pa | "
                "Fan-system residual Pa | Fluid air power kW | "
                "Electrical input kW | Edge dissipation W | Termination |",
                "|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
            ]
        )
        for study in result["fan_variable_friction_speed_studies"]:
            for case in study.get("speed_cases", []):
                point = case.get("fan_operating_point")
                check = case.get("system_pressure_check")
                diagnostics = case.get("solver_diagnostics", {})
                power = case.get("power_evidence")
                airflow = "—" if point is None else point["airflow_m3_h"]
                pressure = (
                    "—" if check is None else check["total_system_pressure_pa"]
                )
                residual = (
                    "—"
                    if check is None
                    else check["fan_minus_system_pressure_pa"]
                )
                fluid_power = (
                    "—" if power is None else power["fluid_air_power_kw"]
                )
                electrical_power = (
                    "—"
                    if power is None or power["electrical_input_kw"] is None
                    else power["electrical_input_kw"]
                )
                edge_dissipation = (
                    "—"
                    if power is None
                    else power["system_components"][
                        "loop_network_edge_dissipation_w"
                    ]
                )
                rpm = (
                    "—" if case.get("speed_rpm") is None else case["speed_rpm"]
                )
                lines.append(
                    f"| {study['study']} | {case['speed_ratio']} | {rpm} | "
                    f"{case['status']} | {airflow} | {pressure} | "
                    f"{diagnostics.get('network_outer_iterations', '—')} | "
                    f"{diagnostics.get('network_max_relative_resistance_closure_error', '—')} | "
                    f"{diagnostics.get('max_abs_mass_balance_residual_m3_h', '—')} | "
                    f"{diagnostics.get('max_abs_pressure_law_residual_pa', '—')} | "
                    f"{residual} | {fluid_power} | {electrical_power} | "
                    f"{edge_dissipation} | "
                    f"{diagnostics.get('termination_reason', '—')} |"
                )

    if result.get("damper_studies"):
        lines.extend(["", "## Loop damper-resistance scenario studies", "", "| Study | Status | Cases | Baseline continuity residual m³/h | Baseline pressure-law residual Pa |", "|---|---|---:|---:|---:|"])
        for item in result["damper_studies"]:
            baseline = item["baseline_solution"]
            lines.append(f"| {item['study']} | {item['status']} | {len(item['cases'])} | {baseline['max_abs_mass_balance_residual_m3_h']} | {baseline['max_abs_pressure_law_residual_pa']} |")

    fan_airflow_consistency = result.get("consistency_checks", {}).get(
        "hvac_fan_operating_airflow"
    )
    if fan_airflow_consistency is not None:
        lines.extend(
            [
                "",
                "## HVAC / fan operating-airflow consistency",
                "",
                f"- Status: **{fan_airflow_consistency['status']}**",
                (
                    "- HVAC governing airflow: "
                    f"**{fan_airflow_consistency['hvac_governing_airflow_m3_h']} m³/h**"
                ),
                (
                    "- Absolute consistency tolerance: "
                    f"**{fan_airflow_consistency['airflow_abs_tolerance_m3_h']} m³/h**"
                ),
                f"- Fan operating points/cases: **{fan_airflow_consistency['study_count']}**",
                f"- Mismatches: **{fan_airflow_consistency['mismatch_count']}**",
                f"- Unresolved: **{fan_airflow_consistency['unresolved_study_count']}**",
                "",
                (
                    "| Study type | Study | HVAC airflow m³/h | Fan operating airflow m³/h | "
                    "Absolute difference m³/h | Status |"
                ),
                "|---|---|---:|---:|---:|---|",
            ]
        )
        for item in fan_airflow_consistency["study_airflow_checks"]:
            fan_airflow = (
                "—"
                if item["fan_operating_airflow_m3_h"] is None
                else item["fan_operating_airflow_m3_h"]
            )
            absolute_difference = (
                "—"
                if item["absolute_difference_m3_h"] is None
                else item["absolute_difference_m3_h"]
            )
            lines.append(
                f"| {item['study_kind']} | {item['study']} | "
                f"{item['hvac_governing_airflow_m3_h']} | {fan_airflow} | "
                f"{absolute_difference} | {item['status']} |"
            )
        lines.extend(["", fan_airflow_consistency["scope_note"]])

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
