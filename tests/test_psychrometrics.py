import pytest

from cleanroomx.hvac_models import AirState
from cleanroomx.psychrometrics import (
    dew_point_c,
    humidity_ratio_kg_kg_da,
    moist_air_enthalpy_kj_kg_da,
    moist_air_specific_volume_m3_kg_da,
)


def test_standard_air_state_is_reasonable() -> None:
    state = AirState(25.0, 50.0, 101.325)
    assert humidity_ratio_kg_kg_da(state) == pytest.approx(0.009852, rel=1e-4)
    assert moist_air_enthalpy_kj_kg_da(state) == pytest.approx(50.248, rel=1e-4)
    assert moist_air_specific_volume_m3_kg_da(state) == pytest.approx(0.858004, rel=1e-4)
    assert dew_point_c(state) == pytest.approx(13.85, abs=0.05)


def test_air_state_rejects_out_of_model_temperature_range() -> None:
    with pytest.raises(ValueError):
        AirState(61.0, 50.0)
