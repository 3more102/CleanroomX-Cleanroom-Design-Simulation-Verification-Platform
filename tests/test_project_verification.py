import pytest

from cleanroomx.models import PressureCascadeRequirement, ProjectSpec, RoomSpec
from cleanroomx.project_verification import verify_project


def room(
    name: str,
    pressure: float | None,
    uncertainty: float = 0.0,
) -> RoomSpec:
    return RoomSpec(
        name,
        5,
        4,
        3,
        1200,
        min_ach=20,
        observed_pressure_pa=pressure,
        observed_pressure_uncertainty_pa=uncertainty,
    )


def test_project_pressure_cascade_passes():
    project = ProjectSpec(
        "Suite",
        rooms=(room("Process", 30), room("Prep", 16), room("Ante", 8)),
        pressure_cascade=(
            PressureCascadeRequirement("Process", "Prep", 10),
            PressureCascadeRequirement("Prep", "Ante", 5),
        ),
    )
    report = verify_project(project)
    assert report.passed
    assert [item.status for item in report.pressure_cascade_findings] == ["pass", "pass"]
    assert report.pressure_cascade_findings[0].actual_delta_pa == 14


def test_project_pressure_cascade_fails():
    project = ProjectSpec(
        "Suite",
        rooms=(room("Process", 20), room("Ante", 14)),
        pressure_cascade=(PressureCascadeRequirement("Process", "Ante", 10),),
    )
    report = verify_project(project)
    assert not report.passed
    assert report.pressure_cascade_findings[0].status == "fail"
    assert report.pressure_cascade_findings[0].actual_delta_pa == 6


def test_missing_pressure_is_not_checked():
    project = ProjectSpec(
        "Suite",
        rooms=(room("Process", None), room("Ante", 5)),
        pressure_cascade=(PressureCascadeRequirement("Process", "Ante", 10),),
    )
    report = verify_project(project)
    assert report.passed
    assert report.pressure_cascade_findings[0].status == "not_checked"


def test_project_rejects_unknown_room_reference():
    with pytest.raises(ValueError, match="unknown room"):
        ProjectSpec(
            "Suite",
            rooms=(room("Process", 20),),
            pressure_cascade=(PressureCascadeRequirement("Process", "Missing", 5),),
        )


def test_project_rejects_duplicate_room_names():
    with pytest.raises(ValueError, match="unique"):
        ProjectSpec("Suite", rooms=(room("Process", 20), room("Process", 10)))


def test_project_rejects_pressure_cycle():
    with pytest.raises(ValueError, match="directed cycle"):
        ProjectSpec(
            "Suite",
            rooms=(room("A", 30), room("B", 20), room("C", 10)),
            pressure_cascade=(
                PressureCascadeRequirement("A", "B", 5),
                PressureCascadeRequirement("B", "C", 5),
                PressureCascadeRequirement("C", "A", 5),
            ),
        )


def test_pressure_cascade_overlap_is_indeterminate():
    project = ProjectSpec(
        "Suite",
        rooms=(room("Process", 20.0, 1.0), room("Ante", 10.0, 1.0)),
        pressure_cascade=(PressureCascadeRequirement("Process", "Ante", 10.0),),
    )
    report = verify_project(project)
    finding = report.pressure_cascade_findings[0]

    assert finding.actual_delta_pa == 10.0
    assert finding.uncertainty_pa == 2.0
    assert finding.interval_low_pa == 8.0
    assert finding.interval_high_pa == 12.0
    assert finding.status == "indeterminate"
    assert report.indeterminate
    assert not report.failed
    assert not report.passed


def test_pressure_cascade_uncertainty_can_still_robustly_pass():
    project = ProjectSpec(
        "Suite",
        rooms=(room("Process", 30.0, 1.0), room("Ante", 16.0, 1.0)),
        pressure_cascade=(PressureCascadeRequirement("Process", "Ante", 10.0),),
    )
    finding = verify_project(project).pressure_cascade_findings[0]
    assert finding.interval_low_pa == 12.0
    assert finding.status == "pass"
