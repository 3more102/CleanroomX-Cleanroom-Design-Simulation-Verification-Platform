import math

import pytest

from cleanroomx.pressure_power import (
    FanPowerEfficiencies,
    analyze_fan_pressure_power,
    fan_power_efficiencies_from_dict,
)


def test_fluid_power_requires_no_efficiency_and_invents_none() -> None:
    result = analyze_fan_pressure_power(3600.0, 500.0)

    assert result["fluid_air_power_w"] == pytest.approx(500.0)
    assert result["fluid_air_power_kw"] == pytest.approx(0.5)
    assert result["efficiencies"] is None
    assert result["shaft_power_kw"] is None
    assert result["electrical_input_kw"] is None
    assert result["specific_fan_power_w_per_m3_s"] is None


def test_explicit_efficiency_chain_reports_shaft_electrical_and_sfp() -> None:
    efficiencies = FanPowerEfficiencies(
        fan_efficiency=0.5,
        motor_efficiency=0.8,
        vfd_efficiency=0.9,
    )
    result = analyze_fan_pressure_power(3600.0, 500.0, efficiencies)

    assert result["shaft_power_kw"] == pytest.approx(1.0)
    assert result["electrical_input_kw"] == pytest.approx(
        1.0 / 0.8 / 0.9
    )
    assert result["specific_fan_power_w_per_m3_s"] == pytest.approx(
        1000.0 / 0.8 / 0.9
    )


def test_fan_efficiency_alone_reports_only_shaft_power() -> None:
    result = analyze_fan_pressure_power(
        1800.0,
        400.0,
        FanPowerEfficiencies(fan_efficiency=0.5),
    )

    assert result["fluid_air_power_kw"] == pytest.approx(0.2)
    assert result["shaft_power_kw"] == pytest.approx(0.4)
    assert result["electrical_input_kw"] is None
    assert result["specific_fan_power_w_per_m3_s"] is None


@pytest.mark.parametrize(
    "data",
    [
        {"fan_efficiency": 0.0},
        {"fan_efficiency": float("nan")},
        {"fan_efficiency": float("inf")},
        {"motor_efficiency": 0.9},
        {"fan_efficiency": 0.7, "vfd_efficiency": 0.97},
    ],
)
def test_invalid_or_incomplete_efficiency_chain_is_rejected(data: dict) -> None:
    with pytest.raises(ValueError):
        fan_power_efficiencies_from_dict(data)


def test_unknown_efficiency_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        fan_power_efficiencies_from_dict(
            {"fan_efficiency": 0.7, "invented_efficiency": 0.9}
        )


@pytest.mark.parametrize(
    ("airflow", "pressure"),
    [
        (float("nan"), 100.0),
        (1000.0, float("inf")),
        (-1.0, 100.0),
        (1000.0, -1.0),
    ],
)
def test_invalid_pressure_power_inputs_are_rejected(
    airflow: float,
    pressure: float,
) -> None:
    with pytest.raises(ValueError):
        analyze_fan_pressure_power(airflow, pressure)
