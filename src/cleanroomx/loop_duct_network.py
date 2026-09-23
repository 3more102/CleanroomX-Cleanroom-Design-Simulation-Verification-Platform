from __future__ import annotations

from dataclasses import dataclass

from .duct import DuctSection, derive_duct_section_quadratic_resistance
from .loop_network import LoopedFlowNetwork, QuadraticFlowEdge, solve_looped_network


@dataclass(frozen=True)
class LoopDuctEdge:
    name: str
    start_node: str
    end_node: str
    section: DuctSection

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("loop-duct edge name cannot be empty")
        if not self.start_node.strip() or not self.end_node.strip():
            raise ValueError("loop-duct edge node names cannot be empty")
        if self.start_node == self.end_node:
            raise ValueError("loop-duct edge cannot connect a node to itself")


@dataclass(frozen=True)
class LoopDuctNetworkStudy:
    name: str
    node_injections_m3_h: dict[str, float]
    edges: tuple[LoopDuctEdge, ...]
    reference_node: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("loop-duct study name cannot be empty")
        if not self.edges:
            raise ValueError("loop-duct study requires at least one edge")


def _derived_edge(edge: LoopDuctEdge) -> tuple[QuadraticFlowEdge, dict]:
    basis = derive_duct_section_quadratic_resistance(edge.section)
    resistance = basis["quadratic_resistance_pa_per_m3_s_squared"]
    if resistance <= 0:
        raise ValueError(
            f"loop-duct edge {edge.name!r} has zero derived quadratic resistance"
        )
    fixed_edge = QuadraticFlowEdge(
        name=edge.name,
        start_node=edge.start_node,
        end_node=edge.end_node,
        resistance_pa_per_m3_s_squared=resistance,
    )
    return fixed_edge, basis


def derive_fixed_loop_network(
    study: LoopDuctNetworkStudy,
) -> tuple[LoopedFlowNetwork, dict[str, dict]]:
    fixed_edges: list[QuadraticFlowEdge] = []
    basis_by_edge: dict[str, dict] = {}
    for edge in study.edges:
        fixed_edge, basis = _derived_edge(edge)
        fixed_edges.append(fixed_edge)
        if edge.name in basis_by_edge:
            raise ValueError("loop-duct edge names must be unique")
        basis_by_edge[edge.name] = basis

    network = LoopedFlowNetwork(
        name=study.name,
        node_injections_m3_h=dict(study.node_injections_m3_h),
        edges=tuple(fixed_edges),
        reference_node=study.reference_node,
    )
    return network, basis_by_edge


def analyze_loop_duct_network(
    study: LoopDuctNetworkStudy,
    *,
    mass_balance_tolerance_m3_h: float = 1e-6,
    max_iterations: int = 100,
) -> dict:
    network, basis_by_edge = derive_fixed_loop_network(study)
    solved = solve_looped_network(
        network,
        mass_balance_tolerance_m3_h=mass_balance_tolerance_m3_h,
        max_iterations=max_iterations,
    )

    enriched_edges: list[dict] = []
    for edge in solved["edges"]:
        basis = basis_by_edge[edge["name"]]
        enriched = dict(edge)
        enriched.update(
            {
                "resistance_basis": "duct_geometry_at_reference_flow",
                "reference_airflow_m3_h": round(
                    basis["reference_airflow_m3_h"], 6
                ),
                "reference_pressure_drop_pa": round(
                    basis["reference_pressure_drop_pa"], 9
                ),
                "shape": basis["shape"],
                "area_m2": round(basis["area_m2"], 9),
                "hydraulic_diameter_m": round(
                    basis["hydraulic_diameter_m"], 9
                ),
                "length_m": round(basis["length_m"], 6),
                "air_density_kg_m3": round(
                    basis["air_density_kg_m3"], 6
                ),
                "local_loss_coefficient": round(
                    basis["local_loss_coefficient"], 9
                ),
                "friction_factor": round(basis["friction_factor"], 9),
                "friction_factor_method": basis["friction_factor_method"],
                "reynolds_number": (
                    None
                    if basis["reynolds_number"] is None
                    else round(basis["reynolds_number"], 6)
                ),
                "absolute_roughness_m": basis["absolute_roughness_m"],
                "relative_roughness": (
                    None
                    if basis["relative_roughness"] is None
                    else round(basis["relative_roughness"], 12)
                ),
                "kinematic_viscosity_m2_s": basis[
                    "kinematic_viscosity_m2_s"
                ],
            }
        )
        enriched_edges.append(enriched)

    result = dict(solved)
    result["study"] = study.name
    result["resistance_basis"] = "duct_geometry_at_reference_flow"
    result["edges"] = enriched_edges
    result["scope_note"] = (
        "Each loop edge is converted once to a fixed quadratic resistance from "
        "explicit duct geometry, density, local-loss coefficient, and a Darcy "
        "factor evaluated at that edge's configured reference airflow. The "
        "loop solver then holds that resistance fixed while balancing the mesh. "
        "Automatic friction may be resolved at the reference condition, but "
        "friction is not iterated as solved flow changes. Fan curves, dampers, "
        "controls, leakage, system effect, compressibility, and transient "
        "behavior are outside this bounded workflow."
    )
    return result
