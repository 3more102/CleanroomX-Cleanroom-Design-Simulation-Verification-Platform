from __future__ import annotations

import pytest

from cleanroomx.engineering_units import (
    EngineeringUnitConversionError,
    convert_engineering_value,
    engineering_unit_family,
    supported_engineering_units,
)


def test_pressure_and_airflow_conversions_are_exact_family_conversions() -> None:
    assert convert_engineering_value(1.0, "kPa", "Pa") == pytest.approx(1000.0)
    assert convert_engineering_value(3600.0, "m3/h", "m3/s") == pytest.approx(1.0)


def test_rate_conversion_does_not_conflate_frequency_semantics() -> None:
    assert convert_engineering_value(1.0, "1/s", "1/h") == pytest.approx(3600.0)
    with pytest.raises(EngineeringUnitConversionError, match="incompatible"):
        convert_engineering_value(1.0, "Hz", "1/h")


def test_affine_temperature_conversion_is_supported_without_rounding() -> None:
    assert convert_engineering_value(0.0, "C", "K") == pytest.approx(273.15)
    assert convert_engineering_value(273.15, "K", "C") == pytest.approx(0.0)


def test_registered_engineering_aliases_are_supported_exactly() -> None:
    assert convert_engineering_value(1.0, "psi", "Pa") == pytest.approx(
        6894.757293168
    )
    assert convert_engineering_value(1.0, "cfm", "m3/s") == pytest.approx(
        0.0004719474432
    )
    assert convert_engineering_value(20.0, "ACH", "1/h") == pytest.approx(20.0)
    assert convert_engineering_value(20.0, "degC", "K") == pytest.approx(293.15)


@pytest.mark.parametrize("unit", ["PSI", "CFM", "ach", "degc"])
def test_unknown_aliases_fail_closed(unit: str) -> None:
    with pytest.raises(EngineeringUnitConversionError, match="unsupported"):
        convert_engineering_value(1.0, unit, "Pa")


def test_non_finite_and_boolean_values_are_rejected() -> None:
    with pytest.raises(EngineeringUnitConversionError, match="finite number"):
        convert_engineering_value(float("inf"), "Pa", "kPa")
    with pytest.raises(EngineeringUnitConversionError, match="finite number"):
        convert_engineering_value(True, "Pa", "kPa")


def test_registry_surface_is_deterministic_and_family_query_is_exact() -> None:
    units = supported_engineering_units()
    assert units == tuple(sorted(units))
    assert "Pa" in units
    assert engineering_unit_family("kPa") == "pressure"
    with pytest.raises(EngineeringUnitConversionError, match="unsupported"):
        engineering_unit_family("KPA")
