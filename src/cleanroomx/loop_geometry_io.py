from __future__ import annotations

import json
from pathlib import Path

from .loop_geometry import (
    ReferenceDuctEdge,
    ReferenceDuctSection,
    ReferenceGeometryLoopNetwork,
)


def reference_geometry_loop_from_dict(data: dict) -> ReferenceGeometryLoopNetwork:
    edges = []
    for edge_data in data["edges"]:
        sections = tuple(
            ReferenceDuctSection(**section)
            for section in edge_data["sections"]
        )
        edges.append(
            ReferenceDuctEdge(
                name=edge_data["name"],
                start_node=edge_data["start_node"],
                end_node=edge_data["end_node"],
                reference_airflow_m3_h=edge_data["reference_airflow_m3_h"],
                sections=sections,
            )
        )
    return ReferenceGeometryLoopNetwork(
        name=data["name"],
        node_injections_m3_h=dict(data["node_injections_m3_h"]),
        edges=tuple(edges),
        reference_node=data["reference_node"],
    )


def load_reference_geometry_loop(
    path: str | Path,
) -> ReferenceGeometryLoopNetwork:
    return reference_geometry_loop_from_dict(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )
