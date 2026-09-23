from __future__ import annotations

import math

from .recovery_models import RecoverySample, RecoveryTestSpec


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
            "The log-linear fit uses nominal concentration values only and is a "
            "diagnostic screening metric. It is not used as the acceptance result and "
            "does not replace the configured test method or uncertainty evaluation."
        ),
    }


def _target_relation(sample: RecoverySample, target: float) -> str:
    if sample.concentration_upper_per_m3 <= target:
        return "confirmed_at_or_below"
    if sample.concentration_lower_per_m3 > target:
        return "confirmed_above"
    return "overlaps_target"


def analyze_recovery_test(spec: RecoveryTestSpec) -> dict:
    target = spec.target_concentration_per_m3
    relations = [_target_relation(sample, target) for sample in spec.samples]

    first_reached_index = next(
        (
            index
            for index, sample in enumerate(spec.samples)
            if sample.concentration_per_m3 <= target
        ),
        None,
    )
    first_possible_index = next(
        (index for index, relation in enumerate(relations) if relation != "confirmed_above"),
        None,
    )
    first_confirmed_index = next(
        (
            index
            for index, relation in enumerate(relations)
            if relation == "confirmed_at_or_below"
        ),
        None,
    )

    reached_target = first_reached_index is not None
    observed_recovery_time = (
        spec.samples[first_reached_index].time_minutes
        if first_reached_index is not None
        else None
    )

    if first_reached_index is None:
        lower_bound = spec.samples[-1].time_minutes
        upper_bound = None
    elif first_reached_index == 0:
        lower_bound = 0.0
        upper_bound = spec.samples[0].time_minutes
    else:
        lower_bound = spec.samples[first_reached_index - 1].time_minutes
        upper_bound = spec.samples[first_reached_index].time_minutes

    first_possible_time = (
        spec.samples[first_possible_index].time_minutes
        if first_possible_index is not None
        else None
    )
    first_confirmed_time = (
        spec.samples[first_confirmed_index].time_minutes
        if first_confirmed_index is not None
        else None
    )

    if spec.max_recovery_time_minutes is None:
        criterion_status = "not_checked"
        criterion_message = "No maximum recovery-time requirement configured."
    else:
        maximum = spec.max_recovery_time_minutes
        confirmed_within_max = any(
            relation == "confirmed_at_or_below" and sample.time_minutes <= maximum
            for sample, relation in zip(spec.samples, relations)
        )
        possible_within_max = any(
            relation != "confirmed_above" and sample.time_minutes <= maximum
            for sample, relation in zip(spec.samples, relations)
        )

        if confirmed_within_max:
            criterion_status = "pass"
            criterion_message = (
                "At least one measured concentration interval is entirely at or below "
                "the configured target within the maximum recovery time."
            )
        elif possible_within_max:
            criterion_status = "indeterminate"
            criterion_message = (
                "At least one sample at or before the maximum recovery time overlaps "
                "the target, but no sample interval is entirely at or below the target "
                "within that time."
            )
        elif spec.samples[-1].time_minutes >= maximum:
            criterion_status = "fail"
            criterion_message = (
                "No measured sample at or before the configured maximum recovery time "
                "could be at or below the target within its supplied concentration "
                "uncertainty interval."
            )
        else:
            criterion_status = "incomplete"
            criterion_message = (
                "No measured sample could be at or below the target, but measurements "
                "ended before the configured maximum recovery time."
            )

    uncertainty_present = any(
        sample.concentration_uncertainty_abs > 0 for sample in spec.samples
    )
    overlap_count = sum(relation == "overlaps_target" for relation in relations)

    return {
        "test": spec.name,
        "particle_size_um": round(spec.particle_size_um, 6),
        "target_concentration_per_m3": round(target, 6),
        "max_recovery_time_minutes": spec.max_recovery_time_minutes,
        "reached_target": reached_target,
        "observed_recovery_time_minutes": observed_recovery_time,
        "recovery_time_window_minutes": {
            "lower_bound": lower_bound,
            "upper_bound": upper_bound,
        },
        "recovery_uncertainty": {
            "method": "deterministic_concentration_interval",
            "uncertainty_present": uncertainty_present,
            "first_possible_at_or_below_target_time_minutes": first_possible_time,
            "first_confirmed_at_or_below_target_time_minutes": first_confirmed_time,
            "possible_target_reached": first_possible_index is not None,
            "confirmed_target_reached": first_confirmed_index is not None,
            "samples_overlapping_target": overlap_count,
            "uncertainty_reference": spec.uncertainty_reference,
        },
        "criterion_status": criterion_status,
        "criterion_message": criterion_message,
        "initial_concentration_per_m3": spec.samples[0].concentration_per_m3,
        "final_concentration_per_m3": spec.samples[-1].concentration_per_m3,
        "test_duration_minutes": spec.samples[-1].time_minutes,
        "sample_count": len(spec.samples),
        "metadata": {
            "instrument_id": spec.instrument_id,
            "sample_location": spec.sample_location,
            "occupancy_state": spec.occupancy_state,
            "method_reference": spec.method_reference,
            "uncertainty_reference": spec.uncertainty_reference,
        },
        "samples": [
            {
                "time_minutes": sample.time_minutes,
                "concentration_per_m3": sample.concentration_per_m3,
                "concentration_uncertainty_abs": sample.concentration_uncertainty_abs,
                "concentration_interval_per_m3": {
                    "lower": sample.concentration_lower_per_m3,
                    "upper": sample.concentration_upper_per_m3,
                },
                "at_or_below_target": sample.concentration_per_m3 <= target,
                "target_relation": relation,
            }
            for sample, relation in zip(spec.samples, relations)
        ],
        "log_linear_fit": _log_linear_fit(spec),
        "engineering_note": (
            "Acceptance uses only the explicit target concentration, optional maximum "
            "recovery time, and user-supplied absolute concentration uncertainty. "
            "Threshold overlap is reported as indeterminate rather than forced to pass "
            "or fail. CleanroomX does not embed ISO class limits, universal recovery-time "
            "criteria, or statistical uncertainty assumptions."
        ),
    }
