from __future__ import annotations

import math
from dataclasses import dataclass

from .fan_curve import FanCurve
from .fan_loop_network import FanLoopNetworkStudy
from .loop_network import LoopedFlowNetwork
from .uncertainty_models import Provenance, UncertainValue


@dataclass(frozen=True)
class FanLoopNetworkUncertaintyStudy:
    name: str
    fan_curve: FanCurve
    loop_network: LoopedFlowNetwork
    fan_discharge_node: str
    fan_suction_node: str
    fixed_pressure_pa: UncertainValue
    edge_resistance_pa_per_m3_s_squared: dict[str, UncertainValue]
    fan_curve_provenance: Provenance | None = None
    max_corner_cases: int = 256

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("fan/loop-network uncertainty study name cannot be empty")
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

        edges_by_name = {edge.name: edge for edge in self.loop_network.edges}
        normalized: dict[str, UncertainValue] = {}
        for edge_name, item in self.edge_resistance_pa_per_m3_s_squared.items():
            if edge_name not in edges_by_name:
                raise ValueError(
                    "edge resistance uncertainty references unknown edge "
                    f"{edge_name!r}"
                )
            if item.unit != "Pa/(m3/s)^2":
                raise ValueError(
                    f"edge resistance uncertainty for {edge_name!r} "
                    "must use unit 'Pa/(m3/s)^2'"
                )
            if item.lower <= 0:
                raise ValueError(
                    f"edge resistance lower uncertainty bound for {edge_name!r} "
                    "must remain > 0"
                )

            nominal_resistance = (
                edges_by_name[edge_name].resistance_pa_per_m3_s_squared
            )
            if not math.isclose(
                item.value,
                nominal_resistance,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                raise ValueError(
                    f"edge uncertainty nominal for {edge_name!r} must match "
                    "the loop-network edge resistance"
                )
            normalized[edge_name] = item
        object.__setattr__(
            self,
            "edge_resistance_pa_per_m3_s_squared",
            normalized,
        )

        FanLoopNetworkStudy(
            name=self.name,
            fan_curve=self.fan_curve,
            loop_network=self.loop_network,
            fan_discharge_node=self.fan_discharge_node,
            fan_suction_node=self.fan_suction_node,
            fixed_pressure_pa=self.fixed_pressure_pa.value,
        )
