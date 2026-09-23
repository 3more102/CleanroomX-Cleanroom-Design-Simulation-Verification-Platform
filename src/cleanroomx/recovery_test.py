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


def analyze_recovery_test(spec: RecoveryTestSpec) -> dict:
    first_reached_index = next(
        (
            index
            for index, sample in enumerate(spec.samples)
            if sample.concentration_per_m3 <= spec.target_concentration_per_m3
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

    if spec.max_recovery_time_minutes is None:
        criterion_status = "not_checked"
        criterion_message = "No maximum recovery-time requirement configured."
    elif reached_target:
        passed = observed_recovery_time <= spec.max_recovery_time_minutes
        criterion_status = "pass" if passed else "fail"
        criterion_message = (
            "Observed recovery reached the configured target within the maximum time."
            if passed
            else "Observed recovery reached the target after the configured maximum time."
        )
    elif spec.samples[-1].time_minutes >= spec.max_recovery_time_minutes:
        criterion_status = "fail"
        criterion_message = (
            "The target concentration was still not reached by or after the configured "
            "maximum recovery time."
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
        "observed_recovery_time_minutes": observed_recovery_time,
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
        "metadata": {
            "instrument_id": spec.instrument_id,
            "sample_location": spec.sample_location,
            "occupancy_state": spec.occupancy_state,
            "method_reference": spec.method_reference,
        },
        "samples": [
            {
                "time_minutes": sample.time_minutes,
                "concentration_per_m3": sample.concentration_per_m3,
                "at_or_below_target": (
                    sample.concentration_per_m3
                    <= spec.target_concentration_per_m3
                ),
            }
            for sample in spec.samples
        ],
        "log_linear_fit": _log_linear_fit(spec),
        "engineering_note": (
            "Acceptance is based only on the explicit target concentration and optional "
            "maximum recovery time supplied by the project. CleanroomX does not embed "
            "ISO class limits or a universal recovery-time criterion."
        ),
    }
