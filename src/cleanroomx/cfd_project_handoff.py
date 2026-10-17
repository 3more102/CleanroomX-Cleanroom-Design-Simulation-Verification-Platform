"""Explicit, dimension-only handoff from CleanroomX rooms to OpenFOAM specs."""
from __future__ import annotations

import copy
import math
from typing import Any

from .cfd_openfoam import (
    PROJECT_GEOMETRY_OMISSIONS,
    PROJECT_GEOMETRY_SCHEMA,
    validate_openfoam_spec,
)
from .spatial_integrity import SPATIAL_LAYOUT_VERSION


def project_room_openfoam_spec(
    template_spec: dict[str, Any],
    *,
    project_name: str,
    spatial_layout: dict[str, Any],
    selection_kind: str,
    selected_room_id: str,
) -> dict[str, Any]:
    """Copy one selected room's dimensions into a validated OpenFOAM spec.

    This handoff intentionally does not map devices, openings, adjacency, flow,
    or boundary conditions. Those remain explicit template inputs and review items.
    """
    validate_openfoam_spec(template_spec)
    if not isinstance(project_name, str) or not project_name.strip():
        raise ValueError("project name must be nonempty")
    if selection_kind != "room":
        raise ValueError("select a room in the CleanroomX design workspace first")
    if not isinstance(selected_room_id, str) or not selected_room_id.strip():
        raise ValueError("selected room ID must be nonempty")
    if type(spatial_layout) is not dict:
        raise ValueError("CleanroomX spatial layout is unavailable")
    if spatial_layout.get("version") != SPATIAL_LAYOUT_VERSION:
        raise ValueError("unsupported CleanroomX spatial layout version")
    rooms = spatial_layout.get("rooms")
    if type(rooms) is not list:
        raise ValueError("CleanroomX spatial layout has no room list")
    matches = [
        room
        for room in rooms
        if type(room) is dict and room.get("id") == selected_room_id
    ]
    if len(matches) != 1:
        raise ValueError("selected room is missing or ambiguous in the current layout")
    room = matches[0]
    room_name = room.get("name")
    if not isinstance(room_name, str) or not room_name.strip():
        raise ValueError("selected room name must be nonempty")
    dimensions: list[float] = []
    for field in ("length_m", "width_m", "height_m"):
        value = room.get(field)
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"selected room {field} must be finite and positive")
        dimensions.append(float(value))

    result = copy.deepcopy(template_spec)
    result["name"] = f"{project_name.strip()} — {room_name.strip()}"
    result["room_m"] = dimensions
    result["project_geometry"] = {
        "schema": PROJECT_GEOMETRY_SCHEMA,
        "project_name": project_name.strip(),
        "room_id": selected_room_id.strip(),
        "room_name": room_name.strip(),
        "dimensions_m": list(dimensions),
        "mapping": "rectangular_room_envelope_only",
        "omitted": list(PROJECT_GEOMETRY_OMISSIONS),
    }
    validate_openfoam_spec(result)
    return result
