import pytest

from cleanroomx.hvac_models import AirState
from cleanroomx.psychrometric_uncertainty import (
    analyze_psychrometric_uncertainty,
)
from cleanroomx.psychrometric_uncertainty_io import (
    psychrometric_uncertainty_from_dict,
)
from cleanroomx.psychrometric_uncertainty_models import UncertainAirState
from cleanroomx.psychrometrics import (
    humidity_ratio_kg_kg_da,
    moist_air_enthalpy_kj_kg_da,
)
from cleanroomx.uncertainty_models import Provenance, UncertainValue


def uv(
    value: float,
    unit: str,
    uncertainty: float = 0.0,
    source: bool = True,
) -> UncertainValue:
    provenance = (
        Provenance(
            "measurement",
            "Psychrometric test basis",
            reference="PSY-001",
        )
        if source
        else None
    )
    return UncertainValue(value, unit, uncertainty, provenance)


def base_state(**overrides) -> UncertainAirState:
    data = {
        "name": "Room air state",
        "dry_bulb_c": uv(22.0, "C", 0.5),
        "relative_humidity_percent": uv(45.0, "%", 2.0),
        "pressure_kpa": uv(101.325, "kPa", 0.3),
    }
    data.update(overrides)
    return UncertainAirState(**data)


def test_zero_uncertainty_matches_core_psychrometrics() -> None:
    design = UncertainAirState(
        name="Nominal only",
        dry_bulb_c=uv(25.0, "C"),
        relative_humidity_percent=uv(50.0, "%"),
        pressure_kpa=uv(101.325, "kPa"),
    )
    result = analyze_psychrometric_uncertainty(design)
    state = AirState(25.0, 50.0, 101.325)

    humidity = result["psychrometric_properties"]["humidity_ratio_g_kg_da"]
    enthalpy = result["psychrometric_properties"]["enthalpy_kj_kg_da"]

    assert result["corner_count"] == 1
    assert humidity["nominal"] == pytest.approx(
        humidity_ratio_kg_kg_da(state) * 1000.0,
        rel=1e-6,
    )
    assert humidity["lower"] == humidity["upper"] == humidity["nominal"]
    assert enthalpy["nominal"] == pytest.approx(
        moist_air_enthalpy_kj_kg_da(state),
        rel=1e-6,
    )


def test_uncertainty_box_expands_derived_properties() -> None:
    result = analyze_psychrometric_uncertainty(base_state())
    for item in result["psychrometric_properties"].values():
        assert item["lower"] <= item["nominal"] <= item["upper"]
        assert item["lower"] < item["upper"]


def test_hot_humid_low_pressure_corner_bounds_humidity_ratio() -> None:
    design = base_state()
    result = analyze_psychrometric_uncertainty(design)
    humidity = result["psychrometric_properties"]["humidity_ratio_g_kg_da"]

    upper_state = AirState(
        design.dry_bulb_c.upper,
        design.relative_humidity_percent.upper,
        design.pressure_kpa.lower,
    )
    lower_state = AirState(
        design.dry_bulb_c.lower,
        design.relative_humidity_percent.lower,
        design.pressure_kpa.upper,
    )

    assert humidity["upper"] == pytest.approx(
        humidity_ratio_kg_kg_da(upper_state) * 1000.0,
        rel=1e-6,
    )
    assert humidity["lower"] == pytest.approx(
        humidity_ratio_kg_kg_da(lower_state) * 1000.0,
        rel=1e-6,
    )


def test_uncertainty_bounds_must_stay_inside_supported_state_domain() -> None:
    with pytest.raises(ValueError, match="within -45 to 60"):
        base_state(dry_bulb_c=uv(59.0, "C", 2.0))

    with pytest.raises(ValueError, match="must remain > 0 and <= 100"):
        base_state(relative_humidity_percent=uv(99.0, "%", 2.0))

    with pytest.raises(ValueError, match="pressure_kpa lower"):
        base_state(pressure_kpa=uv(0.2, "kPa", 0.3))


def test_uncertainty_box_rejects_nonphysical_vapor_pressure_corner() -> None:
    with pytest.raises(ValueError, match="partial pressure"):
        UncertainAirState(
            name="Nonphysical",
            dry_bulb_c=uv(60.0, "C"),
            relative_humidity_percent=uv(100.0, "%"),
            pressure_kpa=uv(10.0, "kPa"),
        )


def test_loader_builds_provenance() -> None:
    design = psychrometric_uncertainty_from_dict(
        {
            "name": "Loader",
            "dry_bulb_c": {
                "value": 23.0,
                "uncertainty_abs": 0.2,
                "provenance": {
                    "source_type": "measurement",
                    "source_name": "Calibrated temperature probe",
                    "reference": "TEMP-17",
                },
            },
            "relative_humidity_percent": {
                "value": 45.0,
                "uncertainty_abs": 1.5,
            },
        }
    )

    assert design.pressure_kpa.value == pytest.approx(101.325)
    assert design.dry_bulb_c.provenance is not None
    assert design.dry_bulb_c.provenance.reference == "TEMP-17"


def test_missing_provenance_is_reported_separately() -> None:
    result = analyze_psychrometric_uncertainty(
        base_state(
            relative_humidity_percent=uv(
                45.0,
                "%",
                2.0,
                source=False,
            )
        )
    )

    assert result["traceability"]["complete"] is False
    assert (
        "relative_humidity_percent"
        in result["traceability"]["missing_provenance"]
    )
