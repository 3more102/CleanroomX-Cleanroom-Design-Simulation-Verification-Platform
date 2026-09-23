from __future__ import annotations

import json
from pathlib import Path

from .loop_network import LoopedFlowNetwork, QuadraticFlowEdge
from .loop_resistance import (
    LoopedDuctResistanceInput,
    derive_loop_edge_resistance,
)


def _edge_from_dict(data: dict) -> QuadraticFlowEdge:
    edge = dict(data)
    has_explicit = "resistance_pa_per_m3_s_squared" in edge
    has_geometry = "duct_geometry" in edge
    if has_explicit == has_geometry:
        raise ValueError(
            "each loop-network edge must provide exactly one of "
            "resistance_pa_per_m3_s_squared or duct_geometry"
        )

    name = edge.pop("name")
    start_node = edge.pop("start_node")
    end_node = edge.pop("end_node")

    if has_explicit:
        resistance = edge.pop("resistance_pa_per_m3_s_squared")
        if edge:
            raise ValueError(
                "unsupported explicit-resistance edge field(s): "
                + ", ".join(sorted(edge))
            )
        return QuadraticFlowEdge(
            name=name,
            start_node=start_node,
            end_node=end_node,
            resistance_pa_per_m3_s_squared=resistance,
        )

    geometry = edge.pop("duct_geometry")
    if edge:
        raise ValueError(
            "unsupported geometry-derived edge field(s): "
            + ", ".join(sorted(edge))
        )
    if not isinstance(geometry, dict):
        raise ValueError("duct_geometry must be an object")

    evidence = derive_loop_edge_resistance(
        LoopedDuctResistanceInput(**geometry)
    )
    return QuadraticFlowEdge(
        name=name,
        start_node=start_node,
        end_node=end_node,
        resistance_pa_per_m3_s_squared=evidence[
            "resistance_pa_per_m3_s_squared"
        ],
        resistance_basis="duct_geometry",
        resistance_evidence=evidence,
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
