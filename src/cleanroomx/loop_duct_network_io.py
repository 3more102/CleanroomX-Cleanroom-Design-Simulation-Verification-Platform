from __future__ import annotations

import json
from pathlib import Path

from .loop_duct_network import (
    FixedFrictionDuctSection,
    GeometryLoopEdge,
    GeometryLoopNetwork,
)


def geometry_loop_network_from_dict(data: dict) -> GeometryLoopNetwork:
    edges = []
    for edge_data in data["edges"]:
        sections = []
        for section_data in edge_data["sections"]:
            if (
                "absolute_roughness_m" in section_data
                or "kinematic_viscosity_m2_s" in section_data
            ):
                raise ValueError(
                    "geometry-derived loop solving requires an explicit fixed "
                    "friction_factor; automatic/flow-dependent friction is outside "
                    "this workflow"
                )
            sections.append(FixedFrictionDuctSection(**section_data))
        edges.append(
            GeometryLoopEdge(
                name=edge_data["name"],
                start_node=edge_data["start_node"],
                end_node=edge_data["end_node"],
                sections=tuple(sections),
            )
        )
    return GeometryLoopNetwork(
        name=data["name"],
        node_injections_m3_h=dict(data["node_injections_m3_h"]),
        edges=tuple(edges),
        reference_node=data["reference_node"],
    )


def load_geometry_loop_network(path: str | Path) -> GeometryLoopNetwork:
    return geometry_loop_network_from_dict(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )
