from __future__ import annotations

import pytest

from cleanroomx.application import run_analysis
from cleanroomx.models import (
    ParticleRequirement,
    PressureCascadeRequirement,
    ProjectSpec,
    RoomSpec,
)
from cleanroomx.project_verification import verify_project
from cleanroomx.verification import aggregate_verification_status, verify_room


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ((), "not_checked"),
        (("not_checked",), "not_checked"),
        (("pass",), "pass"),
        (("pass", "not_checked"), "pass_with_unchecked"),
        (("not_checked", "pass", "not_checked"), "pass_with_unchecked"),
        (("pass", "fail", "not_checked"), "fail"),
    ],
)
def test_aggregate_verification_status_preserves_unchecked_evidence(
    statuses, expected
):
    assert aggregate_verification_status(statuses) == expected


def test_aggregate_verification_status_rejects_unknown_state():
    with pytest.raises(ValueError, match="unsupported verification status"):
        aggregate_verification_status(("pass", "unknown"))  # type: ignore[arg-type]


def test_room_report_distinguishes_no_failure_from_complete_pass():
    report = verify_room(
        RoomSpec(
            name="Draft room",
            length_m=5,
            width_m=4,
            height_m=3,
            supply_airflow_m3_h=1200,
            min_ach=10,
        )
    )

    assert report.passed is True
    assert report.status == "pass_with_unchecked"
    assert report.complete is False
    payload = report.to_dict()
    assert payload["passed"] is True
    assert payload["status"] == "pass_with_unchecked"
    assert payload["complete"] is False


def test_room_report_all_unconfigured_checks_are_not_checked():
    report = verify_room(
        RoomSpec(
            name="Unconfigured room",
            length_m=5,
            width_m=4,
            height_m=3,
            supply_airflow_m3_h=1200,
        )
    )

    assert report.passed is True
    assert report.status == "not_checked"
    assert report.complete is False


def test_failure_remains_failure_even_when_other_checks_are_unchecked():
    report = verify_room(
        RoomSpec(
            name="Failed room",
            length_m=5,
            width_m=4,
            height_m=3,
            supply_airflow_m3_h=300,
            min_ach=20,
        )
    )

    assert report.passed is False
    assert report.status == "fail"
    assert report.complete is False


def test_fully_checked_room_reports_complete_pass():
    report = verify_room(
        RoomSpec(
            name="Checked room",
            length_m=5,
            width_m=4,
            height_m=3,
            supply_airflow_m3_h=1800,
            min_ach=20,
            min_pressure_pa=10,
            observed_pressure_pa=15,
            particle_requirements=(
                ParticleRequirement(
                    size_um=0.5,
                    max_concentration_per_m3=400000,
                    observed_concentration_per_m3=100000,
                ),
            ),
        )
    )

    assert report.passed is True
    assert report.status == "pass"
    assert report.complete is True


def test_project_report_propagates_unchecked_pressure_cascade():
    project = ProjectSpec(
        name="Incomplete cascade",
        rooms=(
            RoomSpec(
                name="High",
                length_m=5,
                width_m=4,
                height_m=3,
                supply_airflow_m3_h=1800,
                min_ach=20,
                min_pressure_pa=10,
                observed_pressure_pa=None,
                particle_requirements=(
                    ParticleRequirement(0.5, 400000, 100000),
                ),
            ),
            RoomSpec(
                name="Low",
                length_m=5,
                width_m=4,
                height_m=3,
                supply_airflow_m3_h=1800,
                min_ach=20,
                min_pressure_pa=5,
                observed_pressure_pa=8,
                particle_requirements=(
                    ParticleRequirement(0.5, 400000, 100000),
                ),
            ),
        ),
        pressure_cascade=(
            PressureCascadeRequirement("High", "Low", 5),
        ),
    )

    report = verify_project(project)

    assert report.passed is True
    assert report.status == "pass_with_unchecked"
    assert report.complete is False
    assert report.to_dict()["status"] == "pass_with_unchecked"


def test_application_surfaces_aggregate_verification_status():
    run = run_analysis(
        "room_verification",
        {
            "name": "Unconfigured room",
            "length_m": 5,
            "width_m": 4,
            "height_m": 3,
            "supply_airflow_m3_h": 1200,
        },
    )

    assert run.status == "not_checked"
    assert run.result["status"] == "not_checked"
    assert run.result["complete"] is False
    assert run.result["passed"] is True
    assert "Status: **not_checked**" in run.markdown
