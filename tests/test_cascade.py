import pytest

from cleanroomx.models import PressureCascadeSpec, PressureRequirement, PressureZone
from cleanroomx.verification import verify_pressure_cascade


def test_pressure_cascade_passes_all_configured_deltas():
    cascade = PressureCascadeSpec(
        "Example suite",
        zones=(
            PressureZone("Core", 30),
            PressureZone("Gowning", 18),
            PressureZone("Corridor", 5),
        ),
        requirements=(
            PressureRequirement("Core", "Gowning", 10),
            PressureRequirement("Gowning", "Corridor", 10),
        ),
    )

    report = verify_pressure_cascade(cascade)

    assert report.passed
    assert [finding.actual for finding in report.findings[1:]] == [12, 13]


def test_pressure_cascade_fails_small_differential():
    cascade = PressureCascadeSpec(
        "Example suite",
        zones=(PressureZone("Core", 30), PressureZone("Corridor", 25)),
        requirements=(PressureRequirement("Core", "Corridor", 10),),
    )

    report = verify_pressure_cascade(cascade)

    assert not report.passed
    assert report.findings[-1].actual == 5
    assert report.findings[-1].status == "fail"


def test_pressure_cascade_detects_direction_cycle():
    cascade = PressureCascadeSpec(
        "Invalid topology",
        zones=(PressureZone("A", 20), PressureZone("B", 10)),
        requirements=(
            PressureRequirement("A", "B", 5),
            PressureRequirement("B", "A", 5),
        ),
    )

    report = verify_pressure_cascade(cascade)

    assert not report.passed
    assert report.findings[0].code == "CASCADE_TOPOLOGY"
    assert report.findings[0].status == "fail"
    assert "A -> B -> A" in report.findings[0].message


def test_pressure_cascade_rejects_unknown_zone_reference():
    with pytest.raises(ValueError, match="unknown zone"):
        PressureCascadeSpec(
            "Bad input",
            zones=(PressureZone("A", 20), PressureZone("B", 10)),
            requirements=(PressureRequirement("A", "C", 5),),
        )
