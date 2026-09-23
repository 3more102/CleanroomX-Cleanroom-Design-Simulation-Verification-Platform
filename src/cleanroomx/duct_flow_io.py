from __future__ import annotations

import json
from pathlib import Path

from .duct_flow import ParallelFlowNetwork, ParallelFlowPath, ParallelFlowSection


def parallel_flow_network_from_dict(data: dict) -> ParallelFlowNetwork:
    return ParallelFlowNetwork(
        name=data["name"],
        total_airflow_m3_h=data["total_airflow_m3_h"],
        paths=tuple(
            ParallelFlowPath(
                name=path["name"],
                sections=tuple(
                    ParallelFlowSection(**section) for section in path["sections"]
                ),
            )
            for path in data["paths"]
        ),
    )


def load_parallel_flow_network(path: str | Path) -> ParallelFlowNetwork:
    return parallel_flow_network_from_dict(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )
