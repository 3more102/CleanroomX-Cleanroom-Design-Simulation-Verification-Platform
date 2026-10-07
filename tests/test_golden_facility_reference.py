from __future__ import annotations

from pathlib import Path

import pytest

from cleanroomx.consistency import analyze_project_consistency
from cleanroomx.consistency_report import markdown_consistency_report
from cleanroomx.hvac_io import load_hvac_project
from cleanroomx.io import load_project
from cleanroomx.project_verification import verify_project


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def test_golden_facility_known_ach_and_pressure_cascade() -> None:
    report = verify_project(load_project(EXAMPLES / "facility_project.json"))

    rooms = {item.room: item for item in report.room_reports}
    assert set(rooms) == {"Process", "Preparation", "Ante"}

    assert rooms["Process"].volume_m3 == pytest.approx(90.0)
    assert rooms["Process"].ach == pytest.approx(30.0)
    assert rooms["Preparation"].volume_m3 == pytest.approx(60.0)
    assert rooms["Preparation"].ach == pytest.approx(20.0)
    assert rooms["Ante"].volume_m3 == pytest.approx(36.0)
    assert rooms["Ante"].ach == pytest.approx(20.0)

    cascades = report.pressure_cascade_findings
    assert [
        (
            item.higher_pressure_room,
            item.lower_pressure_room,
            item.actual_delta_pa,
            item.limit_pa,
            item.status,
        )
        for item in cascades
    ] == [
        ("Process", "Preparation", 14.0, 10.0, "pass"),
        ("Preparation", "Ante", 8.0, 5.0, "pass"),
    ]

    # The example intentionally omits some per-room acceptance criteria.
    # Golden evidence must preserve that incompleteness rather than promote it to PASS.
    assert report.status == "pass_with_unchecked"
    assert report.complete is False
    assert report.verified is False
    assert report.no_failures_detected is True


def test_golden_facility_airflow_consistency_and_report_are_repeatable() -> None:
    verification = load_project(EXAMPLES / "facility_project.json")
    hvac = load_hvac_project(EXAMPLES / "consistency_hvac_demo.json")

    first = analyze_project_consistency(
        verification,
        hvac,
        room_airflow_abs_tolerance_m3_h=0.0,
        require_same_room_set=True,
    )
    second = analyze_project_consistency(
        verification,
        hvac,
        room_airflow_abs_tolerance_m3_h=0.0,
        require_same_room_set=True,
    )

    assert first == second
    assert first["status"] == "pass"
    assert first["shared_room_count"] == 3
    assert first["mismatch_count"] == 0
    assert first["verification_only_rooms"] == []
    assert first["hvac_only_rooms"] == []
    assert all(
        item["status"] == "match" and item["absolute_difference_m3_h"] == pytest.approx(0.0)
        for item in first["room_airflow_checks"]
    )

    markdown = markdown_consistency_report(first)
    assert markdown == markdown_consistency_report(second)
    assert "# CleanroomX Cross-Module Consistency Report" in markdown
    assert "Process" in markdown
    assert "Preparation" in markdown
    assert "Ante" in markdown
