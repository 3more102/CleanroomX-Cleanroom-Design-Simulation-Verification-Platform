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
            "The log-linear fit uses nominal concentration values only. It is a "
            "diagnostic screening metric, does not propagate sample uncertainty, and "
            "is not used as the acceptance result."
        ),
    }


def _target_relation(sample: RecoverySample, target: float) -> str:
    if sample.concentration_upper_per_m3 <= target:
        return "confirmed_at_or_below"
    if sample.concentration_lower_per_m3 > target:
        return "confirmed_above"
    return "overlaps_target"


def _first_index(items: tuple[RecoverySample, ...], predicate) -> int | None:
    return next((index for index, sample in enumerate(items) if predicate(sample)), None)


def analyze_recovery_test(spec: RecoveryTestSpec) -> dict:
    first_reached_index = _first_index(
        spec.samples,
        lambda sample: sample.concentration_per_m3 <= spec.target_concentration_per_m3,
    )
    first_possible_index = _first_index(
        spec.samples,
        lambda sample: sample.concentration_lower_per_m3
        <= spec.target_concentration_per_m3,
    )
    first_confirmed_index = _first_index(
        spec.samples,
        lambda sample: sample.concentration_upper_per_m3
        <= spec.target_concentration_per_m3,
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

    uncertainty_present = any(
        sample.concentration_uncertainty_abs > 0 for sample in spec.samples
    )
    possible_time = (
        spec.samples[first_possible_index].time_minutes
        if first_possible_index is not None
        else None
    )
    confirmed_time = (
        spec.samples[first_confirmed_index].time_minutes
        if first_confirmed_index is not None
        else None
    )

    if spec.max_recovery_time_minutes is None:
        criterion_status = "not_checked"
        criterion_message = "No maximum recovery-time requirement configured."
    else:
        max_time = spec.max_recovery_time_minutes
        confirmed_by_deadline = any(
            sample.time_minutes <= max_time
            and _target_relation(sample, spec.target_concentration_per_m3)
            == "confirmed_at_or_below"
            for sample in spec.samples
        )
        possible_by_deadline = any(
            sample.time_minutes <= max_time
            and _target_relation(sample, spec.target_concentration_per_m3)
            != "confirmed_above"
            for sample in spec.samples
        )
        measurement_reaches_deadline = spec.samples[-1].time_minutes >= max_time

        if confirmed_by_deadline:
            criterion_status = "pass"
            criterion_message = (
                "A measured concentration uncertainty interval is fully at or below "
                "the configured target within the maximum recovery time."
            )
        elif not measurement_reaches_deadline:
            criterion_status = "incomplete"
            criterion_message = (
                "The target is not confirmed and measurements ended before the "
                "configured maximum recovery time."
            )
        elif possible_by_deadline:
            criterion_status = "indeterminate"
            criterion_message = (
                "At least one measured concentration interval at or before the "
                "maximum recovery time overlaps the target, so the configured "
                "criterion cannot be resolved conservatively."
            )
        else:
            criterion_status = "fail"
            criterion_message = (
                "No measured concentration at or before the configured maximum "
                "recovery time is even possibly at or below the target within its "
                "supplied uncertainty interval."
            )

    sample_rows = []
    for sample in spec.samples:
        relation = _target_relation(sample, spec.target_concentration_per_m3)
        sample_rows.append(
            {
                "time_minutes": sample.time_minutes,
                "concentration_per_m3": sample.concentration_per_m3,
                "concentration_uncertainty_abs": sample.concentration_uncertainty_abs,
                "concentration_interval_per_m3": {
                    "lower": sample.concentration_lower_per_m3,
                    "upper": sample.concentration_upper_per_m3,
                },
                "at_or_below_target": (
                    sample.concentration_per_m3
                    <= spec.target_concentration_per_m3
                ),
                "target_relation": relation,
            }
        )

    return {
        "test": spec.name,
        "particle_size_um": round(spec.particle_size_um, 6),
        "target_concentration_per_m3": round(
            spec.target_concentration_per_m3, 6
        ),
        "max_recovery_time_minutes": spec.max_recovery_time_minutes,
        "reached_target": reached_target,
        "observed_recovery_time_minutes": observed_recovery_time,
        "recovery_time_window_minutes": {
            "lower_bound": lower_bound,
            "upper_bound": upper_bound,
        },
        "criterion_status": criterion_status,
        "criterion_message": criterion_message,
        "uncertainty_assessment": {
            "uncertainty_present": uncertainty_present,
            "possible_reached_target": first_possible_index is not None,
            "confirmed_reached_target": first_confirmed_index is not None,
            "first_possible_recovery_sample_time_minutes": possible_time,
            "first_confirmed_recovery_sample_time_minutes": confirmed_time,
            "decision_rule": (
                "PASS requires a complete concentration uncertainty interval at or "
                "below the target by the configured maximum time. FAIL requires "
                "measurements through the maximum time with no sample at or before "
                "that time even possibly at/below target. Threshold overlap is "
                "INDETERMINATE once the maximum time has been reached."
            ),
        },
        "initial_concentration_per_m3": spec.samples[0].concentration_per_m3,
        "final_concentration_per_m3": spec.samples[-1].concentration_per_m3,
        "test_duration_minutes": spec.samples[-1].time_minutes,
        "sample_count": len(spec.samples),
        "metadata": {
            "instrument_id": spec.instrument_id,
            "sample_location": spec.sample_location,
            "occupancy_state": spec.occupancy_state,
            "method_reference": spec.method_reference,
        },
        "samples": sample_rows,
        "log_linear_fit": _log_linear_fit(spec),
        "engineering_note": (
            "Acceptance is based only on the explicit target concentration, optional "
            "maximum recovery time, and sample uncertainty supplied by the project. "
            "CleanroomX does not embed ISO class limits, a universal recovery-time "
            "criterion, or a statistical uncertainty budget."
        ),
    }
