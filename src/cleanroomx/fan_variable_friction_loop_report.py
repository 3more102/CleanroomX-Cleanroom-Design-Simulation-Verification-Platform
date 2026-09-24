from __future__ import annotations


def markdown_fan_variable_friction_loop_report(result: dict) -> str:
    diagnostics = result["solver_diagnostics"]
    lines = [
        f"# CleanroomX Fan / Variable-Friction Loop Report — {result['study']}",
        "",
        f"- Fan curve: **{result['fan_curve']}**",
        f"- Status: **{result['status'].upper()}**",
        f"- Fan discharge node: **{result['fan_discharge_node']}**",
        f"- Fan suction node: **{result['fan_suction_node']}**",
        f"- Fixed pressure: **{result['fixed_pressure_pa']} Pa**",
        "- Fan-curve airflow range: "
        f"**{result['fan_curve_airflow_range_m3_h'][0]}–"
        f"{result['fan_curve_airflow_range_m3_h'][1]} m³/h**",
        "",
        "## Solver diagnostics",
        "",
        f"- Converged: **{diagnostics['converged']}**",
        f"- Termination reason: **{diagnostics['termination_reason']}**",
        "- Operating-point pressure tolerance: "
        f"**{diagnostics['operating_pressure_tolerance_pa']} Pa**",
        f"- Operating iterations: **{diagnostics['operating_iterations']}**",
    ]

    search = result.get("operating_point_search_evidence")
    if search is not None:
        lines.extend(
            [
                "",
                "## Operating-point search evidence",
                "",
                f"- Search method: **{search['method']}**",
                "- Supplied interpolation segment: "
                f"**{search['supplied_segment_low_airflow_m3_h']}–"
                f"{search['supplied_segment_high_airflow_m3_h']} m³/h**",
            ]
        )
        if search["selected_supplied_point_index"] is not None:
            lines.append(
                "- Selected supplied-point index: "
                f"**{search['selected_supplied_point_index']}**"
            )
        bracket = search["final_bisection_bracket"]
        if bracket is None:
            iteration_limit = search.get("iteration_limit_evidence")
            if iteration_limit is None:
                lines.append("- Final bisection bracket: **not applicable**")
            else:
                remaining = iteration_limit["remaining_bisection_bracket"]
                invariant = remaining.get("invariant_audit")
                lines.extend(
                    [
                        "- Accepted operating point: **none (iteration limit)**",
                        "- Last evaluated midpoint airflow: "
                        f"**{iteration_limit['last_evaluated_midpoint_airflow_m3_h']} m³/h**",
                        "- Last evaluated fan-system pressure residual: "
                        f"**{iteration_limit['last_evaluated_fan_minus_system_pressure_pa']} Pa**",
                        "- Pressure tolerance satisfied: "
                        f"**{iteration_limit['pressure_tolerance_satisfied']}**",
                        "- Remaining active bisection bracket: "
                        f"**{remaining['low_airflow_m3_h']}–"
                        f"{remaining['high_airflow_m3_h']} m³/h**",
                        "- Remaining bisection bracket width: "
                        f"**{remaining['width_m3_h']} m³/h**",
                        "- Remaining bracket width / supplied-segment span: "
                        f"**{remaining['width_fraction_of_supplied_segment']}**",
                    ]
                )
                if invariant is not None:
                    lines.extend(
                        [
                            "- Remaining bracket strict sign change preserved: "
                            f"**{invariant['strict_sign_change_preserved']}**",
                            "- Completed binary contraction steps: "
                            f"**{invariant['binary_contraction_step_count']}**",
                            "- Expected remaining width / supplied-segment span: "
                            f"**{invariant['expected_width_fraction_of_supplied_segment']}**",
                            "- Actual remaining width / supplied-segment span: "
                            f"**{invariant['actual_width_fraction_of_supplied_segment']}**",
                            "- Remaining-bracket binary-width consistency error: "
                            f"**{invariant['absolute_width_fraction_consistency_error']}**",
                        ]
                    )
        else:
            lines.extend(
                [
                    "- Final active bisection bracket: "
                    f"**{bracket['low_airflow_m3_h']}–"
                    f"{bracket['high_airflow_m3_h']} m³/h**",
                    "- Final bisection bracket width: "
                    f"**{bracket['width_m3_h']} m³/h**",
                    "- Final bisection half-width: "
                    f"**{bracket['half_width_m3_h']} m³/h**",
                    "- Final bracket width / supplied-segment span: "
                    f"**{bracket['width_fraction_of_supplied_segment']}**",
                    "- Final bracket residuals: "
                    f"**{bracket['low_fan_minus_system_pressure_pa']} Pa / "
                    f"{bracket['high_fan_minus_system_pressure_pa']} Pa**",
                ]
            )
            invariant = bracket.get("invariant_audit")
            if invariant is not None:
                lines.extend(
                    [
                        "- Strict sign-change bracket preserved: "
                        f"**{invariant['strict_sign_change_preserved']}**",
                        "- Selected airflow is bracket midpoint: "
                        f"**{invariant['selected_airflow_is_bracket_midpoint']}**",
                        "- Binary contraction steps before accepted midpoint: "
                        f"**{invariant['binary_contraction_step_count']}**",
                        "- Expected width / supplied-segment span: "
                        f"**{invariant['expected_width_fraction_of_supplied_segment']}**",
                        "- Actual width / supplied-segment span: "
                        f"**{invariant['actual_width_fraction_of_supplied_segment']}**",
                        "- Absolute binary-width consistency error: "
                        f"**{invariant['absolute_width_fraction_consistency_error']}**",
                    ]
                )
        trace_audit = search.get("bisection_trace_audit")
        if trace_audit is not None:
            lines.extend(
                [
                    "- Bisection decision-trace steps: "
                    f"**{trace_audit['step_count']}**",
                    "- Bisection decision sequence (L/H/T): "
                    f"**{trace_audit['decision_sequence']}**",
                    "- Trace length matches operating iterations: "
                    f"**{trace_audit['trace_matches_operating_iterations']}**",
                    "- Every trace step preserves strict sign change: "
                    f"**{trace_audit['all_steps_preserve_strict_sign_change_before_evaluation']}**",
                    "- Every trace midpoint is the arithmetic bracket midpoint: "
                    f"**{trace_audit['all_midpoints_are_arithmetic_bracket_midpoints']}**",
                    "- Terminal tolerance decision is the final trace record: "
                    f"**{trace_audit['termination_record_is_last']}**",
                    "- Trace iteration sequence is contiguous from one: "
                    f"**{trace_audit['iterations_are_contiguous_from_one']}**",
                    "- Trace state transitions replay recorded L/H decisions: "
                    f"**{trace_audit['all_state_transitions_replay_recorded_decisions']}**",
                    "- Trace endpoint replacements (low/high): "
                    f"**{trace_audit['replace_low_endpoint_count']}/"
                    f"{trace_audit['replace_high_endpoint_count']}**",
                ]
            )
        lines.extend(["", search["scope_note"]])

    point = result["fan_operating_point"]
    if point is None:
        lines.extend(["", "## Operating point", "", result["message"]])
    else:
        network = result["operating_network_solution"]
        check = result["system_pressure_check"]
        variable = network["variable_friction"]
        power = result["power_evidence"]
        components = power["system_components"]
        lines.extend(
            [
                "",
                "## Operating point",
                "",
                f"- Airflow: **{point['airflow_m3_h']} m³/h**",
                f"- Fan pressure: **{point['fan_pressure_pa']} Pa**",
                "- Variable-friction loop pressure: "
                f"**{check['loop_network_pressure_pa']} Pa**",
                f"- Total system pressure: **{check['total_system_pressure_pa']} Pa**",
                "- Fan-system pressure residual: "
                f"**{check['fan_minus_system_pressure_pa']} Pa**",
                f"- Fluid air power: **{power['fluid_air_power_kw']} kW**",
                "- Loop edge pressure-power dissipation: "
                f"**{components['loop_network_edge_dissipation_w']} W**",
                "- Loop pressure-power balance residual: "
                f"**{components['loop_network_energy_balance_residual_w']} W**",
                "- Fan-to-fixed-plus-edge-loss power residual: "
                f"**{components['fan_to_fixed_plus_edge_loss_residual_w']} W**",
                "- Shaft power: "
                f"**{power['shaft_power_kw'] if power['shaft_power_kw'] is not None else 'not reported (no explicit fan efficiency)'}**",
                "- Electrical input: "
                f"**{power['electrical_input_kw'] if power['electrical_input_kw'] is not None else 'not reported (explicit fan/motor/VFD efficiencies required)'}**",
                "- Specific fan power: "
                f"**{power['specific_fan_power_w_per_m3_s'] if power['specific_fan_power_w_per_m3_s'] is not None else 'not reported'}**",
                "- Network outer iterations: "
                f"**{variable['outer_iterations']}**",
                "- Maximum relative resistance closure error: "
                f"**{variable['max_relative_resistance_closure_error']}**",
                "- Maximum continuity residual: "
                f"**{network['max_abs_mass_balance_residual_m3_h']} m³/h**",
                "- Maximum edge pressure-law residual: "
                f"**{network['max_abs_pressure_law_residual_pa']} Pa**",
                "",
                "### Operating loop edges",
                "",
                "| Edge | Basis | Airflow (m³/h) | Direction | Resistance Pa/(m³/s)² | Dissipated pressure power W |",
                "|---|---|---:|---|---:|---:|",
            ]
        )
        for edge in network["edges"]:
            lines.append(
                f"| {edge['name']} | {edge['resistance_basis']} | "
                f"{edge['airflow_m3_h']} | {edge['flow_direction']} | "
                f"{edge['resistance_pa_per_m3_s_squared']} | "
                f"{edge['dissipated_pressure_power_w']} |"
            )

        lines.extend(
            [
                "",
                "### Variable-friction edge closure",
                "",
                "| Edge | State | Airflow (m³/h) | Used R | Target R | Relative change | Reynolds |",
                "|---|---|---:|---:|---:|---:|---:|",
            ]
        )
        for row in variable["edge_closure"]:
            target_r = (
                "—"
                if row["target_resistance_pa_per_m3_s_squared"] is None
                else row["target_resistance_pa_per_m3_s_squared"]
            )
            reynolds = (
                "—"
                if row["target_reynolds_number"] is None
                else row["target_reynolds_number"]
            )
            lines.append(
                f"| {row['name']} | {row['state']} | {row['airflow_m3_h']} | "
                f"{row['used_resistance_pa_per_m3_s_squared']} | {target_r} | "
                f"{row['relative_resistance_change']} | {reynolds} |"
            )

    lines.extend(
        [
            "",
            "## Supplied fan-curve checks",
            "",
            "| Airflow (m³/h) | Fan pressure (Pa) | Loop pressure (Pa) | Total system pressure (Pa) | Margin (Pa) | Network outer iterations |",
            "|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in result["fan_curve_point_checks"]:
        lines.append(
            f"| {row['airflow_m3_h']} | {row['fan_pressure_pa']} | "
            f"{row['loop_network_pressure_pa']} | {row['system_pressure_pa']} | "
            f"{row['pressure_margin_pa']} | {row['network_outer_iterations']} |"
        )

    audit = result.get("fan_curve_supplied_point_residual_audit")
    if audit:
        lines.extend(
            [
                "",
                "## Supplied-point residual topology audit",
                "",
                "- Supplied-point coverage: "
                f"**{audit['evaluated_supplied_point_count']}/"
                f"{audit['expected_supplied_point_count']}** "
                f"({'complete' if audit['complete_supplied_point_coverage'] else 'partial'})",
                "- Residual monotonic non-increasing within configured tolerance: "
                f"**{audit['residual_monotonic_non_increasing_with_tolerance']}**",
                "- Tolerance-contact supplied points: "
                f"**{audit['tolerance_contact_point_count']}**",
                "- Solver-eligible strict positive-to-negative supplied segments: "
                f"**{audit['strict_sign_change_segment_count']}**",
                "- Reverse strict negative-to-positive supplied segments (audit-only): "
                f"**{audit['reverse_strict_sign_change_segment_count']}**",
                "- All strict bidirectional sign-change supplied segments: "
                f"**{audit['all_strict_sign_change_segment_count']}**",
                "- Candidate crossing features: "
                f"**{audit['candidate_crossing_feature_count']}**",
                "- Minimum adjacent supplied-point airflow spacing: "
                f"**{audit['minimum_supplied_point_airflow_spacing_m3_h']} m³/h**",
                "- Maximum adjacent supplied-point airflow spacing: "
                f"**{audit['maximum_supplied_point_airflow_spacing_m3_h']} m³/h**",
                "- Supplied-point spacing max/min ratio: "
                f"**{audit['supplied_point_airflow_spacing_ratio_max_to_min']}**",
                "- Selection policy: "
                f"**{audit['selection_policy']}**",
                "- Residual-increase transitions: "
                f"**{audit['residual_increase_transition_count']}**",
                "- Largest positive residual increase: "
                f"**{audit['largest_positive_residual_increase_pa']} Pa**",
            ]
        )
        selected = audit.get("selected_candidate_feature")
        if selected is None:
            lines.append("- Selected discrete candidate: **not available**")
        else:
            if selected["feature_kind"] == "supplied_point_tolerance_contact":
                selected_text = (
                    f"supplied point {selected['point_index']} at "
                    f"{selected['airflow_m3_h']} m³/h"
                )
            else:
                selected_text = (
                    f"strict sign-change segment "
                    f"{selected['low_point_index']}–"
                    f"{selected['high_point_index']} "
                    f"({selected['low_airflow_m3_h']}–"
                    f"{selected['high_airflow_m3_h']} m³/h)"
                )
            lines.extend(
                [
                    "- Selected discrete candidate: "
                    f"**{selected_text}**",
                    "- Selected candidate priority rank: "
                    f"**{audit['selected_candidate_feature_rank']}**",
                    "- Additional discrete candidate features: "
                    f"**{audit['additional_candidate_feature_count']}**",
                    "- Selected candidate is the only discrete feature: "
                    f"**{audit['selected_candidate_is_only_discrete_feature']}**",
                ]
            )
            alternative_gap = audit.get(
                "nearest_alternative_candidate_airflow_interval_gap_m3_h"
            )
            if alternative_gap is None:
                lines.append(
                    "- Nearest alternative candidate interval gap: "
                    "**not available (no additional discrete candidate)**"
                )
            else:
                lines.extend(
                    [
                        "- Nearest alternative candidate interval gap: "
                        f"**{alternative_gap} m³/h**",
                        "- Nearest alternative candidate gap / supplied fan-curve span: "
                        f"**{audit['nearest_alternative_candidate_airflow_interval_gap_fraction_of_supplied_curve_span']}**",
                        "- Nearest alternative candidate gap / minimum supplied-point spacing: "
                        f"**{audit['nearest_alternative_candidate_airflow_interval_gap_fraction_of_minimum_supplied_point_spacing']}**",
                        "- Selected airflow overlaps an alternative candidate interval: "
                        f"**{audit['selected_airflow_overlaps_alternative_candidate_interval']}**",
                    ]
                )
                alternatives = audit.get("alternative_candidate_features") or []
                if alternatives:
                    lines.extend(
                        [
                            "",
                            "| Priority rank | Alternative feature | Airflow interval (m³/h) | Gap from selected airflow (m³/h) | Gap / supplied curve span | Gap / min supplied spacing |",
                            "|---:|---|---|---:|---:|---:|",
                        ]
                    )
                    for feature in alternatives:
                        if (
                            feature["feature_kind"]
                            == "supplied_point_tolerance_contact"
                        ):
                            feature_text = (
                                f"supplied point {feature['point_index']}"
                            )
                        else:
                            feature_text = (
                                "strict sign-change segment "
                                f"{feature['low_point_index']}–"
                                f"{feature['high_point_index']}"
                            )
                        lines.append(
                            f"| {feature['solver_priority_rank']} | "
                            f"{feature_text} | "
                            f"{feature['airflow_interval_low_m3_h']}–"
                            f"{feature['airflow_interval_high_m3_h']} | "
                            f"{feature['selected_airflow_to_feature_interval_gap_m3_h']} | "
                            f"{feature['selected_airflow_to_feature_interval_gap_fraction_of_supplied_curve_span']} | "
                            f"{feature['selected_airflow_to_feature_interval_gap_fraction_of_minimum_supplied_point_spacing']} |"
                        )
        reverse_segments = audit.get("reverse_strict_sign_change_segments") or []
        if reverse_segments:
            lines.extend(
                [
                    "",
                    "| Reverse segment low point | High point | Airflow span (m³/h) | Low residual (Pa) | High residual (Pa) |",
                    "|---:|---:|---|---:|---:|",
                ]
            )
            for segment in reverse_segments:
                lines.append(
                    f"| {segment['low_point_index']} | "
                    f"{segment['high_point_index']} | "
                    f"{segment['low_airflow_m3_h']}–"
                    f"{segment['high_airflow_m3_h']} | "
                    f"{segment['low_fan_minus_system_pressure_pa']} | "
                    f"{segment['high_fan_minus_system_pressure_pa']} |"
                )
        if audit["residual_transitions"]:
            lines.extend(
                [
                    "",
                    "| Low point | High point | Airflow span (m³/h) | Residual change (Pa) | Classification |",
                    "|---:|---:|---|---:|---|",
                ]
            )
            for transition in audit["residual_transitions"]:
                lines.append(
                    f"| {transition['low_point_index']} | "
                    f"{transition['high_point_index']} | "
                    f"{transition['low_airflow_m3_h']}–"
                    f"{transition['high_airflow_m3_h']} | "
                    f"{transition['residual_change_pa']} | "
                    f"{transition['classification']} |"
                )
        lines.extend(["", audit["scope_note"]])

    lines.extend(["", "## Engineering note", "", result["scope_note"], ""])
    return "\n".join(lines)
