import math

import pytest

from cleanroomx.recovery_models import RecoverySample, RecoveryTestSpec
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


def test_recovery_test_fails_when_target_reached_too_late() -> None:
    spec = RecoveryTestSpec(
        name="Late recovery",
        particle_size_um=0.5,
        target_concentration_per_m3=100,
        max_recovery_time_minutes=5,
        samples=(
            RecoverySample(0, 1000),
            RecoverySample(5, 300),
            RecoverySample(8, 80),
        ),
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
        samples=(
            RecoverySample(0, 1000),
            RecoverySample(5, 400),
            RecoverySample(7, 250),
        ),
    )

    result = analyze_recovery_test(spec)

    assert result["reached_target"] is False
    assert result["criterion_status"] == "fail"
    assert result["recovery_time_window_minutes"] == {
        "lower_bound": 7.0,
        "upper_bound": None,
    }


def test_recovery_test_is_incomplete_if_measurements_stop_early() -> None:
    spec = RecoveryTestSpec(
        name="Short test",
        particle_size_um=0.5,
        target_concentration_per_m3=100,
        max_recovery_time_minutes=10,
        samples=(
            RecoverySample(0, 1000),
            RecoverySample(4, 300),
        ),
    )

    result = analyze_recovery_test(spec)

    assert result["criterion_status"] == "incomplete"


def test_no_maximum_time_is_reported_as_not_checked() -> None:
    spec = RecoveryTestSpec(
        name="Characterization only",
        particle_size_um=0.5,
        target_concentration_per_m3=100,
        samples=(
            RecoverySample(0, 1000),
            RecoverySample(6, 80),
        ),
    )

    assert analyze_recovery_test(spec)["criterion_status"] == "not_checked"


def test_log_linear_fit_recovers_effective_ach_for_ideal_decay() -> None:
    effective_ach = 30.0
    rate_per_min = effective_ach / 60.0
    samples = tuple(
        RecoverySample(
            time,
            1_000_000 * math.exp(-rate_per_min * time),
        )
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


def test_sample_times_must_be_strictly_increasing() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        RecoveryTestSpec(
            name="Bad order",
            particle_size_um=0.5,
            target_concentration_per_m3=100,
            samples=(
                RecoverySample(0, 1000),
                RecoverySample(0, 500),
            ),
        )


def test_uncertain_sample_overlap_is_indeterminate() -> None:
    spec = RecoveryTestSpec(
        name="Threshold overlap",
        particle_size_um=0.5,
        target_concentration_per_m3=100,
        max_recovery_time_minutes=5,
        samples=(
            RecoverySample(0, 1000, 20),
            RecoverySample(4, 120, 30),
        ),
        uncertainty_reference="Calibration basis CAL-001",
    )

    result = analyze_recovery_test(spec)

    assert result["reached_target"] is False
    assert result["criterion_status"] == "indeterminate"
    assert result["recovery_uncertainty"]["first_possible_at_or_below_target_time_minutes"] == 4
    assert result["recovery_uncertainty"]["first_confirmed_at_or_below_target_time_minutes"] is None
    assert result["samples"][1]["target_relation"] == "overlaps_target"


def test_uncertain_sample_can_confirm_pass() -> None:
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
        "lower": 85.0,
        "upper": 95.0,
    }
    assert result["samples"][1]["target_relation"] == "confirmed_at_or_below"


def test_uncertain_recovery_fails_when_no_sample_can_meet_target_by_maximum() -> None:
    spec = RecoveryTestSpec(
        name="Robust fail",
        particle_size_um=0.5,
        target_concentration_per_m3=100,
        max_recovery_time_minutes=5,
        samples=(
            RecoverySample(0, 1000, 20),
            RecoverySample(5, 150, 20),
            RecoverySample(8, 90, 30),
        ),
    )

    result = analyze_recovery_test(spec)

    assert result["criterion_status"] == "fail"
    assert result["samples"][1]["target_relation"] == "confirmed_above"
    assert result["samples"][2]["target_relation"] == "overlaps_target"


def test_zero_uncertainty_preserves_legacy_decision() -> None:
    spec = RecoveryTestSpec(
        name="Legacy compatible",
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
    assert result["recovery_uncertainty"]["uncertainty_present"] is False
    assert result["recovery_uncertainty"]["first_possible_at_or_below_target_time_minutes"] == 4
    assert result["recovery_uncertainty"]["first_confirmed_at_or_below_target_time_minutes"] == 4


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"time_minutes": float("nan"), "concentration_per_m3": 100}, "time_minutes"),
        ({"time_minutes": 0, "concentration_per_m3": float("inf")}, "concentration_per_m3"),
        (
            {
                "time_minutes": 0,
                "concentration_per_m3": 100,
                "concentration_uncertainty_abs": float("inf"),
            },
            "concentration_uncertainty_abs",
        ),
    ],
)
def test_recovery_sample_rejects_non_finite_values(kwargs, message) -> None:
    with pytest.raises(ValueError, match=message):
        RecoverySample(**kwargs)


def test_recovery_report_exposes_uncertainty_state() -> None:
    from cleanroomx.recovery_report import markdown_recovery_report

    spec = RecoveryTestSpec(
        name="Report uncertainty",
        particle_size_um=0.5,
        target_concentration_per_m3=100,
        max_recovery_time_minutes=5,
        samples=(
            RecoverySample(0, 1000, 20),
            RecoverySample(4, 120, 30),
        ),
    )
    text = markdown_recovery_report(analyze_recovery_test(spec))

    assert "INDETERMINATE" in text
    assert "overlaps_target" in text
    assert "90.0 to 150.0" in text
