import pytest

from cleanroomx.hvac_models import AirState
from cleanroomx.psychrometrics import (
    dew_point_c,
    humidity_ratio_kg_kg_da,
    moist_air_enthalpy_kj_kg_da,
    moist_air_specific_volume_m3_kg_da,
    saturation_vapor_pressure_kpa,
)


def test_standard_air_state_is_reasonable() -> None:
    state = AirState(25.0, 50.0, 101.325)
    # Reference state derived from the ASHRAE F25 saturation-pressure table
    # value p_ws(25 C) = 3.1697 kPa and the documented perfect-gas relations.
    assert humidity_ratio_kg_kg_da(state) == pytest.approx(0.0098826, rel=3e-4)
    assert moist_air_enthalpy_kj_kg_da(state) == pytest.approx(50.3259, rel=3e-4)
    assert moist_air_specific_volume_m3_kg_da(state) == pytest.approx(0.858045, rel=3e-4)
    assert dew_point_c(state) == pytest.approx(13.864, abs=0.02)


@pytest.mark.parametrize(
    ("temperature_c", "expected_kpa"),
    [
        (-20.0, 0.10324),
        (0.0, 0.61121),
        (25.0, 3.1697),
    ],
)
def test_saturation_pressure_matches_ashrae_f25_reference_table(
    temperature_c: float,
    expected_kpa: float,
) -> None:
    assert saturation_vapor_pressure_kpa(temperature_c) == pytest.approx(
        expected_kpa,
        rel=3e-4,
    )


@pytest.mark.parametrize(
    ("temperature_c", "expected_kpa"),
    [
        (-43.15, 0.00894735),  # IAPWS R14-08 Table 3: 230 K, 8.94735e-6 MPa
        (26.85, 3.53658941),  # IAPWS-IF97 Table 35: 300 K, 3.53658941e-3 MPa
    ],
)
def test_saturation_pressure_matches_iapws_program_verification(
    temperature_c: float,
    expected_kpa: float,
) -> None:
    assert saturation_vapor_pressure_kpa(temperature_c) == pytest.approx(
        expected_kpa,
        rel=5e-7,
    )


def test_dew_point_fails_closed_in_zero_c_phase_boundary_pressure_gap() -> None:
    target_pressure_kpa = 0.61118
    dry_bulb_c = 25.0
    relative_humidity_percent = (
        100.0
        * target_pressure_kpa
        / saturation_vapor_pressure_kpa(dry_bulb_c)
    )
    state = AirState(
        dry_bulb_c,
        relative_humidity_percent,
        101.325,
    )

    with pytest.raises(ValueError, match="phase-boundary"):
        dew_point_c(state)


def test_subfreezing_saturated_air_dew_point_matches_dry_bulb() -> None:
    state = AirState(-20.0, 100.0, 101.325)
    assert dew_point_c(state) == pytest.approx(-20.0, abs=1e-9)


def test_ultradry_state_uses_full_iapws_sublimation_domain() -> None:
    state = AirState(60.0, 1e-12, 101.325)
    assert dew_point_c(state) == pytest.approx(-153.668, abs=0.002)


def test_dew_point_fails_below_iapws_sublimation_domain() -> None:
    state = AirState(60.0, 1e-43, 101.325)
    with pytest.raises(ValueError, match="50 K / -223.15 C"):
        dew_point_c(state)


def test_air_state_rejects_out_of_model_temperature_range() -> None:
    with pytest.raises(ValueError):
        AirState(61.0, 50.0)
