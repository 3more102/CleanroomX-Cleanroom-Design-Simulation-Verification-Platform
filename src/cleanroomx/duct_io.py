from __future__ import annotations

import json
from pathlib import Path

from .hvac_models import DuctNetwork, DuctPath, DuctSegment


def duct_segment_from_dict(data: dict) -> DuctSegment:
    return DuctSegment(
        name=data["name"],
        airflow_m3_h=data["airflow_m3_h"],
        length_m=data["length_m"],
        darcy_friction_factor=data["darcy_friction_factor"],
        local_loss_coefficient=data.get("local_loss_coefficient", 0.0),
        air_density_kg_m3=data.get("air_density_kg_m3", 1.2),
        diameter_m=data.get("diameter_m"),
        width_m=data.get("width_m"),
        height_m=data.get("height_m"),
    )


def duct_path_from_dict(data: dict) -> DuctPath:
    return DuctPath(
        name=data["name"],
        segments=tuple(duct_segment_from_dict(item) for item in data["segments"]),
    )


def duct_network_from_dict(data: dict) -> DuctNetwork:
    return DuctNetwork(
        name=data["name"],
        paths=tuple(duct_path_from_dict(item) for item in data["paths"]),
    )


def load_duct_network(path: str | Path) -> DuctNetwork:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if "duct_network" in data:
        data = data["duct_network"]
    return duct_network_from_dict(data)
