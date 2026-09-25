from __future__ import annotations

from pathlib import Path

from .input_json import load_strict_json
from .fan_curve import FanCurve, FanCurvePoint
from .fan_uncertainty_models import FanSystemUncertaintyStudy
from .uncertainty_models import Provenance, UncertainValue


def _provenance_from_dict(data: dict | None) -> Provenance | None:
    return None if data is None else Provenance(**data)


def _uncertain_value(data: float | int | dict, unit: str) -> UncertainValue:
    if isinstance(data, (int, float)):
        return UncertainValue(float(data), unit)
    return UncertainValue(
        value=data["value"],
        unit=unit,
        uncertainty_abs=data.get("uncertainty_abs", 0.0),
        provenance=_provenance_from_dict(data.get("provenance")),
    )


def fan_system_uncertainty_from_dict(data: dict) -> FanSystemUncertaintyStudy:
    fan_data = data["fan_curve"]
    system_data = data["system_curve"]
    return FanSystemUncertaintyStudy(
        name=data["name"],
        fan_curve=FanCurve(
            name=fan_data["name"],
            points=tuple(FanCurvePoint(**point) for point in fan_data["points"]),
        ),
        system_curve_name=system_data.get("name", "Uncertain system curve"),
        fixed_pressure_pa=_uncertain_value(
            system_data.get("fixed_pressure_pa", 0.0),
            "Pa",
        ),
        resistance_pa_per_m3_s_squared=_uncertain_value(
            system_data["resistance_pa_per_m3_s_squared"],
            "Pa/(m3/s)^2",
        ),
        fan_curve_provenance=_provenance_from_dict(
            fan_data.get("provenance")
        ),
    )


def load_fan_system_uncertainty(
    path: str | Path,
) -> FanSystemUncertaintyStudy:
    return fan_system_uncertainty_from_dict(
        load_strict_json(path)
    )
