"""Geometry-only preflight for compiling a CleanroomX spatial suite to CFD.

This intentionally does *not* generate OpenFOAM dictionaries or infer missing
wall openings, airflows, pressure conditions, or regulatory thresholds.
Only the canonical persisted spatial_layout schema is accepted.
"""
from __future__ import annotations

from collections import deque
import hashlib
import json
import math
from typing import Any

from .spatial_integrity import validate_spatial_layout_document

SCHEMA = "cleanroomx.cfd-suite-topology.v1"
TOLERANCE_M = 1e-6
MAX_ROOMS = 256
MAX_DEVICES = 2048
OPENING_TYPES = frozenset(("door", "opening", "transfer"))


def _interval_intersection(a0: float, a1: float, b0: float, b1: float) -> tuple[float, float] | None:
    start, end = max(a0, b0), min(a1, b1)
    return (start, end) if end - start > TOLERANCE_M else None


def _box(room: dict, default_z: float) -> dict:
    x, y = float(room["x_m"]), float(room["y_m"])
    z = float(room.get("floor_elevation_m", default_z))
    if not all(math.isfinite(value) for value in (
        x, y, z, x + room["length_m"], y + room["width_m"],
        z + room["height_m"],
    )):
        raise ValueError(f"Room {room['id']!r} has overflowing 3D bounds")
    return {
        "id": room["id"], "name": room["name"],
        "x0": x, "x1": x + room["length_m"],
        "y0": y, "y1": y + room["width_m"],
        "z0": z, "z1": z + room["height_m"],
    }


def _interface(a: dict, b: dict) -> dict | None:
    """Find a positive-area, vertical, axis-aligned shared wall."""
    yy = _interval_intersection(a["y0"], a["y1"], b["y0"], b["y1"])
    xx = _interval_intersection(a["x0"], a["x1"], b["x0"], b["x1"])
    zz = _interval_intersection(a["z0"], a["z1"], b["z0"], b["z1"])
    if zz is None:
        return None
    faces = []
    if yy is not None:
        if abs(a["x1"] - b["x0"]) <= TOLERANCE_M:
            faces.append(("x", (a["x1"] + b["x0"]) / 2, yy, "east", "west"))
        if abs(b["x1"] - a["x0"]) <= TOLERANCE_M:
            faces.append(("x", (b["x1"] + a["x0"]) / 2, yy, "west", "east"))
    if xx is not None:
        if abs(a["y1"] - b["y0"]) <= TOLERANCE_M:
            faces.append(("y", (a["y1"] + b["y0"]) / 2, xx, "north", "south"))
        if abs(b["y1"] - a["y0"]) <= TOLERANCE_M:
            faces.append(("y", (b["y1"] + a["y0"]) / 2, xx, "south", "north"))
    if len(faces) != 1:
        return None
    axis, coordinate, shared, side_a, side_b = faces[0]
    return {
        "room_a_id": a["id"], "room_b_id": b["id"],
        "axis": axis, "coordinate_m": coordinate,
        "shared_interval_m": list(shared),
        "bottom_m": zz[0], "top_m": zz[1],
        "side_a": side_a, "side_b": side_b,
        "shared_area_m2": (shared[1] - shared[0]) * (zz[1] - zz[0]),
        "opening_ids": [],
    }


def _opening_matches(device: dict, room: dict, wall: dict) -> bool:
    if device["room_id"] not in (wall["room_a_id"], wall["room_b_id"]):
        return False
    side = wall["side_a"] if device["room_id"] == wall["room_a_id"] else wall["side_b"]
    if device.get("wall_side") != side:
        return False
    coordinate = float(device["x_m"] if wall["axis"] == "x" else device["y_m"])
    if abs(coordinate - wall["coordinate_m"]) > TOLERANCE_M:
        return False
    width = float(device["width_m"])
    center = float(device["y_m"] if wall["axis"] == "x" else device["x_m"])
    left, right = wall["shared_interval_m"]
    if center - width / 2 < left - TOLERANCE_M:
        return False
    if center + width / 2 > right + TOLERANCE_M:
        return False
    z0 = room["z0"] + float(device["z_m"])
    z1 = z0 + float(device["height_m"])
    return z0 >= wall["bottom_m"] - TOLERANCE_M and z1 <= wall["top_m"] + TOLERANCE_M


def _on_room_exterior_wall(device: dict, room: dict) -> bool:
    """Recognize geometrically valid exterior apertures without inventing neighbors."""
    side = device.get("wall_side")
    if side not in {"north", "south", "east", "west"}:
        return False
    axis = "x" if side in {"north", "south"} else "y"
    along = float(device[f"{axis}_m"])
    width = float(device["width_m"])
    if along - width / 2 < room[f"{axis}0"] - TOLERANCE_M:
        return False
    if along + width / 2 > room[f"{axis}1"] + TOLERANCE_M:
        return False
    normal = "y" if axis == "x" else "x"
    wall = room[f"{normal}1"] if side in {"north", "east"} else room[f"{normal}0"]
    if abs(float(device[f"{normal}_m"]) - wall) > TOLERANCE_M:
        return False
    bottom = room["z0"] + float(device["z_m"])
    return (bottom >= room["z0"] - TOLERANCE_M and
            bottom + float(device["height_m"]) <= room["z1"] + TOLERANCE_M)


def _all_connected(ids: list[str], walls: list[dict]) -> bool:
    if not ids:
        return False
    graph: dict[str, set[str]] = {room_id: set() for room_id in ids}
    for wall in walls:
        if not wall["opening_ids"]:
            continue
        a, b = wall["room_a_id"], wall["room_b_id"]
        graph[a].add(b)
        graph[b].add(a)
    reached = {ids[0]}
    work = deque([ids[0]])
    while work:
        for neighbor in graph[work.popleft()]:
            if neighbor not in reached:
                reached.add(neighbor)
                work.append(neighbor)
    return len(reached) == len(ids)


def assess_suite_topology(layout: dict[str, Any]) -> dict[str, Any]:
    """Read-only, deterministic room adjacency and wall-opening preflight.

    A valid geometry topology is *not* a mesh, CFD result, or permission to run
    a solver. Missing duct/terminal flow rates and crack geometry remain missing.
    """
    validate_spatial_layout_document(layout)
    rooms = layout.get("rooms", [])
    devices = layout.get("devices", [])
    if len(rooms) > MAX_ROOMS or len(devices) > MAX_DEVICES:
        raise ValueError("suite preflight size limit exceeded")
    canonical = json.dumps(layout, ensure_ascii=False, allow_nan=False,
                           separators=(",", ":"), sort_keys=True)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    floor = layout.get("floor") or {}
    default_z = float(floor.get("elevation_m", 0.0))
    boxes = sorted((_box(room, default_z) for room in rooms), key=lambda r: r["id"])
    by_id = {box["id"]: box for box in boxes}
    walls: list[dict] = []
    issues: list[dict] = []
    warnings: list[dict] = []

    def issue(code: str, message: str, *ids: str) -> None:
        issues.append({"code": code, "message": message,
                       "subject_ids": sorted(ids)})

    def warning(code: str, message: str, *ids: str) -> None:
        warnings.append({"code": code, "message": message,
                         "subject_ids": sorted(ids)})

    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            x_overlap = _interval_intersection(a["x0"], a["x1"], b["x0"], b["x1"])
            y_overlap = _interval_intersection(a["y0"], a["y1"], b["y0"], b["y1"])
            z_overlap = _interval_intersection(a["z0"], a["z1"], b["z0"], b["z1"])
            if x_overlap and y_overlap and z_overlap:
                issue("room_volume_overlap", "Rooms occupy overlapping 3D volume",
                      a["id"], b["id"])
                continue
            wall = _interface(a, b)
            if wall:
                # A first-generation Cartesian multi-room compiler must not
                # silently replace steps in floor/ceiling level by full-height walls.
                if (abs(a["z0"] - b["z0"]) > TOLERANCE_M or
                        abs(a["z1"] - b["z1"]) > TOLERANCE_M):
                    issue("stepped_shared_wall", "Adjacent rooms have different floor or ceiling elevations",
                          a["id"], b["id"])
                walls.append(wall)

    for device in sorted(devices, key=lambda d: d["id"]):
        if device["type"] not in OPENING_TYPES:
            continue
        device_id = device["id"]
        room_id = device.get("room_id")
        if room_id not in by_id:
            issue("opening_unassigned", "Opening has no valid room assignment", device_id)
            continue
        if not device.get("wall_side"):
            issue("opening_wall_unknown", "Opening requires an explicit wall_side", device_id)
            continue
        if "width_m" not in device or "height_m" not in device:
            issue("opening_dimensions_missing", "Opening requires width and height", device_id)
            continue
        parent = by_id[room_id]
        hits = [wall for wall in walls if _opening_matches(device, parent, wall)]
        if len(hits) == 1:
            hits[0]["opening_ids"].append(device_id)
        elif len(hits) > 1:
            issue("opening_ambiguous", "Opening matches multiple shared walls", device_id)
        elif _on_room_exterior_wall(device, parent):
            # An exterior access door is not an internal fluid connection.
            # Its external boundary conditions still require independent data.
            warning("exterior_opening", "Exterior opening has no inter-room connection",
                    device_id)
        else:
            issue("opening_unmapped", "Opening is not fully within a shared room wall",
                  device_id)

    for wall in walls:
        wall["opening_ids"].sort()
        # Two overlapping openings are not merged into one passage.
        for i, first in enumerate(wall["opening_ids"]):
            for second in wall["opening_ids"][i + 1:]:
                a = next(device for device in devices if device["id"] == first)
                b = next(device for device in devices if device["id"] == second)
                run_axis = "y_m" if wall["axis"] == "x" else "x_m"
                same_interval = (
                    abs(float(a[run_axis]) - float(b[run_axis])) <
                    (float(a["width_m"]) + float(b["width_m"])) / 2 - TOLERANCE_M
                )
                za = by_id[a["room_id"]]["z0"] + a["z_m"]
                zb = by_id[b["room_id"]]["z0"] + b["z_m"]
                vertical_overlap = _interval_intersection(
                    za, za + a["height_m"], zb, zb + b["height_m"])
                if same_interval and vertical_overlap:
                    issue("overlapping_openings", "Openings overlap on a shared wall",
                          first, second)
    if not boxes:
        issue("no_rooms", "A CFD suite requires at least one room")
    elif len(boxes) > 1 and not _all_connected([box["id"] for box in boxes], walls):
        issue("disconnected_suite", "Rooms do not form one connected inter-room opening network")

    issues.sort(key=lambda item: (item["code"], item["subject_ids"]))
    warnings.sort(key=lambda item: (item["code"], item["subject_ids"]))
    return {
        "schema_version": SCHEMA,
        "spatial_layout_sha256": digest,
        "topology_status": "blocked" if issues else "valid",
        "rooms": [
            {"id": b["id"], "name": b["name"],
             "bounds_m": [b["x0"], b["y0"], b["z0"], b["x1"], b["y1"], b["z1"]]}
            for b in boxes
        ],
        "shared_walls": walls,
        "issues": issues,
        "warnings": warnings,
        "openfoam_case_status": "not_generated",
        "ready_for_solver": False,
        "next_required_evidence": [
            "Explicit air-supply and exhaust flow-rate/patch boundary conditions",
            "Door/undercut geometry and wall thickness, where applicable",
            "Watertight multi-region mesh and verified boundary patch mapping",
            "Successful checkMesh and independently reviewed convergence/flux balance",
        ],
        "scope": "Geometry-only preflight; not mesh generation, CFD or regulatory compliance",
    }
