from cleanroomx.models import ParticleRequirement, RoomSpec
from cleanroomx.verification import verify_room


def test_room_passes_configured_requirements():
    room = RoomSpec(
        "R1",
        6,
        4,
        3,
        1800,
        min_ach=20,
        min_pressure_pa=10,
        observed_pressure_pa=14,
        particle_requirements=(ParticleRequirement(0.5, 400000, 120000),),
    )
    report = verify_room(room)
    assert report.passed
    assert {f.status for f in report.findings} == {"pass"}


def test_room_fails_when_any_requirement_fails():
    room = RoomSpec(
        "R2",
        6,
        4,
        3,
        720,
        min_ach=20,
        min_pressure_pa=10,
        observed_pressure_pa=8,
        particle_requirements=(ParticleRequirement(0.5, 100000, 120000),),
    )
    report = verify_room(room)
    assert not report.passed
    assert sum(f.status == "fail" for f in report.findings) == 3


def test_pressure_overlap_is_indeterminate():
    room = RoomSpec(
        "R3",
        6,
        4,
        3,
        1800,
        min_pressure_pa=10.0,
        observed_pressure_pa=10.2,
        observed_pressure_uncertainty_pa=0.5,
    )
    report = verify_room(room)
    pressure = next(item for item in report.findings if item.code == "PRESSURE")

    assert pressure.status == "indeterminate"
    assert pressure.interval_low == 9.7
    assert pressure.interval_high == 10.7
    assert report.indeterminate
    assert not report.failed
    assert not report.passed


def test_pressure_interval_can_robustly_pass():
    room = RoomSpec(
        "R4",
        6,
        4,
        3,
        1800,
        min_pressure_pa=10.0,
        observed_pressure_pa=11.0,
        observed_pressure_uncertainty_pa=0.5,
    )
    pressure = next(
        item for item in verify_room(room).findings if item.code == "PRESSURE"
    )
    assert pressure.status == "pass"
    assert pressure.interval_low == 10.5


def test_pressure_uncertainty_must_be_finite():
    import pytest

    with pytest.raises(ValueError, match="finite"):
        RoomSpec(
            "Bad",
            6,
            4,
            3,
            1800,
            observed_pressure_pa=10.0,
            observed_pressure_uncertainty_pa=float("nan"),
        )
