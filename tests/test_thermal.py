import pytest

from cleanroomx.hvac_models import AirState, ThermalDesign, ThermalLoads
from cleanroomx.thermal import analyze_thermal_design


def test_internal_loads_and_thermal_airflow() -> None:
    design = ThermalDesign(
        room_air=AirState(22.0, 45.0),
        loads=ThermalLoads(
            occupants=2,
            sensible_w_per_person=75.0,
            latent_w_per_person=55.0,
            lighting_w=500.0,
            equipment_w=3000.0,
            envelope_sensible_w=350.0,
            process_latent_w=400.0,
        ),
        supply_air_temp_c=16.0,
    )
    result = analyze_thermal_design(design, cleanroom_airflow_m3_h=1500.0)
    assert result["loads"]["internal_sensible_kw"] == 4.0
    assert result["loads"]["internal_latent_kw"] == 0.51
    assert result["loads"]["internal_total_kw"] == 4.51
    assert result["preliminary_cooling_capacity_kw"] == 4.51
    assert result["thermal_airflow_for_internal_sensible_m3_h"] > 1500.0
    assert result["governing_airflow_basis"] == "internal_sensible_load"


def test_makeup_air_can_govern_total_supply_airflow() -> None:
    design = ThermalDesign(
        room_air=AirState(22.0, 45.0),
        outdoor_air=AirState(30.0, 50.0),
        makeup_air_m3_h=2500.0,
    )
    result = analyze_thermal_design(design, cleanroom_airflow_m3_h=1500.0)
    assert result["governing_supply_airflow_m3_h"] == 2500.0
    assert result["governing_airflow_basis"] == "makeup_air"



def test_extreme_finite_internal_loads_fail_before_nonfinite_result_escape() -> None:
    design = ThermalDesign(
        room_air=AirState(22.0, 45.0),
        loads=ThermalLoads(
            lighting_w=1.0e308,
            equipment_w=1.0e308,
        ),
    )

    with pytest.raises(ValueError, match="internal_sensible_kw must be finite"):
        analyze_thermal_design(design, cleanroom_airflow_m3_h=1500.0)


def test_extreme_capacity_margin_fails_before_nonfinite_capacity_escape() -> None:
    design = ThermalDesign(
        room_air=AirState(22.0, 45.0),
        loads=ThermalLoads(lighting_w=1.0e308),
        capacity_margin_percent=1.0e308,
    )

    with pytest.raises(
        ValueError, match="preliminary_cooling_capacity_kw must be finite"
    ):
        analyze_thermal_design(design, cleanroom_airflow_m3_h=1500.0)
