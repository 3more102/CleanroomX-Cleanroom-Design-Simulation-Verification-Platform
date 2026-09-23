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
                "- Strict sign-change supplied segments: "
                f"**{audit['strict_sign_change_segment_count']}**",
                "- Candidate crossing features: "
                f"**{audit['candidate_crossing_feature_count']}**",
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
                        "- Selected airflow overlaps an alternative candidate interval: "
                        f"**{audit['selected_airflow_overlaps_alternative_candidate_interval']}**",
                    ]
                )
                alternatives = audit.get("alternative_candidate_features") or []
                if alternatives:
                    lines.extend(
                        [
                            "",
                            "| Priority rank | Alternative feature | Airflow interval (m³/h) | Gap from selected airflow (m³/h) |",
                            "|---:|---|---|---:|",
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
                            f"{feature['selected_airflow_to_feature_interval_gap_m3_h']} |"
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
