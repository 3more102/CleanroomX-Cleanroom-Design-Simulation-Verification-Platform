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
    power_availability = result.get("power_evidence_availability")
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
                "| Metric | Availability | Lower | Upper | Unit |",
                "|---|---|---:|---:|---|",
            ]
        )
        for key, label, display_unit in metric_labels:
            evidence = power_ranges.get(key)
            availability = (
                None
                if power_availability is None
                else power_availability.get(key)
            )
            availability_text = (
                "—"
                if availability is None
                else (
                    f"{availability['status']} "
                    f"({availability['available_corner_count']}/"
                    f"{availability['total_corner_count']})"
                )
            )
            if evidence is None:
                lines.append(
                    f"| {label} | {availability_text} | — | — | "
                    f"{display_unit} |"
                )
            else:
                lines.append(
                    f"| {label} | {availability_text} | "
                    f"{evidence['lower']} | {evidence['upper']} | "
                    f"{display_unit} |"
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
                "only. A range is emitted only when that metric is available "
                "at every solved evaluated corner; partial coverage is "
                "withheld rather than summarized from a subset. Efficiency "
                "values are fixed explicit inputs here, not uncertain "
                "variables, and no missing efficiency is inferred.",
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

    no_intersection = result.get("fan_curve_no_intersection_summary")
    if no_intersection and no_intersection["no_intersection_corner_count"]:
        lines.extend(
            [
                "",
                "## No-intersection supplied-boundary diagnostics",
                "",
                "- No-intersection evaluated corners: "
                f"**{no_intersection['no_intersection_corner_count']}**",
                "- Lower supplied-airflow boundary cases: "
                f"**{no_intersection['lower_boundary_corner_count']}**",
                "- Upper supplied-airflow boundary cases: "
                f"**{no_intersection['upper_boundary_corner_count']}**",
            ]
        )
        largest_gap = no_intersection.get(
            "largest_absolute_boundary_pressure_gap_pa"
        )
        if largest_gap is not None:
            lines.extend(
                [
                    "",
                    "| Largest endpoint pressure mismatch | Unit | Source corner input(s) |",
                    "|---:|---|---|",
                ]
            )
            source_texts = []
            for source in largest_gap["sources"]:
                source_texts.append(
                    _fmt_extreme_source(source)
                    + f"; boundary={source['boundary']}"
                    + f"; mismatch={source['mismatch_kind']}"
                    + f"; Q={source['airflow_m3_h']} m³/h"
                    + f"; fan-system={source['fan_minus_system_pressure_pa']} Pa"
                )
            lines.append(
                f"| {largest_gap['value']} | {largest_gap['unit']} | "
                f"{' / '.join(source_texts)} |"
            )
        lines.extend(["", no_intersection["scope_note"]])

    bracket_summary = result.get("fan_curve_intersection_bracket_summary")
    nominal_bracket = result.get("nominal_fan_curve_intersection_bracket")
    if bracket_summary:
        coverage_label = (
            "complete"
            if bracket_summary["complete_study_coverage"]
            else "partial"
        )
        lines.extend(
            [
                "",
                "## Fan/system supplied-curve intersection brackets",
                "",
                "- Evaluated corners with bracket evidence: "
                f"**{bracket_summary['bracket_evidence_corner_count']}/"
                f"{bracket_summary['corner_count']}**",
                "- Bounded intersection supported by endpoint residuals: "
                f"**{bracket_summary['bounded_intersection_supported_count']}**",
                "- Strict sign-change brackets: "
                f"**{bracket_summary['strict_sign_change_count']}**",
                "- Endpoint root/tolerance contacts: "
                f"**{bracket_summary['endpoint_within_tolerance_count']}**",
                f"- Study coverage: **{coverage_label}**",
            ]
        )
        if nominal_bracket is None:
            lines.append("- Nominal intersection bracket: **not available**")
        else:
            low = nominal_bracket["low_endpoint"]
            high = nominal_bracket["high_endpoint"]
            lines.append(
                "- Nominal supplied-point bracket: "
                f"**{low['airflow_m3_h']} m³/h "
                f"({low['fan_minus_system_pressure_pa']} Pa) to "
                f"{high['airflow_m3_h']} m³/h "
                f"({high['fan_minus_system_pressure_pa']} Pa)**"
            )

        lines.extend(
            [
                "",
                "| Metric | Minimum | Unit | Source corner input(s) |",
                "|---|---:|---|---|",
            ]
        )
        bracket_rows = (
            (
                "minimum_nearest_endpoint_absolute_pressure_gap_pa",
                "Nearest endpoint absolute fan-system pressure gap",
            ),
            (
                "minimum_endpoint_pressure_residual_span_pa",
                "Endpoint fan-system residual span",
            ),
        )
        for key, label in bracket_rows:
            evidence = bracket_summary.get(key)
            if evidence is None:
                lines.append(f"| {label} | — | — | — |")
                continue
            source_texts = []
            for source in evidence["sources"]:
                low = source["low_endpoint"]
                high = source["high_endpoint"]
                source_texts.append(
                    _fmt_extreme_source(source)
                    + f"; low={low['airflow_m3_h']} m³/h:"
                    + f"{low['fan_minus_system_pressure_pa']} Pa"
                    + f"; high={high['airflow_m3_h']} m³/h:"
                    + f"{high['fan_minus_system_pressure_pa']} Pa"
                    + f"; termination={source['termination_reason']}"
                )
            lines.append(
                f"| {label} | {evidence['value']} | {evidence['unit']} | "
                f"{' / '.join(source_texts)} |"
            )
        lines.extend(["", bracket_summary["scope_note"]])

    conditioning_summary = result.get(
        "fan_curve_crossing_conditioning_summary"
    )
    nominal_conditioning = result.get(
        "nominal_fan_curve_crossing_conditioning"
    )
    if conditioning_summary:
        coverage_label = (
            "complete"
            if conditioning_summary["complete_study_coverage"]
            else "partial"
        )
        lines.extend(
            [
                "",
                "## Fan/system local crossing conditioning",
                "",
                "- Evaluated corners with conditioning evidence: "
                f"**{conditioning_summary['conditioning_evidence_corner_count']}/"
                f"{conditioning_summary['corner_count']}**",
                "- Evaluated corners with secant-root evidence: "
                f"**{conditioning_summary['secant_root_evidence_corner_count']}/"
                f"{conditioning_summary['corner_count']}**",
                f"- Study coverage: **{coverage_label}**",
            ]
        )
        if nominal_conditioning is None:
            lines.append("- Nominal crossing conditioning: **not available**")
        else:
            lines.extend(
                [
                    "- Nominal fan pressure slope: "
                    f"**{nominal_conditioning['fan_pressure_slope_pa_per_m3_h']} "
                    "Pa/(m³/h)**",
                    "- Nominal system secant slope: "
                    f"**{nominal_conditioning['system_pressure_secant_slope_pa_per_m3_h']} "
                    "Pa/(m³/h)**",
                    "- Nominal fan-minus-system slope: "
                    f"**{nominal_conditioning['fan_minus_system_slope_pa_per_m3_h']} "
                    "Pa/(m³/h)**",
                    "- Nominal secant-root airflow error: "
                    f"**{nominal_conditioning['secant_root_absolute_error_m3_h']} "
                    "m³/h**",
                ]
            )

        lines.extend(
            [
                "",
                "| Metric | Extreme | Unit | Source corner input(s) |",
                "|---|---:|---|---|",
            ]
        )
        conditioning_rows = (
            (
                "minimum_absolute_fan_minus_system_slope_pa_per_m3_h",
                "Minimum absolute fan-minus-system slope",
            ),
            (
                "maximum_airflow_change_per_pa_m3_h_per_pa",
                "Maximum reciprocal airflow-per-pressure gradient",
            ),
            (
                "maximum_secant_root_absolute_error_m3_h",
                "Maximum secant-root airflow error",
            ),
            (
                "maximum_normalized_secant_root_error_fraction",
                "Maximum normalized secant-root error",
            ),
        )
        for key, label in conditioning_rows:
            evidence = conditioning_summary.get(key)
            if evidence is None:
                lines.append(f"| {label} | — | — | — |")
                continue
            source_texts = []
            for source in evidence["sources"]:
                source_texts.append(
                    _fmt_extreme_source(source)
                    + f"; fan-slope={source['fan_pressure_slope_pa_per_m3_h']}"
                    + f"; system-slope={source['system_pressure_secant_slope_pa_per_m3_h']}"
                    + f"; residual-slope={source['fan_minus_system_slope_pa_per_m3_h']}"
                    + f"; secant-error={source['secant_root_absolute_error_m3_h']} m³/h"
                )
            lines.append(
                f"| {label} | {evidence['value']} | {evidence['unit']} | "
                f"{' / '.join(source_texts)} |"
            )
        lines.extend(["", conditioning_summary["scope_note"]])


    pressure_airflow_summary = result.get(
        "pressure_residual_airflow_equivalence_summary"
    )
    nominal_pressure_airflow = result.get(
        "nominal_pressure_residual_airflow_equivalence"
    )
    if pressure_airflow_summary:
        coverage_label = (
            "complete"
            if pressure_airflow_summary["complete_study_coverage"]
            else "partial"
        )
        lines.extend(
            [
                "",
                "## Pressure residual → airflow numerical equivalence",
                "",
                "- Corners with diagnostic evidence: "
                f"**{pressure_airflow_summary['diagnostic_evidence_corner_count']}/"
                f"{pressure_airflow_summary['corner_count']}**",
                "- Corners with evaluable pressure-to-airflow mapping: "
                f"**{pressure_airflow_summary['evaluable_corner_count']}/"
                f"{pressure_airflow_summary['corner_count']}**",
                f"- Study coverage: **{coverage_label}**",
            ]
        )
        if nominal_pressure_airflow is None:
            lines.append(
                "- Nominal pressure-to-airflow equivalence: **not available**"
            )
        elif nominal_pressure_airflow["status"] != "evaluated":
            lines.append(
                "- Nominal pressure-to-airflow equivalence: "
                f"**{nominal_pressure_airflow['status']}**"
            )
        else:
            lines.extend(
                [
                    "- Nominal configured pressure tolerance: "
                    f"**{nominal_pressure_airflow['configured_operating_pressure_tolerance_pa']} Pa**",
                    "- Nominal solved pressure residual: "
                    f"**{nominal_pressure_airflow['solved_pressure_residual_pa']} Pa**",
                    "- Nominal configured-tolerance airflow equivalent: "
                    f"**{nominal_pressure_airflow['configured_tolerance_equivalent_airflow_m3_h']} "
                    "m³/h**",
                    "- Nominal solved-residual airflow equivalent: "
                    f"**{nominal_pressure_airflow['solved_residual_equivalent_airflow_m3_h']} "
                    "m³/h**",
                    "- Nominal signed linearized airflow correction: "
                    f"**{nominal_pressure_airflow['signed_linearized_airflow_correction_m3_h']} "
                    "m³/h**",
                ]
            )
        lines.extend(
            [
                "",
                "| Metric | Maximum | Unit | Source corner input(s) |",
                "|---|---:|---|---|",
            ]
        )
        pressure_airflow_rows = (
            (
                "maximum_configured_tolerance_equivalent_airflow_m3_h",
                "Configured pressure-tolerance airflow equivalent",
            ),
            (
                "maximum_solved_residual_equivalent_airflow_m3_h",
                "Solved pressure-residual airflow equivalent",
            ),
            (
                "maximum_configured_tolerance_equivalent_fraction_of_bracket_span",
                "Configured-tolerance equivalent / bracket span",
            ),
            (
                "maximum_solved_residual_equivalent_fraction_of_bracket_span",
                "Solved-residual equivalent / bracket span",
            ),
        )
        for key, label in pressure_airflow_rows:
            evidence = pressure_airflow_summary.get(key)
            if evidence is None:
                lines.append(f"| {label} | — | — | — |")
                continue
            source_texts = []
            for source in evidence["sources"]:
                source_texts.append(
                    _fmt_extreme_source(source)
                    + f"; residual={source['solved_pressure_residual_pa']} Pa"
                    + f"; residual-slope={source['fan_minus_system_slope_pa_per_m3_h']}"
                    + f"; linearized-dQ={source['signed_linearized_airflow_correction_m3_h']} m³/h"
                )
            lines.append(
                f"| {label} | {evidence['value']} | {evidence['unit']} | "
                f"{' / '.join(source_texts)} |"
            )
        lines.extend(["", pressure_airflow_summary["scope_note"]])

    search_summary = result.get(
        "operating_point_search_resolution_summary"
    )
    nominal_search = result.get("nominal_operating_point_search_evidence")
    if search_summary:
        coverage_label = (
            "complete"
            if search_summary["complete_study_coverage"]
            else "partial"
        )
        lines.extend(
            [
                "",
                "## Bounded operating-point search geometry",
                "",
                "- Corners with operating-point search evidence: "
                f"**{search_summary['search_evidence_corner_count']}/"
                f"{search_summary['corner_count']} total**",
                "- Solved corners with search evidence: "
                f"**{search_summary['solved_search_evidence_corner_count']}/"
                f"{search_summary['solved_corner_count']} solved**",
                "- Bounded-bisection solved corners: "
                f"**{search_summary['bisection_corner_count']}**",
                "- Supplied-point tolerance-contact corners: "
                f"**{search_summary['supplied_point_contact_corner_count']}**",
                "- Bisection corners with invariant evidence: "
                f"**{search_summary['bisection_invariant_evidence_corner_count']}/"
                f"{search_summary['bisection_corner_count']}**",
                "- Corners with retained bisection decision traces: "
                f"**{search_summary['bisection_trace_evidence_corner_count']}**",
                "- Solved bisection corners with decision traces: "
                f"**{search_summary['solved_bisection_trace_evidence_corner_count']}/"
                f"{search_summary['bisection_corner_count']}**",
                "- Iteration-limit corners with decision traces: "
                f"**{search_summary['iteration_limit_bisection_trace_evidence_corner_count']}/"
                f"{search_summary['iteration_limit_search_evidence_corner_count']}**",
                "- Trace-length violations: "
                f"**{search_summary['bisection_trace_length_violation_corner_indices']}**",
                "- Trace sign-bracket violations: "
                f"**{search_summary['bisection_trace_sign_violation_corner_indices']}**",
                "- Trace midpoint-geometry violations: "
                f"**{search_summary['bisection_trace_midpoint_violation_corner_indices']}**",
                "- Trace terminal-position violations (solved only): "
                f"**{search_summary['bisection_trace_terminal_violation_corner_indices']}**",
                "- Trace terminal-outcome violations: "
                f"**{search_summary['bisection_trace_outcome_violation_corner_indices']}**",
                "- Trace iteration-sequence violations: "
                f"**{search_summary['bisection_trace_iteration_sequence_violation_corner_indices']}**",
                "- Trace state-transition replay violations: "
                f"**{search_summary['bisection_trace_state_transition_violation_corner_indices']}**",
                "- Strict sign-bracket violations: "
                f"**{search_summary['strict_sign_change_violation_corner_indices']}**",
                "- Midpoint-centering violations: "
                f"**{search_summary['selected_midpoint_violation_corner_indices']}**",
                "- Bisection iteration-limit corners with search evidence: "
                f"**{search_summary['iteration_limit_search_evidence_corner_count']}**",
                "- Iteration-limit remaining-bracket invariant evidence: "
                f"**{search_summary['iteration_limit_invariant_evidence_corner_count']}**",
                "- Iteration-limit strict sign-bracket violations: "
                f"**{search_summary['iteration_limit_strict_sign_change_violation_corner_indices']}**",
                f"- Complete-study coverage: **{coverage_label}**",
            ]
        )
        if nominal_search is None:
            lines.append("- Nominal search evidence: **not available**")
        else:
            lines.append(
                f"- Nominal search method: **{nominal_search['method']}**"
            )
            nominal_bracket = nominal_search.get("final_bisection_bracket")
            if nominal_bracket is not None:
                lines.extend(
                    [
                        "- Nominal final bisection bracket: "
                        f"**{nominal_bracket['low_airflow_m3_h']}–"
                        f"{nominal_bracket['high_airflow_m3_h']} m³/h**",
                        "- Nominal final bisection half-width: "
                        f"**{nominal_bracket['half_width_m3_h']} m³/h**",
                    ]
                )
                nominal_invariant = nominal_bracket.get("invariant_audit")
                if nominal_invariant is not None:
                    lines.extend(
                        [
                            "- Nominal strict sign bracket preserved: "
                            f"**{nominal_invariant['strict_sign_change_preserved']}**",
                            "- Nominal selected airflow is bracket midpoint: "
                            f"**{nominal_invariant['selected_airflow_is_bracket_midpoint']}**",
                            "- Nominal binary-width consistency error: "
                            f"**{nominal_invariant['absolute_width_fraction_consistency_error']}**",
                        ]
                    )
            nominal_trace_audit = nominal_search.get(
                "bisection_trace_audit"
            )
            if nominal_trace_audit is not None:
                lines.extend(
                    [
                        "- Nominal bisection decision-trace steps: "
                        f"**{nominal_trace_audit['step_count']}**",
                        "- Nominal bisection decision sequence (L/H/T): "
                        f"**{nominal_trace_audit['decision_sequence']}**",
                        "- Nominal trace termination reason: "
                        f"**{nominal_trace_audit['termination_reason']}**",
                        "- Nominal trace terminal outcome consistent: "
                        f"**{nominal_trace_audit['terminal_outcome_consistent']}**",
                        "- Nominal trace invariants all satisfied: "
                        f"**{nominal_trace_audit['trace_matches_operating_iterations'] and nominal_trace_audit['iterations_are_contiguous_from_one'] and nominal_trace_audit['all_steps_preserve_strict_sign_change_before_evaluation'] and nominal_trace_audit['all_midpoints_are_arithmetic_bracket_midpoints'] and nominal_trace_audit['terminal_outcome_consistent'] and nominal_trace_audit['all_state_transitions_replay_recorded_decisions']}**",
                    ]
                )
            nominal_limit = nominal_search.get("iteration_limit_evidence")
            if nominal_limit is not None:
                remaining = nominal_limit["remaining_bisection_bracket"]
                lines.extend(
                    [
                        "- Nominal search stopped at iteration limit; no operating point accepted.",
                        "- Nominal remaining bisection bracket: "
                        f"**{remaining['low_airflow_m3_h']}–"
                        f"{remaining['high_airflow_m3_h']} m³/h**",
                        "- Nominal remaining bisection half-width: "
                        f"**{remaining['half_width_m3_h']} m³/h**",
                    ]
                )

        lines.extend(
            [
                "",
                "| Metric | Maximum | Unit | Source corner input(s) |",
                "|---|---:|---|---|",
            ]
        )
        search_rows = (
            (
                "maximum_final_bisection_bracket_width_m3_h",
                "Final bisection bracket width",
            ),
            (
                "maximum_final_bisection_half_width_m3_h",
                "Final bisection bracket half-width",
            ),
            (
                "maximum_final_bisection_width_fraction_of_supplied_segment",
                "Final bracket width / supplied-segment span",
            ),
        )
        for key, label in search_rows:
            evidence = search_summary.get(key)
            if evidence is None:
                lines.append(f"| {label} | — | — | — |")
                continue
            source_texts = []
            for source in evidence["sources"]:
                bracket = source["final_bisection_bracket"]
                source_texts.append(
                    _fmt_extreme_source(source)
                    + f"; segment={source['supplied_segment_low_airflow_m3_h']}"
                    + f"–{source['supplied_segment_high_airflow_m3_h']} m³/h"
                    + f"; final-bracket={bracket['low_airflow_m3_h']}"
                    + f"–{bracket['high_airflow_m3_h']} m³/h"
                    + f"; iterations={source['operating_iterations']}"
                )
            lines.append(
                f"| {label} | {evidence['value']} | {evidence['unit']} | "
                f"{' / '.join(source_texts)} |"
            )
        invariant_error = search_summary.get(
            "maximum_absolute_width_fraction_consistency_error"
        )
        if invariant_error is not None:
            invariant_sources = []
            for source in invariant_error["sources"]:
                invariant = source["invariant_audit"]
                invariant_sources.append(
                    _fmt_extreme_source(source)
                    + f"; iterations={source['operating_iterations']}"
                    + f"; expected-fraction={invariant['expected_width_fraction_of_supplied_segment']}"
                    + f"; actual-fraction={invariant['actual_width_fraction_of_supplied_segment']}"
                )
            lines.append(
                "| Maximum absolute binary-width consistency error | "
                f"{invariant_error['value']} | {invariant_error['unit']} | "
                f"{' / '.join(invariant_sources)} |"
            )
        trace_steps = search_summary.get("maximum_bisection_trace_step_count")
        if trace_steps is not None:
            trace_sources = []
            for source in trace_steps["sources"]:
                audit = source["bisection_trace_audit"]
                trace_sources.append(
                    _fmt_extreme_source(source)
                    + f"; decision-sequence={audit['decision_sequence']}"
                    + f"; outcome={audit['termination_reason']}"
                    + f"; iterations={source['operating_iterations']}"
                )
            lines.append(
                "| Maximum retained bisection decision-trace steps | "
                f"{trace_steps['value']} | {trace_steps['unit']} | "
                f"{' / '.join(trace_sources)} |"
            )
        limit_error = search_summary.get(
            "maximum_iteration_limit_absolute_width_fraction_consistency_error"
        )
        if limit_error is not None:
            limit_sources = []
            for source in limit_error["sources"]:
                invariant = source["invariant_audit"]
                remaining = source["remaining_bisection_bracket"]
                limit_sources.append(
                    _fmt_extreme_source(source)
                    + f"; iterations={source['operating_iterations']}"
                    + f"; remaining={remaining['low_airflow_m3_h']}"
                    + f"–{remaining['high_airflow_m3_h']} m³/h"
                    + f"; expected-fraction={invariant['expected_width_fraction_of_supplied_segment']}"
                    + f"; actual-fraction={invariant['actual_width_fraction_of_supplied_segment']}"
                )
            lines.append(
                "| Maximum iteration-limit remaining-bracket binary-width consistency error | "
                f"{limit_error['value']} | {limit_error['unit']} | "
                f"{' / '.join(limit_sources)} |"
            )
        lines.extend(["", search_summary["scope_note"]])

    segment_summary = result.get("fan_curve_segment_position_summary")
    nominal_segment = result.get("nominal_fan_curve_segment_position")
    if segment_summary:
        coverage_label = (
            "complete"
            if segment_summary["complete_study_coverage"]
            else "partial"
        )
        lines.extend(
            [
                "",
                "## Fan-curve interpolation segment position",
                "",
                "- Evaluated corners with segment-position evidence: "
                f"**{segment_summary['segment_position_evidence_corner_count']}/"
                f"{segment_summary['corner_count']}**",
                f"- Study coverage: **{coverage_label}**",
            ]
        )
        if nominal_segment is None:
            lines.append("- Nominal segment position: **not available**")
        else:
            lines.extend(
                [
                    "- Nominal interpolation segment: "
                    f"**{nominal_segment['segment_low_airflow_m3_h']} to "
                    f"{nominal_segment['segment_high_airflow_m3_h']} m³/h**",
                    "- Nominal normalized segment position: "
                    f"**{nominal_segment['normalized_segment_position_fraction']}**",
                    "- Nominal nearest supplied segment endpoint: "
                    f"**{nominal_segment['nearest_segment_endpoint']}**, "
                    f"clearance **{nominal_segment['nearest_segment_endpoint_clearance_m3_h']} "
                    "m³/h**",
                ]
            )
        lines.extend(
            [
                "",
                "| Metric | Extreme | Unit | Source corner input(s) |",
                "|---|---:|---|---|",
            ]
        )
        segment_rows = (
            (
                "minimum_nearest_segment_endpoint_clearance_m3_h",
                "Minimum nearest segment-endpoint clearance",
            ),
            (
                "minimum_normalized_nearest_segment_endpoint_clearance_fraction",
                "Minimum normalized segment-endpoint clearance",
            ),
            (
                "maximum_segment_airflow_span_m3_h",
                "Maximum active interpolation-segment span",
            ),
        )
        for key, label in segment_rows:
            evidence = segment_summary.get(key)
            if evidence is None:
                lines.append(f"| {label} | — | — | — |")
                continue
            source_texts = []
            for source in evidence["sources"]:
                source_texts.append(
                    _fmt_extreme_source(source)
                    + f"; segment={source['segment_low_airflow_m3_h']}"
                    + f"–{source['segment_high_airflow_m3_h']} m³/h"
                    + f"; nearest={source['nearest_segment_endpoint']}"
                    + f"; clearance={source['nearest_segment_endpoint_clearance_m3_h']} m³/h"
                )
            lines.append(
                f"| {label} | {evidence['value']} | {evidence['unit']} | "
                f"{' / '.join(source_texts)} |"
            )
        lines.extend(["", segment_summary["scope_note"]])

    residual_summary = result.get(
        "fan_curve_supplied_point_residual_summary"
    )
    nominal_residual_audit = result.get(
        "nominal_fan_curve_supplied_point_residual_audit"
    )
    if residual_summary:
        lines.extend(
            [
                "",
                "## Supplied-point residual topology across corners",
                "",
                "- Corners with audit evidence: "
                f"**{residual_summary['audit_evidence_corner_count']}/"
                f"{residual_summary['corner_count']}**",
                "- Corners with complete supplied-point coverage: "
                f"**{residual_summary['complete_supplied_point_coverage_corner_count']}/"
                f"{residual_summary['corner_count']}**",
                "- Corners monotonic non-increasing within tolerance: "
                f"**{residual_summary['monotonic_non_increasing_corner_count']}/"
                f"{residual_summary['corner_count']}**",
                "- Solved corners with selected-candidate provenance: "
                f"**{residual_summary['selected_candidate_feature_corner_count']}/"
                f"{residual_summary['solved_corner_count']}**",
                "- Solved corners selecting first-priority candidate: "
                f"**{residual_summary['selected_first_priority_candidate_corner_count']}/"
                f"{residual_summary['solved_corner_count']}**",
                "- Solved corners with additional discrete candidates: "
                f"**{residual_summary['solved_with_additional_candidate_feature_corner_count']}**",
                "- Solved corners with alternative-candidate separation evidence: "
                f"**{residual_summary['alternative_candidate_separation_evidence_corner_count']}**",
                "- Solved corners whose selected airflow overlaps an alternative candidate interval: "
                f"**{residual_summary['selected_airflow_overlap_alternative_interval_corner_count']}**",
                "- Corners with residual-increase transitions: "
                f"**{residual_summary['residual_increase_corner_count']}**",
                "- Corners with multiple discrete candidate crossing features: "
                f"**{residual_summary['multiple_candidate_feature_corner_count']}**",
                "- Corners with reverse strict negative-to-positive sign changes: "
                f"**{residual_summary['reverse_strict_sign_change_corner_count']}**",
                "- Reverse strict negative-to-positive segments across corners: "
                f"**{residual_summary['reverse_strict_sign_change_segment_count_total']}**",
                "- Complete study audit coverage: "
                f"**{residual_summary['complete_study_coverage']}**",
            ]
        )
        if nominal_residual_audit is not None:
            lines.extend(
                [
                    "- Nominal discrete candidate crossing features: "
                    f"**{nominal_residual_audit['candidate_crossing_feature_count']}**",
                    "- Nominal reverse strict negative-to-positive sign changes: "
                    f"**{nominal_residual_audit.get('reverse_strict_sign_change_segment_count', 0)}**",
                ]
            )
        if residual_summary[
            "solved_with_additional_candidate_feature_corner_indices"
        ]:
            lines.append(
                "- Solved corner indices with additional discrete candidates: "
                + ", ".join(
                    str(index)
                    for index in residual_summary[
                        "solved_with_additional_candidate_feature_corner_indices"
                    ]
                )
            )
        if residual_summary[
            "selected_airflow_overlap_alternative_interval_corner_indices"
        ]:
            lines.append(
                "- Selected-airflow overlap corner indices: "
                + ", ".join(
                    str(index)
                    for index in residual_summary[
                        "selected_airflow_overlap_alternative_interval_corner_indices"
                    ]
                )
            )
        alternative_gap = residual_summary.get(
            "minimum_selected_to_alternative_candidate_interval_gap_m3_h"
        )
        if alternative_gap is not None:
            source_texts = [
                _fmt_extreme_source(source)
                for source in alternative_gap["sources"]
            ]
            lines.append(
                "- Minimum selected-to-alternative candidate interval gap: "
                f"**{alternative_gap['value']} {alternative_gap['unit']}** "
                f"({' / '.join(source_texts)})"
            )
        normalized_alternative_gap = residual_summary.get(
            "minimum_selected_to_alternative_candidate_interval_gap_fraction_of_supplied_curve_span"
        )
        if normalized_alternative_gap is not None:
            source_texts = [
                _fmt_extreme_source(source)
                + f"; supplied-span={source['supplied_fan_curve_airflow_span_m3_h']} m³/h"
                for source in normalized_alternative_gap["sources"]
            ]
            lines.append(
                "- Minimum selected-to-alternative candidate gap / supplied fan-curve span: "
                f"**{normalized_alternative_gap['value']}** "
                f"({' / '.join(source_texts)})"
            )
        spacing_normalized_alternative_gap = residual_summary.get(
            "minimum_selected_to_alternative_candidate_interval_gap_fraction_of_minimum_supplied_point_spacing"
        )
        if spacing_normalized_alternative_gap is not None:
            source_texts = [
                _fmt_extreme_source(source)
                + f"; min-supplied-spacing={source['minimum_supplied_point_airflow_spacing_m3_h']} m³/h"
                for source in spacing_normalized_alternative_gap["sources"]
            ]
            lines.append(
                "- Minimum selected-to-alternative candidate gap / minimum supplied-point spacing: "
                f"**{spacing_normalized_alternative_gap['value']}** "
                f"({' / '.join(source_texts)})"
            )
        if residual_summary["residual_increase_corner_indices"]:
            lines.append(
                "- Residual-increase corner indices: "
                + ", ".join(
                    str(index)
                    for index in residual_summary[
                        "residual_increase_corner_indices"
                    ]
                )
            )
        if residual_summary["multiple_candidate_feature_corner_indices"]:
            lines.append(
                "- Multiple-candidate-feature corner indices: "
                + ", ".join(
                    str(index)
                    for index in residual_summary[
                        "multiple_candidate_feature_corner_indices"
                    ]
                )
            )
        if residual_summary["reverse_strict_sign_change_corner_indices"]:
            lines.append(
                "- Reverse-sign-change corner indices: "
                + ", ".join(
                    str(index)
                    for index in residual_summary[
                        "reverse_strict_sign_change_corner_indices"
                    ]
                )
            )
        increase = residual_summary.get(
            "maximum_positive_residual_increase_pa"
        )
        if increase is not None:
            source_texts = [
                _fmt_extreme_source(source)
                for source in increase["sources"]
            ]
            lines.append(
                "- Maximum positive supplied-point residual increase: "
                f"**{increase['value']} {increase['unit']}** "
                f"({' / '.join(source_texts)})"
            )
        lines.extend(["", residual_summary["scope_note"]])

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

    excursions = result.get("operating_point_excursions_from_nominal")
    power_excursions = result.get("power_evidence_excursions_from_nominal")
    if excursions:
        lines.extend(
            [
                "",
                "## Evaluated-corner excursions from nominal",
                "",
                "| Metric | Nominal | Lower delta | Upper delta | Lower % | Upper % | Unit |",
                "|---|---:|---:|---:|---:|---:|---|",
            ]
        )
        excursion_rows = (
            ("airflow_m3_h", "Operating airflow"),
            ("fan_pressure_pa", "Fan pressure"),
            ("system_pressure_pa", "System pressure"),
            ("air_power_kw", "Fan air power"),
        )
        for key, label in excursion_rows:
            evidence = excursions[key]
            lower_percent = (
                "—"
                if evidence["lower_percent"] is None
                else evidence["lower_percent"]
            )
            upper_percent = (
                "—"
                if evidence["upper_percent"] is None
                else evidence["upper_percent"]
            )
            lines.append(
                f"| {label} | {evidence['nominal']} | "
                f"{evidence['lower_delta']} | {evidence['upper_delta']} | "
                f"{lower_percent} | {upper_percent} | {evidence['unit']} |"
            )

        if power_excursions:
            power_rows = (
                ("shaft_power_kw", "Shaft power"),
                ("electrical_input_kw", "Electrical input"),
                (
                    "specific_fan_power_w_per_m3_s",
                    "Specific fan power",
                ),
            )
            for key, label in power_rows:
                evidence = power_excursions.get(key)
                if evidence is None:
                    continue
                lower_percent = (
                    "—"
                    if evidence["lower_percent"] is None
                    else evidence["lower_percent"]
                )
                upper_percent = (
                    "—"
                    if evidence["upper_percent"] is None
                    else evidence["upper_percent"]
                )
                lines.append(
                    f"| {label} | {evidence['nominal']} | "
                    f"{evidence['lower_delta']} | {evidence['upper_delta']} | "
                    f"{lower_percent} | {upper_percent} | "
                    f"{evidence['unit']} |"
                )
        lines.extend(
            [
                "",
                "Excursions are relative to the solved nominal case and summarize "
                "evaluated corners only; they are not sensitivity coefficients or "
                "guaranteed continuous-interval extrema.",
            ]
        )

    boundary_summary = result.get("fan_curve_boundary_clearance_summary")
    nominal_boundary = result.get("nominal_fan_curve_boundary_clearance")
    if boundary_summary:
        coverage_label = (
            "complete"
            if boundary_summary["complete_study_coverage"]
            else "partial"
        )
        lines.extend(
            [
                "",
                "## Supplied fan-curve boundary clearance",
                "",
                "- Solved evaluated corners with boundary evidence: "
                f"**{boundary_summary['solved_corner_count']}/"
                f"{boundary_summary['corner_count']}**",
                f"- Study coverage: **{coverage_label}**",
            ]
        )
        if nominal_boundary is None:
            lines.append("- Nominal boundary clearance: **not available**")
        else:
            lines.append(
                "- Nominal nearest-boundary headroom: "
                f"**{nominal_boundary['nearest_boundary_headroom_m3_h']} "
                "m³/h** "
                f"({nominal_boundary['nearest_boundary']} endpoint; "
                "normalized fraction "
                f"{nominal_boundary['nearest_boundary_headroom_fraction']})"
            )

        lines.extend(
            [
                "",
                "| Metric | Minimum | Unit | Source corner input(s) |",
                "|---|---:|---|---|",
            ]
        )
        boundary_rows = (
            (
                "minimum_nearest_boundary_headroom_m3_h",
                "Nearest endpoint airflow headroom",
            ),
            (
                "minimum_nearest_boundary_headroom_fraction",
                "Nearest endpoint normalized headroom",
            ),
        )
        for key, label in boundary_rows:
            evidence = boundary_summary.get(key)
            if evidence is None:
                lines.append(f"| {label} | — | — | — |")
                continue
            source_texts = []
            for source in evidence["sources"]:
                bounds = source["fan_curve_airflow_range_m3_h"]
                source_texts.append(
                    _fmt_extreme_source(source)
                    + f"; Q={source['operating_airflow_m3_h']} m³/h"
                    + f"; range={bounds[0]}–{bounds[1]} m³/h"
                    + f"; nearest={source['nearest_boundary']}"
                )
            lines.append(
                f"| {label} | {evidence['value']} | {evidence['unit']} | "
                f"{' / '.join(source_texts)} |"
            )
        lines.extend(["", boundary_summary["scope_note"]])

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

    integrity = result.get("result_integrity")
    if integrity:
        lines.extend(
            [
                "",
                "### Result integrity",
                "",
                f"- Algorithm: **{integrity['algorithm']}**",
                f"- Canonicalization: `{integrity['canonicalization']}`",
                f"- Scope: `{integrity['scope']}`",
                f"- SHA-256: `{integrity['sha256']}`",
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
