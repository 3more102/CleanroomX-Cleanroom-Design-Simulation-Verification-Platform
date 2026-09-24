from __future__ import annotations

import math
from dataclasses import dataclass

from .fan_curve import FanCurve, FanCurvePoint
from .fan_loop_network import FanLoopNetworkStudy
from .loop_network import LoopedFlowNetwork
from .pressure_power import FanPowerEfficiencies, analyze_fan_pressure_power
from .variable_friction_loop import solve_variable_friction_looped_network


def _positive(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{field_name} must be finite and > 0")
    return value


def _unit_interval(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0 or value > 1:
        raise ValueError(f"{field_name} must be finite and in (0, 1]")
    return value


def _nonnegative(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{field_name} must be finite and >= 0")
    return value


def _positive_integer(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be an integer > 0")
    return value


@dataclass(frozen=True)
class FanVariableFrictionLoopStudy:
    name: str
    fan_curve: FanCurve
    loop_network: LoopedFlowNetwork
    fan_discharge_node: str
    fan_suction_node: str
    fixed_pressure_pa: float = 0.0
    power_efficiencies: FanPowerEfficiencies | None = None
    resistance_relative_tolerance: float = 1e-6
    relaxation: float = 0.5
    near_zero_airflow_m3_h: float = 1e-6
    max_outer_iterations: int = 50
    mass_balance_tolerance_m3_h: float = 1e-6
    max_newton_iterations: int = 100
    operating_pressure_tolerance_pa: float = 1e-6
    max_operating_iterations: int = 80

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError(
                "fan/variable-friction loop study name cannot be empty"
            )
        object.__setattr__(
            self,
            "fixed_pressure_pa",
            _nonnegative(self.fixed_pressure_pa, "fixed_pressure_pa"),
        )
        if (
            self.power_efficiencies is not None
            and not isinstance(self.power_efficiencies, FanPowerEfficiencies)
        ):
            raise ValueError(
                "power_efficiencies must be FanPowerEfficiencies or None"
            )
        object.__setattr__(
            self,
            "resistance_relative_tolerance",
            _positive(
                self.resistance_relative_tolerance,
                "resistance_relative_tolerance",
            ),
        )
        object.__setattr__(
            self,
            "relaxation",
            _unit_interval(self.relaxation, "relaxation"),
        )
        object.__setattr__(
            self,
            "near_zero_airflow_m3_h",
            _nonnegative(
                self.near_zero_airflow_m3_h,
                "near_zero_airflow_m3_h",
            ),
        )
        object.__setattr__(
            self,
            "max_outer_iterations",
            _positive_integer(
                self.max_outer_iterations, "max_outer_iterations"
            ),
        )
        object.__setattr__(
            self,
            "mass_balance_tolerance_m3_h",
            _positive(
                self.mass_balance_tolerance_m3_h,
                "mass_balance_tolerance_m3_h",
            ),
        )
        object.__setattr__(
            self,
            "max_newton_iterations",
            _positive_integer(
                self.max_newton_iterations, "max_newton_iterations"
            ),
        )
        object.__setattr__(
            self,
            "operating_pressure_tolerance_pa",
            _positive(
                self.operating_pressure_tolerance_pa,
                "operating_pressure_tolerance_pa",
            ),
        )
        object.__setattr__(
            self,
            "max_operating_iterations",
            _positive_integer(
                self.max_operating_iterations, "max_operating_iterations"
            ),
        )

        # Reuse the established two-terminal fan/loop topology checks without
        # using the fixed-resistance equivalent-law solver.
        FanLoopNetworkStudy(
            name=self.name,
            fan_curve=self.fan_curve,
            loop_network=self.loop_network,
            fan_discharge_node=self.fan_discharge_node,
            fan_suction_node=self.fan_suction_node,
            fixed_pressure_pa=self.fixed_pressure_pa,
        )


def _network_at_airflow(
    study: FanVariableFrictionLoopStudy,
    airflow_m3_h: float,
) -> LoopedFlowNetwork:
    airflow = _nonnegative(airflow_m3_h, "airflow_m3_h")
    reference_airflow = study.loop_network.node_injections_m3_h[
        study.fan_discharge_node
    ]
    scale = airflow / reference_airflow
    return LoopedFlowNetwork(
        name=study.loop_network.name,
        node_injections_m3_h={
            node: injection * scale
            for node, injection in study.loop_network.node_injections_m3_h.items()
        },
        edges=study.loop_network.edges,
        reference_node=study.loop_network.reference_node,
    )


def _node_pressure(result: dict, node_name: str) -> float:
    for node in result["nodes"]:
        if node["name"] == node_name:
            return float(node["relative_pressure_pa"])
    raise RuntimeError(f"node {node_name!r} missing from loop-network result")


def _fan_pressure(
    left: FanCurvePoint,
    right: FanCurvePoint,
    airflow_m3_h: float,
) -> float:
    fraction = (
        (airflow_m3_h - left.airflow_m3_h)
        / (right.airflow_m3_h - left.airflow_m3_h)
    )
    return left.pressure_pa + fraction * (
        right.pressure_pa - left.pressure_pa
    )


def _solve_network_at_airflow(
    study: FanVariableFrictionLoopStudy,
    airflow_m3_h: float,
) -> tuple[dict, float]:
    network = _network_at_airflow(study, airflow_m3_h)
    solved = solve_variable_friction_looped_network(
        network,
        resistance_relative_tolerance=study.resistance_relative_tolerance,
        relaxation=study.relaxation,
        near_zero_airflow_m3_h=study.near_zero_airflow_m3_h,
        max_outer_iterations=study.max_outer_iterations,
        mass_balance_tolerance_m3_h=study.mass_balance_tolerance_m3_h,
        max_newton_iterations=study.max_newton_iterations,
    )
    discharge_pressure = _node_pressure(solved, study.fan_discharge_node)
    suction_pressure = _node_pressure(solved, study.fan_suction_node)
    network_pressure = discharge_pressure - suction_pressure
    if not math.isfinite(network_pressure) or network_pressure < -1e-9:
        raise RuntimeError(
            "variable-friction loop solution produced invalid fan-terminal "
            "pressure requirement"
        )
    return solved, max(network_pressure, 0.0)


def _point_check(
    study: FanVariableFrictionLoopStudy,
    point: FanCurvePoint,
) -> tuple[dict, dict]:
    network, network_pressure = _solve_network_at_airflow(
        study, point.airflow_m3_h
    )
    total_pressure = study.fixed_pressure_pa + network_pressure
    residual = point.pressure_pa - total_pressure
    vf = network["variable_friction"]
    return (
        {
            "airflow_m3_h": round(point.airflow_m3_h, 6),
            "fan_pressure_pa": round(point.pressure_pa, 9),
            "loop_network_pressure_pa": round(network_pressure, 9),
            "system_pressure_pa": round(total_pressure, 9),
            "pressure_margin_pa": round(residual, 9),
            "network_outer_iterations": vf["outer_iterations"],
            "network_newton_iterations": network["iterations"],
            "max_relative_resistance_closure_error": vf[
                "max_relative_resistance_closure_error"
            ],
        },
        network,
    )


def _fan_curve_supplied_point_residual_audit(
    study: FanVariableFrictionLoopStudy,
    curve_checks: list[dict],
) -> dict:
    tolerance = float(study.operating_pressure_tolerance_pa)
    expected_count = len(study.fan_curve.points)
    observed_count = len(curve_checks)
    residuals = [
        float(check["pressure_margin_pa"]) for check in curve_checks
    ]

    tolerance_contacts = [
        {
            "point_index": index,
            "airflow_m3_h": check["airflow_m3_h"],
            "fan_minus_system_pressure_pa": check["pressure_margin_pa"],
        }
        for index, check in enumerate(curve_checks)
        if abs(float(check["pressure_margin_pa"])) <= tolerance
    ]

    strict_sign_change_segments = []
    reverse_strict_sign_change_segments = []
    residual_transitions = []
    positive_increases = []
    for index, (left, right) in enumerate(
        zip(curve_checks, curve_checks[1:])
    ):
        left_residual = float(left["pressure_margin_pa"])
        right_residual = float(right["pressure_margin_pa"])
        delta = right_residual - left_residual
        if delta > tolerance:
            classification = "increase"
            positive_increases.append(delta)
        elif delta < -tolerance:
            classification = "decrease"
        else:
            classification = "within_tolerance"
        residual_transitions.append(
            {
                "low_point_index": index,
                "high_point_index": index + 1,
                "low_airflow_m3_h": left["airflow_m3_h"],
                "high_airflow_m3_h": right["airflow_m3_h"],
                "residual_change_pa": round(delta, 9),
                "classification": classification,
            }
        )
        if left_residual > 0.0 and right_residual < 0.0:
            strict_sign_change_segments.append(
                {
                    "low_point_index": index,
                    "high_point_index": index + 1,
                    "low_airflow_m3_h": left["airflow_m3_h"],
                    "high_airflow_m3_h": right["airflow_m3_h"],
                    "low_fan_minus_system_pressure_pa": left[
                        "pressure_margin_pa"
                    ],
                    "high_fan_minus_system_pressure_pa": right[
                        "pressure_margin_pa"
                    ],
                }
            )
        elif left_residual < 0.0 and right_residual > 0.0:
            reverse_strict_sign_change_segments.append(
                {
                    "low_point_index": index,
                    "high_point_index": index + 1,
                    "low_airflow_m3_h": left["airflow_m3_h"],
                    "high_airflow_m3_h": right["airflow_m3_h"],
                    "low_fan_minus_system_pressure_pa": left[
                        "pressure_margin_pa"
                    ],
                    "high_fan_minus_system_pressure_pa": right[
                        "pressure_margin_pa"
                    ],
                }
            )

    increase_count = sum(
        transition["classification"] == "increase"
        for transition in residual_transitions
    )
    candidate_features = [
        {
            "feature_kind": "supplied_point_tolerance_contact",
            "point_index": contact["point_index"],
            "supplied_point_index_interval_low": contact["point_index"],
            "supplied_point_index_interval_high": contact["point_index"],
            "airflow_m3_h": contact["airflow_m3_h"],
            "fan_minus_system_pressure_pa": contact[
                "fan_minus_system_pressure_pa"
            ],
        }
        for contact in tolerance_contacts
    ]
    candidate_features.extend(
        {
            "feature_kind": "strict_sign_change_segment",
            **segment,
            "supplied_point_index_interval_low": segment["low_point_index"],
            "supplied_point_index_interval_high": segment["high_point_index"],
        }
        for segment in strict_sign_change_segments
    )
    for priority_rank, feature in enumerate(candidate_features):
        feature["solver_priority_rank"] = priority_rank

    supplied_airflow_spacings_m3_h = [
        float(right.airflow_m3_h) - float(left.airflow_m3_h)
        for left, right in zip(study.fan_curve.points, study.fan_curve.points[1:])
    ]
    minimum_supplied_point_airflow_spacing_m3_h = min(
        supplied_airflow_spacings_m3_h
    )
    maximum_supplied_point_airflow_spacing_m3_h = max(
        supplied_airflow_spacings_m3_h
    )

    return {
        "expected_supplied_point_count": expected_count,
        "evaluated_supplied_point_count": observed_count,
        "complete_supplied_point_coverage": observed_count == expected_count,
        "operating_pressure_tolerance_pa": tolerance,
        "supplied_fan_curve_airflow_span_m3_h": round(
            study.fan_curve.points[-1].airflow_m3_h
            - study.fan_curve.points[0].airflow_m3_h,
            9,
        ),
        "minimum_supplied_point_airflow_spacing_m3_h": round(
            minimum_supplied_point_airflow_spacing_m3_h, 9
        ),
        "maximum_supplied_point_airflow_spacing_m3_h": round(
            maximum_supplied_point_airflow_spacing_m3_h, 9
        ),
        "supplied_point_airflow_spacing_ratio_max_to_min": round(
            maximum_supplied_point_airflow_spacing_m3_h
            / minimum_supplied_point_airflow_spacing_m3_h,
            12,
        ),
        "tolerance_contact_point_count": len(tolerance_contacts),
        "tolerance_contact_points": tolerance_contacts,
        "strict_sign_change_segment_count": len(strict_sign_change_segments),
        "strict_sign_change_segments": strict_sign_change_segments,
        "reverse_strict_sign_change_segment_count": len(
            reverse_strict_sign_change_segments
        ),
        "reverse_strict_sign_change_segments": reverse_strict_sign_change_segments,
        "all_strict_sign_change_segment_count": (
            len(strict_sign_change_segments)
            + len(reverse_strict_sign_change_segments)
        ),
        "candidate_crossing_feature_count": len(candidate_features),
        "candidate_crossing_features_in_solver_priority_order": (
            candidate_features
        ),
        "selected_candidate_feature": None,
        "selected_candidate_feature_rank": None,
        "additional_candidate_feature_count": None,
        "selected_candidate_is_only_discrete_feature": None,
        "alternative_candidate_features": None,
        "nearest_alternative_candidate_airflow_interval_gap_m3_h": None,
        "nearest_alternative_candidate_airflow_interval_gap_fraction_of_supplied_curve_span": None,
        "nearest_alternative_candidate_airflow_interval_gap_fraction_of_minimum_supplied_point_spacing": None,
        "nearest_alternative_candidate_feature_index_interval_gap": None,
        "nearest_alternative_candidate_features_by_index_interval_gap": None,
        "nearest_alternative_candidate_features": None,
        "selected_airflow_overlaps_alternative_candidate_interval": None,
        "selection_policy": (
            "first supplied-point tolerance contact in point order; otherwise "
            "first strict positive-to-negative sign-change segment in segment "
            "order"
        ),
        "residual_transition_count": len(residual_transitions),
        "residual_increase_transition_count": increase_count,
        "residual_monotonic_non_increasing_with_tolerance": (
            increase_count == 0
        ),
        "largest_positive_residual_increase_pa": round(
            max(positive_increases, default=0.0),
            9,
        ),
        "residual_transitions": residual_transitions,
        "scope_note": (
            "This is a discrete audit of fan-minus-system pressure residuals "
            "at the supplied fan-curve points already evaluated by the solver. "
            "It reports tolerance contacts, solver-eligible positive-to-negative "
            "strict sign-change segments, audit-only reverse negative-to-positive "
            "strict sign-change segments, and whether those sampled residuals are "
            "non-increasing within the configured pressure tolerance. Candidate "
            "features remain limited to the solver's actual positive-to-negative "
            "selection priority, while selected-"
            "candidate provenance is added only for solved results. For solved "
            "cases with additional candidates, airflow separation is measured "
            "only to each alternative discrete point or sign-change interval "
            "and normalized by both the supplied fan-curve airflow span and "
            "the minimum adjacent supplied-point airflow spacing. Candidate "
            "separation is also measured between exact supplied-point index "
            "intervals; that value is discrete sample-grid topology only, and "
            "no alternate continuous root location is inferred. Candidate "
            "crossing features are not a count or proof of continuous physical "
            "intersections, and sampled monotonicity is not a dynamic stability, stall/surge, "
            "manufacturer-region, or equipment-acceptance criterion."
        ),
    }


def _with_selected_crossing_feature(
    audit: dict,
    *,
    termination_reason: str,
    selected_airflow_m3_h: float,
    selected_segment_index: int,
) -> dict:
    enriched = dict(audit)
    candidates = audit["candidate_crossing_features_in_solver_priority_order"]
    selected = None

    if termination_reason == "fan_curve_point_residual":
        for feature in candidates:
            if feature["feature_kind"] != "supplied_point_tolerance_contact":
                continue
            if math.isclose(
                float(feature["airflow_m3_h"]),
                float(selected_airflow_m3_h),
                rel_tol=1e-12,
                abs_tol=1e-6,
            ):
                selected = feature
                break
    else:
        for feature in candidates:
            if feature["feature_kind"] != "strict_sign_change_segment":
                continue
            if int(feature["low_point_index"]) == int(selected_segment_index):
                selected = feature
                break

    selected_copy = None if selected is None else dict(selected)
    selected_rank = (
        None if selected_copy is None else selected_copy["solver_priority_rank"]
    )

    alternative_features = None
    nearest_alternative_gap = None
    nearest_alternative_gap_fraction = None
    nearest_alternative_gap_fraction_of_minimum_spacing = None
    nearest_alternative_index_gap = None
    nearest_alternative_features_by_index_gap = None
    nearest_alternative_features = None
    selected_overlaps_alternative_interval = None
    if selected_copy is not None:
        alternative_features = []
        airflow = float(selected_airflow_m3_h)
        supplied_curve_span = float(
            audit["supplied_fan_curve_airflow_span_m3_h"]
        )
        minimum_supplied_point_spacing = float(
            audit["minimum_supplied_point_airflow_spacing_m3_h"]
        )
        selected_index_low = int(
            selected_copy["supplied_point_index_interval_low"]
        )
        selected_index_high = int(
            selected_copy["supplied_point_index_interval_high"]
        )
        for feature in candidates:
            if feature["solver_priority_rank"] == selected_rank:
                continue
            alternative = dict(feature)
            if feature["feature_kind"] == "supplied_point_tolerance_contact":
                low_airflow = float(feature["airflow_m3_h"])
                high_airflow = low_airflow
            else:
                low_airflow = float(feature["low_airflow_m3_h"])
                high_airflow = float(feature["high_airflow_m3_h"])
            alternative_index_low = int(
                feature["supplied_point_index_interval_low"]
            )
            alternative_index_high = int(
                feature["supplied_point_index_interval_high"]
            )
            if selected_index_high < alternative_index_low:
                index_gap = alternative_index_low - selected_index_high
            elif selected_index_low > alternative_index_high:
                index_gap = selected_index_low - alternative_index_high
            else:
                index_gap = 0
            if airflow < low_airflow:
                gap = low_airflow - airflow
            elif airflow > high_airflow:
                gap = airflow - high_airflow
            else:
                gap = 0.0
            alternative.update(
                {
                    "airflow_interval_low_m3_h": round(low_airflow, 9),
                    "airflow_interval_high_m3_h": round(high_airflow, 9),
                    "selected_airflow_to_feature_interval_gap_m3_h": round(
                        gap,
                        9,
                    ),
                    "selected_airflow_to_feature_interval_gap_fraction_of_supplied_curve_span": round(
                        gap / supplied_curve_span,
                        12,
                    ),
                    "selected_airflow_to_feature_interval_gap_fraction_of_minimum_supplied_point_spacing": round(
                        gap / minimum_supplied_point_spacing,
                        12,
                    ),
                    "selected_feature_to_candidate_feature_index_interval_gap": (
                        index_gap
                    ),
                }
            )
            alternative_features.append(alternative)

        if alternative_features:
            nearest_alternative_gap = min(
                float(
                    feature[
                        "selected_airflow_to_feature_interval_gap_m3_h"
                    ]
                )
                for feature in alternative_features
            )
            nearest_alternative_features = [
                dict(feature)
                for feature in alternative_features
                if math.isclose(
                    float(
                        feature[
                            "selected_airflow_to_feature_interval_gap_m3_h"
                        ]
                    ),
                    nearest_alternative_gap,
                    rel_tol=1e-12,
                    abs_tol=1e-9,
                )
            ]
            nearest_alternative_index_gap = min(
                int(
                    feature[
                        "selected_feature_to_candidate_feature_index_interval_gap"
                    ]
                )
                for feature in alternative_features
            )
            nearest_alternative_features_by_index_gap = [
                dict(feature)
                for feature in alternative_features
                if int(
                    feature[
                        "selected_feature_to_candidate_feature_index_interval_gap"
                    ]
                )
                == nearest_alternative_index_gap
            ]
            selected_overlaps_alternative_interval = math.isclose(
                nearest_alternative_gap,
                0.0,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            nearest_alternative_gap_fraction = round(
                nearest_alternative_gap / supplied_curve_span,
                12,
            )
            nearest_alternative_gap_fraction_of_minimum_spacing = round(
                nearest_alternative_gap / minimum_supplied_point_spacing,
                12,
            )
            nearest_alternative_gap = round(nearest_alternative_gap, 9)
        else:
            nearest_alternative_features = []
            nearest_alternative_features_by_index_gap = []
            selected_overlaps_alternative_interval = False

    enriched.update(
        {
            "selected_candidate_feature": selected_copy,
            "selected_candidate_feature_rank": selected_rank,
            "additional_candidate_feature_count": (
                None
                if selected_copy is None
                else max(0, len(candidates) - 1)
            ),
            "selected_candidate_is_only_discrete_feature": (
                None if selected_copy is None else len(candidates) == 1
            ),
            "alternative_candidate_features": alternative_features,
            "nearest_alternative_candidate_airflow_interval_gap_m3_h": (
                nearest_alternative_gap
            ),
            "nearest_alternative_candidate_airflow_interval_gap_fraction_of_supplied_curve_span": (
                nearest_alternative_gap_fraction
            ),
            "nearest_alternative_candidate_airflow_interval_gap_fraction_of_minimum_supplied_point_spacing": (
                nearest_alternative_gap_fraction_of_minimum_spacing
            ),
            "nearest_alternative_candidate_feature_index_interval_gap": (
                nearest_alternative_index_gap
            ),
            "nearest_alternative_candidate_features_by_index_interval_gap": (
                nearest_alternative_features_by_index_gap
            ),
            "nearest_alternative_candidate_features": (
                nearest_alternative_features
            ),
            "selected_airflow_overlaps_alternative_candidate_interval": (
                selected_overlaps_alternative_interval
            ),
        }
    )
    return enriched


def _bisection_decision_trace_audit(
    trace: list[dict] | None,
    *,
    operating_iterations: int,
    termination_reason: str,
    operating_pressure_tolerance_pa: float,
    expected_fixed_pressure_pa: float | None = None,
    study: FanVariableFrictionLoopStudy | None = None,
    segment_left: FanCurvePoint | None = None,
    segment_right: FanCurvePoint | None = None,
    initial_bisection_bracket: dict | None = None,
    solved_terminal_bracket: dict | None = None,
    iteration_limit_terminal_bracket: dict | None = None,
) -> dict | None:
    if trace is None:
        return None

    termination_indices = [
        index
        for index, step in enumerate(trace)
        if step["decision"] == "accept_pressure_tolerance"
    ]
    legend = {
        "L": "replace_low_endpoint",
        "H": "replace_high_endpoint",
        "T": "accept_pressure_tolerance",
    }
    symbol_by_decision = {
        decision: symbol for symbol, decision in legend.items()
    }
    iteration_sequence = [int(step["iteration"]) for step in trace]
    raw_state_checks = []
    pressure_state_checks = []
    geometry_checks = []
    for step in trace:
        iteration = int(step["iteration"])
        low_airflow = float(step["low_airflow_m3_h"])
        high_airflow = float(step["high_airflow_m3_h"])
        midpoint_airflow = float(step["midpoint_airflow_m3_h"])
        low_residual = float(step["low_fan_minus_system_pressure_pa"])
        high_residual = float(step["high_fan_minus_system_pressure_pa"])
        recorded_sign_flag = bool(
            step["strict_sign_change_before_evaluation"]
        )
        recorded_midpoint_flag = bool(
            step["midpoint_is_arithmetic_bracket_midpoint"]
        )
        recorded_width = float(step["width_m3_h"])
        recorded_width_fraction = float(
            step["width_fraction_of_supplied_segment"]
        )
        pressure_fields = (
            "midpoint_fan_pressure_pa",
            "midpoint_loop_network_pressure_pa",
            "midpoint_fixed_pressure_pa",
            "midpoint_system_pressure_pa",
            "midpoint_fan_minus_system_pressure_pa",
        )
        if all(field in step for field in pressure_fields):
            recorded_fan_pressure = float(step["midpoint_fan_pressure_pa"])
            recorded_loop_pressure = float(
                step["midpoint_loop_network_pressure_pa"]
            )
            recorded_fixed_pressure = float(
                step["midpoint_fixed_pressure_pa"]
            )
            recorded_system_pressure = float(
                step["midpoint_system_pressure_pa"]
            )
            recorded_midpoint_residual = float(
                step["midpoint_fan_minus_system_pressure_pa"]
            )
            expected_system_pressure = (
                recorded_fixed_pressure + recorded_loop_pressure
            )
            expected_midpoint_residual = (
                recorded_fan_pressure - recorded_system_pressure
            )
            system_pressure_balance_error = abs(
                recorded_system_pressure - expected_system_pressure
            )
            residual_balance_error = abs(
                recorded_midpoint_residual - expected_midpoint_residual
            )
            fixed_pressure_matches_expected = (
                expected_fixed_pressure_pa is None
                or math.isclose(
                    recorded_fixed_pressure,
                    float(expected_fixed_pressure_pa),
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
            )
            pressure_state_checks.append(
                {
                    "iteration": iteration,
                    "recorded_midpoint_fan_pressure_pa": (
                        recorded_fan_pressure
                    ),
                    "recorded_midpoint_loop_network_pressure_pa": (
                        recorded_loop_pressure
                    ),
                    "recorded_midpoint_fixed_pressure_pa": (
                        recorded_fixed_pressure
                    ),
                    "recorded_midpoint_system_pressure_pa": (
                        recorded_system_pressure
                    ),
                    "expected_midpoint_system_pressure_pa": (
                        expected_system_pressure
                    ),
                    "absolute_system_pressure_balance_error_pa": (
                        system_pressure_balance_error
                    ),
                    "recorded_midpoint_fan_minus_system_pressure_pa": (
                        recorded_midpoint_residual
                    ),
                    "expected_midpoint_fan_minus_system_pressure_pa": (
                        expected_midpoint_residual
                    ),
                    "absolute_residual_balance_error_pa": (
                        residual_balance_error
                    ),
                    "recorded_fixed_pressure_matches_study": (
                        fixed_pressure_matches_expected
                    ),
                    "recorded_system_pressure_matches_fixed_plus_loop": (
                        math.isclose(
                            recorded_system_pressure,
                            expected_system_pressure,
                            rel_tol=0.0,
                            abs_tol=2e-9,
                        )
                    ),
                    "recorded_residual_matches_fan_minus_system": (
                        math.isclose(
                            recorded_midpoint_residual,
                            expected_midpoint_residual,
                            rel_tol=0.0,
                            abs_tol=2e-9,
                        )
                    ),
                }
            )
        expected_width = high_airflow - low_airflow
        expected_width_fraction = 0.5 ** (iteration - 1)
        absolute_width_error = abs(recorded_width - expected_width)
        absolute_width_fraction_error = abs(
            recorded_width_fraction - expected_width_fraction
        )
        expected_midpoint_airflow = 0.5 * (low_airflow + high_airflow)
        absolute_midpoint_error = abs(
            midpoint_airflow - expected_midpoint_airflow
        )
        numeric_sign_change = low_residual > 0.0 and high_residual < 0.0
        numeric_midpoint_centered = math.isclose(
            midpoint_airflow,
            expected_midpoint_airflow,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        raw_state_checks.append(
            {
                "iteration": iteration,
                "numeric_strict_sign_change_before_evaluation": (
                    numeric_sign_change
                ),
                "recorded_strict_sign_change_flag": recorded_sign_flag,
                "recorded_sign_flag_matches_numeric_residuals": (
                    recorded_sign_flag == numeric_sign_change
                ),
                "recorded_midpoint_airflow_m3_h": midpoint_airflow,
                "expected_midpoint_airflow_from_endpoints_m3_h": (
                    expected_midpoint_airflow
                ),
                "absolute_midpoint_error_m3_h": absolute_midpoint_error,
                "numeric_midpoint_is_arithmetic_bracket_midpoint": (
                    numeric_midpoint_centered
                ),
                "recorded_midpoint_flag": recorded_midpoint_flag,
                "recorded_midpoint_flag_matches_numeric_geometry": (
                    recorded_midpoint_flag == numeric_midpoint_centered
                ),
            }
        )
        geometry_checks.append(
            {
                "iteration": iteration,
                "recorded_width_m3_h": recorded_width,
                "expected_width_from_endpoints_m3_h": expected_width,
                "absolute_width_error_m3_h": absolute_width_error,
                "recorded_width_fraction_of_supplied_segment": (
                    recorded_width_fraction
                ),
                "expected_width_fraction_from_iteration": (
                    expected_width_fraction
                ),
                "absolute_width_fraction_error": (
                    absolute_width_fraction_error
                ),
                "recorded_width_matches_airflow_bracket": math.isclose(
                    recorded_width,
                    expected_width,
                    rel_tol=0.0,
                    abs_tol=2e-9,
                ),
                "recorded_width_fraction_matches_iteration_sequence": (
                    math.isclose(
                        recorded_width_fraction,
                        expected_width_fraction,
                        rel_tol=0.0,
                        abs_tol=1e-12,
                    )
                ),
            }
        )

    residual_replay_checks = []
    residual_replay_available = (
        study is not None
        and segment_left is not None
        and segment_right is not None
    )
    residual_replay_absolute_tolerance_pa = 1e-9
    if residual_replay_available:
        assert study is not None
        assert segment_left is not None
        assert segment_right is not None
        replay_low_airflow = float(segment_left.airflow_m3_h)
        replay_high_airflow = float(segment_right.airflow_m3_h)
        residual_cache: dict[float, float] = {}

        def _independent_residual(airflow_m3_h: float) -> float:
            airflow = float(airflow_m3_h)
            if airflow not in residual_cache:
                _network, network_pressure = _solve_network_at_airflow(
                    study,
                    airflow,
                )
                fan_pressure = _fan_pressure(
                    segment_left,
                    segment_right,
                    airflow,
                )
                residual_cache[airflow] = fan_pressure - (
                    study.fixed_pressure_pa + network_pressure
                )
            return residual_cache[airflow]

        for step in trace:
            replay_midpoint_airflow = 0.5 * (
                replay_low_airflow + replay_high_airflow
            )
            recomputed_low_residual = _independent_residual(
                replay_low_airflow
            )
            recomputed_high_residual = _independent_residual(
                replay_high_airflow
            )
            recomputed_midpoint_residual = _independent_residual(
                replay_midpoint_airflow
            )
            recorded_low_residual = float(
                step["low_fan_minus_system_pressure_pa"]
            )
            recorded_high_residual = float(
                step["high_fan_minus_system_pressure_pa"]
            )
            recorded_midpoint_residual = float(
                step["midpoint_fan_minus_system_pressure_pa"]
            )
            low_error = abs(
                recorded_low_residual - recomputed_low_residual
            )
            high_error = abs(
                recorded_high_residual - recomputed_high_residual
            )
            midpoint_error = abs(
                recorded_midpoint_residual - recomputed_midpoint_residual
            )
            low_matches = math.isclose(
                recorded_low_residual,
                recomputed_low_residual,
                rel_tol=0.0,
                abs_tol=residual_replay_absolute_tolerance_pa,
            )
            high_matches = math.isclose(
                recorded_high_residual,
                recomputed_high_residual,
                rel_tol=0.0,
                abs_tol=residual_replay_absolute_tolerance_pa,
            )
            midpoint_matches = math.isclose(
                recorded_midpoint_residual,
                recomputed_midpoint_residual,
                rel_tol=0.0,
                abs_tol=residual_replay_absolute_tolerance_pa,
            )
            residual_replay_checks.append(
                {
                    "iteration": int(step["iteration"]),
                    "replayed_low_airflow_m3_h": round(
                        replay_low_airflow,
                        9,
                    ),
                    "replayed_high_airflow_m3_h": round(
                        replay_high_airflow,
                        9,
                    ),
                    "replayed_midpoint_airflow_m3_h": round(
                        replay_midpoint_airflow,
                        9,
                    ),
                    "recorded_low_fan_minus_system_pressure_pa": (
                        recorded_low_residual
                    ),
                    "recomputed_low_fan_minus_system_pressure_pa": round(
                        recomputed_low_residual,
                        9,
                    ),
                    "absolute_low_residual_replay_error_pa": low_error,
                    "recorded_high_fan_minus_system_pressure_pa": (
                        recorded_high_residual
                    ),
                    "recomputed_high_fan_minus_system_pressure_pa": round(
                        recomputed_high_residual,
                        9,
                    ),
                    "absolute_high_residual_replay_error_pa": high_error,
                    "recorded_midpoint_fan_minus_system_pressure_pa": (
                        recorded_midpoint_residual
                    ),
                    "recomputed_midpoint_fan_minus_system_pressure_pa": round(
                        recomputed_midpoint_residual,
                        9,
                    ),
                    "absolute_midpoint_residual_replay_error_pa": (
                        midpoint_error
                    ),
                    "low_residual_matches_independent_replay": low_matches,
                    "high_residual_matches_independent_replay": high_matches,
                    "midpoint_residual_matches_independent_replay": (
                        midpoint_matches
                    ),
                    "all_residuals_match_independent_replay": (
                        low_matches and high_matches and midpoint_matches
                    ),
                }
            )
            decision = step["decision"]
            if decision == "replace_low_endpoint":
                replay_low_airflow = replay_midpoint_airflow
            elif decision == "replace_high_endpoint":
                replay_high_airflow = replay_midpoint_airflow

    decision_semantic_checks = []
    tolerance = float(operating_pressure_tolerance_pa)
    for step in trace:
        midpoint_residual = float(
            step["midpoint_fan_minus_system_pressure_pa"]
        )
        if abs(midpoint_residual) <= tolerance:
            expected_decision = "accept_pressure_tolerance"
        elif midpoint_residual > 0.0:
            expected_decision = "replace_low_endpoint"
        else:
            expected_decision = "replace_high_endpoint"
        recorded_decision = step["decision"]
        decision_semantic_checks.append(
            {
                "iteration": int(step["iteration"]),
                "midpoint_fan_minus_system_pressure_pa": midpoint_residual,
                "operating_pressure_tolerance_pa": tolerance,
                "midpoint_within_pressure_tolerance": (
                    abs(midpoint_residual) <= tolerance
                ),
                "recorded_decision": recorded_decision,
                "expected_decision_from_midpoint_residual": (
                    expected_decision
                ),
                "decision_matches_midpoint_residual_semantics": (
                    recorded_decision == expected_decision
                ),
            }
        )

    transition_checks = []
    for transition_index, (step, next_step) in enumerate(
        zip(trace, trace[1:]),
        start=1,
    ):
        decision = step["decision"]
        expected_low_airflow = float(step["low_airflow_m3_h"])
        expected_high_airflow = float(step["high_airflow_m3_h"])
        expected_low_residual = float(
            step["low_fan_minus_system_pressure_pa"]
        )
        expected_high_residual = float(
            step["high_fan_minus_system_pressure_pa"]
        )
        replayable_decision = decision in {
            "replace_low_endpoint",
            "replace_high_endpoint",
        }
        if decision == "replace_low_endpoint":
            expected_low_airflow = float(step["midpoint_airflow_m3_h"])
            expected_low_residual = float(
                step["midpoint_fan_minus_system_pressure_pa"]
            )
        elif decision == "replace_high_endpoint":
            expected_high_airflow = float(step["midpoint_airflow_m3_h"])
            expected_high_residual = float(
                step["midpoint_fan_minus_system_pressure_pa"]
            )

        next_iteration_is_contiguous = (
            int(next_step["iteration"]) == int(step["iteration"]) + 1
        )
        next_airflow_bracket_matches_decision = (
            replayable_decision
            and math.isclose(
                float(next_step["low_airflow_m3_h"]),
                expected_low_airflow,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            and math.isclose(
                float(next_step["high_airflow_m3_h"]),
                expected_high_airflow,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
        )
        next_residual_bracket_matches_decision = (
            replayable_decision
            and math.isclose(
                float(next_step["low_fan_minus_system_pressure_pa"]),
                expected_low_residual,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            and math.isclose(
                float(next_step["high_fan_minus_system_pressure_pa"]),
                expected_high_residual,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
        )
        transition_checks.append(
            {
                "transition_index": transition_index,
                "from_iteration": int(step["iteration"]),
                "to_iteration": int(next_step["iteration"]),
                "decision": decision,
                "next_iteration_is_contiguous": (
                    next_iteration_is_contiguous
                ),
                "next_airflow_bracket_matches_decision": (
                    next_airflow_bracket_matches_decision
                ),
                "next_residual_bracket_matches_decision": (
                    next_residual_bracket_matches_decision
                ),
                "state_transition_replays_recorded_decision": (
                    next_iteration_is_contiguous
                    and next_airflow_bracket_matches_decision
                    and next_residual_bracket_matches_decision
                ),
            }
        )

    origin_replay = None
    terminal_bracket_for_origin_replay = (
        iteration_limit_terminal_bracket
        if termination_reason == "bisection_iteration_limit"
        else solved_terminal_bracket
    )
    if trace and initial_bisection_bracket is not None:
        replay_low_airflow = float(
            initial_bisection_bracket["low_airflow_m3_h"]
        )
        replay_high_airflow = float(
            initial_bisection_bracket["high_airflow_m3_h"]
        )
        replay_low_residual = float(
            initial_bisection_bracket["low_fan_minus_system_pressure_pa"]
        )
        replay_high_residual = float(
            initial_bisection_bracket["high_fan_minus_system_pressure_pa"]
        )
        origin_step_checks = []
        for trace_index, step in enumerate(trace):
            airflow_matches = (
                math.isclose(
                    float(step["low_airflow_m3_h"]),
                    replay_low_airflow,
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
                and math.isclose(
                    float(step["high_airflow_m3_h"]),
                    replay_high_airflow,
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
            )
            residual_matches = (
                math.isclose(
                    float(step["low_fan_minus_system_pressure_pa"]),
                    replay_low_residual,
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
                and math.isclose(
                    float(step["high_fan_minus_system_pressure_pa"]),
                    replay_high_residual,
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
            )
            current_bracket_matches = airflow_matches and residual_matches
            decision = step["decision"]
            replayable_decision = decision in {
                "replace_low_endpoint",
                "replace_high_endpoint",
                "accept_pressure_tolerance",
            }
            if decision == "replace_low_endpoint":
                replay_low_airflow = float(step["midpoint_airflow_m3_h"])
                replay_low_residual = float(
                    step["midpoint_fan_minus_system_pressure_pa"]
                )
            elif decision == "replace_high_endpoint":
                replay_high_airflow = float(step["midpoint_airflow_m3_h"])
                replay_high_residual = float(
                    step["midpoint_fan_minus_system_pressure_pa"]
                )
            origin_step_checks.append(
                {
                    "trace_index": trace_index,
                    "iteration": int(step["iteration"]),
                    "decision": decision,
                    "airflow_bracket_matches_origin_replay": airflow_matches,
                    "residual_bracket_matches_origin_replay": residual_matches,
                    "current_bracket_matches_origin_replay": (
                        current_bracket_matches
                    ),
                    "decision_is_replayable": replayable_decision,
                }
            )

        terminal_matches = False
        if terminal_bracket_for_origin_replay is not None:
            terminal_matches = (
                math.isclose(
                    float(
                        terminal_bracket_for_origin_replay[
                            "low_airflow_m3_h"
                        ]
                    ),
                    replay_low_airflow,
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
                and math.isclose(
                    float(
                        terminal_bracket_for_origin_replay[
                            "high_airflow_m3_h"
                        ]
                    ),
                    replay_high_airflow,
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
                and math.isclose(
                    float(
                        terminal_bracket_for_origin_replay[
                            "low_fan_minus_system_pressure_pa"
                        ]
                    ),
                    replay_low_residual,
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
                and math.isclose(
                    float(
                        terminal_bracket_for_origin_replay[
                            "high_fan_minus_system_pressure_pa"
                        ]
                    ),
                    replay_high_residual,
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
            )
        all_steps_match = all(
            check["current_bracket_matches_origin_replay"]
            and check["decision_is_replayable"]
            for check in origin_step_checks
        )
        origin_replay = {
            "initial_bracket_matches_first_trace_step": (
                bool(origin_step_checks)
                and origin_step_checks[0][
                    "current_bracket_matches_origin_replay"
                ]
            ),
            "all_trace_steps_match_origin_replay": all_steps_match,
            "terminal_bracket_matches_origin_replay": terminal_matches,
            "trace_origin_to_terminal_replay_consistent": (
                all_steps_match and terminal_matches
            ),
            "replayed_terminal_bracket": {
                "low_airflow_m3_h": round(replay_low_airflow, 9),
                "high_airflow_m3_h": round(replay_high_airflow, 9),
                "low_fan_minus_system_pressure_pa": round(
                    replay_low_residual,
                    9,
                ),
                "high_fan_minus_system_pressure_pa": round(
                    replay_high_residual,
                    9,
                ),
            },
            "step_checks": origin_step_checks,
        }

    terminal_limit_replay = None
    if (
        termination_reason == "bisection_iteration_limit"
        and trace
        and iteration_limit_terminal_bracket is not None
    ):
        last_step = trace[-1]
        last_decision = last_step["decision"]
        expected_low_airflow = float(last_step["low_airflow_m3_h"])
        expected_high_airflow = float(last_step["high_airflow_m3_h"])
        expected_low_residual = float(
            last_step["low_fan_minus_system_pressure_pa"]
        )
        expected_high_residual = float(
            last_step["high_fan_minus_system_pressure_pa"]
        )
        replayable_decision = last_decision in {
            "replace_low_endpoint",
            "replace_high_endpoint",
        }
        if last_decision == "replace_low_endpoint":
            expected_low_airflow = float(
                last_step["midpoint_airflow_m3_h"]
            )
            expected_low_residual = float(
                last_step["midpoint_fan_minus_system_pressure_pa"]
            )
        elif last_decision == "replace_high_endpoint":
            expected_high_airflow = float(
                last_step["midpoint_airflow_m3_h"]
            )
            expected_high_residual = float(
                last_step["midpoint_fan_minus_system_pressure_pa"]
            )

        airflow_matches = (
            replayable_decision
            and math.isclose(
                float(iteration_limit_terminal_bracket["low_airflow_m3_h"]),
                expected_low_airflow,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            and math.isclose(
                float(iteration_limit_terminal_bracket["high_airflow_m3_h"]),
                expected_high_airflow,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
        )
        residual_matches = (
            replayable_decision
            and math.isclose(
                float(
                    iteration_limit_terminal_bracket[
                        "low_fan_minus_system_pressure_pa"
                    ]
                ),
                expected_low_residual,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            and math.isclose(
                float(
                    iteration_limit_terminal_bracket[
                        "high_fan_minus_system_pressure_pa"
                    ]
                ),
                expected_high_residual,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
        )
        terminal_limit_replay = {
            "from_iteration": int(last_step["iteration"]),
            "decision": last_decision,
            "terminal_airflow_bracket_matches_decision": airflow_matches,
            "terminal_residual_bracket_matches_decision": residual_matches,
            "terminal_bracket_replays_recorded_decision": (
                airflow_matches and residual_matches
            ),
        }

    if termination_reason == "pressure_residual":
        terminal_outcome_consistent = (
            bool(trace)
            and termination_indices == [len(trace) - 1]
        )
    elif termination_reason == "bisection_iteration_limit":
        terminal_outcome_consistent = (
            bool(trace)
            and not termination_indices
            and terminal_limit_replay is not None
            and terminal_limit_replay[
                "terminal_bracket_replays_recorded_decision"
            ]
        )
    else:
        terminal_outcome_consistent = False

    return {
        "step_count": len(trace),
        "termination_reason": termination_reason,
        "trace_matches_operating_iterations": (
            len(trace) == operating_iterations
        ),
        "iteration_sequence": iteration_sequence,
        "iterations_are_contiguous_from_one": (
            iteration_sequence == list(range(1, len(trace) + 1))
        ),
        "raw_state_check_count": len(raw_state_checks),
        "all_numeric_brackets_preserve_strict_sign_change": all(
            check["numeric_strict_sign_change_before_evaluation"]
            for check in raw_state_checks
        ),
        "all_recorded_sign_flags_match_numeric_residuals": all(
            check["recorded_sign_flag_matches_numeric_residuals"]
            for check in raw_state_checks
        ),
        "all_numeric_midpoints_are_arithmetic_bracket_midpoints": all(
            check["numeric_midpoint_is_arithmetic_bracket_midpoint"]
            for check in raw_state_checks
        ),
        "all_recorded_midpoint_flags_match_numeric_geometry": all(
            check["recorded_midpoint_flag_matches_numeric_geometry"]
            for check in raw_state_checks
        ),
        "all_trace_raw_state_consistent": all(
            check["numeric_strict_sign_change_before_evaluation"]
            and check["recorded_sign_flag_matches_numeric_residuals"]
            and check["numeric_midpoint_is_arithmetic_bracket_midpoint"]
            and check["recorded_midpoint_flag_matches_numeric_geometry"]
            for check in raw_state_checks
        ),
        "maximum_absolute_trace_midpoint_error_m3_h": max(
            (
                check["absolute_midpoint_error_m3_h"]
                for check in raw_state_checks
            ),
            default=0.0,
        ),
        "raw_state_checks": raw_state_checks,
        "pressure_state_check_count": len(pressure_state_checks),
        "pressure_state_evidence_complete": (
            len(pressure_state_checks) == len(trace)
        ),
        "all_recorded_fixed_pressure_values_match_study": (
            len(pressure_state_checks) == len(trace)
            and all(
                check["recorded_fixed_pressure_matches_study"]
                for check in pressure_state_checks
            )
        ),
        "all_recorded_system_pressures_match_fixed_plus_loop": (
            len(pressure_state_checks) == len(trace)
            and all(
                check["recorded_system_pressure_matches_fixed_plus_loop"]
                for check in pressure_state_checks
            )
        ),
        "all_recorded_residuals_match_fan_minus_system": (
            len(pressure_state_checks) == len(trace)
            and all(
                check["recorded_residual_matches_fan_minus_system"]
                for check in pressure_state_checks
            )
        ),
        "all_trace_pressure_state_consistent": (
            len(pressure_state_checks) == len(trace)
            and all(
                check["recorded_fixed_pressure_matches_study"]
                and check[
                    "recorded_system_pressure_matches_fixed_plus_loop"
                ]
                and check["recorded_residual_matches_fan_minus_system"]
                for check in pressure_state_checks
            )
        ),
        "maximum_absolute_trace_system_pressure_balance_error_pa": max(
            (
                check["absolute_system_pressure_balance_error_pa"]
                for check in pressure_state_checks
            ),
            default=0.0,
        ),
        "maximum_absolute_trace_residual_balance_error_pa": max(
            (
                check["absolute_residual_balance_error_pa"]
                for check in pressure_state_checks
            ),
            default=0.0,
        ),
        "pressure_state_checks": pressure_state_checks,
        "residual_replay_available": residual_replay_available,
        "residual_replay_check_count": len(residual_replay_checks),
        "residual_replay_absolute_tolerance_pa": (
            residual_replay_absolute_tolerance_pa
            if residual_replay_available
            else None
        ),
        "all_recorded_low_residuals_match_independent_replay": (
            all(
                check["low_residual_matches_independent_replay"]
                for check in residual_replay_checks
            )
            if residual_replay_available
            else None
        ),
        "all_recorded_high_residuals_match_independent_replay": (
            all(
                check["high_residual_matches_independent_replay"]
                for check in residual_replay_checks
            )
            if residual_replay_available
            else None
        ),
        "all_recorded_midpoint_residuals_match_independent_replay": (
            all(
                check["midpoint_residual_matches_independent_replay"]
                for check in residual_replay_checks
            )
            if residual_replay_available
            else None
        ),
        "all_trace_residuals_match_independent_replay": (
            all(
                check["all_residuals_match_independent_replay"]
                for check in residual_replay_checks
            )
            if residual_replay_available
            else None
        ),
        "maximum_absolute_trace_residual_replay_error_pa": (
            max(
                max(
                    check["absolute_low_residual_replay_error_pa"],
                    check["absolute_high_residual_replay_error_pa"],
                    check["absolute_midpoint_residual_replay_error_pa"],
                )
                for check in residual_replay_checks
            )
            if residual_replay_checks
            else None
        ),
        "residual_replay_checks": residual_replay_checks,
        "all_steps_preserve_strict_sign_change_before_evaluation": all(
            step["strict_sign_change_before_evaluation"]
            for step in trace
        ),
        "all_midpoints_are_arithmetic_bracket_midpoints": all(
            step["midpoint_is_arithmetic_bracket_midpoint"]
            for step in trace
        ),
        "geometry_check_count": len(geometry_checks),
        "all_recorded_widths_match_airflow_brackets": all(
            check["recorded_width_matches_airflow_bracket"]
            for check in geometry_checks
        ),
        "all_recorded_width_fractions_match_iteration_sequence": all(
            check["recorded_width_fraction_matches_iteration_sequence"]
            for check in geometry_checks
        ),
        "all_trace_geometry_consistent": all(
            check["recorded_width_matches_airflow_bracket"]
            and check[
                "recorded_width_fraction_matches_iteration_sequence"
            ]
            for check in geometry_checks
        ),
        "maximum_absolute_trace_width_error_m3_h": (
            max(
                (
                    check["absolute_width_error_m3_h"]
                    for check in geometry_checks
                ),
                default=0.0,
            )
        ),
        "maximum_absolute_trace_width_fraction_error": (
            max(
                (
                    check["absolute_width_fraction_error"]
                    for check in geometry_checks
                ),
                default=0.0,
            )
        ),
        "geometry_checks": geometry_checks,
        "decision_semantic_check_count": len(decision_semantic_checks),
        "all_decisions_match_midpoint_residual_semantics": all(
            check["decision_matches_midpoint_residual_semantics"]
            for check in decision_semantic_checks
        ),
        "decision_semantic_violation_iterations": [
            check["iteration"]
            for check in decision_semantic_checks
            if not check["decision_matches_midpoint_residual_semantics"]
        ],
        "decision_semantic_checks": decision_semantic_checks,
        "termination_record_count": len(termination_indices),
        "termination_record_is_last": (
            termination_indices == [len(trace) - 1]
        ),
        "terminal_outcome_consistent": terminal_outcome_consistent,
        "trace_origin_replay": origin_replay,
        "trace_origin_to_terminal_replay_consistent": (
            origin_replay is not None
            and origin_replay["trace_origin_to_terminal_replay_consistent"]
        ),
        "iteration_limit_terminal_replay": terminal_limit_replay,
        "replace_low_endpoint_count": sum(
            step["decision"] == "replace_low_endpoint" for step in trace
        ),
        "replace_high_endpoint_count": sum(
            step["decision"] == "replace_high_endpoint" for step in trace
        ),
        "transition_record_count": len(transition_checks),
        "all_airflow_bracket_transitions_replay_recorded_decisions": all(
            check["next_airflow_bracket_matches_decision"]
            for check in transition_checks
        ),
        "all_residual_bracket_transitions_replay_recorded_decisions": all(
            check["next_residual_bracket_matches_decision"]
            for check in transition_checks
        ),
        "all_state_transitions_replay_recorded_decisions": all(
            check["state_transition_replays_recorded_decision"]
            for check in transition_checks
        ),
        "transition_checks": transition_checks,
        "decision_sequence": "".join(
            symbol_by_decision[step["decision"]] for step in trace
        ),
        "decision_legend": legend,
        "scope_note": (
            "The decision trace preserves every completed bounded-bisection "
            "midpoint evaluation. L replaces the positive-residual low "
            "endpoint, H replaces the negative-residual high endpoint, and T "
            "accepts a midpoint within the configured operating-pressure "
            "tolerance. The replay audit verifies that each nonterminal L/H "
            "decision produces the next recorded airflow/residual bracket, "
            "that iteration numbering is contiguous, and that every recorded "
            "bracket width equals its endpoint span with the binary width "
            "fraction implied by its iteration. The raw-state audit "
            "independently recomputes strict sign-change and arithmetic-"
            "midpoint facts from the recorded numeric state and checks the "
            "stored flags against those recomputed facts. The pressure-state "
            "audit independently checks each retained midpoint's fixed-plus-"
            "loop system-pressure identity and fan-minus-system residual "
            "identity, and anchors the retained fixed-pressure component to "
            "the study input. The independent residual-replay audit "
            "reconstructs the active bisection states from the selected "
            "supplied fan segment, freshly re-solves the nonlinear loop at "
            "each low/high/midpoint airflow, and checks retained residuals "
            "against that independent fan/system evaluation. The decision-semantics audit "
            "independently verifies each L/H/T choice against the recorded "
            "midpoint residual and configured operating-pressure tolerance. "
            "The origin replay additionally anchors the first trace state to "
            "the selected supplied-point "
            "bracket and reconstructs the complete decision chain through the "
            "terminal retained bracket. For an iteration-limit "
            "outcome, the final L/H decision is additionally replayed into "
            "the retained remaining bracket without accepting an operating "
            "point. This is numerical implementation provenance only; it is "
            "not physical uncertainty, an interpolation-error bound, a "
            "stability margin, or an equipment-acceptance criterion."
        ),
    }

def _nonconverged_result(
    study: FanVariableFrictionLoopStudy,
    *,
    curve_checks: list[dict],
    message: str,
) -> dict:
    return {
        "study": study.name,
        "status": "non_converged",
        "fan_curve": study.fan_curve.name,
        "fan_discharge_node": study.fan_discharge_node,
        "fan_suction_node": study.fan_suction_node,
        "fixed_pressure_pa": round(study.fixed_pressure_pa, 6),
        "fan_curve_airflow_range_m3_h": [
            round(study.fan_curve.points[0].airflow_m3_h, 6),
            round(study.fan_curve.points[-1].airflow_m3_h, 6),
        ],
        "fan_curve_point_checks": curve_checks,
        "fan_curve_supplied_point_residual_audit": (
            _fan_curve_supplied_point_residual_audit(
                study,
                curve_checks,
            )
        ),
        "fan_operating_point": None,
        "operating_point_search_evidence": None,
        "operating_network_solution": None,
        "system_pressure_check": None,
        "power_evidence": None,
        "solver_diagnostics": {
            "converged": False,
            "termination_reason": "network_solver_non_convergence",
            "operating_iterations": 0,
            "operating_pressure_tolerance_pa": (
                study.operating_pressure_tolerance_pa
            ),
        },
        "message": message,
        "scope_note": _scope_note(),
    }


def _scope_note() -> str:
    return (
        "This workflow couples the supplied fan curve directly to the "
        "two-terminal loop network while re-solving flow-dependent Darcy "
        "friction at every evaluated airflow. Fan pressure is interpolated "
        "only between supplied fan points and is never extrapolated. "
        "Automatic Darcy updates reuse the existing explicit roughness, "
        "kinematic-viscosity, density, geometry, and local-K model; edges "
        "with explicit resistance or user-supplied friction remain fixed. "
        "This is a steady incompressible engineering screening model, not "
        "CFD. It does not infer dampers, leakage, controls, system effect, "
        "acoustics, stall/surge limits, motor/VFD limits, transients, or "
        "manufacturer acceptance. Fluid pressure power is reported directly; "
        "shaft/electrical power is reported only from explicit efficiencies."
    )


def solve_fan_variable_friction_loop(
    study: FanVariableFrictionLoopStudy,
) -> dict:
    points = study.fan_curve.points
    curve_checks: list[dict] = []
    point_networks: list[dict] = []

    try:
        for point in points:
            check, network = _point_check(study, point)
            curve_checks.append(check)
            point_networks.append(network)
    except RuntimeError as exc:
        return _nonconverged_result(
            study,
            curve_checks=curve_checks,
            message=(
                "The variable-friction loop solver did not converge while "
                f"evaluating the bounded fan curve: {exc}"
            ),
        )

    tolerance = study.operating_pressure_tolerance_pa
    selected_airflow: float | None = None
    selected_fan_pressure: float | None = None
    selected_network: dict | None = None
    selected_network_pressure: float | None = None
    selected_segment = 0
    selected_supplied_point_index: int | None = None
    final_bisection_bracket: dict | None = None
    initial_bisection_bracket: dict | None = None
    bisection_trace: list[dict] | None = None
    operating_iterations = 0
    termination_reason = "no_intersection_in_supplied_range"

    for index, (point, check, network) in enumerate(
        zip(points, curve_checks, point_networks)
    ):
        if abs(float(check["pressure_margin_pa"])) <= tolerance:
            selected_airflow = point.airflow_m3_h
            selected_fan_pressure = point.pressure_pa
            selected_network = network
            selected_network_pressure = float(
                check["loop_network_pressure_pa"]
            )
            selected_segment = min(index, len(points) - 2)
            selected_supplied_point_index = index
            termination_reason = "fan_curve_point_residual"
            break

    if selected_airflow is None:
        for index, (left, right) in enumerate(zip(points, points[1:])):
            left_residual = float(curve_checks[index]["pressure_margin_pa"])
            right_residual = float(
                curve_checks[index + 1]["pressure_margin_pa"]
            )
            if not (left_residual > 0.0 and right_residual < 0.0):
                continue

            low = left.airflow_m3_h
            high = right.airflow_m3_h
            low_residual = left_residual
            high_residual = right_residual
            supplied_segment_span = high - low
            initial_bisection_bracket = {
                "low_airflow_m3_h": round(low, 9),
                "high_airflow_m3_h": round(high, 9),
                "low_fan_minus_system_pressure_pa": round(
                    low_residual,
                    9,
                ),
                "high_fan_minus_system_pressure_pa": round(
                    high_residual,
                    9,
                ),
            }
            bisection_trace = []
            final: tuple[float, float, dict, float, float] | None = None

            try:
                for iteration in range(1, study.max_operating_iterations + 1):
                    airflow = 0.5 * (low + high)
                    fan_pressure = _fan_pressure(left, right, airflow)
                    network, network_pressure = _solve_network_at_airflow(
                        study, airflow
                    )
                    system_pressure = (
                        study.fixed_pressure_pa + network_pressure
                    )
                    residual = fan_pressure - system_pressure
                    final = (
                        airflow,
                        fan_pressure,
                        network,
                        network_pressure,
                        residual,
                    )
                    operating_iterations = iteration
                    bracket_width = high - low
                    width_fraction = bracket_width / supplied_segment_span
                    bracket_midpoint = 0.5 * (low + high)
                    if abs(residual) <= tolerance:
                        decision = "accept_pressure_tolerance"
                    elif residual > 0.0:
                        decision = "replace_low_endpoint"
                    else:
                        decision = "replace_high_endpoint"
                    assert bisection_trace is not None
                    bisection_trace.append(
                        {
                            "iteration": iteration,
                            "low_airflow_m3_h": round(low, 9),
                            "high_airflow_m3_h": round(high, 9),
                            "midpoint_airflow_m3_h": round(airflow, 9),
                            "width_m3_h": round(bracket_width, 9),
                            "width_fraction_of_supplied_segment": round(
                                width_fraction,
                                15,
                            ),
                            "low_fan_minus_system_pressure_pa": round(
                                low_residual,
                                9,
                            ),
                            "high_fan_minus_system_pressure_pa": round(
                                high_residual,
                                9,
                            ),
                            "midpoint_fan_pressure_pa": round(
                                fan_pressure,
                                9,
                            ),
                            "midpoint_loop_network_pressure_pa": round(
                                network_pressure,
                                9,
                            ),
                            "midpoint_fixed_pressure_pa": round(
                                study.fixed_pressure_pa,
                                9,
                            ),
                            "midpoint_system_pressure_pa": round(
                                system_pressure,
                                9,
                            ),
                            "midpoint_fan_minus_system_pressure_pa": round(
                                residual,
                                9,
                            ),
                            "decision": decision,
                            "strict_sign_change_before_evaluation": (
                                low_residual > 0.0
                                and high_residual < 0.0
                            ),
                            "midpoint_is_arithmetic_bracket_midpoint": (
                                math.isclose(
                                    airflow,
                                    bracket_midpoint,
                                    rel_tol=0.0,
                                    abs_tol=1e-12,
                                )
                            ),
                        }
                    )
                    if abs(residual) <= tolerance:
                        expected_width_fraction = 0.5 ** (iteration - 1)
                        final_bisection_bracket = {
                            "low_airflow_m3_h": round(low, 9),
                            "high_airflow_m3_h": round(high, 9),
                            "width_m3_h": round(bracket_width, 9),
                            "half_width_m3_h": round(
                                0.5 * bracket_width,
                                9,
                            ),
                            "low_fan_minus_system_pressure_pa": round(
                                low_residual,
                                9,
                            ),
                            "high_fan_minus_system_pressure_pa": round(
                                high_residual,
                                9,
                            ),
                            "selected_midpoint_airflow_m3_h": round(
                                airflow,
                                9,
                            ),
                            "selected_fan_minus_system_pressure_pa": round(
                                residual,
                                9,
                            ),
                            "width_fraction_of_supplied_segment": round(
                                width_fraction,
                                12,
                            ),
                            "iteration": iteration,
                            "invariant_audit": {
                                "strict_sign_change_preserved": (
                                    low_residual > 0.0
                                    and high_residual < 0.0
                                ),
                                "selected_airflow_is_bracket_midpoint": (
                                    math.isclose(
                                        airflow,
                                        bracket_midpoint,
                                        rel_tol=0.0,
                                        abs_tol=1e-12,
                                    )
                                ),
                                "binary_contraction_step_count": (
                                    iteration - 1
                                ),
                                "expected_width_fraction_of_supplied_segment": round(
                                    expected_width_fraction,
                                    15,
                                ),
                                "actual_width_fraction_of_supplied_segment": round(
                                    width_fraction,
                                    15,
                                ),
                                "absolute_width_fraction_consistency_error": round(
                                    abs(
                                        width_fraction
                                        - expected_width_fraction
                                    ),
                                    18,
                                ),
                            },
                        }
                        termination_reason = "pressure_residual"
                        break
                    if residual > 0.0:
                        low = airflow
                        low_residual = residual
                    else:
                        high = airflow
                        high_residual = residual
                else:
                    termination_reason = "bisection_iteration_limit"
            except RuntimeError as exc:
                return _nonconverged_result(
                    study,
                    curve_checks=curve_checks,
                    message=(
                        "The variable-friction loop solver did not converge "
                        "during bounded fan/system root search: "
                        f"{exc}"
                    ),
                )

            if final is None:
                continue
            (
                selected_airflow,
                selected_fan_pressure,
                selected_network,
                selected_network_pressure,
                residual,
            ) = final
            selected_segment = index
            if abs(residual) > tolerance:
                terminal_width = high - low
                terminal_width_fraction = (
                    terminal_width / supplied_segment_span
                )
                expected_terminal_width_fraction = (
                    0.5 ** operating_iterations
                )
                terminal_bracket = {
                    "low_airflow_m3_h": round(low, 9),
                    "high_airflow_m3_h": round(high, 9),
                    "width_m3_h": round(terminal_width, 9),
                    "half_width_m3_h": round(
                        0.5 * terminal_width,
                        9,
                    ),
                    "low_fan_minus_system_pressure_pa": round(
                        low_residual,
                        9,
                    ),
                    "high_fan_minus_system_pressure_pa": round(
                        high_residual,
                        9,
                    ),
                    "width_fraction_of_supplied_segment": round(
                        terminal_width_fraction,
                        12,
                    ),
                    "completed_iteration_count": operating_iterations,
                    "invariant_audit": {
                        "strict_sign_change_preserved": (
                            low_residual > 0.0
                            and high_residual < 0.0
                        ),
                        "binary_contraction_step_count": (
                            operating_iterations
                        ),
                        "expected_width_fraction_of_supplied_segment": round(
                            expected_terminal_width_fraction,
                            15,
                        ),
                        "actual_width_fraction_of_supplied_segment": round(
                            terminal_width_fraction,
                            15,
                        ),
                        "absolute_width_fraction_consistency_error": round(
                            abs(
                                terminal_width_fraction
                                - expected_terminal_width_fraction
                            ),
                            18,
                        ),
                    },
                }
                search_evidence = {
                    "method": "bounded_bisection",
                    "supplied_segment_index": selected_segment,
                    "supplied_segment_low_airflow_m3_h": round(
                        left.airflow_m3_h,
                        6,
                    ),
                    "supplied_segment_high_airflow_m3_h": round(
                        right.airflow_m3_h,
                        6,
                    ),
                    "selected_supplied_point_index": None,
                    "operating_iterations": operating_iterations,
                    "initial_bisection_bracket": initial_bisection_bracket,
                    "final_bisection_bracket": None,
                    "bisection_trace": bisection_trace,
                    "bisection_trace_audit": _bisection_decision_trace_audit(
                        bisection_trace,
                        operating_iterations=operating_iterations,
                        termination_reason=termination_reason,
                        operating_pressure_tolerance_pa=tolerance,
                        expected_fixed_pressure_pa=study.fixed_pressure_pa,
                        study=study,
                        segment_left=left,
                        segment_right=right,
                        initial_bisection_bracket=initial_bisection_bracket,
                        iteration_limit_terminal_bracket=terminal_bracket,
                    ),
                    "iteration_limit_evidence": {
                        "last_evaluated_midpoint_airflow_m3_h": round(
                            selected_airflow,
                            9,
                        ),
                        "last_evaluated_fan_minus_system_pressure_pa": round(
                            residual,
                            9,
                        ),
                        "pressure_tolerance_satisfied": False,
                        "remaining_bisection_bracket": terminal_bracket,
                    },
                    "scope_note": (
                        "The iteration-limit evidence retains the active "
                        "signed-residual bracket remaining after the final "
                        "budgeted bisection evaluation. Its geometry and "
                        "binary-contraction audit are solver implementation "
                        "diagnostics only; no operating point is accepted, "
                        "and the remaining bracket is not physical airflow "
                        "uncertainty, interpolation error, a continuous "
                        "worst-case bound, or an equipment-acceptance limit."
                    ),
                }
                return {
                    **_nonconverged_result(
                        study,
                        curve_checks=curve_checks,
                        message=(
                            "Bounded fan/system bisection reached "
                            "max_operating_iterations before satisfying the "
                            "configured pressure residual tolerance."
                        ),
                    ),
                    "operating_point_search_evidence": search_evidence,
                    "solver_diagnostics": {
                        "converged": False,
                        "termination_reason": termination_reason,
                        "operating_iterations": operating_iterations,
                        "operating_pressure_tolerance_pa": tolerance,
                        "final_pressure_residual_pa": round(residual, 9),
                        "bracket_low_airflow_m3_h": round(low, 9),
                        "bracket_high_airflow_m3_h": round(high, 9),
                    },
                }
            break

    base = {
        "study": study.name,
        "fan_curve": study.fan_curve.name,
        "fan_discharge_node": study.fan_discharge_node,
        "fan_suction_node": study.fan_suction_node,
        "fixed_pressure_pa": round(study.fixed_pressure_pa, 6),
        "fan_curve_airflow_range_m3_h": [
            round(points[0].airflow_m3_h, 6),
            round(points[-1].airflow_m3_h, 6),
        ],
        "fan_curve_point_checks": curve_checks,
        "fan_curve_supplied_point_residual_audit": (
            _fan_curve_supplied_point_residual_audit(
                study,
                curve_checks,
            )
        ),
    }

    if selected_airflow is None:
        if float(curve_checks[0]["pressure_margin_pa"]) < 0.0:
            message = (
                "System pressure exceeds fan pressure at the lowest supplied "
                "airflow point. No lower-flow fan extrapolation is performed."
            )
        else:
            message = (
                "Fan pressure remains above system pressure at the highest "
                "supplied airflow point. No higher-flow fan extrapolation is "
                "performed."
            )
        return {
            **base,
            "status": "no_intersection_in_supplied_range",
            "fan_operating_point": None,
            "operating_point_search_evidence": None,
            "operating_network_solution": None,
            "system_pressure_check": None,
            "power_evidence": None,
            "solver_diagnostics": {
                "converged": True,
                "termination_reason": termination_reason,
                "operating_iterations": 0,
                "operating_pressure_tolerance_pa": tolerance,
            },
            "message": message,
            "scope_note": _scope_note(),
        }

    assert selected_fan_pressure is not None
    assert selected_network is not None
    assert selected_network_pressure is not None
    system_pressure = study.fixed_pressure_pa + selected_network_pressure
    residual = selected_fan_pressure - system_pressure
    airflow_m3_s = selected_airflow / 3600.0
    left = points[selected_segment]
    right = points[selected_segment + 1]
    vf = selected_network["variable_friction"]
    power_evidence = analyze_fan_pressure_power(
        selected_airflow,
        selected_fan_pressure,
        study.power_efficiencies,
    )
    network_pressure_power_w = (
        airflow_m3_s * selected_network_pressure
    )
    fixed_pressure_power_w = airflow_m3_s * study.fixed_pressure_pa
    edge_dissipation_w = selected_network["pressure_power"][
        "total_edge_dissipation_w"
    ]
    fan_to_system_power_residual_w = (
        power_evidence["fluid_air_power_w"]
        - fixed_pressure_power_w
        - edge_dissipation_w
    )
    selected_residual_audit = _with_selected_crossing_feature(
        base["fan_curve_supplied_point_residual_audit"],
        termination_reason=termination_reason,
        selected_airflow_m3_h=selected_airflow,
        selected_segment_index=selected_segment,
    )
    operating_point_search_evidence = {
        "method": (
            "supplied_point_tolerance_contact"
            if termination_reason == "fan_curve_point_residual"
            else "bounded_bisection"
        ),
        "supplied_segment_index": selected_segment,
        "supplied_segment_low_airflow_m3_h": round(
            left.airflow_m3_h,
            6,
        ),
        "supplied_segment_high_airflow_m3_h": round(
            right.airflow_m3_h,
            6,
        ),
        "selected_supplied_point_index": selected_supplied_point_index,
        "operating_iterations": operating_iterations,
        "initial_bisection_bracket": initial_bisection_bracket,
        "final_bisection_bracket": final_bisection_bracket,
        "bisection_trace": bisection_trace,
        "bisection_trace_audit": _bisection_decision_trace_audit(
            bisection_trace,
            operating_iterations=operating_iterations,
            termination_reason=termination_reason,
            operating_pressure_tolerance_pa=tolerance,
            expected_fixed_pressure_pa=study.fixed_pressure_pa,
            study=study,
            segment_left=left,
            segment_right=right,
            initial_bisection_bracket=initial_bisection_bracket,
            solved_terminal_bracket=final_bisection_bracket,
        ),
        "scope_note": (
            "The final bisection bracket is the active signed-residual search "
            "interval immediately before a pressure-tolerance midpoint "
            "termination. Bounded-bisection solutions also retain every "
            "midpoint decision that led to that terminal bracket. Iteration-"
            "limit outcomes retain the same completed decision trace and "
            "replay its final L/H decision into the remaining active bracket "
            "without accepting a root; direct supplied-point contacts do not "
            "fabricate a bisection trace. Bracket width and the decision trace "
            "are numerical search "
            "provenance only; they are not physical airflow uncertainty, "
            "interpolation-error bounds, continuous worst-case guarantees, "
            "stability margins, or equipment-acceptance criteria."
        ),
    }

    power_evidence["system_components"] = {
        "fixed_pressure_power_w": round(fixed_pressure_power_w, 9),
        "loop_network_terminal_pressure_power_w": round(
            network_pressure_power_w, 9
        ),
        "loop_network_edge_dissipation_w": edge_dissipation_w,
        "loop_network_energy_balance_residual_w": selected_network[
            "pressure_power"
        ]["balance_residual_w"],
        "fan_to_fixed_plus_edge_loss_residual_w": round(
            fan_to_system_power_residual_w, 9
        ),
    }

    return {
        **base,
        "status": "solved",
        "fan_curve_supplied_point_residual_audit": selected_residual_audit,
        "operating_point_search_evidence": operating_point_search_evidence,
        "fan_operating_point": {
            "airflow_m3_h": round(selected_airflow, 6),
            "airflow_m3_s": round(airflow_m3_s, 9),
            "fan_pressure_pa": round(selected_fan_pressure, 9),
            "system_pressure_pa": round(system_pressure, 9),
            "pressure_residual_pa": round(residual, 9),
            "air_power_kw": round(
                airflow_m3_s * system_pressure / 1000.0, 9
            ),
            "interpolation_segment": {
                "low_airflow_m3_h": round(left.airflow_m3_h, 6),
                "high_airflow_m3_h": round(right.airflow_m3_h, 6),
            },
        },
        "operating_network_solution": selected_network,
        "power_evidence": power_evidence,
        "system_pressure_check": {
            "fixed_pressure_pa": round(study.fixed_pressure_pa, 6),
            "loop_network_pressure_pa": round(
                selected_network_pressure, 9
            ),
            "total_system_pressure_pa": round(system_pressure, 9),
            "fan_pressure_pa": round(selected_fan_pressure, 9),
            "fan_minus_system_pressure_pa": round(residual, 9),
        },
        "solver_diagnostics": {
            "converged": True,
            "termination_reason": termination_reason,
            "operating_iterations": operating_iterations,
            "operating_pressure_tolerance_pa": tolerance,
            "network_outer_iterations": vf["outer_iterations"],
            "network_newton_iterations": selected_network["iterations"],
            "network_resistance_relative_tolerance": vf[
                "resistance_relative_tolerance"
            ],
            "network_max_relative_resistance_closure_error": vf[
                "max_relative_resistance_closure_error"
            ],
            "max_abs_mass_balance_residual_m3_h": selected_network[
                "max_abs_mass_balance_residual_m3_h"
            ],
            "max_abs_pressure_law_residual_pa": selected_network[
                "max_abs_pressure_law_residual_pa"
            ],
        },
        "message": (
            "Operating point found inside the supplied fan-curve range by "
            "bounded interpolation with a complete variable-friction loop "
            "re-solve at every evaluated airflow."
        ),
        "scope_note": _scope_note(),
    }
