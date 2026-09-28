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


def _strict_numeric_fields(
    item: dict,
    field_name: str,
    numeric_fields: frozenset[str],
) -> dict:
    normalized = dict(item)
    for key in numeric_fields:
        if key not in normalized or normalized[key] is None:
            continue
        value = normalized[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(
                f"{field_name}.{key} must be a finite number"
            )
    return normalized


_NODE_NUMERIC_FIELDS = frozenset(
    {
        "supply_m3_h",
        "return_m3_h",
        "exhaust_m3_h",
        "fixed_pressure_pa",
    }
)
_PATH_NUMERIC_FIELDS = frozenset(
    {
        "coefficient_m3_s_pa_n",
        "exponent",
        "discharge_coefficient",
        "area_m2",
        "air_density_kg_m3",
        "pressure_offset_pa",
        "linearization_pressure_pa",
    }
)
_TARGET_NUMERIC_FIELDS = frozenset(
    {
        "minimum_delta_pa",
        "maximum_delta_pa",
    }
)


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
            PressureNode(
                **_strict_numeric_fields(
                    item,
                    f"nodes[{index}]",
                    _NODE_NUMERIC_FIELDS,
                )
            )
            for index, item in enumerate(
                _objects(node_data, "nodes")
            )
        )
        paths = tuple(
            PressurePath(
                **_strict_numeric_fields(
                    item,
                    f"paths[{index}]",
                    _PATH_NUMERIC_FIELDS,
                )
            )
            for index, item in enumerate(
                _objects(path_data, "paths")
            )
        )
        targets = tuple(
            PressureTarget(
                **_strict_numeric_fields(
                    item,
                    f"targets[{index}]",
                    _TARGET_NUMERIC_FIELDS,
                )
            )
            for index, item in enumerate(
                _objects(target_data, "targets")
            )
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
