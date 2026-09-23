import math

import pytest

from cleanroomx.measurement import (
    MeasurementProvenance,
    MeasurementRequirement,
    MeasurementSpec,
    UncertaintyComponent,
    analyze_measurement,
    combined_standard_uncertainty,
)
from cleanroomx.measurement_io import measurement_from_dict


def test_combined_standard_uncertainty_uses_rss() -> None:
    components = (
        UncertaintyComponent("instrument", 3.0),
        UncertaintyComponent("repeatability", 4.0),
    )
    assert combined_standard_uncertainty(components) == pytest.approx(5.0)


def test_sensitivity_coefficient_scales_component() -> None:
    components = (
        UncertaintyComponent("temperature correction", 2.0, sensitivity_coefficient=0.5),
        UncertaintyComponent("instrument", 1.0),
    )
    assert combined_standard_uncertainty(components) == pytest.approx(math.sqrt(2.0))


def test_upper_limit_pass_requires_full_interval_below_limit() -> None:
    spec = MeasurementSpec(
        measurand="Particle concentration",
        value=80.0,
        unit="particles/m3",
        components=(UncertaintyComponent("counter", 5.0),),
        coverage_factor=2.0,
        requirement=MeasurementRequirement("upper", upper_limit=100.0),
    )
    assert analyze_measurement(spec)["criterion_status"] == "pass"


def test_upper_limit_overlap_is_indeterminate() -> None:
    spec = MeasurementSpec(
        measurand="Particle concentration",
        value=95.0,
        unit="particles/m3",
        components=(UncertaintyComponent("counter", 5.0),),
        coverage_factor=2.0,
        requirement=MeasurementRequirement("upper", upper_limit=100.0),
    )
    result = analyze_measurement(spec)
    assert result["coverage_interval"] == {
        "lower_bound": 85.0,
        "upper_bound": 105.0,
    }
    assert result["criterion_status"] == "indeterminate"


def test_lower_limit_fail_when_full_interval_is_below_limit() -> None:
    spec = MeasurementSpec(
        measurand="Differential pressure",
        value=7.0,
        unit="Pa",
        components=(UncertaintyComponent("manometer", 1.0),),
        coverage_factor=2.0,
        requirement=MeasurementRequirement("lower", lower_limit=10.0),
    )
    assert analyze_measurement(spec)["criterion_status"] == "fail"


def test_range_requirement_passes_when_interval_is_inside_range() -> None:
    spec = MeasurementSpec(
        measurand="Room temperature",
        value=22.0,
        unit="degC",
        components=(UncertaintyComponent("sensor", 0.2),),
        coverage_factor=2.0,
        requirement=MeasurementRequirement(
            "range",
            lower_limit=20.0,
            upper_limit=24.0,
        ),
    )
    assert analyze_measurement(spec)["criterion_status"] == "pass"


def test_no_requirement_is_not_checked() -> None:
    spec = MeasurementSpec(
        measurand="Air velocity",
        value=0.45,
        unit="m/s",
        components=(UncertaintyComponent("anemometer", 0.02),),
    )
    assert analyze_measurement(spec)["criterion_status"] == "not_checked"


def test_provenance_and_component_sources_are_preserved() -> None:
    spec = MeasurementSpec(
        measurand="Differential pressure",
        value=12.0,
        unit="Pa",
        components=(
            UncertaintyComponent(
                "manometer calibration",
                0.4,
                evaluation_type="B",
                source="Calibration certificate CAL-17",
            ),
        ),
        provenance=MeasurementProvenance(
            instrument_id="DP-01",
            calibration_reference="CAL-17",
            procedure_reference="SOP-CR-05",
            sample_location="Process to ante-room",
        ),
    )
    result = analyze_measurement(spec)
    assert result["provenance"]["instrument_id"] == "DP-01"
    assert result["components"][0]["source"] == "Calibration certificate CAL-17"


def test_measurement_from_dict_builds_nested_models() -> None:
    spec = measurement_from_dict(
        {
            "measurand": "Differential pressure",
            "value": 12.0,
            "unit": "Pa",
            "coverage_factor": 2.0,
            "requirement": {
                "kind": "lower",
                "lower_limit": 10.0,
                "reference": "Project URS",
            },
            "provenance": {"instrument_id": "DP-01"},
            "components": [
                {
                    "name": "instrument",
                    "standard_uncertainty": 0.5,
                    "evaluation_type": "B",
                }
            ],
        }
    )
    assert spec.requirement is not None
    assert spec.requirement.lower_limit == 10.0
    assert spec.provenance.instrument_id == "DP-01"


def test_invalid_range_requirement_is_rejected() -> None:
    with pytest.raises(ValueError, match="lower_limit < upper_limit"):
        MeasurementRequirement("range", lower_limit=24.0, upper_limit=20.0)
