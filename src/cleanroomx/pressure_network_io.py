from __future__ import annotations

from pathlib import Path

from .pressure_network import (
    PressureNode,
    PressurePath,
    PressureTarget,
    RoomPressureNetwork,
)
from .strict_json import load_strict_json


def _object(value: object, field_name: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    return dict(value)


def _objects(value: object, field_name: str) -> list[dict]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be an array")
    return [
        _object(item, f"{field_name}[{index}]")
        for index, item in enumerate(value)
    ]


def pressure_network_from_dict(data: dict) -> RoomPressureNetwork:
    payload = _object(data, "pressure network")
    try:
        name = payload.pop("name")
        node_data = payload.pop("nodes")
        path_data = payload.pop("paths")
    except KeyError as exc:
        raise ValueError(
            f"pressure network is missing required field: {exc.args[0]}"
        ) from exc
    target_data = payload.pop("targets", [])
    if payload:
        raise ValueError(
            "unsupported pressure-network field(s): "
            + ", ".join(sorted(payload))
        )

    try:
        nodes = tuple(
            PressureNode(**item)
            for item in _objects(node_data, "nodes")
        )
        paths = tuple(
            PressurePath(**item)
            for item in _objects(path_data, "paths")
        )
        targets = tuple(
            PressureTarget(**item)
            for item in _objects(target_data, "targets")
        )
    except TypeError as exc:
        raise ValueError(
            f"invalid pressure-network field set: {exc}"
        ) from exc

    return RoomPressureNetwork(
        name=name,
        nodes=nodes,
        paths=paths,
        targets=targets,
    )


def load_pressure_network(
    path: str | Path,
) -> RoomPressureNetwork:
    return pressure_network_from_dict(
        load_strict_json(path)
    )
