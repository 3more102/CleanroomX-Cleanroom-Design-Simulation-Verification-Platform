import pytest

from cleanroomx.io import room_from_dict
from cleanroomx.models import ParticleRequirement, PressureCascadeRequirement, ProjectSpec, Provenance, RoomSpec
from cleanroomx.project_verification import verify_project
from cleanroomx.verification import verify_room


def test_legacy_verification_behavior_is_preserved_without_uncertainty():
    room = RoomSpec(
        "Legacy",
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
    assert {finding.status for finding in report.findings} == {"pass"}


def test_pressure_overlap_is_indeterminate_and_not_passing():
    room = RoomSpec(
        "Pressure",
        5,
        4,
        3,
        1200,
        min_pressure_pa=10,
        observed_pressure_pa=11,
        observed_pressure_uncertainty_pa=2,
    )
    report = verify_room(room)
    finding = next(item for item in report.findings if item.code == "PRESSURE")
    assert finding.status == "indeterminate"
    assert finding.interval_low == 9
    assert finding.interval_high == 13
    assert not report.passed


def test_particle_limit_uses_upper_uncertainty_bound_for_pass():
    room = RoomSpec(
        "Particles",
        5,
        4,
        3,
        1200,
        particle_requirements=(ParticleRequirement(0.5, 100000, 80000, 10000),),
    )
    finding = next(item for item in verify_room(room).findings if item.code == "PARTICLES_0.5UM")
    assert finding.status == "pass"
    assert finding.interval_high == 90000


def test_particle_overlap_is_indeterminate():
    room = RoomSpec(
        "Particles",
        5,
        4,
        3,
        1200,
        particle_requirements=(ParticleRequirement(0.5, 100000, 95000, 10000),),
    )
    report = verify_room(room)
    finding = next(item for item in report.findings if item.code == "PARTICLES_0.5UM")
    assert finding.status == "indeterminate"
    assert not report.passed


def test_pressure_cascade_combines_room_uncertainties_conservatively():
    project = ProjectSpec(
        "Suite",
        rooms=(
            RoomSpec("High", 5, 4, 3, 1200, observed_pressure_pa=20, observed_pressure_uncertainty_pa=2),
            RoomSpec("Low", 5, 4, 3, 1200, observed_pressure_pa=10, observed_pressure_uncertainty_pa=1),
        ),
        pressure_cascade=(PressureCascadeRequirement("High", "Low", 9),),
    )
    report = verify_project(project)
    finding = report.pressure_cascade_findings[0]
    assert finding.actual_delta_pa == 10
    assert finding.uncertainty_pa == 3
    assert finding.interval_low_pa == 7
    assert finding.interval_high_pa == 13
    assert finding.status == "indeterminate"
    assert not report.passed


def test_provenance_is_loaded_and_serialized_into_findings():
    room = room_from_dict(
        {
            "name": "Traceable",
            "length_m": 5,
            "width_m": 4,
            "height_m": 3,
            "supply_airflow_m3_h": 1200,
            "supply_airflow_uncertainty_m3_h": 50,
            "min_ach": 15,
            "ach_requirement_reference": "URS-HVAC-007",
            "airflow_provenance": {
                "source": "TAB report",
                "reference": "TAB-2026-014",
                "instrument_id": "AFM-17",
                "calibration_reference": "CAL-2026-88",
                "observed_at": "2026-09-20T10:30:00+03:00",
            },
        }
    )
    report = verify_room(room).to_dict()
    ach = next(item for item in report["findings"] if item["code"] == "ACH")
    assert ach["requirement_reference"] == "URS-HVAC-007"
    assert ach["provenance"]["source"] == "TAB report"
    assert ach["provenance"]["instrument_id"] == "AFM-17"


def test_negative_uncertainty_is_rejected():
    with pytest.raises(ValueError, match="uncertainty"):
        RoomSpec("Bad", 5, 4, 3, 1200, observed_pressure_uncertainty_pa=-0.1)

    with pytest.raises(ValueError, match="uncertainty"):
        ParticleRequirement(0.5, 100000, 90000, -1)


def test_provenance_rejects_blank_source():
    with pytest.raises(ValueError, match="source"):
        Provenance("   ")
