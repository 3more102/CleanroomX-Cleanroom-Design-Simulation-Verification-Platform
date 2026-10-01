from __future__ import annotations

from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Any


class EngineeringUnitConversionError(ValueError):
    """Raised when an engineering value cannot be converted safely."""


@dataclass(frozen=True)
class EngineeringUnitDefinition:
    family: str
    scale_to_base: float
    offset_to_base: float = 0.0


# Exact, case-sensitive spellings only.  The family is intentionally stricter
# than dimensional analysis: e.g. Hz is not interchangeable with an air-change
# rate merely because both reduce to inverse time.
_ENGINEERING_UNITS = MappingProxyType(
    {
        "Pa": EngineeringUnitDefinition("pressure", 1.0),
        "kPa": EngineeringUnitDefinition("pressure", 1000.0),
        "m3/s": EngineeringUnitDefinition("volumetric_flow", 1.0),
        "m3/h": EngineeringUnitDefinition("volumetric_flow", 1.0 / 3600.0),
        "L/s": EngineeringUnitDefinition("volumetric_flow", 0.001),
        "1/s": EngineeringUnitDefinition("rate", 1.0),
        "1/min": EngineeringUnitDefinition("rate", 1.0 / 60.0),
        "1/h": EngineeringUnitDefinition("rate", 1.0 / 3600.0),
        "Hz": EngineeringUnitDefinition("frequency", 1.0),
        "W": EngineeringUnitDefinition("power", 1.0),
        "kW": EngineeringUnitDefinition("power", 1000.0),
        "m": EngineeringUnitDefinition("length", 1.0),
        "cm": EngineeringUnitDefinition("length", 0.01),
        "mm": EngineeringUnitDefinition("length", 0.001),
        "kg/s": EngineeringUnitDefinition("mass_flow", 1.0),
        "kg/h": EngineeringUnitDefinition("mass_flow", 1.0 / 3600.0),
        "C": EngineeringUnitDefinition("temperature", 1.0, 273.15),
        "K": EngineeringUnitDefinition("temperature", 1.0, 0.0),
    }
)


def supported_engineering_units() -> tuple[str, ...]:
    """Return deterministic exact unit spellings supported by the authority."""
    return tuple(sorted(_ENGINEERING_UNITS))


def engineering_unit_family(unit: str) -> str:
    if not isinstance(unit, str) or not unit:
        raise EngineeringUnitConversionError("unit must be a non-empty string")
    definition = _ENGINEERING_UNITS.get(unit)
    if definition is None:
        raise EngineeringUnitConversionError(f"unsupported engineering unit {unit!r}")
    return definition.family


def convert_engineering_value(value: Any, from_unit: str, to_unit: str) -> float:
    """Convert a finite numeric value between explicitly compatible units.

    The registry is deliberately closed and exact. Unknown spellings, aliases,
    and cross-family conversions fail closed rather than being guessed.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EngineeringUnitConversionError("engineering value must be a finite number")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise EngineeringUnitConversionError("engineering value must be a finite number")

    source = _ENGINEERING_UNITS.get(from_unit)
    if source is None:
        raise EngineeringUnitConversionError(
            f"unsupported engineering unit {from_unit!r}"
        )
    target = _ENGINEERING_UNITS.get(to_unit)
    if target is None:
        raise EngineeringUnitConversionError(
            f"unsupported engineering unit {to_unit!r}"
        )
    if source.family != target.family:
        raise EngineeringUnitConversionError(
            f"incompatible engineering unit families {source.family!r} and "
            f"{target.family!r}"
        )

    base_value = numeric * source.scale_to_base + source.offset_to_base
    converted = (base_value - target.offset_to_base) / target.scale_to_base
    if not math.isfinite(converted):
        raise EngineeringUnitConversionError(
            "engineering unit conversion produced a non-finite value"
        )
    return 0.0 if converted == 0.0 else converted
