from __future__ import annotations

from dataclasses import dataclass

from .fan_curve import FanCurve
from .uncertainty_models import Provenance, UncertainValue


@dataclass(frozen=True)
class FanSystemUncertaintyStudy:
    name: str
    fan_curve: FanCurve
    system_curve_name: str
    fixed_pressure_pa: UncertainValue
    resistance_pa_per_m3_s_squared: UncertainValue
    fan_curve_provenance: Provenance | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("fan/system uncertainty study name cannot be empty")
        if not self.system_curve_name.strip():
            raise ValueError("system_curve_name cannot be empty")
        if self.fixed_pressure_pa.unit != "Pa":
            raise ValueError("fixed_pressure_pa unit must be 'Pa'")
        if self.resistance_pa_per_m3_s_squared.unit != "Pa/(m3/s)^2":
            raise ValueError(
                "resistance_pa_per_m3_s_squared unit must be 'Pa/(m3/s)^2'"
            )
        if self.fixed_pressure_pa.lower < 0:
            raise ValueError(
                "fixed_pressure_pa lower uncertainty bound must remain >= 0"
            )
        if self.resistance_pa_per_m3_s_squared.lower <= 0:
            raise ValueError(
                "resistance_pa_per_m3_s_squared lower uncertainty bound must remain > 0"
            )
