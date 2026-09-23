from __future__ import annotations

from dataclasses import dataclass

from .fan_loop_network import FanLoopNetworkStudy
from .uncertainty_models import Provenance, UncertainValue


_RESISTANCE_UNIT = "Pa/(m3/s)^2"


@dataclass(frozen=True)
class FanLoopNetworkUncertaintyStudy:
    name: str
    fan_loop_study: FanLoopNetworkStudy
    fixed_pressure_pa: UncertainValue
    edge_resistances: dict[str, UncertainValue]
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

        network_edges = {
            edge.name: edge
            for edge in self.fan_loop_study.loop_network.edges
        }
        if set(self.edge_resistances) != set(network_edges):
            missing = sorted(set(network_edges) - set(self.edge_resistances))
            extra = sorted(set(self.edge_resistances) - set(network_edges))
            details = []
            if missing:
                details.append("missing: " + ", ".join(missing))
            if extra:
                details.append("unknown: " + ", ".join(extra))
            raise ValueError(
                "edge_resistances must match loop-network edge names"
                + (f" ({'; '.join(details)})" if details else "")
            )

        normalized = dict(self.edge_resistances)
        for edge_name, item in normalized.items():
            if item.unit != _RESISTANCE_UNIT:
                raise ValueError(
                    f"edge resistance unit for {edge_name!r} must be "
                    f"{_RESISTANCE_UNIT!r}"
                )
            if item.lower <= 0:
                raise ValueError(
                    f"edge resistance lower uncertainty bound for {edge_name!r} "
                    "must remain > 0"
                )
            nominal = network_edges[edge_name].resistance_pa_per_m3_s_squared
            if abs(item.value - nominal) > max(1e-12, abs(nominal) * 1e-12):
                raise ValueError(
                    f"edge resistance nominal value for {edge_name!r} must match "
                    "the loop-network resistance"
                )

        if abs(
            self.fixed_pressure_pa.value
            - self.fan_loop_study.fixed_pressure_pa
        ) > max(1e-12, abs(self.fan_loop_study.fixed_pressure_pa) * 1e-12):
            raise ValueError(
                "fixed_pressure_pa nominal value must match fan_loop_study"
            )

        object.__setattr__(self, "edge_resistances", normalized)
