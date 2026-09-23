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
