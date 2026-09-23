from __future__ import annotations

import json
from pathlib import Path

from .duct import DuctSection
from .loop_network_geometry import GeometryLoopedFlowNetwork, LoopDuctEdge


def _duct_section_from_dict(data: dict) -> DuctSection:
    values = dict(data)
    if (
        "friction_factor" not in values
        and (
            "absolute_roughness_m" in values
            or "kinematic_viscosity_m2_s" in values
        )
    ):
        values["friction_factor"] = None
    return DuctSection(**values)


def geometry_looped_flow_network_from_dict(
    data: dict,
) -> GeometryLoopedFlowNetwork:
    return GeometryLoopedFlowNetwork(
        name=data["name"],
        node_injections_m3_h=dict(data["node_injections_m3_h"]),
        edges=tuple(
            LoopDuctEdge(
                name=edge["name"],
                start_node=edge["start_node"],
                end_node=edge["end_node"],
                sections=tuple(
                    _duct_section_from_dict(section)
                    for section in edge["sections"]
                ),
            )
            for edge in data["edges"]
        ),
        reference_node=data["reference_node"],
    )


def load_geometry_looped_flow_network(
    path: str | Path,
) -> GeometryLoopedFlowNetwork:
    return geometry_looped_flow_network_from_dict(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )
