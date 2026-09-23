import pytest

from cleanroomx.hvac_models import AirState, ThermalDesign, ThermalLoads
from cleanroomx.thermal import analyze_thermal_design
from cleanroomx.thermal_uncertainty import (
    ThermalUncertaintyCase,
    analyze_thermal_uncertainty,
)
from cleanroomx.thermal_uncertainty_io import thermal_uncertainty_case_from_dict
from cleanroomx.uncertainty_models import Provenance, UncertainValue


def uv(
    value: float,
    unit: str,
    uncertainty: float = 0.0,
    source: bool = True,
) -> UncertainValue:
    provenance = (
        Provenance("measurement", "Test source", reference="REF-1")
        if source
        else None
    )
    return UncertainValue(value, unit, uncertainty, provenance)


def base_case(**overrides) -> ThermalUncertaintyCase:
    values = {
        "name": "Thermal envelope",
        "cleanroom_airflow_m3_h": uv(1500.0, "m3/h"),
        "room_dry_bulb_c": uv(22.0, "degC"),
        "room_relative_humidity_percent": uv(45.0, "%RH"),
        "room_pressure_kpa": uv(101.325, "kPa"),
        "makeup_air_m3_h": uv(800.0, "m3/h"),
        "outdoor_dry_bulb_c": uv(34.0, "degC"),
        "outdoor_relative_humidity_percent": uv(50.0, "%RH"),
        "outdoor_pressure_kpa": uv(101.325, "kPa"),
        "supply_air_temp_c": uv(16.0, "degC"),
        "loads": ThermalLoads(
            occupants=2,
            sensible_w_per_person=75,
            latent_w_per_person=55,
            lighting_w=500,
            equipment_w=3000,
            envelope_sensible_w=350,
            process_latent_w=400,
        ),
        "capacity_margin_percent": 10.0,
    }
    values.update(overrides)
    return ThermalUncertaintyCase(**values)


def test_zero_uncertainty_matches_nominal_thermal_model() -> None:
    case = base_case()
    result = analyze_thermal_uncertainty(case)

    design = ThermalDesign(
        room_air=AirState(22.0, 45.0),
        outdoor_air=AirState(34.0, 50.0),
        makeup_air_m3_h=800.0,
        supply_air_temp_c=16.0,
        loads=case.loads,
        capacity_margin_percent=10.0,
    )
    baseline = analyze_thermal_design(design, 1500.0)

    assert result["scenario_count"] == 1
    assert result["preliminary_cooling_capacity_kw"] == {
        "nominal": baseline["preliminary_cooling_capacity_kw"],
        "lower": baseline["preliminary_cooling_capacity_kw"],
        "upper": baseline["preliminary_cooling_capacity_kw"],
    }
    assert result["governing_supply_airflow_m3_h"]["nominal"] == (
        baseline["governing_supply_airflow_m3_h"]
    )


def test_endpoint_uncertainty_expands_reported_envelopes() -> None:
    case = base_case(
        cleanroom_airflow_m3_h=uv(1500.0, "m3/h", 100.0),
        room_dry_bulb_c=uv(22.0, "degC", 0.5),
        outdoor_dry_bulb_c=uv(34.0, "degC", 1.0),
        makeup_air_m3_h=uv(800.0, "m3/h", 40.0),
    )

    result = analyze_thermal_uncertainty(case)

    assert result["scenario_count"] == 16
    cooling = result["preliminary_cooling_capacity_kw"]
    airflow = result["governing_supply_airflow_m3_h"]
    assert cooling["lower"] <= cooling["nominal"] <= cooling["upper"]
    assert airflow["lower"] <= airflow["nominal"] <= airflow["upper"]
    assert cooling["lower"] < cooling["upper"]
    assert set(result["uncertain_dimensions"]) == {
        "cleanroom_airflow_m3_h",
        "room_dry_bulb_c",
        "outdoor_dry_bulb_c",
        "makeup_air_m3_h",
    }


def test_supply_temperature_interval_can_make_thermal_airflow_partial() -> None:
    case = base_case(
        room_dry_bulb_c=uv(22.0, "degC"),
        supply_air_temp_c=uv(22.0, "degC", 1.0),
    )

    result = analyze_thermal_uncertainty(case)
    thermal_airflow = result["thermal_airflow_for_internal_sensible_m3_h"]

    assert result["scenario_count"] == 2
    assert thermal_airflow["status"] == "partially_defined"
    assert thermal_airflow["lower"] is not None
    assert thermal_airflow["upper"] is not None


def test_invalid_relative_humidity_interval_is_rejected() -> None:
    with pytest.raises(ValueError, match="relative-humidity uncertainty interval"):
        base_case(
            room_relative_humidity_percent=uv(99.0, "%RH", 2.0),
        )


def test_makeup_air_uncertainty_requires_outdoor_state() -> None:
    with pytest.raises(ValueError, match="outdoor air state is required"):
        base_case(
            makeup_air_m3_h=uv(0.0, "m3/h", 20.0),
            outdoor_dry_bulb_c=None,
            outdoor_relative_humidity_percent=None,
            outdoor_pressure_kpa=None,
        )


def test_loader_accepts_scalar_and_provenance_inputs() -> None:
    case = thermal_uncertainty_case_from_dict(
        {
            "name": "Loader",
            "cleanroom_airflow_m3_h": {
                "value": 1400,
                "uncertainty_abs": 50,
                "provenance": {
                    "source_type": "measurement",
                    "source_name": "TAB",
                    "revision": "B",
                },
            },
            "thermal_design": {
                "room_air": {
                    "dry_bulb_c": 22,
                    "relative_humidity_percent": 45,
                },
                "supply_air_temp_c": 16,
            },
        }
    )

    assert case.cleanroom_airflow_m3_h.provenance is not None
    assert case.cleanroom_airflow_m3_h.provenance.revision == "B"
    assert case.room_pressure_kpa.value == 101.325
    assert case.supply_air_temp_c is not None
    assert case.supply_air_temp_c.uncertainty_abs == 0
