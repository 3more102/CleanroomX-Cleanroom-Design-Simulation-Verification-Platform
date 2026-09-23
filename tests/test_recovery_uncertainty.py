import math

import pytest

from cleanroomx.recovery_uncertainty import (
    analyze_recovery_uncertainty,
)
from cleanroomx.recovery_uncertainty_io import (
    recovery_uncertainty_from_dict,
)
from cleanroomx.recovery_uncertainty_models import (
    RecoveryUncertaintySpec,
    UncertainRecoverySample,
)
from cleanroomx.recovery_uncertainty_report import (
    markdown_recovery_uncertainty_report,
)


def make_spec(samples, maximum=10):
    return RecoveryUncertaintySpec(
        name="Recovery uncertainty",
        particle_size_um=0.5,
        target_concentration_per_m3=100.0,
        max_recovery_time_minutes=maximum,
        samples=tuple(samples),
    )


def test_pass_requires_complete_interval_at_or_below_target_by_limit():
    result = analyze_recovery_uncertainty(
        make_spec(
            [
                UncertainRecoverySample(0, 1000, 50),
                UncertainRecoverySample(8, 90, 5),
            ]
        )
    )
    assert result["criterion_status"] == "pass"
    assert (
        result["first_definite_recovery_time_minutes"]
        == 8.0
    )


def test_overlap_at_limit_is_indeterminate_not_pass():
    result = analyze_recovery_uncertainty(
        make_spec(
            [
                UncertainRecoverySample(0, 1000, 50),
                UncertainRecoverySample(10, 105, 10),
            ]
        )
    )
    assert (
        result["samples"][-1]["target_status"]
        == "indeterminate"
    )
    assert result["criterion_status"] == "indeterminate"


def test_fail_when_limit_reached_and_samples_are_definitely_above():
    result = analyze_recovery_uncertainty(
        make_spec(
            [
                UncertainRecoverySample(0, 1000, 20),
                UncertainRecoverySample(10, 140, 10),
                UncertainRecoverySample(12, 90, 5),
            ]
        )
    )
    assert result["criterion_status"] == "fail"
    assert (
        result["first_definite_recovery_time_minutes"]
        == 12.0
    )


def test_incomplete_when_measurements_end_before_limit():
    result = analyze_recovery_uncertainty(
        make_spec(
            [
                UncertainRecoverySample(0, 1000, 20),
                UncertainRecoverySample(6, 180, 10),
            ]
        )
    )
    assert result["criterion_status"] == "incomplete"


def test_no_maximum_time_is_not_checked_but_reports_recovery_state():
    result = analyze_recovery_uncertainty(
        make_spec(
            [
                UncertainRecoverySample(0, 1000, 20),
                UncertainRecoverySample(6, 100, 5),
            ],
            maximum=None,
        )
    )
    assert result["criterion_status"] == "not_checked"
    assert result["target_recovery_status"] == "possible"


def test_lower_concentration_bound_is_clamped_at_zero():
    sample = UncertainRecoverySample(1, 5, 10)
    assert sample.lower_concentration_per_m3 == 0.0
    assert sample.upper_concentration_per_m3 == 15.0


@pytest.mark.parametrize(
    "value",
    [math.nan, math.inf, -math.inf],
)
def test_non_finite_concentration_is_rejected(value):
    with pytest.raises(ValueError, match="finite"):
        UncertainRecoverySample(0, value, 1)


def test_sample_times_must_be_strictly_increasing():
    with pytest.raises(
        ValueError,
        match="strictly increasing",
    ):
        make_spec(
            [
                UncertainRecoverySample(1, 200, 10),
                UncertainRecoverySample(1, 100, 10),
            ]
        )


def test_json_loader_accepts_provenance_and_zero_default_uncertainty():
    spec = recovery_uncertainty_from_dict(
        {
            "name": "Loaded",
            "particle_size_um": 0.5,
            "target_concentration_per_m3": 100,
            "samples": [
                {
                    "time_minutes": 0,
                    "concentration_per_m3": 200,
                    "provenance": {
                        "source_type": "measurement",
                        "source_name": "Counter",
                    },
                },
                {
                    "time_minutes": 5,
                    "concentration_per_m3": 90,
                },
            ],
        }
    )
    assert (
        spec.samples[0].concentration_uncertainty_abs
        == 0.0
    )
    assert (
        spec.samples[0].provenance.source_name
        == "Counter"
    )


def test_markdown_report_exposes_indeterminate_state():
    result = analyze_recovery_uncertainty(
        make_spec(
            [
                UncertainRecoverySample(0, 1000, 10),
                UncertainRecoverySample(10, 100, 5),
            ]
        )
    )
    report = markdown_recovery_uncertainty_report(
        result
    )
    assert (
        "Criterion status: **INDETERMINATE**"
        in report
    )
    assert "95.0–105.0" in report
