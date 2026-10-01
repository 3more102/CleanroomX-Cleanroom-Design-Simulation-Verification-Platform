from __future__ import annotations

import pytest

from cleanroomx.engineering_units import (
    EngineeringUnitConversionError,
    convert_engineering_value,
    supported_engineering_units,
)


def test_pressure_conversion_is_traceable_and_deterministic() -> None:
    conversion = convert_engineering_value(
        1.25,
        source_unit="kPa",
        target_unit="Pa",
    )

    assert conversion.output_value == pytest.approx(1250.0)
    assert conversion.dimension == "pressure"
    assert conversion.scale == pytest.approx(1000.0)
    assert conversion.offset == 0.0
    assert conversion.to_dict()["source_canonical_unit"] == "kPa"


def test_temperature_conversion_handles_affine_offset() -> None:
    freezing = convert_engineering_value(
        32.0,
        source_unit="degF",
        target_unit="degC",
    )
    boiling = convert_engineering_value(
        100.0,
        source_unit="degC",
        target_unit="degF",
    )

    assert freezing.output_value == pytest.approx(0.0, abs=1e-12)
    assert boiling.output_value == pytest.approx(212.0, abs=1e-12)


def test_airflow_aliases_share_one_canonical_dimension() -> None:
    conversion = convert_engineering_value(
        3600.0,
        source_unit="m³/h",
        target_unit="m3/s",
    )

    assert conversion.output_value == pytest.approx(1.0)
    assert conversion.source_canonical_unit == "m3/h"
    assert conversion.target_canonical_unit == "m3/s"


def test_air_change_rate_aliases_do_not_expand_into_generic_frequency() -> None:
    conversion = convert_engineering_value(
        20.0,
        source_unit="ACH",
        target_unit="1/h",
    )

    assert conversion.output_value == pytest.approx(20.0)
    assert "Hz" not in supported_engineering_units()


def test_unknown_or_incompatible_units_fail_closed() -> None:
    with pytest.raises(
        EngineeringUnitConversionError,
        match="unsupported source engineering unit",
    ):
        convert_engineering_value(1.0, source_unit="unknown", target_unit="Pa")

    with pytest.raises(
        EngineeringUnitConversionError,
        match="incompatible engineering-unit dimensions",
    ):
        convert_engineering_value(1.0, source_unit="Pa", target_unit="m3/s")


@pytest.mark.parametrize("value", [True, float("inf"), float("-inf"), float("nan")])
def test_non_numeric_or_non_finite_conversion_values_are_rejected(value) -> None:
    with pytest.raises(EngineeringUnitConversionError):
        convert_engineering_value(value, source_unit="Pa", target_unit="kPa")


def test_finite_input_that_overflows_conversion_fails_closed() -> None:
    with pytest.raises(
        EngineeringUnitConversionError,
        match="non-finite base value",
    ):
        convert_engineering_value(
            1.0e308,
            source_unit="bar",
            target_unit="Pa",
        )
