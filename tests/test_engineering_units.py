from __future__ import annotations

import pytest

from cleanroomx.engineering_units import (
    EngineeringUnitConversionError,
    convert_engineering_value,
    engineering_unit_conversion,
    engineering_unit_family,
    supported_engineering_units,
)


def test_pressure_and_airflow_conversions_are_explicit_family_conversions() -> None:
    assert convert_engineering_value(1.0, "kPa", "Pa") == pytest.approx(1000.0)
    assert convert_engineering_value(3600.0, "m3/h", "m3/s") == pytest.approx(1.0)
    assert convert_engineering_value(1.0, "psi", "Pa") == pytest.approx(
        6894.757293168
    )
    assert convert_engineering_value(2118.880003, "cfm", "m3/s") == pytest.approx(
        1.0,
        rel=1e-6,
    )


def test_rate_conversion_does_not_conflate_frequency_semantics() -> None:
    assert convert_engineering_value(1.0, "1/s", "1/h") == pytest.approx(3600.0)
    assert convert_engineering_value(20.0, "ACH", "1/h") == pytest.approx(20.0)
    with pytest.raises(EngineeringUnitConversionError, match="incompatible"):
        convert_engineering_value(1.0, "Hz", "1/h")


def test_affine_temperature_conversion_supports_celsius_fahrenheit_kelvin() -> None:
    assert convert_engineering_value(0.0, "C", "K") == pytest.approx(273.15)
    assert convert_engineering_value(273.15, "K", "degC") == pytest.approx(0.0)
    assert convert_engineering_value(32.0, "degF", "degC") == pytest.approx(
        0.0,
        abs=1e-12,
    )
    assert convert_engineering_value(100.0, "°C", "°F") == pytest.approx(
        212.0,
        abs=1e-12,
    )


def test_conversion_provenance_is_explicit_and_canonical() -> None:
    conversion = engineering_unit_conversion(3600.0, "m³/h", "m3/s")

    assert conversion.output_value == pytest.approx(1.0)
    assert conversion.source_canonical_unit == "m3/h"
    assert conversion.target_canonical_unit == "m3/s"
    assert conversion.family == "volumetric_flow"
    assert conversion.scale == pytest.approx(1.0 / 3600.0)
    assert conversion.offset == 0.0
    assert conversion.to_dict()["input_value"] == 3600.0


@pytest.mark.parametrize("unit", ["KPA", "m³/min", "degrees C", "SCFM"])
def test_unregistered_spellings_fail_closed(unit: str) -> None:
    with pytest.raises(EngineeringUnitConversionError, match="unsupported"):
        convert_engineering_value(1.0, unit, "Pa")


def test_cross_family_conversion_fails_closed() -> None:
    with pytest.raises(EngineeringUnitConversionError, match="incompatible"):
        convert_engineering_value(1.0, "Pa", "m3/s")


def test_non_finite_and_boolean_values_are_rejected() -> None:
    with pytest.raises(EngineeringUnitConversionError, match="finite number"):
        convert_engineering_value(float("inf"), "Pa", "kPa")
    with pytest.raises(EngineeringUnitConversionError, match="finite number"):
        convert_engineering_value(True, "Pa", "kPa")


def test_registry_surface_is_deterministic_and_family_query_is_exact() -> None:
    units = supported_engineering_units()
    assert units == tuple(sorted(units))
    assert "Pa" in units
    assert "m³/s" in units
    assert "ACH" in units
    assert engineering_unit_family("kPa") == "pressure"
    assert engineering_unit_family("Hz") == "frequency"
    assert engineering_unit_family("1/h") == "inverse_time_rate"
    with pytest.raises(EngineeringUnitConversionError, match="unsupported"):
        engineering_unit_family("KPA")
