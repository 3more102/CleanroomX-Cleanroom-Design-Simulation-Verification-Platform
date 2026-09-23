import math

import pytest

from cleanroomx.recovery import analyze_recovery_test
from cleanroomx.recovery_io import recovery_test_from_dict
from cleanroomx.recovery_models import RecoverySample, RecoveryTestSpec
from cleanroomx.recovery_report import markdown_recovery_report


def test_recovery_analysis_interpolates_target_crossing() -> None:
    spec = RecoveryTestSpec(
        name="Demo",
        target_concentration_per_m3=100,
        max_recovery_time_minutes=10,
        samples=(
            RecoverySample(0, 1000),
            RecoverySample(5, 200),
            RecoverySample(10, 50),
        ),
    )
    result = analyze_recovery_test(spec)
    assert 7.0 < result["observed_recovery_time_minutes"] < 8.0
    assert result["passes_max_recovery_time"] is True
    assert result["target_reached_in_samples"] is True


def test_recovery_analysis_reports_target_not_reached() -> None:
    spec = RecoveryTestSpec(
        name="Demo",
        target_concentration_per_m3=100,
        max_recovery_time_minutes=6,
        samples=(
            RecoverySample(0, 1000),
            RecoverySample(6, 250),
        ),
    )
    result = analyze_recovery_test(spec)
    assert result["observed_recovery_time_minutes"] is None
    assert result["passes_max_recovery_time"] is False


def test_exponential_samples_fit_expected_removal_rate() -> None:
    samples = tuple(
        RecoverySample(t, 1000 * math.exp(-0.2 * t))
        for t in (0, 2, 4, 6)
    )
    spec = RecoveryTestSpec(
        name="Fit",
        target_concentration_per_m3=100,
        samples=samples,
    )
    result = analyze_recovery_test(spec)
    assert result["fit"]["fitted_effective_removal_rate_per_min"] == pytest.approx(0.2)
    assert result["fit"]["r_squared_log_concentration"] == pytest.approx(1.0)


def test_json_loader_and_model_comparison() -> None:
    spec = recovery_test_from_dict(
        {
            "name": "JSON Demo",
            "target_concentration_per_m3": 100,
            "design_ach": 12,
            "removal_efficiency": 1.0,
            "samples": [
                {"time_minutes": 0, "concentration_per_m3": 1000},
                {"time_minutes": 12, "concentration_per_m3": 90},
            ],
        }
    )
    result = analyze_recovery_test(spec)
    assert result["screening_model"]["predicted_recovery_time_minutes"] == pytest.approx(
        11.5129,
        abs=1e-4,
    )
    assert result["screening_model"]["observed_minus_predicted_minutes"] is not None


def test_validation_rejects_non_increasing_sample_times() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        RecoveryTestSpec(
            name="Bad",
            target_concentration_per_m3=100,
            samples=(
                RecoverySample(0, 1000),
                RecoverySample(0, 500),
            ),
        )


def test_markdown_report_contains_fit_and_samples() -> None:
    result = analyze_recovery_test(
        RecoveryTestSpec(
            name="Report",
            target_concentration_per_m3=100,
            samples=(
                RecoverySample(0, 1000),
                RecoverySample(10, 80),
            ),
        )
    )
    report = markdown_recovery_report(result)
    assert "Log-linear fit" in report
    assert "## Samples" in report
