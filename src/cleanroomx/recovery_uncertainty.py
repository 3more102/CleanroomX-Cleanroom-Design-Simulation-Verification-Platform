from __future__ import annotations

from dataclasses import asdict

from .recovery_uncertainty_models import (
    RecoveryUncertaintySpec,
    UncertainRecoverySample,
)


def _sample_status(
    sample: UncertainRecoverySample,
    target: float,
) -> str:
    if sample.upper_concentration_per_m3 <= target:
        return "at_or_below_target"
    if sample.lower_concentration_per_m3 > target:
        return "above_target"
    return "indeterminate"


def analyze_recovery_uncertainty(
    spec: RecoveryUncertaintySpec,
) -> dict:
    sample_results = []
    for sample in spec.samples:
        status = _sample_status(
            sample,
            spec.target_concentration_per_m3,
        )
        sample_results.append(
            {
                "time_minutes": sample.time_minutes,
                "concentration_per_m3": (
                    sample.concentration_per_m3
                ),
                "concentration_uncertainty_abs": (
                    sample.concentration_uncertainty_abs
                ),
                "concentration_interval_per_m3": {
                    "lower": (
                        sample.lower_concentration_per_m3
                    ),
                    "upper": (
                        sample.upper_concentration_per_m3
                    ),
                },
                "target_status": status,
                "provenance": (
                    asdict(sample.provenance)
                    if sample.provenance
                    else None
                ),
            }
        )

    definite_indices = [
        index
        for index, item in enumerate(sample_results)
        if item["target_status"] == "at_or_below_target"
    ]
    possible_indices = [
        index
        for index, item in enumerate(sample_results)
        if item["target_status"] != "above_target"
    ]

    first_definite = (
        definite_indices[0] if definite_indices else None
    )
    first_possible = (
        possible_indices[0] if possible_indices else None
    )

    definite_time = (
        spec.samples[first_definite].time_minutes
        if first_definite is not None
        else None
    )
    possible_time = (
        spec.samples[first_possible].time_minutes
        if first_possible is not None
        else None
    )

    if first_definite is not None:
        target_recovery_status = "definite"
    elif first_possible is not None:
        target_recovery_status = "possible"
    else:
        target_recovery_status = "not_observed"

    maximum = spec.max_recovery_time_minutes
    if maximum is None:
        criterion_status = "not_checked"
        criterion_message = (
            "No maximum recovery-time requirement configured."
        )
    else:
        definite_by_limit = any(
            item["time_minutes"] <= maximum
            and item["target_status"] == "at_or_below_target"
            for item in sample_results
        )
        possible_by_limit = any(
            item["time_minutes"] <= maximum
            and item["target_status"] == "indeterminate"
            for item in sample_results
        )
        test_reaches_limit = (
            spec.samples[-1].time_minutes >= maximum
        )

        if definite_by_limit:
            criterion_status = "pass"
            criterion_message = (
                "At least one measured concentration interval "
                "is wholly at or below the configured target at "
                "or before the maximum recovery time."
            )
        elif possible_by_limit:
            criterion_status = "indeterminate"
            criterion_message = (
                "A measured concentration interval overlaps the "
                "configured target at or before the maximum "
                "recovery time, so pass/fail cannot be resolved "
                "from the supplied uncertainty bounds."
            )
        elif test_reaches_limit:
            criterion_status = "fail"
            criterion_message = (
                "No measured concentration interval is at or "
                "below, or overlapping, the configured target at "
                "or before the maximum recovery time."
            )
        else:
            criterion_status = "incomplete"
            criterion_message = (
                "Measurements ended before the configured maximum "
                "recovery time without a definite or "
                "uncertainty-overlap recovery observation."
            )

    missing_provenance = [
        f"sample at {sample.time_minutes} min"
        for sample in spec.samples
        if sample.provenance is None
    ]

    return {
        "analysis": spec.name,
        "method": "conservative_concentration_interval",
        "particle_size_um": spec.particle_size_um,
        "target_concentration_per_m3": (
            spec.target_concentration_per_m3
        ),
        "max_recovery_time_minutes": maximum,
        "target_recovery_status": target_recovery_status,
        "first_possible_recovery_time_minutes": possible_time,
        "first_definite_recovery_time_minutes": definite_time,
        "criterion_status": criterion_status,
        "criterion_message": criterion_message,
        "test_duration_minutes": spec.samples[-1].time_minutes,
        "sample_count": len(spec.samples),
        "metadata": {
            "instrument_id": spec.instrument_id,
            "sample_location": spec.sample_location,
            "occupancy_state": spec.occupancy_state,
            "method_reference": spec.method_reference,
        },
        "samples": sample_results,
        "traceability": {
            "input_count": len(spec.samples),
            "inputs_with_provenance": (
                len(spec.samples) - len(missing_provenance)
            ),
            "complete": not missing_provenance,
            "missing_provenance": missing_provenance,
        },
        "engineering_note": (
            "This workflow applies deterministic worst-case "
            "absolute concentration bounds to measured recovery "
            "samples. It does not infer an exact crossing time "
            "between samples, does not assume a statistical "
            "distribution, and does not embed ISO classification "
            "or universal recovery-time limits. Project "
            "qualification and regulatory decision rules take "
            "precedence."
        ),
    }
