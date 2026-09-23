from __future__ import annotations

import json
from pathlib import Path

from .duct import DuctSection
from .loop_duct_network import LoopDuctEdge, LoopDuctNetworkStudy


def loop_duct_network_study_from_dict(data: dict) -> LoopDuctNetworkStudy:
    edges: list[LoopDuctEdge] = []
    for edge in data["edges"]:
        section_data = dict(edge["section"])
        section_data.setdefault("name", edge["name"])
        section_data.setdefault("friction_factor", None)
        edges.append(
            LoopDuctEdge(
                name=edge["name"],
                start_node=edge["start_node"],
                end_node=edge["end_node"],
                section=DuctSection(**section_data),
            )
        )

    return LoopDuctNetworkStudy(
        name=data["name"],
        node_injections_m3_h=dict(data["node_injections_m3_h"]),
        edges=tuple(edges),
        reference_node=data["reference_node"],
    )


def load_loop_duct_network_study(
    path: str | Path,
) -> LoopDuctNetworkStudy:
    return loop_duct_network_study_from_dict(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )
