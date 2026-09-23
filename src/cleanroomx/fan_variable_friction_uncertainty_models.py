from __future__ import annotations

import math
from dataclasses import dataclass

from .fan_curve import FanCurve
from .fan_variable_friction_loop import FanVariableFrictionLoopStudy
from .loop_network import LoopedFlowNetwork
from .pressure_power import FanPowerEfficiencies
from .uncertainty_models import Provenance, UncertainValue


def _is_automatic_geometry_edge(edge) -> bool:
    evidence = edge.resistance_evidence
    return (
        edge.resistance_basis == "duct_geometry"
        and evidence is not None
        and evidence.get("absolute_roughness_m") is not None
        and evidence.get("kinematic_viscosity_m2_s") is not None
    )


@dataclass(frozen=True)
class FanVariableFrictionLoopUncertaintyStudy:
    name: str
    fan_curve: FanCurve
    loop_network: LoopedFlowNetwork
    fan_discharge_node: str
    fan_suction_node: str
    fixed_pressure_pa: UncertainValue
    edge_resistance_pa_per_m3_s_squared: dict[str, UncertainValue]
    power_efficiencies: FanPowerEfficiencies | None = None
    fan_curve_provenance: Provenance | None = None
    max_corner_cases: int = 256
    resistance_relative_tolerance: float = 1e-6
    relaxation: float = 0.5
    near_zero_airflow_m3_h: float = 1e-6
    max_outer_iterations: int = 50
    mass_balance_tolerance_m3_h: float = 1e-6
    max_newton_iterations: int = 100
    operating_pressure_tolerance_pa: float = 1e-6
    max_operating_iterations: int = 80

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError(
                "fan/variable-friction loop uncertainty study name cannot be empty"
            )
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
            edge = edges_by_name[edge_name]
            if _is_automatic_geometry_edge(edge):
                raise ValueError(
                    f"edge resistance uncertainty for {edge_name!r} cannot be "
                    "applied to an automatic-friction edge; bound physical "
                    "geometry/fluid inputs in a dedicated model instead of "
                    "freezing the nonlinear Darcy update"
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
            if not math.isclose(
                item.value,
                edge.resistance_pa_per_m3_s_squared,
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

        FanVariableFrictionLoopStudy(
            name=self.name,
            fan_curve=self.fan_curve,
            loop_network=self.loop_network,
            fan_discharge_node=self.fan_discharge_node,
            fan_suction_node=self.fan_suction_node,
            fixed_pressure_pa=self.fixed_pressure_pa.value,
            power_efficiencies=self.power_efficiencies,
            resistance_relative_tolerance=self.resistance_relative_tolerance,
            relaxation=self.relaxation,
            near_zero_airflow_m3_h=self.near_zero_airflow_m3_h,
            max_outer_iterations=self.max_outer_iterations,
            mass_balance_tolerance_m3_h=self.mass_balance_tolerance_m3_h,
            max_newton_iterations=self.max_newton_iterations,
            operating_pressure_tolerance_pa=self.operating_pressure_tolerance_pa,
            max_operating_iterations=self.max_operating_iterations,
        )
