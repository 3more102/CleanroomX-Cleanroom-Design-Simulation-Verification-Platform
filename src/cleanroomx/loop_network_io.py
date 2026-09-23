from __future__ import annotations

import json
from pathlib import Path

from .loop_network import LoopedFlowNetwork, QuadraticFlowEdge


def looped_flow_network_from_dict(data: dict) -> LoopedFlowNetwork:
    return LoopedFlowNetwork(
        name=data["name"],
        node_injections_m3_h=dict(data["node_injections_m3_h"]),
        edges=tuple(
            QuadraticFlowEdge(**edge)
            for edge in data["edges"]
        ),
        reference_node=data["reference_node"],
    )


def load_looped_flow_network(path: str | Path) -> LoopedFlowNetwork:
    return looped_flow_network_from_dict(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )
