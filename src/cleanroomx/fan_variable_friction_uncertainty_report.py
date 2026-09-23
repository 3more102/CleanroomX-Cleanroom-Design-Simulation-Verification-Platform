from __future__ import annotations


def _fmt(value: object) -> str:
    return "—" if value is None else str(value)


def _fmt_extreme_source(source: dict) -> str:
    parts = [
        f"corner {source['corner_index']}",
        f"fixed={source['fixed_pressure_pa']} Pa",
    ]
    if "fan_speed_ratio" in source:
        parts.append(f"speed={source['fan_speed_ratio']}")
    if "fan_curve_scenario" in source:
        parts.append(f"scenario={source['fan_curve_scenario']}")

    labels = (
        ("fan_curve_pressure_pa", "fan-P"),
        ("fan_curve_airflow_m3_h", "fan-Q"),
        ("edge_local_loss_coefficient", "K"),
        ("edge_absolute_roughness_m", "roughness"),
        ("edge_kinematic_viscosity_m2_s", "viscosity"),
        ("edge_air_density_kg_m3", "density"),
        ("edge_length_m", "length"),
        ("edge_circular_diameter_m", "diameter"),
        ("edge_rectangular_width_m", "width"),
        ("edge_rectangular_height_m", "height"),
    )
    for key, label in labels:
        values = source.get(key)
        if values:
            encoded = ", ".join(
                f"{name}={value}" for name, value in values.items()
            )
            parts.append(f"{label}[{encoded}]")
    return "; ".join(parts)


def markdown_fan_variable_friction_loop_uncertainty_report(
    result: dict,
) -> str:
    lines = [
        "# CleanroomX Fan / Variable-Friction Loop Uncertainty Report — "
        f"{result['analysis']}",
        "",
        f"- Status: **{result['status'].upper()}**",
        f"- Fan curve: **{result['fan_curve']}**",
        f"- Loop network: **{result['loop_network']}**",
        f"- Solved corners: **{result['solved_corner_count']}/{result['corner_count']}**",
        "",
        "## Input intervals",
        "",
    ]

    fixed = result["input_intervals"]["fixed_pressure_pa"]
    lines.append(
        f"- Fixed pressure: **{fixed['lower']} to {fixed['upper']} Pa** "
        f"(nominal {fixed['nominal']} Pa)"
    )
    speed = result["input_intervals"].get("fan_speed_ratio")
    if speed is not None:
        lines.append(
            f"- Fan speed ratio: **{speed['lower']} to {speed['upper']}** "
            f"(nominal {speed['nominal']})"
        )
    for airflow, interval in result["input_intervals"].get(
        "fan_curve_pressure_pa", {}
    ).items():
        lines.append(
            f"- Fan pressure at `{airflow} m³/h`: "
            f"**{interval['lower']} to {interval['upper']} Pa** "
            f"(nominal {interval['nominal']} Pa)"
        )
    for point_index, interval in result["input_intervals"].get(
        "fan_curve_airflow_m3_h", {}
    ).items():
        lines.append(
            f"- Fan airflow at point index `{point_index}`: "
            f"**{interval['lower']} to {interval['upper']} m³/h** "
            f"(nominal {interval['nominal']} m³/h)"
        )
    for name, interval in result["input_intervals"][
        "edge_local_loss_coefficient"
    ].items():
        lines.append(
            f"- Edge `{name}` local-loss coefficient K: "
            f"**{interval['lower']} to {interval['upper']}** "
            f"(nominal {interval['nominal']})"
        )
    for name, interval in result["input_intervals"].get(
        "edge_absolute_roughness_m", {}
    ).items():
        lines.append(
            f"- Edge `{name}` Absolute roughness: "
            f"**{interval['lower']} to {interval['upper']} m** "
            f"(nominal {interval['nominal']} m)"
        )
    for name, interval in result["input_intervals"].get(
        "edge_kinematic_viscosity_m2_s", {}
    ).items():
        lines.append(
            f"- Edge `{name}` Kinematic viscosity: "
            f"**{interval['lower']} to {interval['upper']} m²/s** "
            f"(nominal {interval['nominal']} m²/s)"
        )
    for name, interval in result["input_intervals"].get(
        "edge_air_density_kg_m3", {}
    ).items():
        lines.append(
            f"- Edge `{name}` Air density: "
            f"**{interval['lower']} to {interval['upper']} kg/m³** "
            f"(nominal {interval['nominal']} kg/m³)"
        )
    for name, interval in result["input_intervals"].get(
        "edge_length_m", {}
    ).items():
        lines.append(
            f"- Edge `{name}` Duct length: "
            f"**{interval['lower']} to {interval['upper']} m** "
            f"(nominal {interval['nominal']} m)"
        )
    for name, interval in result["input_intervals"].get(
        "edge_circular_diameter_m", {}
    ).items():
        lines.append(
            f"- Edge `{name}` Circular diameter: "
            f"**{interval['lower']} to {interval['upper']} m** "
            f"(nominal {interval['nominal']} m)"
        )
    for name, interval in result["input_intervals"].get(
        "edge_rectangular_width_m", {}
    ).items():
        lines.append(
            f"- Edge `{name}` Rectangular width: "
            f"**{interval['lower']} to {interval['upper']} m** "
            f"(nominal {interval['nominal']} m)"
        )
    for name, interval in result["input_intervals"].get(
        "edge_rectangular_height_m", {}
    ).items():
        lines.append(
            f"- Edge `{name}` Rectangular height: "
            f"**{interval['lower']} to {interval['upper']} m** "
            f"(nominal {interval['nominal']} m)"
        )

    scenarios = result.get("fan_curve_scenarios", [])
    if scenarios:
        lines.extend(["", "## Whole fan-curve scenarios", ""])
        for scenario in scenarios:
            point_text = ", ".join(
                f"{point['airflow_m3_h']} m³/h @ {point['pressure_pa']} Pa"
                for point in scenario["points"]
            )
            lines.append(
                f"- `{scenario['name']}`: {point_text}"
            )

    lines.extend(["", "## Nominal operating point", ""])
    nominal = result["nominal_operating_point"]
    if nominal is None:
        lines.append(
            f"Nominal state: **{result['nominal_status']}**; "
            "no nominal operating point is reported."
        )
    else:
        lines.extend(
            [
                f"- Airflow: **{nominal['airflow_m3_h']} m³/h**",
                f"- Fan pressure: **{nominal['fan_pressure_pa']} Pa**",
                f"- System pressure: **{nominal['system_pressure_pa']} Pa**",
                f"- Air power: **{nominal['air_power_kw']} kW**",
            ]
        )

    lines.extend(["", "## Bounded corner envelope", ""])
    envelope = result["operating_point_envelope"]
    if envelope is None:
        lines.append(result["message"])
    else:
        witnesses = result.get("operating_point_extreme_cases") or {}
        lines.extend(
            [
                "- Airflow: "
                f"**{envelope['airflow_m3_h']['lower']} to "
                f"{envelope['airflow_m3_h']['upper']} m³/h**"
                + (
                    " "
                    f"(corner indices {witnesses['airflow_m3_h']['lower']['corner_index']} "
                    f"to {witnesses['airflow_m3_h']['upper']['corner_index']})"
                    if "airflow_m3_h" in witnesses
                    else ""
                ),
                "- Fan pressure: "
                f"**{envelope['fan_pressure_pa']['lower']} to "
                f"{envelope['fan_pressure_pa']['upper']} Pa**"
                + (
                    " "
                    f"(corner indices {witnesses['fan_pressure_pa']['lower']['corner_index']} "
                    f"to {witnesses['fan_pressure_pa']['upper']['corner_index']})"
                    if "fan_pressure_pa" in witnesses
                    else ""
                ),
                "- System pressure: "
                f"**{envelope['system_pressure_pa']['lower']} to "
                f"{envelope['system_pressure_pa']['upper']} Pa**"
                + (
                    " "
                    f"(corner indices {witnesses['system_pressure_pa']['lower']['corner_index']} "
                    f"to {witnesses['system_pressure_pa']['upper']['corner_index']})"
                    if "system_pressure_pa" in witnesses
                    else ""
                ),
                "- Air power: "
                f"**{envelope['air_power_kw']['lower']} to "
                f"{envelope['air_power_kw']['upper']} kW**"
                + (
                    " "
                    f"(corner indices {witnesses['air_power_kw']['lower']['corner_index']} "
                    f"to {witnesses['air_power_kw']['upper']['corner_index']})"
                    if "air_power_kw" in witnesses
                    else ""
                ),
            ]
        )

    extrema_sources = result.get("operating_point_extrema_sources")
    if extrema_sources is not None:
        lines.extend(["", "## Critical evaluated cases", ""])
        for metric_key, metric_label in (
            ("airflow_m3_h", "Airflow"),
            ("fan_pressure_pa", "Fan pressure"),
            ("system_pressure_pa", "System pressure"),
            ("air_power_kw", "Air power"),
        ):
            for bound in ("lower", "upper"):
                evidence = extrema_sources[metric_key][bound]
                sources = []
                for source in evidence["sources"]:
                    context = [f"corner {source['corner_index']}"]
                    if "fan_curve_scenario" in source:
                        context.append(
                            f"scenario={source['fan_curve_scenario']}"
                        )
                    if "fan_speed_ratio" in source:
                        context.append(
                            f"speed={source['fan_speed_ratio']}"
                        )
                    context.append(
                        f"fixed={source['fixed_pressure_pa']} Pa"
                    )
                    sources.append("(" + ", ".join(context) + ")")
                lines.append(
                    f"- {metric_label} {bound}: "
                    f"**{evidence['value']} {evidence['unit']}** — "
                    + ", ".join(sources)
                )

    extrema_sources = result.get("operating_point_extrema_sources")
    if extrema_sources:
        metric_labels = {
            "airflow_m3_h": "Airflow m³/h",
            "fan_pressure_pa": "Fan pressure Pa",
            "system_pressure_pa": "System pressure Pa",
            "air_power_kw": "Air power kW",
        }
        lines.extend(
            [
                "",
                "## Envelope witness provenance",
                "",
                "| Metric | Bound | Value | Source corner input(s) |",
                "|---|---|---:|---|",
            ]
        )
        for metric, label in metric_labels.items():
            metric_sources = extrema_sources.get(metric)
            if metric_sources is None:
                continue
            for bound in ("lower", "upper"):
                witness = metric_sources[bound]
                source_text = " / ".join(
                    _fmt_extreme_source(source)
                    for source in witness["sources"]
                )
                lines.append(
                    f"| {label} | {bound} | {witness['value']} | "
                    f"{source_text} |"
                )

    power_ranges = result.get("power_evidence_corner_ranges")
    power_sources = result.get("power_evidence_extrema_sources")
    if power_ranges is not None:
        efficiencies = result.get("power_efficiencies")
        lines.extend(
            [
                "",
                "## Power-chain evaluated-corner ranges",
                "",
            ]
        )
        if efficiencies is None:
            lines.append(
                "- Explicit fan/motor/VFD efficiencies: **not supplied**; "
                "shaft power, electrical input, and specific fan power are "
                "therefore not reported."
            )
        else:
            lines.append(
                "- Explicit fixed efficiencies: "
                f"fan={_fmt(efficiencies.get('fan_efficiency'))}, "
                f"motor={_fmt(efficiencies.get('motor_efficiency'))}, "
                f"VFD={_fmt(efficiencies.get('vfd_efficiency'))}."
            )

        metric_labels = (
            ("fluid_air_power_kw", "Fluid air power", "kW"),
            ("shaft_power_kw", "Shaft power", "kW"),
            ("electrical_input_kw", "Electrical input", "kW"),
            (
                "specific_fan_power_w_per_m3_s",
                "Specific fan power",
                "W/(m³/s)",
            ),
        )
        lines.extend(
            [
                "",
                "| Metric | Lower | Upper | Unit |",
                "|---|---:|---:|---|",
            ]
        )
        for key, label, display_unit in metric_labels:
            evidence = power_ranges.get(key)
            if evidence is None:
                lines.append(f"| {label} | — | — | {display_unit} |")
            else:
                lines.append(
                    f"| {label} | {evidence['lower']} | "
                    f"{evidence['upper']} | {display_unit} |"
                )

        if power_sources is not None:
            lines.extend(
                [
                    "",
                    "| Metric | Bound | Value | Source corner input(s) |",
                    "|---|---|---:|---|",
                ]
            )
            for key, label, _display_unit in metric_labels:
                metric_sources = power_sources.get(key)
                if metric_sources is None:
                    continue
                for bound in ("lower", "upper"):
                    evidence = metric_sources[bound]
                    source_text = " / ".join(
                        _fmt_extreme_source(source)
                        for source in evidence["sources"]
                    )
                    lines.append(
                        f"| {label} | {bound} | {evidence['value']} "
                        f"{evidence['unit']} | {source_text} |"
                    )

        lines.extend(
            [
                "",
                "These are min/max values across evaluated solved corners "
                "only. Efficiency values are fixed explicit inputs here, not "
                "uncertain variables, and no missing efficiency is inferred.",
            ]
        )

    edge_ranges = result.get("edge_airflow_corner_ranges")
    if edge_ranges:
        lines.extend(
            [
                "",
                "## Internal edge-airflow corner ranges",
                "",
                "| Edge | Lower m³/h | Lower corner | Upper m³/h | Upper corner | Direction reversal |",
                "|---|---:|---:|---:|---:|---|",
            ]
        )
        for edge in edge_ranges:
            lines.append(
                f"| {edge['edge']} | {edge['lower_airflow_m3_h']} | "
                f"{edge['lower_corner_index']} | "
                f"{edge['upper_airflow_m3_h']} | "
                f"{edge['upper_corner_index']} | "
                f"{'yes' if edge['direction_reversal_across_corners'] else 'no'} |"
            )

    outcome = result.get("corner_outcome_diagnostics")
    if outcome:
        status_counts = ", ".join(
            f"{status}={count}"
            for status, count in outcome["status_counts"].items()
        )
        reason_counts = ", ".join(
            f"{reason}={count}"
            for reason, count in outcome[
                "termination_reason_counts"
            ].items()
        )
        lines.extend(
            [
                "",
                "## Corner outcome diagnostics",
                "",
                f"- Status counts: **{status_counts}**",
                f"- Solver termination reasons: **{reason_counts}**",
            ]
        )
        unresolved = outcome["unresolved_cases"]
        if not unresolved:
            lines.append("- Unresolved evaluated corners: **none**")
        else:
            lines.extend(
                [
                    "- Unresolved evaluated corners: "
                    f"**{len(unresolved)}**",
                    "",
                    "| Corner | Status | Termination reason | Scenario | Speed ratio | Fixed pressure Pa |",
                    "|---:|---|---|---|---:|---:|",
                ]
            )
            for case in unresolved:
                lines.append(
                    f"| {case['corner_index']} | {case['status']} | "
                    f"{case['termination_reason']} | "
                    f"{case.get('fan_curve_scenario', '—')} | "
                    f"{case.get('fan_speed_ratio', '—')} | "
                    f"{case['fixed_pressure_pa']} |"
                )

    quality = result.get("solver_quality_summary")
    if quality:
        coverage_label = (
            "complete" if quality["complete_study_coverage"] else "incomplete"
        )
        lines.extend(
            [
                "",
                "## Aggregate solver-quality evidence",
                "",
                "- Solved evaluated corners: "
                f"**{quality['solved_corner_count']}/{quality['corner_count']}**",
                "- Complete study coverage: "
                f"**{coverage_label}** (nominal status: {quality['nominal_status']})",
                "",
                "| Metric | Worst value | Unit | Configured tolerance | Witness source corner(s) |",
                "|---|---:|---|---:|---|",
            ]
        )
        tolerances = quality["configured_tolerances"]
        metric_rows = (
            (
                "absolute_operating_pressure_residual_pa",
                "Absolute operating pressure residual",
                "operating_pressure_tolerance_pa",
            ),
            (
                "network_max_relative_resistance_closure_error",
                "Resistance closure error",
                "resistance_relative_tolerance",
            ),
            (
                "max_abs_mass_balance_residual_m3_h",
                "Mass-balance residual",
                "mass_balance_tolerance_m3_h",
            ),
            (
                "max_abs_pressure_law_residual_pa",
                "Pressure-law residual",
                None,
            ),
            (
                "network_outer_iterations",
                "Network outer iterations",
                None,
            ),
            (
                "network_newton_iterations",
                "Network Newton iterations",
                None,
            ),
            (
                "operating_iterations",
                "Operating-point iterations",
                None,
            ),
        )
        for metric_key, label, tolerance_key in metric_rows:
            evidence = quality["worst_metrics"].get(metric_key)
            tolerance = (
                "—" if tolerance_key is None else tolerances[tolerance_key]
            )
            if evidence is None:
                lines.append(f"| {label} | — | — | {tolerance} | — |")
                continue
            source_texts = []
            for source in evidence["sources"]:
                source_text = _fmt_extreme_source(source)
                if "observed_value" in source:
                    source_text += f"; observed={source['observed_value']}"
                source_texts.append(source_text)
            lines.append(
                f"| {label} | {evidence['value']} | {evidence['unit']} | "
                f"{tolerance} | {' / '.join(source_texts)} |"
            )

        assessment = quality.get("configured_tolerance_assessment")
        checks = quality.get("configured_tolerance_checks", {})
        if assessment:
            lines.extend(
                [
                    "",
                    "### Configured solver-tolerance checks",
                    "",
                    f"- Assessment: **{assessment['status']}**",
                    "- Evaluable configured checks: "
                    f"**{assessment['evaluable_check_count']}/"
                    f"{assessment['configured_check_count']}**",
                    "",
                    "| Metric | Worst value | Tolerance | Utilization | Remaining margin | Result |",
                    "|---|---:|---:|---:|---:|---|",
                ]
            )
            tolerance_rows = (
                (
                    "absolute_operating_pressure_residual_pa",
                    "Absolute operating pressure residual",
                ),
                (
                    "network_max_relative_resistance_closure_error",
                    "Resistance closure error",
                ),
                (
                    "max_abs_mass_balance_residual_m3_h",
                    "Mass-balance residual",
                ),
            )
            for metric_key, label in tolerance_rows:
                check = checks.get(metric_key)
                if not check:
                    continue
                observed = (
                    "—"
                    if check["observed_value"] is None
                    else check["observed_value"]
                )
                utilization = (
                    "—"
                    if check["utilization_ratio"] is None
                    else check["utilization_ratio"]
                )
                margin = (
                    "—"
                    if check["remaining_margin"] is None
                    else check["remaining_margin"]
                )
                lines.append(
                    f"| {label} | {observed} | "
                    f"{check['configured_tolerance']} | {utilization} | "
                    f"{margin} | {check['status']} |"
                )

        iteration_assessment = quality.get("configured_iteration_assessment")
        iteration_checks = quality.get("configured_iteration_checks", {})
        if iteration_assessment:
            lines.extend(
                [
                    "",
                    "### Configured solver-iteration checks",
                    "",
                    f"- Assessment: **{iteration_assessment['status']}**",
                    "- Evaluable configured checks: "
                    f"**{iteration_assessment['evaluable_check_count']}/"
                    f"{iteration_assessment['configured_check_count']}**",
                    "",
                    "| Metric | Worst iterations | Configured limit | Utilization | Remaining iterations | Result |",
                    "|---|---:|---:|---:|---:|---|",
                ]
            )
            iteration_rows = (
                ("network_outer_iterations", "Network outer iterations"),
                ("network_newton_iterations", "Network Newton iterations"),
                ("operating_iterations", "Operating-point iterations"),
            )
            for metric_key, label in iteration_rows:
                check = iteration_checks.get(metric_key)
                if not check:
                    continue
                observed = (
                    "—"
                    if check["observed_iterations"] is None
                    else check["observed_iterations"]
                )
                utilization = (
                    "—"
                    if check["utilization_ratio"] is None
                    else check["utilization_ratio"]
                )
                remaining = (
                    "—"
                    if check["remaining_iterations"] is None
                    else check["remaining_iterations"]
                )
                lines.append(
                    f"| {label} | {observed} | "
                    f"{check['configured_limit']} | {utilization} | "
                    f"{remaining} | {check['status']} |"
                )

        lines.extend(["", quality["scope_note"]])

    edge_sources = result.get("edge_airflow_extrema_sources")
    if edge_sources:
        lines.extend(
            [
                "",
                "## Internal edge-airflow witness provenance",
                "",
                "| Edge | Bound | Value m³/h | Source corner input(s) |",
                "|---|---|---:|---|",
            ]
        )
        for edge in edge_sources:
            for bound in ("lower", "upper"):
                evidence = edge[bound]
                source_text = " / ".join(
                    _fmt_extreme_source(source)
                    for source in evidence["sources"]
                )
                lines.append(
                    f"| {edge['edge']} | {bound} | {evidence['value']} | "
                    f"{source_text} |"
                )

    lines.extend(
        [
            "",
            "## Corner results",
            "",
            "| Fixed pressure Pa | Speed ratio | Fan-curve scenario | Fan-point pressures Pa | Fan-point airflows m³/h | Local-loss K values | Physical-input values | Status | Airflow m³/h | Pressure Pa |",
            "|---:|---:|---|---|---|---|---|---|---:|---:|",
        ]
    )
    for corner in result["corners"]:
        point = corner["operating_point"]
        fan_pressures = ", ".join(
            f"{airflow}={value}"
            for airflow, value in corner.get(
                "fan_curve_pressure_pa", {}
            ).items()
        )
        fan_airflows = ", ".join(
            f"point {point_index}={value}"
            for point_index, value in corner.get(
                "fan_curve_airflow_m3_h", {}
            ).items()
        )
        local_losses = ", ".join(
            f"{name}={value}"
            for name, value in corner[
                "edge_local_loss_coefficient"
            ].items()
        )
        physical_values = []
        for label, key, unit in (
            ("roughness", "edge_absolute_roughness_m", "m"),
            ("viscosity", "edge_kinematic_viscosity_m2_s", "m²/s"),
            ("density", "edge_air_density_kg_m3", "kg/m³"),
            ("length", "edge_length_m", "m"),
            ("diameter", "edge_circular_diameter_m", "m"),
            ("width", "edge_rectangular_width_m", "m"),
            ("height", "edge_rectangular_height_m", "m"),
        ):
            for name, value in corner.get(key, {}).items():
                physical_values.append(
                    f"{name} {label}={value} {unit}"
                )
        lines.append(
            f"| {corner['fixed_pressure_pa']} | "
            f"{corner.get('fan_speed_ratio', '—')} | "
            f"{corner.get('fan_curve_scenario', '—')} | "
            f"{fan_pressures or '—'} | {fan_airflows or '—'} | "
            f"{local_losses or '—'} | "
            f"{', '.join(physical_values) or '—'} | {corner['status']} | "
            f"{_fmt(None if point is None else point['airflow_m3_h'])} | "
            f"{_fmt(None if point is None else point['system_pressure_pa'])} |"
        )

    traceability = result["traceability"]
    lines.extend(
        [
            "",
            "## Traceability",
            "",
            "- Provenance complete for bounded inputs: "
            f"**{'yes' if traceability['complete'] else 'no'}**",
        ]
    )
    if traceability["missing_provenance"]:
        lines.append(
            "- Missing provenance: "
            + ", ".join(traceability["missing_provenance"])
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
