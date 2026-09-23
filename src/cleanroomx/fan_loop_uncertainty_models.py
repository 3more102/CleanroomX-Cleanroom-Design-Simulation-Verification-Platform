from __future__ import annotations

from dataclasses import dataclass

from .fan_curve import FanCurve
from .fan_loop_network import FanLoopNetworkStudy
from .loop_network import LoopedFlowNetwork
from .uncertainty_models import Provenance, UncertainValue


@dataclass(frozen=True)
class FanLoopUncertaintyStudy:
    name: str
    fan_curve: FanCurve
    loop_network: LoopedFlowNetwork
    fan_discharge_node: str
    fan_suction_node: str
    fixed_pressure_pa: UncertainValue
    edge_resistance_multipliers: dict[str, UncertainValue]
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

        edge_names = {edge.name for edge in self.loop_network.edges}
        normalized: dict[str, UncertainValue] = {}
        for edge_name, multiplier in self.edge_resistance_multipliers.items():
            if edge_name not in edge_names:
                raise ValueError(
                    f"edge_resistance_multipliers references unknown edge {edge_name!r}"
                )
            if multiplier.unit != "ratio":
                raise ValueError(
                    f"edge resistance multiplier for {edge_name!r} "
                    "must use unit 'ratio'"
                )
            if multiplier.lower <= 0:
                raise ValueError(
                    f"edge resistance multiplier for {edge_name!r} "
                    "must have a lower uncertainty bound > 0"
                )
            normalized[edge_name] = multiplier
        object.__setattr__(self, "edge_resistance_multipliers", normalized)

        FanLoopNetworkStudy(
            name=self.name,
            fan_curve=self.fan_curve,
            loop_network=self.loop_network,
            fan_discharge_node=self.fan_discharge_node,
            fan_suction_node=self.fan_suction_node,
            fixed_pressure_pa=self.fixed_pressure_pa.value,
        )
