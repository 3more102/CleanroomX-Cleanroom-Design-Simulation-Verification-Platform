"""Door aperture geometry for CleanroomX's spatial design visualization.

Coordinates are room-relative for the wall axis (u) and z. This module
only produces depiction geometry. It neither cuts a CFD mesh nor models
door-opening flow or closed-door leakage.
"""
from __future__ import annotations

import math

EPS = 1e-8


def door_aperture(room: dict, door: dict) -> dict | None:
    """Return the wall-aligned aperture or None for an invalid/off-wall door."""
    if door.get("type") != "door" or door.get("room_id") != room.get("id"):
        return None
    side = door.get("wall_side")
    if side not in ("east", "west", "north", "south"):
        return None
    try:
        x, y, z = (float(door[k]) for k in ("x_m", "y_m", "z_m"))
        width, height = (float(door[k]) for k in ("width_m", "height_m"))
        rx, ry = float(room["x_m"]), float(room["y_m"])
        length, depth, ceiling = (
            float(room[k]) for k in ("length_m", "width_m", "height_m")
        )
    except (TypeError, ValueError, KeyError):
        return None
    if not all(math.isfinite(v) for v in (
        x, y, z, width, height, rx, ry, length, depth, ceiling
    )):
        return None
    if width <= EPS or height <= EPS or length <= EPS or depth <= EPS:
        return None
    if side in ("east", "west"):
        wall_x = rx + length if side == "east" else rx
        if abs(x - wall_x) > EPS:
            return None
        u, span = y - ry, depth
    else:
        wall_y = ry + depth if side == "north" else ry
        if abs(y - wall_y) > EPS:
            return None
        u, span = x - rx, length
    low, high = u - width / 2, u + width / 2
    if low < -EPS or high > span + EPS or z < -EPS or z + height > ceiling + EPS:
        return None
    return {
        "side": side,
        "u0": max(0.0, low),
        "u1": min(span, high),
        "z0": max(0.0, z),
        "z1": min(ceiling, z + height),
    }


def adjoining_room(room: dict, door: dict, rooms: list[dict]) -> dict | None:
    """Locate exactly one physical neighbor over the aperture, if present.

    An exterior door legitimately returns None. Ambiguous overlapping
    neighbors also return None rather than inventing a connection.
    """
    aperture = door_aperture(room, door)
    if aperture is None:
        return None
    side = aperture["side"]
    candidate_rooms = []
    try:
        rz = float(room.get("floor_elevation_m", 0))
        for other in rooms:
            if other["id"] == room["id"]:
                continue
            oz = float(other.get("floor_elevation_m", 0))
            if abs(oz - rz) > EPS:
                continue
            if float(other["height_m"]) + EPS < aperture["z1"]:
                continue
            if side in ("east", "west"):
                other_wall = float(other["x_m"]) if side == "east" else (
                    float(other["x_m"]) + float(other["length_m"])
                )
                owner_wall = float(room["x_m"]) + (
                    float(room["length_m"]) if side == "east" else 0
                )
                if abs(other_wall - owner_wall) > EPS:
                    continue
                low = float(room["y_m"]) + aperture["u0"]
                high = float(room["y_m"]) + aperture["u1"]
                other_low = float(other["y_m"])
                other_high = other_low + float(other["width_m"])
            else:
                other_wall = float(other["y_m"]) if side == "north" else (
                    float(other["y_m"]) + float(other["width_m"])
                )
                owner_wall = float(room["y_m"]) + (
                    float(room["width_m"]) if side == "north" else 0
                )
                if abs(other_wall - owner_wall) > EPS:
                    continue
                low = float(room["x_m"]) + aperture["u0"]
                high = float(room["x_m"]) + aperture["u1"]
                other_low = float(other["x_m"])
                other_high = other_low + float(other["length_m"])
            if low >= other_low - EPS and high <= other_high + EPS:
                candidate_rooms.append(other)
    except (KeyError, TypeError, ValueError):
        return None
    return candidate_rooms[0] if len(candidate_rooms) == 1 else None


def solid_wall_panels(
    span: float, height: float, apertures: list[dict]
) -> list[tuple[float, float, float, float]]:
    """Partition a wall into non-opening rectangles (u0,u1,z0,z1).

    Supports multiple non-overlapping or overlapping rectangular apertures
    with arbitrary sill/head heights, including doors to floor level.
    """
    valid = [
        a for a in apertures
        if 0 <= a["u0"] < a["u1"] <= span
        and 0 <= a["z0"] < a["z1"] <= height
    ]
    boundaries = sorted({0.0, span} | {
        value for a in valid for value in (a["u0"], a["u1"])
    })
    patches = []
    for u0, u1 in zip(boundaries, boundaries[1:]):
        if u1 - u0 <= EPS:
            continue
        mid = (u0 + u1) / 2
        removed = sorted(
            (a["z0"], a["z1"])
            for a in valid if a["u0"] - EPS <= mid <= a["u1"] + EPS
        )
        cursor = 0.0
        for z0, z1 in removed:
            if z0 > cursor + EPS:
                patches.append((u0, u1, cursor, z0))
            cursor = max(cursor, z1)
        if cursor < height - EPS:
            patches.append((u0, u1, cursor, height))
    return patches


def wall_point(room: dict, side: str, u: float, z: float) -> tuple[float, float, float]:
    """Map a point on a room wall into world-space XYZ."""
    z_world = float(room.get("floor_elevation_m", 0)) + z
    if side == "east":
        return float(room["x_m"]) + float(room["length_m"]), float(room["y_m"]) + u, z_world
    if side == "west":
        return float(room["x_m"]), float(room["y_m"]) + u, z_world
    if side == "north":
        return float(room["x_m"]) + u, float(room["y_m"]) + float(room["width_m"]), z_world
    if side == "south":
        return float(room["x_m"]) + u, float(room["y_m"]), z_world
    raise ValueError("unsupported wall side")


def opening_corners(room: dict, aperture: dict) -> tuple[tuple[float, float, float], ...]:
    """Door bottom-left, bottom-right, top-right, top-left in wall coordinates."""
    side = aperture["side"]
    return tuple(
        wall_point(room, side, u, z)
        for u, z in (
            (aperture["u0"], aperture["z0"]),
            (aperture["u1"], aperture["z0"]),
            (aperture["u1"], aperture["z1"]),
            (aperture["u0"], aperture["z1"]),
        )
    )


def door_leaf_corners(room: dict, door: dict, aperture: dict) -> tuple:
    """Depict a closed panel or a 90-degree leaf hinged into its owner room."""
    corners = list(opening_corners(room, aperture))
    if door.get("door_state", "closed") == "closed":
        return tuple(corners)
    if door.get("door_state") != "open":
        raise ValueError("Door state must be open or closed")
    outward = {"east":(1,0),"west":(-1,0),"north":(0,1),"south":(0,-1)}[aperture["side"]]
    hinge, free = (1,0) if door.get("swing")=="right" else (0,1)
    width = aperture["u1"]-aperture["u0"]
    for base, top in ((hinge,3-hinge),(free,3-free)):
        if base == free:
            anchor=corners[hinge]
            corners[base]=(anchor[0]-outward[0]*width,anchor[1]-outward[1]*width,corners[base][2])
            corners[top]=(anchor[0]-outward[0]*width,anchor[1]-outward[1]*width,corners[top][2])
    return tuple(corners)
