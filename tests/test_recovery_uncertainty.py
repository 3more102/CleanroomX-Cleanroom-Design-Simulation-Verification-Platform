import pytest

from cleanroomx.recovery_io import recovery_test_from_dict
from cleanroomx.recovery_models import RecoverySample, RecoveryTestSpec
from cleanroomx.recovery_test import analyze_recovery_test


def test_recovery_uncertainty_marks_nominal_pass_as_indeterminate() -> None:
    spec = RecoveryTestSpec(
        name="Uncertain recovery",
        particle_size_um=0.5,
        target_concentration_per_m3=100,
        max_recovery_time_minutes=10,
        samples=(
            RecoverySample(0, 1000, uncertainty_percent=5),
            RecoverySample(8, 95, uncertainty_abs_per_m3=10),
        ),
    )

    result = analyze_recovery_test(spec)

    assert result["criterion_status"] == "pass"
    assert result["uncertainty_summary"]["coverage"] == "complete"
    assert (
        result["uncertainty_summary"]["nominal_recovery_sample_uncertainty_status"]
        == "indeterminate"
    )
    assert result["samples"][1]["uncertainty"]["lower_bound"] == pytest.approx(85)
    assert result["samples"][1]["uncertainty"]["upper_bound"] == pytest.approx(105)


def test_recovery_uncertainty_finds_first_certain_sample() -> None:
    spec = RecoveryTestSpec(
        name="Certain recovery",
        particle_size_um=0.5,
        target_concentration_per_m3=100,
        samples=(
            RecoverySample(0, 1000, uncertainty_percent=5),
            RecoverySample(6, 95, uncertainty_abs_per_m3=10),
            RecoverySample(8, 80, uncertainty_abs_per_m3=10),
        ),
    )

    summary = analyze_recovery_test(spec)["uncertainty_summary"]

    assert summary["first_certainly_at_or_below_target_time_minutes"] == 8
    assert summary["indeterminate_count"] == 1


def test_recovery_io_preserves_provenance() -> None:
    spec = recovery_test_from_dict(
        {
            "name": "Traceable recovery",
            "particle_size_um": 0.5,
            "target_concentration_per_m3": 100,
            "instrument_id": "PC-01",
            "instrument_serial_number": "SN-123",
            "calibration_certificate_id": "CAL-2026-11",
            "calibration_date": "2026-08-01",
            "calibration_due_date": "2027-08-01",
            "data_source": "qualification-run-17.csv",
            "analyst": "QA Lab",
            "samples": [
                {"time_minutes": 0, "concentration_per_m3": 1000},
                {"time_minutes": 5, "concentration_per_m3": 80},
            ],
        }
    )

    result = analyze_recovery_test(spec)

    assert result["metadata"]["instrument_serial_number"] == "SN-123"
    assert result["metadata"]["calibration_certificate_id"] == "CAL-2026-11"
    assert result["metadata"]["data_source"] == "qualification-run-17.csv"


def test_recovery_sample_rejects_two_uncertainty_modes() -> None:
    with pytest.raises(ValueError, match="either uncertainty_abs_per_m3"):
        RecoverySample(
            1,
            100,
            uncertainty_abs_per_m3=5,
            uncertainty_percent=5,
        )
