from __future__ import annotations

import math

from .recovery_models import RecoveryTestSpec


def _log_linear_fit(spec: RecoveryTestSpec) -> dict:
    points = [
        (sample.time_minutes, math.log(sample.concentration_per_m3))
        for sample in spec.samples
        if sample.concentration_per_m3 > 0
    ]
    if len(points) < 2:
        return {
            "available": False,
            "reason": "At least two positive concentration samples are required.",
        }

    n = len(points)
    mean_t = sum(t for t, _ in points) / n
    mean_y = sum(y for _, y in points) / n
    ss_t = sum((t - mean_t) ** 2 for t, _ in points)
    if ss_t == 0:
        return {
            "available": False,
            "reason": "Positive concentration samples must span more than one time.",
        }

    slope = sum((t - mean_t) * (y - mean_y) for t, y in points) / ss_t
    intercept = mean_y - slope * mean_t
    fitted = [intercept + slope * t for t, _ in points]
    ss_res = sum((y - yhat) ** 2 for (_, y), yhat in zip(points, fitted))
    ss_tot = sum((y - mean_y) ** 2 for _, y in points)
    r_squared = None if ss_tot == 0 else 1.0 - (ss_res / ss_tot)

    decay_rate = -slope if slope < 0 else None
    effective_ach = decay_rate * 60.0 if decay_rate is not None else None
    crossing = None
    if slope < 0:
        candidate = (math.log(spec.target_concentration_per_m3) - intercept) / slope
        if candidate >= 0:
            crossing = candidate

    return {
        "available": True,
        "slope_ln_concentration_per_min": round(slope, 8),
        "intercept_ln_concentration": round(intercept, 8),
        "r_squared": round(r_squared, 6) if r_squared is not None else None,
        "estimated_decay_rate_per_min": (
            round(decay_rate, 8) if decay_rate is not None else None
        ),
        "estimated_effective_ach_1_h": (
            round(effective_ach, 4) if effective_ach is not None else None
        ),
        "fitted_target_crossing_time_minutes": (
            round(crossing, 4) if crossing is not None else None
        ),
        "screening_note": (
            "The log-linear fit is a diagnostic screening metric only. It is not used "
            "as the acceptance result and does not replace the configured test method."
        ),
    }


def _sample_target_relation(
    concentration: float,
    uncertainty: float,
    target: float,
) -> tuple[str, float, float]:
    lower = concentration - uncertainty
    upper = concentration + uncertainty
    if upper <= target:
        return "at_or_below", lower, upper
    if lower > target:
        return "above", lower, upper
    return "indeterminate", lower, upper


