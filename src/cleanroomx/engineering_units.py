from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any


class EngineeringUnitConversionError(ValueError):
    """Raised when a requested engineering-unit conversion is not authoritative."""


@dataclass(frozen=True, kw_only=True)
class _UnitDefinition:
    canonical: str
    dimension: str
    scale_to_base: float
    offset_to_base: float = 0.0


@dataclass(frozen=True, kw_only=True)
class EngineeringUnitConversion:
    source_unit: str
    target_unit: str
    source_canonical_unit: str
    target_canonical_unit: str
    dimension: str
    input_value: float
    output_value: float
    scale: float
    offset: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_unit": self.source_unit,
            "target_unit": self.target_unit,
            "source_canonical_unit": self.source_canonical_unit,
            "target_canonical_unit": self.target_canonical_unit,
            "dimension": self.dimension,
            "input_value": self.input_value,
            "output_value": self.output_value,
            "scale": self.scale,
            "offset": self.offset,
        }


def _definition(
    canonical: str,
    dimension: str,
    scale_to_base: float,
    offset_to_base: float = 0.0,
) -> _UnitDefinition:
    return _UnitDefinition(
        canonical=canonical,
        dimension=dimension,
        scale_to_base=float(scale_to_base),
        offset_to_base=float(offset_to_base),
    )


_PA = _definition("Pa", "pressure", 1.0)
_KPA = _definition("kPa", "pressure", 1_000.0)
_BAR = _definition("bar", "pressure", 100_000.0)
_MBAR = _definition("mbar", "pressure", 100.0)
_PSI = _definition("psi", "pressure", 6_894.757293168)
# NIST SP 811 conventional water-column definitions. These tokens do not
# represent temperature-specific water-column variants.
_IN_H2O = _definition("inH2O", "pressure", 249.0889)
_MM_H2O = _definition("mmH2O", "pressure", 9.80665)

_M3_S = _definition("m3/s", "volumetric_flow", 1.0)
_M3_H = _definition("m3/h", "volumetric_flow", 1.0 / 3_600.0)
_L_S = _definition("L/s", "volumetric_flow", 0.001)
_L_MIN = _definition("L/min", "volumetric_flow", 0.001 / 60.0)
_CFM = _definition("cfm", "volumetric_flow", 0.0004719474432)

_ACH = _definition("1/h", "air_change_rate", 1.0)

_K = _definition("K", "temperature", 1.0)
_DEGC = _definition("degC", "temperature", 1.0, 273.15)
_DEGF = _definition(
    "degF",
    "temperature",
    5.0 / 9.0,
    273.15 - (32.0 * 5.0 / 9.0),
)

_M = _definition("m", "length", 1.0)
_MM = _definition("mm", "length", 0.001)
_CM = _definition("cm", "length", 0.01)
_FT = _definition("ft", "length", 0.3048)
_IN = _definition("in", "length", 0.0254)

_M2 = _definition("m2", "area", 1.0)
_CM2 = _definition("cm2", "area", 0.0001)
_MM2 = _definition("mm2", "area", 0.000001)
_FT2 = _definition("ft2", "area", 0.09290304)
_IN2 = _definition("in2", "area", 0.00064516)

_M3 = _definition("m3", "volume", 1.0)
_L = _definition("L", "volume", 0.001)
_FT3 = _definition("ft3", "volume", 0.028316846592)

_M_S = _definition("m/s", "velocity", 1.0)
_FT_S = _definition("ft/s", "velocity", 0.3048)
_FT_MIN = _definition("ft/min", "velocity", 0.00508)

_W = _definition("W", "power", 1.0)
_KW = _definition("kW", "power", 1_000.0)
# Unqualified Btu/h is defined here as International Table Btu per hour.
# NIST SP 811: 1 Btu_IT = 1.05505585262 kJ exactly.
_BTU_H = _definition("Btu/h", "power", 1_055.055_852_62 / 3_600.0)

_KG_S = _definition("kg/s", "mass_flow", 1.0)
_KG_H = _definition("kg/h", "mass_flow", 1.0 / 3_600.0)
_G_S = _definition("g/s", "mass_flow", 0.001)
_LB_H = _definition("lb/h", "mass_flow", 0.45359237 / 3_600.0)

_KG_KG = _definition("kg/kg", "humidity_ratio", 1.0)
_G_KG = _definition("g/kg", "humidity_ratio", 0.001)


_UNIT_DEFINITIONS: dict[str, _UnitDefinition] = {
    "Pa": _PA,
    "kPa": _KPA,
    "bar": _BAR,
    "mbar": _MBAR,
    "psi": _PSI,
    "inH2O": _IN_H2O,
    "inH₂O": _IN_H2O,
    "mmH2O": _MM_H2O,
    "mmH₂O": _MM_H2O,
    "m3/s": _M3_S,
    "m^3/s": _M3_S,
    "m³/s": _M3_S,
    "m3/h": _M3_H,
    "m^3/h": _M3_H,
    "m³/h": _M3_H,
    "L/s": _L_S,
    "L/min": _L_MIN,
    "cfm": _CFM,
    "1/h": _ACH,
    "h^-1": _ACH,
    "h⁻¹": _ACH,
    "ACH": _ACH,
    "K": _K,
    "C": _DEGC,
    "degC": _DEGC,
    "°C": _DEGC,
    "degF": _DEGF,
    "°F": _DEGF,
    "m": _M,
    "mm": _MM,
    "cm": _CM,
    "ft": _FT,
    "in": _IN,
    "m2": _M2,
    "m^2": _M2,
    "m²": _M2,
    "cm2": _CM2,
    "cm^2": _CM2,
    "cm²": _CM2,
    "mm2": _MM2,
    "mm^2": _MM2,
    "mm²": _MM2,
    "ft2": _FT2,
    "ft^2": _FT2,
    "ft²": _FT2,
    "in2": _IN2,
    "in^2": _IN2,
    "in²": _IN2,
    "m3": _M3,
    "m^3": _M3,
    "m³": _M3,
    "L": _L,
    "ft3": _FT3,
    "ft^3": _FT3,
    "ft³": _FT3,
    "m/s": _M_S,
    "ft/s": _FT_S,
    "ft/min": _FT_MIN,
    "W": _W,
    "kW": _KW,
    "Btu/h": _BTU_H,
    "BTU/h": _BTU_H,
    "kg/s": _KG_S,
    "kg/h": _KG_H,
    "g/s": _G_S,
    "lb/h": _LB_H,
    "kg/kg": _KG_KG,
    "g/kg": _G_KG,
}


def _finite_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EngineeringUnitConversionError(
            f"{field_name} must be a finite numeric value"
        )
    try:
        result = float(value)
    except OverflowError as exc:
        raise EngineeringUnitConversionError(
            f"{field_name} must be representable as a finite numeric value"
        ) from exc
    if not math.isfinite(result):
        raise EngineeringUnitConversionError(
            f"{field_name} must be a finite numeric value"
        )
    return 0.0 if result == 0.0 else result


def supported_engineering_units() -> tuple[str, ...]:
    """Return the exact accepted unit spellings in deterministic order."""
    return tuple(sorted(_UNIT_DEFINITIONS))


def convert_engineering_value(
    value: Any,
    *,
    source_unit: str,
    target_unit: str,
) -> EngineeringUnitConversion:
    """Convert a finite numeric value using the explicit CleanroomX unit registry.

    Only explicitly registered unit spellings are accepted. Conversion across
    different engineering dimensions is rejected instead of inferred.
    """
    numeric = _finite_number(value, "engineering unit conversion value")
    source = _UNIT_DEFINITIONS.get(source_unit)
    if source is None:
        raise EngineeringUnitConversionError(
            f"unsupported source engineering unit {source_unit!r}"
        )
    target = _UNIT_DEFINITIONS.get(target_unit)
    if target is None:
        raise EngineeringUnitConversionError(
            f"unsupported target engineering unit {target_unit!r}"
        )
    if source.dimension != target.dimension:
        raise EngineeringUnitConversionError(
            "incompatible engineering-unit dimensions: "
            f"{source_unit!r} is {source.dimension!r} but "
            f"{target_unit!r} is {target.dimension!r}"
        )

    base_value = numeric * source.scale_to_base + source.offset_to_base
    if not math.isfinite(base_value):
        raise EngineeringUnitConversionError(
            "engineering unit conversion produced a non-finite base value"
        )
    output = (base_value - target.offset_to_base) / target.scale_to_base
    if not math.isfinite(output):
        raise EngineeringUnitConversionError(
            "engineering unit conversion produced a non-finite output value"
        )
    output = 0.0 if output == 0.0 else output
    scale = source.scale_to_base / target.scale_to_base
    offset = (
        source.offset_to_base - target.offset_to_base
    ) / target.scale_to_base
    offset = 0.0 if offset == 0.0 else offset
    return EngineeringUnitConversion(
        source_unit=source_unit,
        target_unit=target_unit,
        source_canonical_unit=source.canonical,
        target_canonical_unit=target.canonical,
        dimension=source.dimension,
        input_value=numeric,
        output_value=output,
        scale=scale,
        offset=offset,
    )
