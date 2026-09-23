from __future__ import annotations

import json
from pathlib import Path

from .loop_geometry import ReferenceDuctEdge, ReferenceGeometryLoopNetwork


def reference_geometry_loop_from_dict(data: dict) -> ReferenceGeometryLoopNetwork:
    return ReferenceGeometryLoopNetwork(
        name=data["name"],
        node_injections_m3_h=dict(data["node_injections_m3_h"]),
        edges=tuple(ReferenceDuctEdge(**edge) for edge in data["edges"]),
        reference_node=data["reference_node"],
    )


def load_reference_geometry_loop(
    path: str | Path,
) -> ReferenceGeometryLoopNetwork:
    return reference_geometry_loop_from_dict(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )
