import math

import pytest

from cleanroomx.recovery_models import RecoverySample, RecoveryTestSpec
from cleanroomx.recovery_test import analyze_recovery_test


def test_zero_uncertainty_preserves_nominal_recovery_behavior() -> None:
    spec = RecoveryTestSpec(
        name="Nominal recovery",
        particle_size_um=0.5,
        target_concentration_per_m3=100,
        max_recovery_time_minutes=5,
        samples=(
            RecoverySample(0, 1000),
            RecoverySample(4, 90),
        ),
    )
    result = analyze_recovery_test(spec)

    assert result["criterion_status"] == "pass"
    assert result["reached_target"] is True
    assert result["possible_target_reached"] is True
    assert result["observed_recovery_time_minutes"] == 4
    assert result["possible_recovery_time_minutes"] == 4
    assert result["samples"][1]["target_relation"] == "at_or_below"


def test_uncertainty_overlap_before_limit_is_indeterminate() -> None:
    spec = RecoveryTestSpec(
        name="Ambiguous crossing",
        particle_size_um=0.5,
        target_concentration_per_m3=100,
        max_recovery_time_minutes=5,
        samples=(
            RecoverySample(0, 1000, 20),
            RecoverySample(4, 105, 10),
            RecoverySample(8, 80, 5),
        ),
    )
    result = analyze_recovery_test(spec)

    assert result["criterion_status"] == "indeterminate"
    assert result["possible_recovery_time_minutes"] == 4
    assert result["observed_recovery_time_minutes"] == 8
    assert result["recovery_time_window_minutes"] == {
        "lower_bound": 0.0,
        "upper_bound": 8.0,
    }


def test_pass_requires_complete_interval_below_target() -> None:
    spec = RecoveryTestSpec(
        name="Robust pass",
        particle_size_um=0.5,
        target_concentration_per_m3=100,
        max_recovery_time_minutes=5,
        samples=(
            RecoverySample(0, 1000, 20),
            RecoverySample(4, 90, 5),
        ),
    )
    result = analyze_recovery_test(spec)

    assert result["criterion_status"] == "pass"
    assert result["samples"][1]["concentration_interval_per_m3"] == {
        "lower_bound": 85.0,
        "upper_bound": 95.0,
    }


def test_possible_crossing_only_after_limit_fails() -> None:
    spec = RecoveryTestSpec(
        name="Late possible crossing",
        particle_size_um=0.5,
        target_concentration_per_m3=100,
        max_recovery_time_minutes=5,
        samples=(
            RecoverySample(0, 1000, 20),
            RecoverySample(5, 150, 10),
            RecoverySample(8, 105, 10),
        ),
    )
    result = analyze_recovery_test(spec)

    assert result["criterion_status"] == "fail"
    assert result["possible_recovery_time_minutes"] == 8
    assert result["reached_target"] is False


def test_ambiguous_only_result_reports_indeterminate_target_state() -> None:
    spec = RecoveryTestSpec(
        name="Ambiguous only",
        particle_size_um=0.5,
        target_concentration_per_m3=100,
        max_recovery_time_minutes=10,
        samples=(
            RecoverySample(0, 1000, 20),
            RecoverySample(6, 105, 10),
        ),
    )
    result = analyze_recovery_test(spec)

    assert result["target_state"] == "indeterminate"
    assert result["possible_target_reached"] is True
    assert result["reached_target"] is False
    assert result["criterion_status"] == "indeterminate"


def test_log_linear_fit_still_uses_nominal_concentrations() -> None:
    effective_ach = 30.0
    rate_per_min = effective_ach / 60.0
    samples = tuple(
        RecoverySample(
            time,
            1_000_000 * math.exp(-rate_per_min * time),
            100.0,
        )
        for time in (0, 2, 4, 6)
    )
    spec = RecoveryTestSpec(
        name="Ideal decay with uncertainty",
        particle_size_um=0.5,
        target_concentration_per_m3=50_000,
        samples=samples,
    )

    fit = analyze_recovery_test(spec)["log_linear_fit"]

    assert fit["estimated_effective_ach_1_h"] == pytest.approx(30.0, abs=0.0001)
    assert fit["r_squared"] == pytest.approx(1.0)


@pytest.mark.parametrize(
    "sample",
    [
        lambda: RecoverySample(0, 5, 6),
        lambda: RecoverySample(float("nan"), 100, 0),
        lambda: RecoverySample(0, float("inf"), 0),
        lambda: RecoverySample(0, 100, float("nan")),
    ],
)
def test_invalid_recovery_uncertainty_inputs_are_rejected(sample) -> None:
    with pytest.raises(ValueError):
        sample()
