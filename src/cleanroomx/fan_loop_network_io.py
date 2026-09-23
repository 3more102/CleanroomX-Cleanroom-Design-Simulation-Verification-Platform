from __future__ import annotations

import json
from pathlib import Path

from .fan_curve import FanCurve, FanCurvePoint
from .fan_loop_network import FanDrivenLoopNetworkStudy
from .loop_network_io import looped_flow_network_from_dict


def fan_driven_loop_network_study_from_dict(
    data: dict,
) -> FanDrivenLoopNetworkStudy:
    fan_data = data["fan_curve"]
    loop_data = dict(data["loop_network"])
    if "node_injections_m3_h" in loop_data:
        raise ValueError(
            "fan-driven loop input owns the source/sink injection pattern; "
            "do not provide loop_network.node_injections_m3_h"
        )

    edges = loop_data["edges"]
    nodes: list[str] = []
    for edge in edges:
        for key in ("start_node", "end_node"):
            node = edge[key]
            if node not in nodes:
                nodes.append(node)

    source_node = data["source_node"]
    sink_node = data["sink_node"]
    if source_node not in nodes or sink_node not in nodes:
        raise ValueError("source_node and sink_node must appear in loop-network edges")

    reference_airflow = data.get("network_reference_airflow_m3_h", 3600.0)
    injections = {node: 0.0 for node in nodes}
    injections[source_node] = reference_airflow
    injections[sink_node] = -reference_airflow

    reference_network = looped_flow_network_from_dict(
        {
            "name": loop_data.get("name", f"{data['name']} passive loop"),
            "reference_node": loop_data.get("reference_node", sink_node),
            "node_injections_m3_h": injections,
            "edges": edges,
        }
    )

    return FanDrivenLoopNetworkStudy(
        name=data["name"],
        fan_curve=FanCurve(
            name=fan_data["name"],
            points=tuple(FanCurvePoint(**point) for point in fan_data["points"]),
        ),
        fixed_pressure_pa=data.get("fixed_pressure_pa", 0.0),
        reference_network=reference_network,
        source_node=source_node,
        sink_node=sink_node,
    )


def load_fan_driven_loop_network_study(
    path: str | Path,
) -> FanDrivenLoopNetworkStudy:
    return fan_driven_loop_network_study_from_dict(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )
