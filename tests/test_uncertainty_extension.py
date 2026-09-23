import pytest

from cleanroomx.models import PressureCascadeRequirement, ProjectSpec, RoomSpec
from cleanroomx.project_verification import verify_project
from cleanroomx.recovery_models import RecoverySample, RecoveryTestSpec
from cleanroomx.recovery_test import analyze_recovery_test
from cleanroomx.verification import verify_room


def room(name: str, pressure: float, uncertainty: float = 0.0) -> RoomSpec:
    return RoomSpec(
        name=name,
        length_m=5,
        width_m=4,
        height_m=3,
        supply_airflow_m3_h=1200,
        observed_pressure_pa=pressure,
        observed_pressure_uncertainty_pa=uncertainty,
    )


def test_room_pressure_interval_can_be_indeterminate() -> None:
    report = verify_room(
        RoomSpec(
            "Bay",
            5,
            4,
            3,
            1200,
            min_pressure_pa=10,
            observed_pressure_pa=11,
            observed_pressure_uncertainty_pa=2,
        )
    )
    finding = next(item for item in report.findings if item.code == "PRESSURE")
    assert finding.status == "indeterminate"
    assert finding.interval_low == 9
    assert finding.interval_high == 13
    assert report.passed is False


def test_room_pressure_interval_robust_pass_and_fail() -> None:
    passing = verify_room(
        RoomSpec(
            "Pass",
            5,
            4,
            3,
            1200,
            min_pressure_pa=10,
            observed_pressure_pa=13,
            observed_pressure_uncertainty_pa=2,
        )
    )
    failing = verify_room(
        RoomSpec(
            "Fail",
            5,
            4,
            3,
            1200,
            min_pressure_pa=10,
            observed_pressure_pa=7,
            observed_pressure_uncertainty_pa=2,
        )
    )
    assert next(item for item in passing.findings if item.code == "PRESSURE").status == "pass"
    assert next(item for item in failing.findings if item.code == "PRESSURE").status == "fail"


def test_pressure_cascade_uses_worst_case_difference_interval() -> None:
    project = ProjectSpec(
        "Suite",
        rooms=(room("Process", 20, 1.5), room("Ante", 10, 1.0)),
        pressure_cascade=(PressureCascadeRequirement("Process", "Ante", 9),),
    )
    finding = verify_project(project).pressure_cascade_findings[0]
    assert finding.actual_delta_pa == 10
    assert finding.uncertainty_pa == pytest.approx(2.5)
    assert finding.interval_low_pa == pytest.approx(7.5)
    assert finding.interval_high_pa == pytest.approx(12.5)
    assert finding.status == "indeterminate"


def test_zero_pressure_uncertainty_preserves_nominal_behavior() -> None:
    project = ProjectSpec(
        "Suite",
        rooms=(room("Process", 20), room("Ante", 10)),
        pressure_cascade=(PressureCascadeRequirement("Process", "Ante", 9),),
    )
    finding = verify_project(project).pressure_cascade_findings[0]
    assert finding.status == "pass"
    assert finding.interval_low_pa == 10
    assert finding.interval_high_pa == 10


def test_recovery_sample_uncertainty_can_make_result_indeterminate() -> None:
    spec = RecoveryTestSpec(
        name="Uncertain recovery",
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
    assert result["possible_recovery_time_minutes"] == 4
    assert result["observed_recovery_time_minutes"] == 8
    assert result["criterion_status"] == "indeterminate"
    assert result["samples"][1]["target_relation"] == "indeterminate"


def test_recovery_uncertainty_pass_requires_full_interval_below_target() -> None:
    spec = RecoveryTestSpec(
        name="Robust recovery",
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
    assert result["reached_target"] is True
    assert result["samples"][1]["concentration_interval_per_m3"] == {
        "lower_bound": 85.0,
        "upper_bound": 95.0,
    }


def test_recovery_uncertainty_interval_cannot_cross_zero() -> None:
    with pytest.raises(ValueError, match="cannot extend below zero"):
        RecoverySample(1, 5, 6)
