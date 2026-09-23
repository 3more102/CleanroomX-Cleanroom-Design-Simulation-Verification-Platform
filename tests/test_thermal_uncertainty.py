import pytest

from cleanroomx.hvac_models import AirState
from cleanroomx.thermal_uncertainty import analyze_thermal_uncertainty
from cleanroomx.thermal_uncertainty_io import thermal_uncertainty_from_dict
from cleanroomx.thermal_uncertainty_models import UncertainThermalDesign
from cleanroomx.uncertainty_models import Provenance, UncertainValue


def uv(
    value: float,
    unit: str,
    uncertainty: float = 0.0,
    source: bool = True,
) -> UncertainValue:
    provenance = (
        Provenance("design_input", "Thermal test basis", reference="TH-001")
        if source
        else None
    )
    return UncertainValue(value, unit, uncertainty, provenance)


def base_design(**overrides) -> UncertainThermalDesign:
    data = {
        "name": "Thermal uncertainty",
        "room_air": AirState(22.0, 45.0),
        "cleanroom_airflow_m3_h": uv(1500.0, "m3/h", 100.0),
        "internal_sensible_kw": uv(4.0, "kW", 0.4),
        "internal_latent_kw": uv(0.5, "kW", 0.1),
        "supply_air_temp_c": uv(16.0, "C", 1.0),
        "capacity_margin_percent": 10.0,
        "available_cooling_capacity_kw": 6.0,
    }
    data.update(overrides)
    return UncertainThermalDesign(**data)


def test_internal_load_interval_and_capacity_pass() -> None:
    result = analyze_thermal_uncertainty(base_design())

    assert result["loads_kw"]["internal_total"] == {
        "nominal": 4.5,
        "lower": 4.0,
        "upper": 5.0,
    }
    assert result["cooling_capacity_kw"]["nominal"] == pytest.approx(4.95)
    assert result["cooling_capacity_kw"]["lower"] == pytest.approx(4.4)
    assert result["cooling_capacity_kw"]["upper"] == pytest.approx(5.5)
    assert result["cooling_capacity_kw"]["status"] == "pass"
    assert result["overall_status"] == "pass"


def test_capacity_overlap_is_indeterminate() -> None:
    result = analyze_thermal_uncertainty(
        base_design(available_cooling_capacity_kw=5.0)
    )

    assert result["cooling_capacity_kw"]["lower"] < 5.0
    assert result["cooling_capacity_kw"]["upper"] > 5.0
    assert result["cooling_capacity_kw"]["status"] == "indeterminate"
    assert result["overall_status"] == "indeterminate"


def test_capacity_below_complete_interval_fails() -> None:
    result = analyze_thermal_uncertainty(
        base_design(available_cooling_capacity_kw=3.5)
    )

    assert result["cooling_capacity_kw"]["status"] == "fail"
    assert result["overall_status"] == "fail"


def test_cold_makeup_air_produces_heating_interval() -> None:
    result = analyze_thermal_uncertainty(
        UncertainThermalDesign(
            name="Winter",
            room_air=AirState(22.0, 45.0),
            outdoor_air=AirState(0.0, 50.0),
            cleanroom_airflow_m3_h=uv(1200.0, "m3/h", 50.0),
            internal_sensible_kw=uv(0.0, "kW"),
            internal_latent_kw=uv(0.0, "kW"),
            makeup_airflow_m3_h=uv(800.0, "m3/h", 80.0),
            available_heating_capacity_kw=10.0,
        )
    )

    makeup = result["loads_kw"]["makeup_air_total"]
    assert makeup["nominal"] < 0
    assert makeup["lower"] < makeup["upper"] < 0
    assert result["cooling_capacity_kw"]["upper"] == 0
    assert result["heating_capacity_kw"]["lower"] > 0
    assert result["heating_capacity_kw"]["status"] in {"pass", "indeterminate"}


def test_thermal_airflow_interval_expands_with_load_and_supply_temp() -> None:
    result = analyze_thermal_uncertainty(base_design())
    thermal = result["airflow_m3_h"]["thermal_for_internal_sensible"]

    assert thermal is not None
    assert thermal["lower"] < thermal["nominal"] < thermal["upper"]
    assert result["airflow_m3_h"]["governing"]["lower"] <= result["airflow_m3_h"]["governing"]["upper"]
    assert result["airflow_m3_h"]["governing"]["nominal_basis"] == "internal_sensible_load"


def test_supply_temperature_interval_must_stay_below_room_for_positive_load() -> None:
    with pytest.raises(ValueError, match="must remain below"):
        base_design(supply_air_temp_c=uv(21.0, "C", 1.5))


def test_makeup_air_requires_outdoor_state() -> None:
    with pytest.raises(ValueError, match="outdoor_air is required"):
        base_design(
            makeup_airflow_m3_h=uv(100.0, "m3/h", 10.0),
            outdoor_air=None,
        )


def test_loader_builds_provenance_and_capacity_limits() -> None:
    design = thermal_uncertainty_from_dict(
        {
            "name": "Loader",
            "room_air": {
                "dry_bulb_c": 22.0,
                "relative_humidity_percent": 45.0,
            },
            "outdoor_air": {
                "dry_bulb_c": 32.0,
                "relative_humidity_percent": 50.0,
            },
            "cleanroom_airflow_m3_h": {
                "value": 1800.0,
                "uncertainty_abs": 90.0,
                "provenance": {
                    "source_type": "design",
                    "source_name": "Airflow schedule",
                    "reference": "HVAC-101",
                },
            },
            "internal_sensible_kw": {
                "value": 5.0,
                "uncertainty_abs": 0.5,
            },
            "internal_latent_kw": {
                "value": 0.7,
                "uncertainty_abs": 0.1,
            },
            "makeup_airflow_m3_h": {
                "value": 600.0,
                "uncertainty_abs": 60.0,
            },
            "supply_air_temp_c": {
                "value": 16.0,
                "uncertainty_abs": 0.5,
            },
            "capacity_margin_percent": 15.0,
            "available_cooling_capacity_kw": 15.0,
        }
    )

    assert design.cleanroom_airflow_m3_h.provenance is not None
    assert design.cleanroom_airflow_m3_h.provenance.reference == "HVAC-101"
    assert design.available_cooling_capacity_kw == 15.0
    assert design.capacity_margin_percent == 15.0


def test_missing_provenance_is_reported_separately() -> None:
    result = analyze_thermal_uncertainty(
        base_design(
            internal_latent_kw=uv(0.5, "kW", 0.1, source=False)
        )
    )

    assert result["overall_status"] == "pass"
    assert result["traceability"]["complete"] is False
    assert "internal_latent_kw" in result["traceability"]["missing_provenance"]
