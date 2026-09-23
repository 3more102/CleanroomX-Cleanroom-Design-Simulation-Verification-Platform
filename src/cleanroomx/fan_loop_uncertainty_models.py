from __future__ import annotations

import math
from dataclasses import dataclass

from .fan_curve import FanCurve
from .fan_loop_network import FanLoopNetworkStudy
from .loop_network import LoopedFlowNetwork
from .uncertainty_models import Provenance, UncertainValue


def _nonnegative(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{field_name} must be finite and >= 0")
    return value


@dataclass(frozen=True)
class EdgeResistanceUncertainty:
    edge_name: str
    uncertainty_abs: float
    provenance: Provenance | None = None

    def __post_init__(self) -> None:
        if not self.edge_name.strip():
            raise ValueError("edge uncertainty name cannot be empty")
        object.__setattr__(
            self,
            "uncertainty_abs",
            _nonnegative(self.uncertainty_abs, "uncertainty_abs"),
        )


@dataclass(frozen=True)
class FanLoopNetworkUncertaintyStudy:
    name: str
    fan_curve: FanCurve
    loop_network: LoopedFlowNetwork
    fan_discharge_node: str
    fan_suction_node: str
    fixed_pressure_pa: UncertainValue
    edge_resistance_uncertainties: tuple[EdgeResistanceUncertainty, ...] = ()
    fan_curve_provenance: Provenance | None = None
    max_corner_cases: int = 256

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("fan/loop uncertainty study name cannot be empty")
        if self.fixed_pressure_pa.unit != "Pa":
            raise ValueError("fixed_pressure_pa unit must be 'Pa'")
        if self.fixed_pressure_pa.lower < 0:
            raise ValueError(
                "fixed_pressure_pa lower uncertainty bound must remain >= 0"
            )
        if (
            isinstance(self.max_corner_cases, bool)
            or not isinstance(self.max_corner_cases, int)
            or self.max_corner_cases <= 0
        ):
            raise ValueError("max_corner_cases must be an integer > 0")

        base_edges = {edge.name: edge for edge in self.loop_network.edges}
        normalized = tuple(
            sorted(
                self.edge_resistance_uncertainties,
                key=lambda item: item.edge_name,
            )
        )
        names = [item.edge_name for item in normalized]
        if len(names) != len(set(names)):
            raise ValueError(
                "edge resistance uncertainty names must be unique"
            )
        for item in normalized:
            if item.edge_name not in base_edges:
                raise ValueError(
                    "edge resistance uncertainty references unknown edge "
                    f"{item.edge_name!r}"
                )
            lower = (
                base_edges[item.edge_name].resistance_pa_per_m3_s_squared
                - item.uncertainty_abs
            )
            if lower <= 0:
                raise ValueError(
                    f"edge {item.edge_name!r} lower uncertainty bound "
                    "must remain > 0"
                )
        object.__setattr__(
            self, "edge_resistance_uncertainties", normalized
        )

        FanLoopNetworkStudy(
            name=self.name,
            fan_curve=self.fan_curve,
            loop_network=self.loop_network,
            fan_discharge_node=self.fan_discharge_node,
            fan_suction_node=self.fan_suction_node,
            fixed_pressure_pa=self.fixed_pressure_pa.value,
        )
