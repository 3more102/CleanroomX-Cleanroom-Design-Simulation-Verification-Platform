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


def test_subfreezing_saturated_air_dew_point_matches_dry_bulb() -> None:
    state = AirState(-20.0, 100.0, 101.325)
    assert dew_point_c(state) == pytest.approx(-20.0, abs=1e-9)


def test_ultradry_state_fails_when_dew_point_leaves_supported_inversion() -> None:
    state = AirState(60.0, 1e-12, 101.325)
    with pytest.raises(ValueError, match="below -100 C"):
        dew_point_c(state)


def test_air_state_rejects_out_of_model_temperature_range() -> None:
    with pytest.raises(ValueError):
        AirState(61.0, 50.0)
