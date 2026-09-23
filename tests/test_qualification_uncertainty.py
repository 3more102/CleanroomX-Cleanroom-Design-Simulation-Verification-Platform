import pytest

from cleanroomx.qualification import analyze_qualification_uncertainty
from cleanroomx.qualification_io import qualification_uncertainty_from_dict
from cleanroomx.qualification_models import (
    MeasurementCheck,
    PressureCascadeCheck,
    QualificationRequirement,
    QualificationUncertaintySpec,
)
from cleanroomx.uncertainty_models import Provenance, UncertainValue


def uv(value: float, unit: str, uncertainty: float = 0.0, source: bool = True) -> UncertainValue:
    provenance = (
        Provenance("measurement", "Qualification record", reference="Q-001")
        if source
        else None
    )
    return UncertainValue(value, unit, uncertainty, provenance)


def test_minimum_requirement_passes_only_when_full_interval_meets_limit() -> None:
    spec = QualificationUncertaintySpec(
        "Pressure",
        measurements=(
            MeasurementCheck(
                "Room differential pressure",
                uv(14, "Pa", 1),
                QualificationRequirement("minimum", 10, "Pa", "URS-P-01"),
            ),
        ),
    )

    result = analyze_qualification_uncertainty(spec)
    check = result["measurements"][0]

    assert check["interval"] == {"lower": 13.0, "upper": 15.0}
    assert check["status"] == "pass"
    assert result["overall_status"] == "pass"


def test_minimum_overlap_is_indeterminate() -> None:
    spec = QualificationUncertaintySpec(
        "Pressure",
        measurements=(
            MeasurementCheck(
                "Room differential pressure",
                uv(11, "Pa", 2),
                QualificationRequirement("minimum", 10, "Pa"),
            ),
        ),
    )

    result = analyze_qualification_uncertainty(spec)

    assert result["measurements"][0]["status"] == "indeterminate"
    assert result["overall_status"] == "indeterminate"


def test_maximum_requirement_passes_only_when_full_interval_is_below_limit() -> None:
    spec = QualificationUncertaintySpec(
        "Particle check",
        measurements=(
            MeasurementCheck(
                "0.5 um particle concentration",
                uv(120000, "particles/m3", 10000),
                QualificationRequirement("maximum", 400000, "particles/m3"),
            ),
        ),
    )

    assert analyze_qualification_uncertainty(spec)["overall_status"] == "pass"


def test_maximum_requirement_fails_when_full_interval_exceeds_limit() -> None:
    spec = QualificationUncertaintySpec(
        "Particle check",
        measurements=(
            MeasurementCheck(
                "0.5 um particle concentration",
                uv(450000, "particles/m3", 20000),
                QualificationRequirement("maximum", 400000, "particles/m3"),
            ),
        ),
    )

    assert analyze_qualification_uncertainty(spec)["overall_status"] == "fail"


def test_pressure_cascade_uses_worst_case_interval() -> None:
    spec = QualificationUncertaintySpec(
        "Cascade",
        pressure_cascades=(
            PressureCascadeCheck(
                "Process to preparation",
                higher_pressure=uv(30, "Pa", 0.5),
                lower_pressure=uv(16, "Pa", 0.5),
                min_delta_pa=10,
                requirement_reference="URS-CASCADE-01",
            ),
        ),
    )

    check = analyze_qualification_uncertainty(spec)["pressure_cascades"][0]

    assert check["nominal_delta_pa"] == 14
    assert check["interval_pa"] == {"lower": 13.0, "upper": 15.0}
    assert check["status"] == "pass"


def test_pressure_cascade_overlap_is_indeterminate() -> None:
    spec = QualificationUncertaintySpec(
        "Cascade",
        pressure_cascades=(
            PressureCascadeCheck(
                "High to low",
                higher_pressure=uv(20, "Pa", 2),
                lower_pressure=uv(10, "Pa", 1),
                min_delta_pa=9,
            ),
        ),
    )

    result = analyze_qualification_uncertainty(spec)
    check = result["pressure_cascades"][0]

    assert check["interval_pa"] == {"lower": 7.0, "upper": 13.0}
    assert check["status"] == "indeterminate"
    assert result["overall_status"] == "indeterminate"


def test_fail_takes_precedence_over_indeterminate() -> None:
    spec = QualificationUncertaintySpec(
        "Mixed",
        measurements=(
            MeasurementCheck(
                "Ambiguous pressure",
                uv(11, "Pa", 2),
                QualificationRequirement("minimum", 10, "Pa"),
            ),
            MeasurementCheck(
                "High particles",
                uv(500000, "particles/m3", 10000),
                QualificationRequirement("maximum", 400000, "particles/m3"),
            ),
        ),
    )

    assert analyze_qualification_uncertainty(spec)["overall_status"] == "fail"


def test_missing_provenance_is_reported_without_changing_status() -> None:
    spec = QualificationUncertaintySpec(
        "Traceability",
        measurements=(
            MeasurementCheck(
                "Pressure",
                uv(14, "Pa", 1, source=False),
                QualificationRequirement("minimum", 10, "Pa"),
            ),
        ),
    )

    result = analyze_qualification_uncertainty(spec)

    assert result["overall_status"] == "pass"
    assert result["traceability"]["complete"] is False
    assert result["traceability"]["missing_provenance"] == ["Pressure"]


def test_json_loader_builds_measurements_and_cascades() -> None:
    spec = qualification_uncertainty_from_dict(
        {
            "name": "Suite qualification",
            "measurements": [
                {
                    "name": "Particle concentration",
                    "observed": {
                        "value": 120000,
                        "unit": "particles/m3",
                        "uncertainty_abs": 10000,
                        "provenance": {
                            "source_type": "measurement",
                            "source_name": "Particle counter run",
                            "reference": "PC-17",
                        },
                    },
                    "requirement": {
                        "kind": "maximum",
                        "limit": 400000,
                        "unit": "particles/m3",
                        "reference": "URS-PARTICLE-01",
                    },
                }
            ],
            "pressure_cascades": [
                {
                    "name": "Process to ante",
                    "higher_pressure": {
                        "value": 30,
                        "unit": "Pa",
                        "uncertainty_abs": 0.5,
                    },
                    "lower_pressure": {
                        "value": 8,
                        "unit": "Pa",
                        "uncertainty_abs": 0.5,
                    },
                    "min_delta_pa": 10,
                    "requirement_reference": "URS-CASCADE-01",
                }
            ],
        }
    )

    assert len(spec.measurements) == 1
    assert len(spec.pressure_cascades) == 1
    assert spec.measurements[0].observed.provenance is not None
    assert spec.measurements[0].requirement.reference == "URS-PARTICLE-01"


def test_measurement_unit_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError, match="does not match"):
        MeasurementCheck(
            "Bad units",
            uv(12, "Pa"),
            QualificationRequirement("minimum", 10, "m/s"),
        )


def test_pressure_cascade_requires_pa_inputs() -> None:
    with pytest.raises(ValueError, match="must use 'Pa'"):
        PressureCascadeCheck(
            "Bad cascade",
            higher_pressure=uv(20, "kPa"),
            lower_pressure=uv(10, "Pa"),
            min_delta_pa=5,
        )
