import pytest

from cleanroomx.models import PressureCascadeSpec, PressureRelationship, ZonePressure
from cleanroomx.verification import verify_pressure_cascade


def test_pressure_cascade_passes_all_configured_edges():
    cascade = PressureCascadeSpec(
        "Suite A",
        zones=(ZonePressure("Core", 30), ZonePressure("Gowning", 18), ZonePressure("Corridor", 5)),
        relationships=(
            PressureRelationship("Core", "Gowning", 10),
            PressureRelationship("Gowning", "Corridor", 10),
        ),
    )
    report = verify_pressure_cascade(cascade)
    assert report.passed
    assert [finding.actual for finding in report.findings] == [12, 13]


def test_pressure_cascade_reports_failed_edge():
    cascade = PressureCascadeSpec(
        "Suite B",
        zones=(ZonePressure("A", 20), ZonePressure("B", 15)),
        relationships=(PressureRelationship("A", "B", 10),),
    )
    report = verify_pressure_cascade(cascade)
    assert not report.passed
    assert report.findings[0].actual == 5
    assert report.findings[0].limit == 10


def test_unknown_zone_is_rejected():
    with pytest.raises(ValueError, match="unknown lower_zone"):
        PressureCascadeSpec(
            "Bad",
            zones=(ZonePressure("A", 20), ZonePressure("B", 10)),
            relationships=(PressureRelationship("A", "Missing", 5),),
        )


def test_duplicate_zone_name_is_rejected():
    with pytest.raises(ValueError, match="unique"):
        PressureCascadeSpec(
            "Bad",
            zones=(ZonePressure("A", 20), ZonePressure("A", 10)),
            relationships=(),
        )