def analyze_recovery_test(spec: RecoveryTestSpec) -> dict:
    sample_rows: list[dict] = []
    relations: list[str] = []
    for sample in spec.samples:
        relation, lower, upper = _sample_target_relation(
            sample.concentration_per_m3,
            sample.concentration_uncertainty_per_m3,
            spec.target_concentration_per_m3,
        )
        relations.append(relation)
        sample_rows.append(
            {
                "time_minutes": sample.time_minutes,
                "concentration_per_m3": sample.concentration_per_m3,
                "concentration_uncertainty_per_m3": (
                    sample.concentration_uncertainty_per_m3
                ),
                "concentration_interval_per_m3": {
                    "lower_bound": lower,
                    "upper_bound": upper,
                },
                "target_relation": relation,
                "at_or_below_target": relation == "at_or_below",
            }
        )

    first_definite_index = next(
        (index for index, relation in enumerate(relations) if relation == "at_or_below"),
        None,
    )
    first_possible_index = next(
        (index for index, relation in enumerate(relations) if relation != "above"),
        None,
    )

    reached_target = first_definite_index is not None
    possible_target_reached = first_possible_index is not None
    observed_recovery_time = (
        spec.samples[first_definite_index].time_minutes
        if first_definite_index is not None
        else None
    )
    possible_recovery_time = (
        spec.samples[first_possible_index].time_minutes
        if first_possible_index is not None
        else None
    )

    if first_definite_index is not None:
        if first_possible_index is None or first_possible_index == 0:
            lower_bound = 0.0
        else:
            lower_bound = spec.samples[first_possible_index - 1].time_minutes
        upper_bound = spec.samples[first_definite_index].time_minutes
    elif first_possible_index is not None:
        lower_bound = (
            0.0
            if first_possible_index == 0
            else spec.samples[first_possible_index - 1].time_minutes
        )
        upper_bound = None
    else:
        lower_bound = spec.samples[-1].time_minutes
        upper_bound = None

    if reached_target:
        target_state = "reached"
    elif possible_target_reached:
        target_state = "indeterminate"
    else:
        target_state = "not_reached"

    if spec.max_recovery_time_minutes is None:
        criterion_status = "not_checked"
        criterion_message = "No maximum recovery-time requirement configured."
    elif first_definite_index is not None:
        definite_time = spec.samples[first_definite_index].time_minutes
        possible_time = (
            spec.samples[first_possible_index].time_minutes
            if first_possible_index is not None
            else definite_time
        )
        if definite_time <= spec.max_recovery_time_minutes:
            criterion_status = "pass"
            criterion_message = (
                "A measured sample is definitely at or below the configured target, "
                "including concentration uncertainty, within the maximum time."
            )
        elif possible_time <= spec.max_recovery_time_minutes:
            criterion_status = "indeterminate"
            criterion_message = (
                "A concentration uncertainty interval overlaps the target within the "
                "maximum time, but definite recovery is only demonstrated later."
            )
        else:
            criterion_status = "fail"
            criterion_message = (
                "No measured sample is at or possibly below the configured target within "
                "the maximum recovery time."
            )
    elif first_possible_index is not None:
        possible_time = spec.samples[first_possible_index].time_minutes
        if possible_time <= spec.max_recovery_time_minutes:
            criterion_status = "indeterminate"
            criterion_message = (
                "A measured concentration uncertainty interval overlaps the target within "
                "the maximum time, so recovery cannot be robustly passed or failed."
            )
        elif spec.samples[-1].time_minutes >= spec.max_recovery_time_minutes:
            criterion_status = "fail"
            criterion_message = (
                "No measured sample is at or possibly below the target within the "
                "configured maximum recovery time."
            )
        else:
            criterion_status = "incomplete"
            criterion_message = (
                "The target is not definitely reached and measurements ended before the "
                "configured maximum recovery time."
            )
    elif spec.samples[-1].time_minutes >= spec.max_recovery_time_minutes:
        criterion_status = "fail"
        criterion_message = (
            "The complete concentration intervals remain above the target by or after "
            "the configured maximum recovery time."
        )
    else:
        criterion_status = "incomplete"
        criterion_message = (
            "The target concentration was not reached, but measurements ended before "
            "the configured maximum recovery time."
        )

    return {
        "test": spec.name,
        "particle_size_um": round(spec.particle_size_um, 6),
        "target_concentration_per_m3": round(
            spec.target_concentration_per_m3, 6
        ),
        "max_recovery_time_minutes": spec.max_recovery_time_minutes,
        "reached_target": reached_target,
        "possible_target_reached": possible_target_reached,
        "target_state": target_state,
        "observed_recovery_time_minutes": observed_recovery_time,
        "possible_recovery_time_minutes": possible_recovery_time,
        "recovery_time_window_minutes": {
            "lower_bound": lower_bound,
            "upper_bound": upper_bound,
        },
        "criterion_status": criterion_status,
        "criterion_message": criterion_message,
        "initial_concentration_per_m3": spec.samples[0].concentration_per_m3,
        "final_concentration_per_m3": spec.samples[-1].concentration_per_m3,
        "test_duration_minutes": spec.samples[-1].time_minutes,
        "sample_count": len(spec.samples),
        "uncertainty_applied": any(
            sample.concentration_uncertainty_per_m3 > 0
            for sample in spec.samples
        ),
        "metadata": {
            "instrument_id": spec.instrument_id,
            "sample_location": spec.sample_location,
            "occupancy_state": spec.occupancy_state,
            "method_reference": spec.method_reference,
        },
        "samples": sample_rows,
        "log_linear_fit": _log_linear_fit(spec),
        "engineering_note": (
            "Acceptance is based only on the explicit target concentration and optional "
            "maximum recovery time supplied by the project. When sample uncertainty is "
            "provided, CleanroomX uses conservative concentration intervals and reports "
            "indeterminate rather than forcing a pass/fail when an interval overlaps the "
            "target. The log-linear diagnostic still uses nominal concentrations only."
        ),
    }
