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

    increase_count = sum(
        transition["classification"] == "increase"
        for transition in residual_transitions
    )
    candidate_features = [
        {
            "feature_kind": "supplied_point_tolerance_contact",
            "point_index": contact["point_index"],
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
        }
        for segment in strict_sign_change_segments
    )
    for priority_rank, feature in enumerate(candidate_features):
        feature["solver_priority_rank"] = priority_rank

    return {
        "expected_supplied_point_count": expected_count,
        "evaluated_supplied_point_count": observed_count,
        "complete_supplied_point_coverage": observed_count == expected_count,
        "operating_pressure_tolerance_pa": tolerance,
        "tolerance_contact_point_count": len(tolerance_contacts),
        "tolerance_contact_points": tolerance_contacts,
        "strict_sign_change_segment_count": len(strict_sign_change_segments),
        "strict_sign_change_segments": strict_sign_change_segments,
        "candidate_crossing_feature_count": len(candidate_features),
        "candidate_crossing_features_in_solver_priority_order": (
            candidate_features
        ),
        "selected_candidate_feature": None,
        "selected_candidate_feature_rank": None,
        "additional_candidate_feature_count": None,
        "selected_candidate_is_only_discrete_feature": None,
        "alternative_candidate_features": None,
        "alternative_candidate_below_selected_airflow_count": None,
        "alternative_candidate_overlap_selected_airflow_count": None,
        "alternative_candidate_above_selected_airflow_count": None,
        "nearest_alternative_candidate_airflow_interval_gap_m3_h": None,
        "nearest_alternative_candidate_features": None,
        "nearest_below_alternative_candidate_airflow_interval_gap_m3_h": None,
        "nearest_below_alternative_candidate_features": None,
        "nearest_above_alternative_candidate_airflow_interval_gap_m3_h": None,
        "nearest_above_alternative_candidate_features": None,
        "selected_airflow_overlaps_alternative_candidate_interval": None,
        "alternative_candidates_on_both_sides_of_selected_airflow": None,
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
            "It reports tolerance contacts, strict sign-change segments, and "
            "whether those sampled residuals are non-increasing within the "
            "configured pressure tolerance. Candidate features are ordered "
            "using the solver's actual selection priority, while selected-"
            "candidate provenance is added only for solved results. For solved "
            "cases with additional candidates, airflow separation is measured "
            "only to each alternative discrete point or sign-change interval, "
            "and each alternative is classified as below, overlapping, or above "
            "the selected airflow. No alternate continuous root location is "
            "inferred. Candidate "
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
    alternative_below_count = None
    alternative_overlap_count = None
    alternative_above_count = None
    nearest_alternative_gap = None
    nearest_alternative_features = None
    nearest_below_gap = None
    nearest_below_features = None
    nearest_above_gap = None
    nearest_above_features = None
    selected_overlaps_alternative_interval = None
    alternatives_on_both_sides = None

    if selected_copy is not None:
        alternative_features = []
        airflow = float(selected_airflow_m3_h)
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

            if airflow < low_airflow:
                gap = low_airflow - airflow
                relative_position = "above_selected_airflow"
            elif airflow > high_airflow:
                gap = airflow - high_airflow
                relative_position = "below_selected_airflow"
            else:
                gap = 0.0
                relative_position = "overlaps_selected_airflow"

            alternative.update(
                {
                    "airflow_interval_low_m3_h": round(low_airflow, 9),
                    "airflow_interval_high_m3_h": round(high_airflow, 9),
                    "relative_to_selected_airflow": relative_position,
                    "selected_airflow_to_feature_interval_gap_m3_h": round(
                        gap,
                        9,
                    ),
                }
            )
            alternative_features.append(alternative)

        below_features = [
            feature
            for feature in alternative_features
            if feature["relative_to_selected_airflow"] == "below_selected_airflow"
        ]
        overlap_features = [
            feature
            for feature in alternative_features
            if feature["relative_to_selected_airflow"] == "overlaps_selected_airflow"
        ]
        above_features = [
            feature
            for feature in alternative_features
            if feature["relative_to_selected_airflow"] == "above_selected_airflow"
        ]
        alternative_below_count = len(below_features)
        alternative_overlap_count = len(overlap_features)
        alternative_above_count = len(above_features)
        selected_overlaps_alternative_interval = bool(overlap_features)
        alternatives_on_both_sides = bool(below_features and above_features)

        def _nearest_features(features: list[dict]) -> tuple[float | None, list[dict]]:
            if not features:
                return None, []
            nearest_gap = min(
                float(
                    feature[
                        "selected_airflow_to_feature_interval_gap_m3_h"
                    ]
                )
                for feature in features
            )
            nearest = [
                dict(feature)
                for feature in features
                if math.isclose(
                    float(
                        feature[
                            "selected_airflow_to_feature_interval_gap_m3_h"
                        ]
                    ),
                    nearest_gap,
                    rel_tol=1e-12,
                    abs_tol=1e-9,
                )
            ]
            return round(nearest_gap, 9), nearest

        nearest_alternative_gap, nearest_alternative_features = (
            _nearest_features(alternative_features)
        )
        nearest_below_gap, nearest_below_features = _nearest_features(
            below_features
        )
        nearest_above_gap, nearest_above_features = _nearest_features(
            above_features
        )

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
            "alternative_candidate_below_selected_airflow_count": (
                alternative_below_count
            ),
            "alternative_candidate_overlap_selected_airflow_count": (
                alternative_overlap_count
            ),
            "alternative_candidate_above_selected_airflow_count": (
                alternative_above_count
            ),
            "nearest_alternative_candidate_airflow_interval_gap_m3_h": (
                nearest_alternative_gap
            ),
            "nearest_alternative_candidate_features": (
                nearest_alternative_features
            ),
            "nearest_below_alternative_candidate_airflow_interval_gap_m3_h": (
                nearest_below_gap
            ),
            "nearest_below_alternative_candidate_features": (
                nearest_below_features
            ),
            "nearest_above_alternative_candidate_airflow_interval_gap_m3_h": (
                nearest_above_gap
            ),
            "nearest_above_alternative_candidate_features": (
                nearest_above_features
            ),
            "selected_airflow_overlaps_alternative_candidate_interval": (
                selected_overlaps_alternative_interval
            ),
            "alternative_candidates_on_both_sides_of_selected_airflow": (
                alternatives_on_both_sides
            ),
        }
    )
    return enriched

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
                    if abs(residual) <= tolerance:
                        bracket_width = high - low
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
                                bracket_width / supplied_segment_span,
                                12,
                            ),
                            "iteration": iteration,
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
        "final_bisection_bracket": final_bisection_bracket,
        "scope_note": (
            "The final bisection bracket is the active signed-residual search "
            "interval immediately before a pressure-tolerance midpoint "
            "termination. Its width and half-width are numerical search-"
            "geometry evidence only; they are not physical airflow "
            "uncertainty, interpolation error, continuous worst-case bounds, "
            "or equipment-acceptance limits. Supplied-point tolerance-contact "
            "solutions do not fabricate a bisection bracket."
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
