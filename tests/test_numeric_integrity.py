from __future__ import annotations

import math

import pytest

from cleanroomx.airflow import analyze_air_balance
from cleanroomx.calculations import decay_concentration, recovery_time_minutes
from cleanroomx.fan import analyze_supply_fan
from cleanroomx.hvac_models import (
    AirBalanceDesign,
    AirState,
    FanSystem,
    FilterUnit,
    HVACRoom,
    ThermalDesign,
    ThermalLoads,
)
from cleanroomx.models import ParticleRequirement, PressureCascadeRequirement, RoomSpec
from cleanroomx.psychrometrics import dry_air_mass_flow_kg_s, saturation_vapor_pressure_kpa
from cleanroomx.thermal import analyze_thermal_design


_NONFINITE = (math.nan, math.inf, -math.inf)


@pytest.mark.parametrize("value", _NONFINITE)
@pytest.mark.parametrize(
    "field",
    ("length_m", "width_m", "height_m", "supply_airflow_m3_h"),
)
def test_room_spec_rejects_nonfinite_positive_inputs(field: str, value: float) -> None:
    kwargs = {
        "name": "R1",
        "length_m": 5.0,
        "width_m": 4.0,
        "height_m": 3.0,
        "supply_airflow_m3_h": 1200.0,
    }
    kwargs[field] = value
    with pytest.raises(ValueError, match="finite"):
        RoomSpec(**kwargs)


@pytest.mark.parametrize("value", _NONFINITE)
@pytest.mark.parametrize(
    "field",
    ("min_ach", "min_pressure_pa", "observed_pressure_pa"),
)
def test_room_spec_rejects_nonfinite_optional_engineering_inputs(
    field: str, value: float
) -> None:
    kwargs = {
        "name": "R1",
        "length_m": 5.0,
        "width_m": 4.0,
        "height_m": 3.0,
        "supply_airflow_m3_h": 1200.0,
        field: value,
    }
    with pytest.raises(ValueError, match="finite"):
        RoomSpec(**kwargs)


@pytest.mark.parametrize("value", _NONFINITE)
def test_particle_and_pressure_requirements_reject_nonfinite_values(value: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        ParticleRequirement(value, 1000.0, 100.0)
    with pytest.raises(ValueError, match="finite"):
        ParticleRequirement(0.5, value, 100.0)
    with pytest.raises(ValueError, match="finite"):
        ParticleRequirement(0.5, 1000.0, value)
    with pytest.raises(ValueError, match="finite"):
        PressureCascadeRequirement("High", "Low", value)


@pytest.mark.parametrize("value", _NONFINITE)
def test_hvac_models_reject_nonfinite_values(value: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        AirState(22.0, 45.0, value)
    with pytest.raises(ValueError, match="finite"):
        ThermalLoads(equipment_w=value)
    with pytest.raises(ValueError, match="finite"):
        ThermalDesign(room_air=AirState(22.0, 45.0), makeup_air_m3_h=value)
    with pytest.raises(ValueError, match="finite"):
        ThermalDesign(room_air=AirState(22.0, 45.0), supply_air_temp_c=value)
    with pytest.raises(ValueError, match="finite"):
        AirBalanceDesign(return_airflow_m3_h=value)
    with pytest.raises(ValueError, match="finite"):
        FilterUnit("FFU", rated_airflow_m3_h=value)
    with pytest.raises(ValueError, match="finite"):
        FanSystem("Supply", duct_pressure_drop_pa=value)
    with pytest.raises(ValueError, match="finite"):
        HVACRoom(
            "Room",
            cleanroom_airflow_m3_h=value,
            thermal_design=ThermalDesign(room_air=AirState(22.0, 45.0)),
        )


@pytest.mark.parametrize("value", _NONFINITE)
def test_direct_calculation_apis_reject_nonfinite_values(value: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        decay_concentration(value, ach=20.0, time_minutes=5.0)
    with pytest.raises(ValueError, match="finite"):
        decay_concentration(1000.0, ach=value, time_minutes=5.0)
    with pytest.raises(ValueError, match="finite"):
        decay_concentration(1000.0, ach=20.0, time_minutes=value)
    with pytest.raises(ValueError, match="finite"):
        recovery_time_minutes(1000.0, 100.0, ach=value)

    balance = AirBalanceDesign()
    with pytest.raises(ValueError, match="finite"):
        analyze_air_balance(value, balance)

    system = FanSystem("Supply")
    with pytest.raises(ValueError, match="finite"):
        analyze_supply_fan(value, system)
    with pytest.raises(ValueError, match="finite"):
        analyze_supply_fan(
            1000.0, system, terminal_filter_pressure_drop_pa=value
        )
    with pytest.raises(ValueError, match="finite"):
        analyze_supply_fan(
            1000.0, system, duct_pressure_drop_override_pa=value
        )

    design = ThermalDesign(room_air=AirState(22.0, 45.0))
    with pytest.raises(ValueError, match="finite"):
        analyze_thermal_design(design, value)

    with pytest.raises(ValueError, match="finite"):
        saturation_vapor_pressure_kpa(value)
    with pytest.raises(ValueError, match="finite"):
        dry_air_mass_flow_kg_s(value, AirState(22.0, 45.0))


def test_finite_foundational_inputs_preserve_existing_results() -> None:
    room = RoomSpec(
        "R1",
        6,
        4,
        3,
        1800,
        min_ach=20,
        min_pressure_pa=10,
        observed_pressure_pa=14,
        particle_requirements=(ParticleRequirement(0.5, 400000, 120000),),
    )
    assert room.length_m == 6.0
    assert room.supply_airflow_m3_h == 1800.0
    assert isinstance(room.length_m, float)
    assert isinstance(room.supply_airflow_m3_h, float)

    numeric_string_room = RoomSpec("R2", "6", "4", "3", "1800")
    assert numeric_string_room.length_m == 6.0
    assert numeric_string_room.supply_airflow_m3_h == 1800.0

    fan = analyze_supply_fan(
        3600,
        FanSystem(
            name="Supply",
            duct_pressure_drop_pa=300,
            coil_pressure_drop_pa=150,
            other_pressure_drop_pa=50,
            fan_efficiency=0.5,
            motor_efficiency=0.8,
        ),
        terminal_filter_pressure_drop_pa=100,
    )
    assert fan["total_static_pressure_pa"] == 600
    assert fan["estimated_electrical_input_kw"] == 1.5
