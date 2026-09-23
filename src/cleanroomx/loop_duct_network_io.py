from __future__ import annotations

import json
from pathlib import Path

from .duct import DuctSection
from .loop_duct_network import GeometryDerivedLoopEdge, GeometryDerivedLoopNetwork


def _section_from_dict(data: dict, reference_airflow_m3_h: float) -> DuctSection:
    values = dict(data)
    if "airflow_m3_h" in values:
        raise ValueError(
            "geometry-derived loop sections must not define airflow_m3_h; "
            "use the edge reference_airflow_m3_h"
        )
    values["airflow_m3_h"] = reference_airflow_m3_h
    values.setdefault("friction_factor", None)
    return DuctSection(**values)


def geometry_derived_loop_network_from_dict(data: dict) -> GeometryDerivedLoopNetwork:
    edges = []
    for edge_data in data["edges"]:
        reference_airflow = edge_data["reference_airflow_m3_h"]
        edges.append(
            GeometryDerivedLoopEdge(
                name=edge_data["name"],
                start_node=edge_data["start_node"],
                end_node=edge_data["end_node"],
                reference_airflow_m3_h=reference_airflow,
                sections=tuple(
                    _section_from_dict(section, reference_airflow)
                    for section in edge_data["sections"]
                ),
            )
        )
    return GeometryDerivedLoopNetwork(
        name=data["name"],
        node_injections_m3_h=dict(data["node_injections_m3_h"]),
        edges=tuple(edges),
        reference_node=data["reference_node"],
    )


def load_geometry_derived_loop_network(
    path: str | Path,
) -> GeometryDerivedLoopNetwork:
    return geometry_derived_loop_network_from_dict(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )
