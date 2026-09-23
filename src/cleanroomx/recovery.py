from __future__ import annotations

import math

from .calculations import recovery_time_minutes
from .recovery_models import RecoverySample, RecoveryTestSpec


def _first_target_crossing_minutes(
    samples: tuple[RecoverySample, ...],
    target_concentration_per_m3: float,
) -> float | None:
    first = samples[0]
    if first.concentration_per_m3 <= target_concentration_per_m3:
        return 0.0

    for previous, current in zip(samples, samples[1:]):
        if current.concentration_per_m3 <= target_concentration_per_m3:
            if current.concentration_per_m3 == target_concentration_per_m3:
                return current.time_minutes
            log_previous = math.log(previous.concentration_per_m3)
            log_current = math.log(current.concentration_per_m3)
            log_target = math.log(target_concentration_per_m3)
            fraction = (log_target - log_previous) / (log_current - log_previous)
            return previous.time_minutes + fraction * (
                current.time_minutes - previous.time_minutes
            )
    return None


def _log_linear_fit(samples: tuple[RecoverySample, ...]) -> dict:
    xs = [sample.time_minutes for sample in samples]
    ys = [math.log(sample.concentration_per_m3) for sample in samples]
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    ss_x = sum((x - x_mean) ** 2 for x in xs)
    slope = sum(
        (x - x_mean) * (y - y_mean)
        for x, y in zip(xs, ys)
    ) / ss_x
    intercept = y_mean - slope * x_mean

    fitted = [intercept + slope * x for x in xs]
    ss_res = sum(
        (observed - predicted) ** 2
        for observed, predicted in zip(ys, fitted)
    )
    ss_tot = sum((observed - y_mean) ** 2 for observed in ys)
    r_squared = None if ss_tot == 0 else 1.0 - ss_res / ss_tot

    removal_rate_per_min = -slope
    half_life_minutes = (
        math.log(2.0) / removal_rate_per_min
        if removal_rate_per_min > 0
        else None
    )
    return {
        "fitted_log_slope_per_min": round(slope, 8),
        "fitted_effective_removal_rate_per_min": round(
            removal_rate_per_min, 8
        ),
        "fitted_effective_removal_rate_per_h": round(
            removal_rate_per_min * 60.0, 6
        ),
        "fitted_half_life_minutes": (
            round(half_life_minutes, 4)
            if half_life_minutes is not None
            else None
        ),
        "r_squared_log_concentration": (
            round(r_squared, 6) if r_squared is not None else None
        ),
    }


def analyze_recovery_test(spec: RecoveryTestSpec) -> dict:
    initial = spec.samples[0].concentration_per_m3
    final = spec.samples[-1].concentration_per_m3
    observed_crossing = _first_target_crossing_minutes(
        spec.samples,
        spec.target_concentration_per_m3,
    )

    if spec.max_recovery_time_minutes is None:
        passes = None
    else:
        passes = (
            observed_crossing is not None
            and observed_crossing <= spec.max_recovery_time_minutes
        )

    model_recovery = None
    model_difference = None
    if spec.design_ach is not None:
        model_recovery = recovery_time_minutes(
            initial,
            spec.target_concentration_per_m3,
            spec.design_ach,
            spec.removal_efficiency,
        )
        if observed_crossing is not None:
            model_difference = observed_crossing - model_recovery

    fit = _log_linear_fit(spec.samples)
    reduction_percent = (1.0 - final / initial) * 100.0

    return {
        "name": spec.name,
        "sample_count": len(spec.samples),
        "initial_concentration_per_m3": round(initial, 6),
        "final_concentration_per_m3": round(final, 6),
        "target_concentration_per_m3": round(
            spec.target_concentration_per_m3, 6
        ),
        "observed_recovery_time_minutes": (
            round(observed_crossing, 4)
            if observed_crossing is not None
            else None
        ),
        "target_reached_in_samples": observed_crossing is not None,
        "max_recovery_time_minutes": spec.max_recovery_time_minutes,
        "passes_max_recovery_time": passes,
        "reduction_percent_at_last_sample": round(reduction_percent, 4),
        "fit": fit,
        "screening_model": {
            "design_ach": spec.design_ach,
            "removal_efficiency": spec.removal_efficiency,
            "predicted_recovery_time_minutes": (
                round(model_recovery, 4)
                if model_recovery is not None
                else None
            ),
            "observed_minus_predicted_minutes": (
                round(model_difference, 4)
                if model_difference is not None
                else None
            ),
        },
        "samples": [
            {
                "time_minutes": sample.time_minutes,
                "concentration_per_m3": sample.concentration_per_m3,
            }
            for sample in spec.samples
        ],
        "engineering_note": (
            "The observed crossing is interpolated between measured samples on a log-"
            "concentration scale. The fitted removal rate is a descriptive regression, "
            "not a certification result or a substitute for the applicable recovery-test "
            "procedure, instrumentation requirements, sampling plan, or acceptance criteria."
        ),
    }
