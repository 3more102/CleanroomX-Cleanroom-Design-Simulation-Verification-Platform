from __future__ import annotations

from pathlib import Path

from .jsonio import load_strict_json

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
        load_strict_json(path)
    )
