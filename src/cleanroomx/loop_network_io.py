from __future__ import annotations

import json
from pathlib import Path

from .duct import DuctSection, derive_duct_section_quadratic_resistance
from .loop_network import LoopedFlowNetwork, QuadraticFlowEdge


def _with_optional_friction_factor(data: dict) -> dict:
    values = dict(data)
    if (
        "friction_factor" not in values
        and (
            "absolute_roughness_m" in values
            or "kinematic_viscosity_m2_s" in values
        )
    ):
        values["friction_factor"] = None
    return values


def _edge_from_dict(data: dict) -> QuadraticFlowEdge:
    values = dict(data)
    duct_data = values.pop("duct", None)
    has_explicit_resistance = "resistance_pa_per_m3_s_squared" in values

    if has_explicit_resistance == (duct_data is not None):
        raise ValueError(
            "loop edge must provide exactly one of "
            "resistance_pa_per_m3_s_squared or duct"
        )

    if duct_data is None:
        return QuadraticFlowEdge(
            name=values["name"],
            start_node=values["start_node"],
            end_node=values["end_node"],
            resistance_pa_per_m3_s_squared=values[
                "resistance_pa_per_m3_s_squared"
            ],
            resistance_basis={"source": "explicit_resistance"},
        )

    duct_values = dict(duct_data)
    if "name" in duct_values or "airflow_m3_h" in duct_values:
        raise ValueError(
            "duct edge uses the outer edge name and reference_airflow_m3_h; "
            "do not provide duct name or airflow_m3_h"
        )
    try:
        reference_airflow_m3_h = duct_values.pop("reference_airflow_m3_h")
    except KeyError as exc:
        raise ValueError(
            "duct-derived loop edge requires reference_airflow_m3_h"
        ) from exc

    section = DuctSection(
        name=values["name"],
        airflow_m3_h=reference_airflow_m3_h,
        **_with_optional_friction_factor(duct_values),
    )
    derived = derive_duct_section_quadratic_resistance(section)
    basis = {"source": "duct_geometry", **derived}
    return QuadraticFlowEdge(
        name=values["name"],
        start_node=values["start_node"],
        end_node=values["end_node"],
        resistance_pa_per_m3_s_squared=derived[
            "quadratic_resistance_pa_per_m3_s_squared"
        ],
        resistance_basis=basis,
    )


def looped_flow_network_from_dict(data: dict) -> LoopedFlowNetwork:
    return LoopedFlowNetwork(
        name=data["name"],
        node_injections_m3_h=dict(data["node_injections_m3_h"]),
        edges=tuple(_edge_from_dict(edge) for edge in data["edges"]),
        reference_node=data["reference_node"],
    )


def load_looped_flow_network(path: str | Path) -> LoopedFlowNetwork:
    return looped_flow_network_from_dict(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )
