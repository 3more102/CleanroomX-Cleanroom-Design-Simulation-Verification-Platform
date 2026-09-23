import math

import pytest

from cleanroomx.recovery_io import recovery_test_from_dict
from cleanroomx.recovery_models import RecoverySample, RecoveryTestSpec
from cleanroomx.recovery_report import markdown_recovery_report
from cleanroomx.recovery_test import analyze_recovery_test


def test_recovery_test_passes_configured_maximum() -> None:
    spec = RecoveryTestSpec(
        name="Process Bay recovery",
        particle_size_um=0.5,
        target_concentration_per_m3=100_000,
        max_recovery_time_minutes=12,
        samples=(
            RecoverySample(0, 1_000_000),
            RecoverySample(4, 500_000),
            RecoverySample(8, 200_000),
            RecoverySample(10, 90_000),
        ),
    )
    result = analyze_recovery_test(spec)
    assert result["reached_target"] is True
    assert result["observed_recovery_time_minutes"] == 10
    assert result["recovery_time_window_minutes"] == {
        "lower_bound": 8.0,
        "upper_bound": 10.0,
    }
    assert result["criterion_status"] == "pass"
    assert result["uncertainty_assessment"]["uncertainty_present"] is False


def test_recovery_test_fails_when_target_reached_too_late() -> None:
    spec = RecoveryTestSpec(
        name="Late recovery",
        particle_size_um=0.5,
        target_concentration_per_m3=100,
        max_recovery_time_minutes=5,
        samples=(RecoverySample(0, 1000), RecoverySample(5, 300), RecoverySample(8, 80)),
    )
    result = analyze_recovery_test(spec)
    assert result["observed_recovery_time_minutes"] == 8
    assert result["criterion_status"] == "fail"


def test_recovery_test_fails_if_still_above_target_after_maximum() -> None:
    spec = RecoveryTestSpec(
        name="No recovery",
        particle_size_um=0.5,
        target_concentration_per_m3=100,
        max_recovery_time_minutes=5,
        samples=(RecoverySample(0, 1000), RecoverySample(5, 400), RecoverySample(7, 250)),
    )
    result = analyze_recovery_test(spec)
    assert result["reached_target"] is False
    assert result["criterion_status"] == "fail"
    assert result["recovery_time_window_minutes"] == {"lower_bound": 7.0, "upper_bound": None}


def test_recovery_test_is_incomplete_if_measurements_stop_early() -> None:
    spec = RecoveryTestSpec(
        name="Short test",
        particle_size_um=0.5,
        target_concentration_per_m3=100,
        max_recovery_time_minutes=10,
        samples=(RecoverySample(0, 1000), RecoverySample(4, 300)),
    )
    assert analyze_recovery_test(spec)["criterion_status"] == "incomplete"


def test_no_maximum_time_is_reported_as_not_checked() -> None:
    spec = RecoveryTestSpec(
        name="Characterization only",
        particle_size_um=0.5,
        target_concentration_per_m3=100,
        samples=(RecoverySample(0, 1000), RecoverySample(6, 80)),
    )
    assert analyze_recovery_test(spec)["criterion_status"] == "not_checked"


def test_uncertainty_pass_requires_full_interval_below_target_by_deadline() -> None:
    spec = RecoveryTestSpec(
        name="Conservative pass",
        particle_size_um=0.5,
        target_concentration_per_m3=100,
        max_recovery_time_minutes=10,
        samples=(RecoverySample(0, 1000, 50), RecoverySample(6, 150, 20), RecoverySample(9, 80, 10)),
    )
    result = analyze_recovery_test(spec)
    assert result["criterion_status"] == "pass"
    assert result["uncertainty_assessment"]["first_confirmed_recovery_sample_time_minutes"] == 9
    assert result["samples"][-1]["target_relation"] == "confirmed_at_or_below"


def test_uncertainty_overlap_at_deadline_is_indeterminate() -> None:
    spec = RecoveryTestSpec(
        name="Ambiguous recovery",
        particle_size_um=0.5,
        target_concentration_per_m3=100,
        max_recovery_time_minutes=10,
        samples=(RecoverySample(0, 1000, 20), RecoverySample(6, 180, 20), RecoverySample(10, 95, 15)),
    )
    result = analyze_recovery_test(spec)
    assert result["criterion_status"] == "indeterminate"
    assert result["reached_target"] is True
    assert result["uncertainty_assessment"]["possible_reached_target"] is True
    assert result["uncertainty_assessment"]["confirmed_reached_target"] is False
    assert result["samples"][-1]["concentration_interval_per_m3"] == {"lower": 80.0, "upper": 110.0}


def test_uncertainty_fail_when_even_lower_bounds_stay_above_target() -> None:
    spec = RecoveryTestSpec(
        name="Definite fail",
        particle_size_um=0.5,
        target_concentration_per_m3=100,
        max_recovery_time_minutes=5,
        samples=(RecoverySample(0, 1000, 50), RecoverySample(5, 180, 20), RecoverySample(7, 140, 10)),
    )
    result = analyze_recovery_test(spec)
    assert result["criterion_status"] == "fail"
    assert result["uncertainty_assessment"]["possible_reached_target"] is False


def test_uncertain_sample_loader_and_report() -> None:
    spec = recovery_test_from_dict({
        "name": "Loaded uncertainty",
        "particle_size_um": 0.5,
        "target_concentration_per_m3": 100,
        "max_recovery_time_minutes": 5,
        "samples": [
            {"time_minutes": 0, "concentration_per_m3": 1000},
            {"time_minutes": 5, "concentration_per_m3": 95, "concentration_uncertainty_abs": 10},
        ],
    })
    result = analyze_recovery_test(spec)
    report = markdown_recovery_report(result)
    assert spec.samples[1].concentration_uncertainty_abs == 10
    assert result["criterion_status"] == "indeterminate"
    assert "Measurement uncertainty" in report
    assert "overlaps_target" in report


def test_log_linear_fit_recovers_effective_ach_for_ideal_decay() -> None:
    effective_ach = 30.0
    rate_per_min = effective_ach / 60.0
    samples = tuple(
        RecoverySample(time, 1_000_000 * math.exp(-rate_per_min * time))
        for time in (0, 2, 4, 6)
    )
    spec = RecoveryTestSpec(
        name="Ideal decay",
        particle_size_um=0.5,
        target_concentration_per_m3=50_000,
        samples=samples,
    )
    fit = analyze_recovery_test(spec)["log_linear_fit"]
    assert fit["available"] is True
    assert fit["estimated_effective_ach_1_h"] == pytest.approx(30.0, abs=0.0001)
    assert fit["r_squared"] == pytest.approx(1.0)
    assert "nominal concentration values only" in fit["screening_note"]


def test_sample_times_must_be_strictly_increasing() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        RecoveryTestSpec(
            name="Bad order",
            particle_size_um=0.5,
            target_concentration_per_m3=100,
            samples=(RecoverySample(0, 1000), RecoverySample(0, 500)),
        )


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_recovery_inputs_are_rejected(bad: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        RecoverySample(bad, 100)
    with pytest.raises(ValueError, match="finite"):
        RecoverySample(0, bad)
    with pytest.raises(ValueError, match="finite"):
        RecoverySample(0, 100, bad)


def test_negative_uncertainty_is_rejected() -> None:
    with pytest.raises(ValueError, match="concentration_uncertainty_abs"):
        RecoverySample(0, 100, -1)
