from __future__ import annotations

from dataclasses import dataclass
import copy
import math
import uuid
from typing import Any, Callable

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from .spatial_domain import (
    SpatialTransform2D,
    engineering_fields_for_room,
    engineering_mapping_issues,
    engineering_sync_states,
    mapped_pressure_values,
    mark_layout_synchronized,
    pressure_relationships,
    room_plan_bounds,
    room_prism_vertices,
)
from .spatial_integrity import (
    DEVICE_TYPES,
    SPATIAL_GEOMETRY_EPSILON_M,
    SPATIAL_LAYOUT_VERSION,
    SPATIAL_METADATA_KEY,
)


class SpatialSyncError(ValueError):
    """Raised when spatial geometry cannot be mapped to engineering input safely."""


def _finite_number(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _positive(value: Any, default: float) -> float:
    number = _finite_number(value, default)
    return number if number > 0 else default


def _room_id(name: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in name).strip("-")
    return slug or "room"


def _unique_id(preferred: Any, used_ids: set[str], *, fallback: str) -> str:
    """Return a deterministic non-empty identifier unique within one collection."""
    base = str(preferred).strip() if preferred is not None else ""
    base = base or fallback
    candidate = base
    suffix = 2
    while candidate in used_ids:
        candidate = f"{base}-{suffix}"
        suffix += 1
    used_ids.add(candidate)
    return candidate


def empty_layout() -> dict:
    return {
        "version": SPATIAL_LAYOUT_VERSION,
        "floor": {
            "id": "floor-1",
            "name": "Floor 1",
            "elevation_m": 0.0,
            "default_ceiling_height_m": 3.0,
            "units": "m",
        },
        "grid_m": 0.5,
        "rooms": [],
        "devices": [],
        "view": {
            "zoom_2d": 1.0,
            "pan_x": 0.0,
            "pan_y": 0.0,
            "azimuth_deg": 35.0,
            "elevation_deg": 28.0,
            "zoom_3d": 1.0,
            "pan_3d_x": 0.0,
            "pan_3d_y": 0.0,
            "snap_to_grid": True,
            "show_pressure": True,
            "show_labels": True,
            "show_devices": True,
            "show_relationships": True,
        },
    }


def normalize_layout(value: Any) -> dict:
    source = value if isinstance(value, dict) else {}
    result = empty_layout()
    result["grid_m"] = _positive(source.get("grid_m"), 0.5)

    raw_floor = source.get("floor", {})
    if isinstance(raw_floor, dict):
        result["floor"] = {
            "id": str(raw_floor.get("id") or "floor-1").strip() or "floor-1",
            "name": str(raw_floor.get("name") or "Floor 1").strip() or "Floor 1",
            "elevation_m": _finite_number(raw_floor.get("elevation_m"), 0.0),
            "default_ceiling_height_m": _positive(
                raw_floor.get("default_ceiling_height_m"), 3.0
            ),
            "units": "m",
        }
    floor_elevation = result["floor"]["elevation_m"]
    default_height = result["floor"]["default_ceiling_height_m"]

    rooms: list[dict] = []
    used_ids: set[str] = set()
    raw_rooms = source.get("rooms", [])
    if isinstance(raw_rooms, list):
        for index, raw in enumerate(raw_rooms):
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name") or f"Room {index + 1}").strip() or f"Room {index + 1}"
            room_id = _unique_id(
                raw.get("id"),
                used_ids,
                fallback=_room_id(name),
            )
            room = {
                "id": room_id,
                "name": name,
                "x_m": _finite_number(raw.get("x_m"), 0.0),
                "y_m": _finite_number(raw.get("y_m"), 0.0),
                "length_m": _positive(raw.get("length_m"), 4.0),
                "width_m": _positive(raw.get("width_m"), 4.0),
                "height_m": _positive(raw.get("height_m"), default_height),
                "floor_elevation_m": _finite_number(
                    raw.get("floor_elevation_m"), floor_elevation
                ),
            }
            if raw.get("pressure_pa") is not None:
                room["pressure_pa"] = _finite_number(raw.get("pressure_pa"), 0.0)
            for field in ("classification", "analysis_room_name", "notes"):
                if raw.get(field) is not None:
                    text = str(raw.get(field)).strip()
                    if text:
                        room[field] = text
            if isinstance(raw.get("metadata"), dict):
                room["metadata"] = copy.deepcopy(raw["metadata"])
            ref = raw.get("engineering_ref")
            if isinstance(ref, dict):
                analysis_id = str(ref.get("analysis_id") or "").strip()
                room_name = str(ref.get("room_name") or "").strip()
                if analysis_id and room_name:
                    normalized_ref = {
                        "analysis_id": analysis_id,
                        "room_name": room_name,
                    }
                    synced = ref.get("synced_geometry")
                    if isinstance(synced, dict):
                        normalized_ref["synced_geometry"] = {
                            "length_m": _positive(synced.get("length_m"), room["length_m"]),
                            "width_m": _positive(synced.get("width_m"), room["width_m"]),
                            "height_m": _positive(synced.get("height_m"), room["height_m"]),
                        }
                    room["engineering_ref"] = normalized_ref
            rooms.append(room)
    result["rooms"] = rooms

    devices: list[dict] = []
    used_device_ids: set[str] = set()
    raw_devices = source.get("devices", [])
    if isinstance(raw_devices, list):
        for index, raw in enumerate(raw_devices):
            if not isinstance(raw, dict):
                continue
            device_type = str(raw.get("type") or "equipment").lower()
            if device_type not in DEVICE_TYPES:
                device_type = "equipment"
            device_id = _unique_id(
                raw.get("id"),
                used_device_ids,
                fallback=f"device-{index + 1}",
            )
            room_id = raw.get("room_id")
            if room_id is not None:
                room_id = str(room_id).strip() or None
            default_width = 0.9 if device_type == "door" else (0.6 if device_type == "transfer" else 0.4)
            default_height = 2.1 if device_type == "door" else (0.4 if device_type == "transfer" else 0.2)
            device = {
                "id": device_id,
                "type": device_type,
                "name": str(raw.get("name") or device_type.upper()),
                "room_id": room_id,
                "x_m": _finite_number(raw.get("x_m"), 0.0),
                "y_m": _finite_number(raw.get("y_m"), 0.0),
                "z_m": _finite_number(raw.get("z_m"), 0.0),
                "width_m": _positive(raw.get("width_m"), default_width),
                "height_m": _positive(raw.get("height_m"), default_height),
                "orientation_deg": _finite_number(raw.get("orientation_deg"), 0.0),
            }
            wall_side = str(raw.get("wall_side") or "").strip().lower()
            if wall_side in {"north", "south", "east", "west"}:
                device["wall_side"] = wall_side
            swing = str(raw.get("swing") or "").strip()
            if swing:
                device["swing"] = swing
            devices.append(device)
    result["devices"] = devices

    view = source.get("view", {})
    if isinstance(view, dict):
        result["view"].update(
            {
                "zoom_2d": max(0.2, min(8.0, _positive(view.get("zoom_2d"), 1.0))),
                "pan_x": _finite_number(view.get("pan_x"), 0.0),
                "pan_y": _finite_number(view.get("pan_y"), 0.0),
                "azimuth_deg": _finite_number(view.get("azimuth_deg"), 35.0),
                "elevation_deg": max(5.0, min(75.0, _finite_number(view.get("elevation_deg"), 28.0))),
                "zoom_3d": max(0.2, min(8.0, _positive(view.get("zoom_3d"), 1.0))),
                "pan_3d_x": _finite_number(view.get("pan_3d_x"), 0.0),
                "pan_3d_y": _finite_number(view.get("pan_3d_y"), 0.0),
                "snap_to_grid": bool(view.get("snap_to_grid", True)),
                "show_pressure": bool(view.get("show_pressure", True)),
                "show_labels": bool(view.get("show_labels", True)),
                "show_devices": bool(view.get("show_devices", True)),
                "show_relationships": bool(view.get("show_relationships", True)),
            }
        )
    return result


def layout_metrics(value: Any) -> dict:
    """Return deterministic geometry/device counts without changing solver semantics."""
    layout = normalize_layout(value)
    rooms = layout["rooms"]
    devices = layout["devices"]
    counts = {device_type: 0 for device_type in DEVICE_TYPES}
    for device in devices:
        counts[device["type"]] += 1
    return {
        "room_count": len(rooms),
        "total_floor_area_m2": sum(room["length_m"] * room["width_m"] for room in rooms),
        "total_volume_m3": sum(
            room["length_m"] * room["width_m"] * room["height_m"] for room in rooms
        ),
        "device_counts": counts,
    }


def derive_layout_from_analysis(analysis: Any) -> dict:
    layout = empty_layout()
    if analysis is None or not isinstance(getattr(analysis, "input", None), dict):
        return layout

    payload = analysis.input
    kind = getattr(analysis, "kind", "")
    if kind == "room_verification":
        raw_rooms = [payload]
    elif kind == "project_verification":
        raw_rooms = payload.get("rooms", [])
    else:
        raw_rooms = []

    x_cursor = 0.0
    used_ids: set[str] = set()
    for index, raw in enumerate(raw_rooms):
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or f"Room {index + 1}")
        length = _positive(raw.get("length_m"), 4.0)
        width = _positive(raw.get("width_m"), 4.0)
        height = _positive(raw.get("height_m"), 3.0)
        room = {
            "id": _unique_id(None, used_ids, fallback=_room_id(name)),
            "name": name,
            "analysis_room_name": name,
            "x_m": x_cursor,
            "y_m": 0.0,
            "length_m": length,
            "width_m": width,
            "height_m": height,
            "floor_elevation_m": layout["floor"]["elevation_m"],
        }
        if raw.get("observed_pressure_pa") is not None:
            room["pressure_pa"] = _finite_number(raw.get("observed_pressure_pa"), 0.0)
        layout["rooms"].append(room)
        x_cursor += length + 1.0
    return layout


def ensure_project_layout(project: Any, analysis: Any = None) -> dict:
    metadata = getattr(project, "metadata", None)
    if not isinstance(metadata, dict):
        project.metadata = {}
        metadata = project.metadata

    raw = metadata.get(SPATIAL_METADATA_KEY)
    if isinstance(raw, dict):
        normalized = normalize_layout(raw)
        metadata[SPATIAL_METADATA_KEY] = normalized
        return normalized

    normalized = derive_layout_from_analysis(analysis)
    if not normalized["rooms"]:
        for candidate in getattr(project, "analyses", []):
            normalized = derive_layout_from_analysis(candidate)
            if normalized["rooms"]:
                break

    # Do not persist an empty auto-layout. This lets a later verification analysis
    # seed the workspace without overwriting a deliberately persisted empty layout.
    if normalized["rooms"]:
        normalized = normalize_layout(normalized)
        metadata[SPATIAL_METADATA_KEY] = normalized
    return normalized


def _duplicate_room_names(rooms: list[dict]) -> list[str]:
    first_names: dict[str, str] = {}
    duplicates: list[str] = []
    duplicate_keys: set[str] = set()
    for room in rooms:
        if not isinstance(room, dict):
            continue
        name = str(room.get("name") or "").strip()
        if not name:
            continue
        key = name.casefold()
        first = first_names.get(key)
        if first is None:
            first_names[key] = name
        elif key not in duplicate_keys:
            duplicates.append(first)
            duplicate_keys.add(key)
    return duplicates


def _require_unique_sync_names(rooms: list[dict], *, source: str) -> None:
    duplicates = _duplicate_room_names(rooms)
    if not duplicates:
        return
    labels = ", ".join(repr(name) for name in duplicates)
    raise SpatialSyncError(
        f"Cannot synchronize spatial geometry because {source} contains duplicate "
        f"room name(s): {labels}. Give every room a unique name and try again."
    )


def sync_layout_to_analysis(layout: dict, analysis: Any) -> bool:
    if analysis is None or not isinstance(getattr(analysis, "input", None), dict):
        return False
    rooms = normalize_layout(layout)["rooms"]
    if not rooms:
        return False

    changed = False
    analysis_id = str(getattr(analysis, "id", "") or "")
    if getattr(analysis, "kind", "") == "room_verification":
        source = rooms[0]
        ref = source.get("engineering_ref")
        if (
            isinstance(ref, dict)
            and str(ref.get("analysis_id") or "")
            and str(ref.get("analysis_id") or "") != analysis_id
        ):
            raise SpatialSyncError(
                "Cannot synchronize this room because it is explicitly mapped to "
                f"analysis {ref.get('analysis_id')!r}, not {analysis_id!r}."
            )
        for key in ("name", "length_m", "width_m", "height_m"):
            value = source[key]
            if analysis.input.get(key) != value:
                analysis.input[key] = value
                changed = True
        if "observed_pressure_pa" in analysis.input and "pressure_pa" in source:
            if analysis.input.get("observed_pressure_pa") != source["pressure_pa"]:
                analysis.input["observed_pressure_pa"] = source["pressure_pa"]
                changed = True
        return changed

    if getattr(analysis, "kind", "") != "project_verification":
        return False
    raw_rooms = analysis.input.get("rooms")
    if not isinstance(raw_rooms, list):
        return False

    _require_unique_sync_names(rooms, source="the spatial layout")
    _require_unique_sync_names(raw_rooms, source="the active analysis")
    by_name = {
        str(room.get("name")).strip().casefold(): room
        for room in raw_rooms
        if isinstance(room, dict) and str(room.get("name") or "").strip()
    }
    used_source_links: set[str] = set()
    for source in rooms:
        ref = source.get("engineering_ref")
        if isinstance(ref, dict) and str(ref.get("analysis_id") or ""):
            if str(ref.get("analysis_id")) != analysis_id:
                raise SpatialSyncError(
                    f"Spatial room {source['name']!r} is mapped to a different "
                    f"analysis ({ref.get('analysis_id')!r})."
                )
            source_name = str(ref.get("room_name") or "").strip()
        else:
            source_name = str(source.get("analysis_room_name") or source["name"]).strip()
        source_key = source_name.casefold()
        if source_key in used_source_links:
            raise SpatialSyncError(
                "Cannot synchronize spatial geometry because multiple layout rooms "
                f"map to analysis room {source_name!r}."
            )
        used_source_links.add(source_key)
        target = by_name.get(source_key)
        if target is None:
            if source.get("analysis_room_name"):
                raise SpatialSyncError(
                    f"Linked analysis room {source_name!r} does not exist in the active analysis."
                )
            continue
        for key in ("length_m", "width_m", "height_m"):
            if target.get(key) != source[key]:
                target[key] = source[key]
                changed = True
        if "observed_pressure_pa" in target and "pressure_pa" in source:
            if target.get("observed_pressure_pa") != source["pressure_pa"]:
                target["observed_pressure_pa"] = source["pressure_pa"]
                changed = True
    return changed


def _room_overlap_records(
    rooms: list[dict],
) -> list[tuple[int, int, list[float]]]:
    """Return deterministic room-overlap records using an adaptive broad phase.

    The sweep axis is chosen from projected room density. Exact two-dimensional
    overlap checks still use the same explicit engineering tolerance as before.
    Results are sorted by original room order to preserve validation/report order.
    """
    if len(rooms) < 2:
        return []

    bounds = [
        (
            index,
            room["x_m"],
            room["y_m"],
            room["x_m"] + room["length_m"],
            room["y_m"] + room["width_m"],
        )
        for index, room in enumerate(rooms)
    ]
    min_x = min(item[1] for item in bounds)
    min_y = min(item[2] for item in bounds)
    max_x = max(item[3] for item in bounds)
    max_y = max(item[4] for item in bounds)
    x_span = max(max_x - min_x, SPATIAL_GEOMETRY_EPSILON_M)
    y_span = max(max_y - min_y, SPATIAL_GEOMETRY_EPSILON_M)
    x_density = sum(item[3] - item[1] for item in bounds) / x_span
    y_density = sum(item[4] - item[2] for item in bounds) / y_span
    sweep_x = x_density <= y_density

    def axis_start(item: tuple[int, float, float, float, float]) -> float:
        return item[1] if sweep_x else item[2]

    def axis_end(item: tuple[int, float, float, float, float]) -> float:
        return item[3] if sweep_x else item[4]

    ordered = sorted(bounds, key=lambda item: (axis_start(item), item[0]))
    active: list[tuple[int, float, float, float, float]] = []
    overlaps: list[tuple[int, int, list[float]]] = []

    for current in ordered:
        current_start = axis_start(current)
        active = [
            item
            for item in active
            if axis_end(item) > current_start + SPATIAL_GEOMETRY_EPSILON_M
        ]
        for other in active:
            x0 = max(current[1], other[1])
            y0 = max(current[2], other[2])
            x1 = min(current[3], other[3])
            y1 = min(current[4], other[4])
            if (
                x1 > x0 + SPATIAL_GEOMETRY_EPSILON_M
                and y1 > y0 + SPATIAL_GEOMETRY_EPSILON_M
            ):
                left_index, right_index = sorted((current[0], other[0]))
                overlaps.append((left_index, right_index, [x0, y0, x1, y1]))

        active.append(current)

    overlaps.sort(key=lambda item: (item[0], item[1]))
    return overlaps


def _spatial_validation_key(layout: dict) -> tuple:
    """Return the validation-relevant state, deliberately excluding camera/view data."""
    rooms = layout.get("rooms", []) if isinstance(layout, dict) else []
    devices = layout.get("devices", []) if isinstance(layout, dict) else []
    return (
        tuple(
            (
                room.get("id"),
                room.get("name"),
                room.get("x_m"),
                room.get("y_m"),
                room.get("length_m"),
                room.get("width_m"),
                room.get("height_m"),
            )
            for room in rooms
            if isinstance(room, dict)
        ),
        tuple(
            (
                device.get("id"),
                device.get("name"),
                device.get("room_id"),
                device.get("type"),
                device.get("x_m"),
                device.get("y_m"),
                device.get("z_m"),
                device.get("width_m"),
                device.get("height_m"),
                device.get("wall_side"),
            )
            for device in devices
            if isinstance(device, dict)
        ),
    )


def validate_layout(value: Any) -> list[dict]:
    """Return advisory spatial-edit warnings without mutating persisted layout data."""
    layout = normalize_layout(value)
    rooms = layout["rooms"]
    devices = layout["devices"]
    issues: list[dict] = []

    first_room_by_name: dict[str, dict] = {}
    for room in rooms:
        normalized_name = str(room["name"]).strip().casefold()
        first = first_room_by_name.get(normalized_name)
        if first is None:
            first_room_by_name[normalized_name] = room
        else:
            issues.append(
                {
                    "code": "duplicate_room_name",
                    "severity": "warning",
                    "item_ids": [first["id"], room["id"]],
                    "message": (
                        f"Duplicate room name '{room['name']}' can make analysis synchronization ambiguous."
                    ),
                }
            )

    for left_index, right_index, bounds_m in _room_overlap_records(rooms):
        left = rooms[left_index]
        right = rooms[right_index]
        x0, y0, x1, y1 = bounds_m
        issues.append(
            {
                "code": "room_overlap",
                "severity": "warning",
                "item_ids": [left["id"], right["id"]],
                "bounds_m": bounds_m,
                "message": (
                    f"Rooms '{left['name']}' and '{right['name']}' overlap "
                    f"by {(x1 - x0) * (y1 - y0):g} m²."
                ),
            }
        )

    room_by_id = {room["id"]: room for room in rooms}
    for device in devices:
        room_id = device.get("room_id")
        if not room_id:
            if rooms:
                issues.append(
                    {
                        "code": "device_unassigned",
                        "severity": "warning",
                        "item_ids": [device["id"]],
                        "message": f"Device '{device['name']}' is not assigned to a room.",
                    }
                )
            continue

        room = room_by_id.get(str(room_id))
        if room is None:
            issues.append(
                {
                    "code": "orphan_device_room",
                    "severity": "warning",
                    "item_ids": [device["id"]],
                    "message": (
                        f"Device '{device['name']}' references missing room id '{room_id}'."
                    ),
                }
            )
            continue

        x = device["x_m"]
        y = device["y_m"]
        z = device["z_m"]
        inside_xy = (
            room["x_m"] - SPATIAL_GEOMETRY_EPSILON_M <= x <= room["x_m"] + room["length_m"] + SPATIAL_GEOMETRY_EPSILON_M
            and room["y_m"] - SPATIAL_GEOMETRY_EPSILON_M <= y <= room["y_m"] + room["width_m"] + SPATIAL_GEOMETRY_EPSILON_M
        )
        if not inside_xy:
            issues.append(
                {
                    "code": "device_outside_room",
                    "severity": "warning",
                    "item_ids": [device["id"], room["id"]],
                    "message": (
                        f"Device '{device['name']}' lies outside assigned room '{room['name']}'."
                    ),
                }
            )
        if z < -SPATIAL_GEOMETRY_EPSILON_M or z > room["height_m"] + SPATIAL_GEOMETRY_EPSILON_M:
            issues.append(
                {
                    "code": "device_elevation_outside_room",
                    "severity": "warning",
                    "item_ids": [device["id"], room["id"]],
                    "message": (
                        f"Device '{device['name']}' elevation {z:g} m is outside "
                        f"room '{room['name']}' height 0–{room['height_m']:g} m."
                    ),
                }
            )
        if device["type"] in {"door", "transfer"}:
            opening_top = z + device.get("height_m", 0.0)
            if opening_top > room["height_m"] + SPATIAL_GEOMETRY_EPSILON_M:
                issues.append(
                    {
                        "code": "opening_above_room",
                        "severity": "warning",
                        "item_ids": [device["id"], room["id"]],
                        "message": (
                            f"Opening '{device['name']}' top elevation {opening_top:g} m "
                            f"exceeds room '{room['name']}' height {room['height_m']:g} m."
                        ),
                    }
                )
            side = device.get("wall_side")
            expected = None
            actual = None
            if side == "south":
                expected, actual = room["y_m"], y
            elif side == "north":
                expected, actual = room["y_m"] + room["width_m"], y
            elif side == "west":
                expected, actual = room["x_m"], x
            elif side == "east":
                expected, actual = room["x_m"] + room["length_m"], x
            if (
                expected is not None
                and actual is not None
                and abs(actual - expected) > SPATIAL_GEOMETRY_EPSILON_M
            ):
                issues.append(
                    {
                        "code": "opening_off_wall",
                        "severity": "warning",
                        "item_ids": [device["id"], room["id"]],
                        "message": (
                            f"Opening '{device['name']}' is associated with the {side} wall "
                            f"of room '{room['name']}' but is not located on that wall."
                        ),
                    }
                )

    return issues

def _pressure_fill(pressure: Any, min_pressure: float | None, max_pressure: float | None) -> str:
    if pressure is None or min_pressure is None or max_pressure is None:
        return "#dfe7ef"
    if max_pressure <= min_pressure:
        ratio = 0.5
    else:
        ratio = (_finite_number(pressure, min_pressure) - min_pressure) / (max_pressure - min_pressure)
    ratio = max(0.0, min(1.0, ratio))
    # Low pressure: cool blue. High pressure: warm amber.
    r = int(90 + 145 * ratio)
    g = int(150 + 55 * (1.0 - abs(ratio - 0.5) * 2.0))
    b = int(225 - 135 * ratio)
    return f"#{r:02x}{g:02x}{b:02x}"


@dataclass
class _Hit:
    kind: str
    item_id: str


class SpatialDesignWorkspace(ttk.Frame):
    """Synchronized 2D/3D cleanroom design workspace backed by project metadata."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        project_getter: Callable[[], Any],
        analysis_getter: Callable[[], Any],
        on_change: Callable[[], None],
        on_sync_requested: Callable[[], None],
        status_setter: Callable[[str], None],
        on_history_record: Callable[
            [dict, tuple[str, str] | None, dict, tuple[str, str] | None, str],
            bool,
        ] | None = None,
        on_undo_requested: Callable[[], bool] | None = None,
        on_redo_requested: Callable[[], bool] | None = None,
    ):
        super().__init__(master)
        self._project_getter = project_getter
        self._analysis_getter = analysis_getter
        self._on_change = on_change
        self._on_sync_requested = on_sync_requested
        self._status_setter = status_setter
        self._on_history_record = on_history_record
        self._on_undo_requested = on_undo_requested
        self._on_redo_requested = on_redo_requested

        self.layout = empty_layout()
        self.selected: _Hit | None = None
        self._drag_anchor: tuple[float, float] | None = None
        self._pan_anchor: tuple[int, int] | None = None
        self._pan_origin: tuple[float, float] | None = None
        self._orbit_anchor: tuple[int, int] | None = None
        self._orbit_origin: tuple[float, float] | None = None
        self._hovered: _Hit | None = None
        self._show_grid = tk.BooleanVar(value=True)
        self._snap_to_grid = tk.BooleanVar(value=True)
        self._show_pressure = tk.BooleanVar(value=True)
        self._show_labels = tk.BooleanVar(value=True)
        self._show_devices = tk.BooleanVar(value=True)
        self._show_relationships = tk.BooleanVar(value=True)
        self._coord_var = tk.StringVar(value="x 0.00 m   y 0.00 m")
        self._selection_var = tk.StringVar(value="No selection")
        self._validation_var = tk.StringVar(value="Spatial checks: PASS")
        self._engineering_var = tk.StringVar(value="Engineering mapping: no selection")
        self._metrics_var = tk.StringVar(value="0 rooms")
        self._zoom_var = tk.StringVar(value="Zoom 100%")
        self._validation_issues: list[dict] = []
        self._last_validation_key: tuple | None = None
        self._property_vars: dict[str, tk.StringVar] = {}
        self._history_can_undo = False
        self._history_can_redo = False
        self._drag_history_before: tuple[dict, tuple[str, str] | None] | None = None
        self._resize_room_id: str | None = None

        self._build()
        self.refresh()

    def _build(self) -> None:
        toolbar = ttk.Frame(self, padding=(6, 6, 6, 3))
        toolbar.pack(fill="x")

        ttk.Button(toolbar, text="+ Room", command=self.add_room).pack(side="left", padx=2)
        for device_type, label in (
            ("door", "+ Door"),
            ("ffu", "+ FFU"),
            ("supply", "+ Supply"),
            ("return", "+ Return"),
            ("exhaust", "+ Exhaust"),
            ("equipment", "+ Equipment"),
            ("sensor", "+ Sensor"),
            ("transfer", "+ Transfer"),
        ):
            ttk.Button(
                toolbar,
                text=label,
                command=lambda t=device_type: self.add_device(t),
            ).pack(side="left", padx=2)
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=6)
        self._undo_button = ttk.Button(toolbar, text="Undo", command=self.undo_edit, state="disabled")
        self._undo_button.pack(side="left", padx=2)
        self._redo_button = ttk.Button(toolbar, text="Redo", command=self.redo_edit, state="disabled")
        self._redo_button.pack(side="left", padx=2)
        ttk.Button(toolbar, text="Delete", command=self.delete_selected).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Fit", command=self.fit_views).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Reset 2D", command=self.reset_2d).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Floor…", command=self.edit_floor).pack(side="left", padx=2)
        ttk.Button(
            toolbar,
            text="Sync dimensions to active analysis",
            command=self._on_sync_requested,
        ).pack(side="right", padx=2)

        viewbar = ttk.Frame(self, padding=(6, 0, 6, 3))
        viewbar.pack(fill="x")
        ttk.Checkbutton(
            viewbar, text="Grid", variable=self._show_grid, command=self.redraw
        ).pack(side="left", padx=(2, 6))
        for label, variable, key in (
            ("Snap", self._snap_to_grid, "snap_to_grid"),
            ("Pressure", self._show_pressure, "show_pressure"),
            ("Labels", self._show_labels, "show_labels"),
            ("Devices", self._show_devices, "show_devices"),
            ("Relations", self._show_relationships, "show_relationships"),
        ):
            ttk.Checkbutton(
                viewbar,
                text=label,
                variable=variable,
                command=lambda k=key, v=variable: self._set_view_flag(k, v.get()),
            ).pack(side="left", padx=2)
        ttk.Label(viewbar, textvariable=self._zoom_var).pack(side="left", padx=(8, 2))
        ttk.Button(viewbar, text="Validate", command=self.report_validation).pack(
            side="left", padx=(10, 2)
        )
        ttk.Label(viewbar, textvariable=self._validation_var).pack(
            side="left", padx=(8, 2)
        )

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=6, pady=(3, 6))

        two_d = ttk.Frame(body)
        body.add(two_d, weight=4)
        ttk.Label(two_d, text="2D Layout", font=("TkDefaultFont", 10, "bold")).pack(
            anchor="w", padx=4, pady=(2, 4)
        )
        self.canvas_2d = tk.Canvas(two_d, background="#f7f9fb", highlightthickness=1)
        self.canvas_2d.pack(fill="both", expand=True)
        ttk.Label(two_d, textvariable=self._coord_var, anchor="w").pack(fill="x", padx=4, pady=(2, 0))
        ttk.Label(two_d, textvariable=self._metrics_var, anchor="w").pack(fill="x", padx=4, pady=(0, 2))

        right = ttk.Panedwindow(body, orient="vertical")
        body.add(right, weight=4)

        three_d = ttk.Frame(right)
        right.add(three_d, weight=3)
        header3 = ttk.Frame(three_d)
        header3.pack(fill="x")
        ttk.Label(header3, text="3D View", font=("TkDefaultFont", 10, "bold")).pack(
            side="left", padx=4, pady=(2, 4)
        )
        for label, delta in (("↺", -15), ("↻", 15)):
            ttk.Button(header3, text=label, width=3, command=lambda d=delta: self.rotate_3d(d)).pack(
                side="right", padx=2
            )
        ttk.Button(header3, text="↓", width=3, command=lambda: self.tilt_3d(-5)).pack(side="right", padx=2)
        ttk.Button(header3, text="↑", width=3, command=lambda: self.tilt_3d(5)).pack(side="right", padx=2)
        ttk.Button(header3, text="Reset", command=self.reset_3d).pack(side="right", padx=2)
        self.canvas_3d = tk.Canvas(three_d, background="#111820", highlightthickness=1)
        self.canvas_3d.pack(fill="both", expand=True)

        inspector = ttk.Frame(right, padding=6)
        right.add(inspector, weight=2)
        ttk.Label(inspector, text="Properties", font=("TkDefaultFont", 10, "bold")).grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 6)
        )
        ttk.Label(inspector, textvariable=self._selection_var).grid(
            row=1, column=0, columnspan=4, sticky="w", pady=(0, 6)
        )
        fields = (
            ("name", "Name"),
            ("x_m", "X (m)"),
            ("y_m", "Y (m)"),
            ("z_m", "Z (m)"),
            ("length_m", "Length (m)"),
            ("width_m", "Width (m)"),
            ("height_m", "Height (m)"),
            ("pressure_pa", "Pressure (Pa)"),
            ("floor_elevation_m", "Floor elev. (m)"),
            ("classification", "Classification"),
            ("analysis_room_name", "Analysis room"),
            ("notes", "Notes"),
            ("room_id", "Room ID"),
            ("orientation_deg", "Orientation (deg)"),
            ("wall_side", "Wall side"),
            ("swing", "Swing"),
        )
        for index, (key, label) in enumerate(fields):
            row = 2 + index // 2
            column = (index % 2) * 2
            ttk.Label(inspector, text=label).grid(row=row, column=column, sticky="w", padx=(0, 4), pady=2)
            var = tk.StringVar()
            self._property_vars[key] = var
            ttk.Entry(inspector, textvariable=var, width=18).grid(
                row=row, column=column + 1, sticky="ew", padx=(0, 8), pady=2
            )
        button_row = 2 + (len(fields) + 1) // 2
        ttk.Label(
            inspector,
            textvariable=self._engineering_var,
            justify="left",
            wraplength=560,
        ).grid(row=button_row, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Button(inspector, text="Apply", command=self.apply_properties).grid(
            row=button_row, column=3, sticky="e", pady=(8, 0)
        )
        inspector.columnconfigure(1, weight=1)
        inspector.columnconfigure(3, weight=1)

        self.canvas_2d.bind("<Configure>", lambda event: self.redraw())
        self.canvas_3d.bind("<Configure>", lambda event: self._draw_3d())
        self.canvas_2d.bind("<Motion>", self._on_motion)
        self.canvas_2d.bind("<Leave>", self._on_leave_2d)
        self.canvas_2d.bind("<Button-1>", self._on_left_down)
        self.canvas_2d.bind("<B1-Motion>", self._on_left_drag)
        self.canvas_2d.bind("<ButtonRelease-1>", self._on_left_up)
        self.canvas_2d.bind("<Button-2>", self._on_pan_down)
        self.canvas_2d.bind("<B2-Motion>", self._on_pan_drag)
        self.canvas_2d.bind("<Button-3>", self._on_pan_down)
        self.canvas_2d.bind("<B3-Motion>", self._on_pan_drag)
        self.canvas_2d.bind("<MouseWheel>", self._on_wheel)
        self.canvas_2d.bind("<Button-4>", lambda event: self._zoom_at(1.1, event.x, event.y))
        self.canvas_2d.bind("<Button-5>", lambda event: self._zoom_at(1 / 1.1, event.x, event.y))
        self.canvas_3d.bind("<MouseWheel>", self._on_wheel_3d)
        self.canvas_3d.bind("<Button-4>", lambda event: self._zoom_3d(1.1))
        self.canvas_3d.bind("<Button-5>", lambda event: self._zoom_3d(1 / 1.1))
        self.canvas_3d.bind("<Button-1>", self._on_3d_click)
        self.canvas_3d.bind("<Shift-Button-1>", self._on_orbit_3d_down)
        self.canvas_3d.bind("<Shift-B1-Motion>", self._on_orbit_3d_drag)
        self.canvas_3d.bind("<Button-2>", self._on_pan_3d_down)
        self.canvas_3d.bind("<B2-Motion>", self._on_pan_3d_drag)
        self.canvas_3d.bind("<Button-3>", self._on_pan_3d_down)
        self.canvas_3d.bind("<B3-Motion>", self._on_pan_3d_drag)
        for canvas in (self.canvas_2d, self.canvas_3d):
            canvas.bind("<Control-z>", self._on_undo_shortcut)
            canvas.bind("<Control-y>", self._on_redo_shortcut)
            canvas.bind("<Control-Shift-Z>", self._on_redo_shortcut)
            canvas.bind("<Delete>", lambda event: self.delete_selected())
            canvas.bind("<Left>", lambda event: self._nudge_selected(-1, 0))
            canvas.bind("<Right>", lambda event: self._nudge_selected(1, 0))
            canvas.bind("<Up>", lambda event: self._nudge_selected(0, -1))
            canvas.bind("<Down>", lambda event: self._nudge_selected(0, 1))

    def refresh(self) -> None:
        project = self._project_getter()
        analysis = self._analysis_getter()
        self.layout = ensure_project_layout(project, analysis)
        view = self.layout.get("view", {})
        self._snap_to_grid.set(bool(view.get("snap_to_grid", True)))
        self._show_pressure.set(bool(view.get("show_pressure", True)))
        self._show_labels.set(bool(view.get("show_labels", True)))
        self._show_devices.set(bool(view.get("show_devices", True)))
        self._show_relationships.set(bool(view.get("show_relationships", True)))
        if self.selected and not self._selected_object():
            self.selected = None
        self._load_property_panel()
        self._update_history_controls()
        self.redraw()

    def _set_view_flag(self, key: str, value: bool) -> None:
        self.layout.setdefault("view", {})[key] = bool(value)
        project = self._project_getter()
        project.metadata[SPATIAL_METADATA_KEY] = normalize_layout(self.layout)
        self.layout = project.metadata[SPATIAL_METADATA_KEY]
        self._on_change()
        self._status_setter("Spatial view settings updated")
        self.redraw()

    def _update_metrics(self) -> None:
        metrics = layout_metrics(self.layout)
        counts = metrics["device_counts"]
        self._metrics_var.set(
            f"{metrics['room_count']} rooms · "
            f"{metrics['total_floor_area_m2']:.1f} m² · "
            f"{metrics['total_volume_m3']:.1f} m³ · "
            f"FFU {counts['ffu']} · Supply {counts['supply']} · "
            f"Return {counts['return']} · Exhaust {counts['exhaust']}"
        )
        self._zoom_var.set(f"Zoom {self.layout['view']['zoom_2d'] * 100:.0f}%")

    def edit_floor(self) -> None:
        floor = self.layout["floor"]
        history_before = self._history_layout()
        selection_before = self._selection_state()
        name = simpledialog.askstring(
            "Floor",
            "Floor name:",
            initialvalue=floor["name"],
            parent=self,
        )
        if name is None:
            return
        elevation = simpledialog.askfloat(
            "Floor",
            "Elevation (m):",
            initialvalue=floor["elevation_m"],
            parent=self,
        )
        if elevation is None:
            return
        ceiling = simpledialog.askfloat(
            "Floor",
            "Default ceiling height (m):",
            initialvalue=floor["default_ceiling_height_m"],
            minvalue=0.01,
            parent=self,
        )
        if ceiling is None:
            return
        grid = simpledialog.askfloat(
            "Grid",
            "Grid spacing (m):",
            initialvalue=self.layout["grid_m"],
            minvalue=0.01,
            parent=self,
        )
        if grid is None:
            return
        floor["name"] = name.strip() or floor["name"]
        floor["elevation_m"] = float(elevation)
        floor["default_ceiling_height_m"] = float(ceiling)
        self.layout["grid_m"] = float(grid)
        self._persist(
            "Floor settings updated",
            history_before=history_before,
            selection_before=selection_before,
        )

    def _selection_state(self) -> tuple[str, str] | None:
        if self.selected is None:
            return None
        return (self.selected.kind, self.selected.item_id)

    def _history_layout(self) -> dict:
        snapshot = copy.deepcopy(normalize_layout(self.layout))
        snapshot.pop("view", None)
        return snapshot

    def history_selection(self) -> tuple[str, str] | None:
        return self._selection_state()

    def restore_history_selection(
        self, selection: tuple[str, str] | None
    ) -> None:
        self.selected = _Hit(*selection) if selection is not None else None
        if self.selected and not self._selected_object():
            self.selected = None
        self._load_property_panel()
        self.redraw()

    def set_history_availability(self, can_undo: bool, can_redo: bool) -> None:
        self._history_can_undo = bool(can_undo)
        self._history_can_redo = bool(can_redo)
        self._update_history_controls()

    def _update_history_controls(self) -> None:
        if hasattr(self, "_undo_button"):
            self._undo_button.configure(
                state="normal" if getattr(self, "_history_can_undo", False) else "disabled"
            )
        if hasattr(self, "_redo_button"):
            self._redo_button.configure(
                state="normal" if getattr(self, "_history_can_redo", False) else "disabled"
            )

    def undo_edit(self) -> bool:
        callback = getattr(self, "_on_undo_requested", None)
        if callback is None:
            self._status_setter("Project undo is unavailable")
            return False
        return bool(callback())

    def redo_edit(self) -> bool:
        callback = getattr(self, "_on_redo_requested", None)
        if callback is None:
            self._status_setter("Project redo is unavailable")
            return False
        return bool(callback())

    def _on_undo_shortcut(self, event=None):
        self.undo_edit()
        return "break"

    def _on_redo_shortcut(self, event=None):
        self.redo_edit()
        return "break"

    def _persist(
        self,
        message: str,
        *,
        history_before: dict | None = None,
        selection_before: tuple[str, str] | None = None,
    ) -> None:
        project = self._project_getter()
        project.metadata[SPATIAL_METADATA_KEY] = normalize_layout(self.layout)
        self.layout = project.metadata[SPATIAL_METADATA_KEY]
        history_callback = getattr(self, "_on_history_record", None)
        if history_before is not None and history_callback is not None:
            history_callback(
                history_before,
                selection_before,
                self._history_layout(),
                self._selection_state(),
                message,
            )
        self._on_change()
        self._status_setter(message)
        self._update_history_controls()
        self.redraw()

    def _selected_object(self) -> dict | None:
        if self.selected is None:
            return None
        collection = self.layout["rooms"] if self.selected.kind == "room" else self.layout["devices"]
        return next((item for item in collection if item["id"] == self.selected.item_id), None)

    def _warning_item_ids(self) -> set[str]:
        return {
            str(item_id)
            for issue in self._validation_issues
            for item_id in issue.get("item_ids", [])
        }

    def _update_validation_summary(self) -> None:
        count = len(self._validation_issues)
        self._validation_var.set(
            "Spatial checks: PASS" if count == 0 else f"Spatial checks: {count} warning(s)"
        )

    def _refresh_validation(self, *, force: bool = False) -> None:
        analysis = self._analysis_getter()
        mapping_records = engineering_sync_states(self.layout, analysis)
        mapping_key = tuple(
            (
                record["room_id"],
                record["state"],
                record.get("analysis_id"),
                record.get("engineering_room_name"),
                tuple(record.get("differences", {})),
            )
            for record in mapping_records
        )
        validation_key = (_spatial_validation_key(self.layout), mapping_key)
        if force or validation_key != self._last_validation_key:
            self._validation_issues = (
                validate_layout(self.layout)
                + engineering_mapping_issues(self.layout, analysis)
            )
            self._last_validation_key = validation_key
            self._update_validation_summary()

    def report_validation(self) -> None:
        self._refresh_validation(force=True)
        if not self._validation_issues:
            self._status_setter("Spatial checks: PASS")
            self.redraw()
            return
        messages = [issue["message"] for issue in self._validation_issues[:3]]
        suffix = (
            ""
            if len(self._validation_issues) <= 3
            else f" (+{len(self._validation_issues) - 3} more)"
        )
        self._status_setter("Spatial checks: " + " | ".join(messages) + suffix)
        self.redraw()

    def _load_property_panel(self) -> None:
        item = self._selected_object()
        if item is None:
            self._selection_var.set("No selection")
            self._engineering_var.set("Engineering mapping: no selection")
            for var in self._property_vars.values():
                var.set("")
            return
        prefix = "Room" if self.selected and self.selected.kind == "room" else item.get("type", "Device").title()
        self._selection_var.set(f"{prefix}: {item.get('name', '')}")
        for key, var in self._property_vars.items():
            value = item.get(key, "")
            var.set("" if value is None else str(value))
        if self.selected and self.selected.kind == "room":
            analysis = self._analysis_getter()
            states = {
                record["room_id"]: record
                for record in engineering_sync_states(self.layout, analysis)
            }
            record = states.get(item["id"], {"state": "unmapped", "differences": {}})
            state_text = str(record["state"]).replace("_", " ")
            fields = engineering_fields_for_room(self.layout, analysis, item["id"])
            detail = ", ".join(f"{key}={value}" for key, value in fields.items())
            differences = ", ".join(record.get("differences", {}))
            message = f"Engineering mapping: {state_text}"
            if record.get("analysis_id"):
                message += f" | analysis={record['analysis_id']}"
            if differences:
                message += f" | differs: {differences}"
            if detail:
                message += f" | engineering: {detail}"
            self._engineering_var.set(message)
        else:
            self._engineering_var.set("Engineering mapping: spatial device")

    def apply_properties(self) -> None:
        item = self._selected_object()
        if item is None:
            return
        history_before = self._history_layout()
        selection_before = self._selection_state()
        name = self._property_vars["name"].get().strip()
        if name:
            item["name"] = name
        for key in ("x_m", "y_m"):
            text = self._property_vars[key].get().strip()
            if text:
                item[key] = _finite_number(text, item.get(key, 0.0))
        if self.selected and self.selected.kind == "room":
            for key in ("length_m", "width_m", "height_m"):
                text = self._property_vars[key].get().strip()
                if text:
                    item[key] = _positive(text, item[key])
            floor_elevation = self._property_vars["floor_elevation_m"].get().strip()
            if floor_elevation:
                item["floor_elevation_m"] = _finite_number(
                    floor_elevation, item.get("floor_elevation_m", 0.0)
                )
            pressure = self._property_vars["pressure_pa"].get().strip()
            if pressure:
                item["pressure_pa"] = _finite_number(pressure, item.get("pressure_pa", 0.0))
            elif "pressure_pa" in item:
                item.pop("pressure_pa", None)
            for key in ("classification", "analysis_room_name", "notes"):
                text = self._property_vars[key].get().strip()
                if text:
                    item[key] = text
                else:
                    item.pop(key, None)
            ref = item.get("engineering_ref")
            if isinstance(ref, dict):
                current_link = str(item.get("analysis_room_name") or "").strip()
                if (
                    current_link
                    and current_link.casefold()
                    != str(ref.get("room_name") or "").strip().casefold()
                ):
                    item.pop("engineering_ref", None)
        elif self.selected and self.selected.kind == "device":
            z_text = self._property_vars["z_m"].get().strip()
            if z_text:
                item["z_m"] = _finite_number(z_text, item.get("z_m", 0.0))
            for key in ("width_m", "height_m"):
                text = self._property_vars[key].get().strip()
                if text:
                    item[key] = _positive(text, item.get(key, 0.2))
            orientation = self._property_vars["orientation_deg"].get().strip()
            if orientation:
                item["orientation_deg"] = _finite_number(
                    orientation, item.get("orientation_deg", 0.0)
                )
            room_id = self._property_vars["room_id"].get().strip()
            item["room_id"] = room_id or None
            wall_side = self._property_vars["wall_side"].get().strip().lower()
            if wall_side in {"north", "south", "east", "west"}:
                item["wall_side"] = wall_side
            else:
                item.pop("wall_side", None)
            swing = self._property_vars["swing"].get().strip()
            if swing:
                item["swing"] = swing
            else:
                item.pop("swing", None)
        self._load_property_panel()
        self._persist(
            "Spatial properties updated",
            history_before=history_before,
            selection_before=selection_before,
        )

    def add_room(self) -> None:
        history_before = self._history_layout()
        selection_before = self._selection_state()
        x = max(
            (room["x_m"] + room["length_m"] for room in self.layout["rooms"]),
            default=0.0,
        )
        index = len(self.layout["rooms"]) + 1
        room = {
            "id": f"room-{uuid.uuid4().hex[:8]}",
            "name": f"Room {index}",
            "x_m": x + (1.0 if self.layout["rooms"] else 0.0),
            "y_m": 0.0,
            "length_m": 4.0,
            "width_m": 4.0,
            "height_m": self.layout["floor"]["default_ceiling_height_m"],
            "floor_elevation_m": self.layout["floor"]["elevation_m"],
        }
        self.layout["rooms"].append(room)
        self.selected = _Hit("room", room["id"])
        self._load_property_panel()
        self._persist(
            f"Added {room['name']}",
            history_before=history_before,
            selection_before=selection_before,
        )

    def add_device(self, device_type: str) -> None:
        history_before = self._history_layout()
        selection_before = self._selection_state()
        device_type = device_type if device_type in DEVICE_TYPES else "equipment"
        room = self._selected_object() if self.selected and self.selected.kind == "room" else None
        if room is None and self.layout["rooms"]:
            room = self.layout["rooms"][0]
        if room:
            x = room["x_m"] + room["length_m"] / 2.0
            y = room["y_m"] + room["width_m"] / 2.0
            z = room["height_m"] if device_type in {"ffu", "supply", "return", "exhaust", "sensor"} else 0.0
            room_id = room["id"]
            if device_type in {"door", "transfer"}:
                y = room["y_m"]
                z = 0.0 if device_type == "door" else min(1.0, room["height_m"] / 2.0)
        else:
            x = y = z = 0.0
            room_id = None
        default_width = 0.9 if device_type == "door" else (0.6 if device_type == "transfer" else 0.4)
        default_height = 2.1 if device_type == "door" else (0.4 if device_type == "transfer" else 0.2)
        device = {
            "id": f"device-{uuid.uuid4().hex[:8]}",
            "type": device_type,
            "name": device_type.upper(),
            "room_id": room_id,
            "x_m": x,
            "y_m": y,
            "z_m": z,
            "width_m": default_width,
            "height_m": default_height,
            "orientation_deg": 0.0,
        }
        if device_type in {"door", "transfer"}:
            device["wall_side"] = "south"
        if device_type == "door":
            device["swing"] = "left"
        self.layout["devices"].append(device)
        self.selected = _Hit("device", device["id"])
        self._load_property_panel()
        self._persist(
            f"Added {device_type}",
            history_before=history_before,
            selection_before=selection_before,
        )

    def delete_selected(self) -> None:
        if self.selected is None:
            return
        item = self._selected_object()
        item_name = item.get("name", "selected item") if isinstance(item, dict) else "selected item"
        if not messagebox.askyesno(
            "Delete spatial item",
            f"Delete {item_name!r}? This can be undone with project Undo.",
            parent=self.winfo_toplevel(),
        ):
            return
        history_before = self._history_layout()
        selection_before = self._selection_state()
        collection_name = "rooms" if self.selected.kind == "room" else "devices"
        item_id = self.selected.item_id
        self.layout[collection_name] = [item for item in self.layout[collection_name] if item["id"] != item_id]
        if self.selected.kind == "room":
            self.layout["devices"] = [
                item for item in self.layout["devices"] if item.get("room_id") != item_id
            ]
        self.selected = None
        self._load_property_panel()
        self._persist(
            "Deleted spatial item",
            history_before=history_before,
            selection_before=selection_before,
        )

    def _bounds(self) -> tuple[float, float, float, float]:
        rooms = self.layout["rooms"]
        if not rooms:
            return (0.0, 0.0, 10.0, 8.0)
        min_x = min(room["x_m"] for room in rooms)
        min_y = min(room["y_m"] for room in rooms)
        max_x = max(room["x_m"] + room["length_m"] for room in rooms)
        max_y = max(room["y_m"] + room["width_m"] for room in rooms)
        return min_x, min_y, max_x, max_y

    def _scale_2d(self) -> float:
        return 55.0 * self.layout["view"]["zoom_2d"]

    def _transform_2d(self) -> SpatialTransform2D:
        return SpatialTransform2D(
            width_px=max(1.0, float(self.canvas_2d.winfo_width())),
            height_px=max(1.0, float(self.canvas_2d.winfo_height())),
            pixels_per_m=self._scale_2d(),
            pan_x_px=self.layout["view"]["pan_x"],
            pan_y_px=self.layout["view"]["pan_y"],
        )

    def _world_to_canvas(self, x: float, y: float) -> tuple[float, float]:
        return self._transform_2d().model_to_screen(x, y)

    def _canvas_to_world(self, x: float, y: float) -> tuple[float, float]:
        return self._transform_2d().screen_to_model(x, y)

    def fit_views(self) -> None:
        min_x, min_y, max_x, max_y = self._bounds()
        width_m = max(1.0, max_x - min_x)
        height_m = max(1.0, max_y - min_y)
        cw = max(200, self.canvas_2d.winfo_width())
        ch = max(200, self.canvas_2d.winfo_height())
        self.layout["view"]["zoom_2d"] = max(0.2, min(5.0, 0.78 * min(cw / (55 * width_m), ch / (55 * height_m))))
        scale = self._scale_2d()
        cx = (min_x + max_x) / 2
        cy = (min_y + max_y) / 2
        self.layout["view"]["pan_x"] = -cx * scale
        self.layout["view"]["pan_y"] = -cy * scale

        floor_z = self.layout["floor"]["elevation_m"]
        z_values = [floor_z]
        for room in self.layout["rooms"]:
            z0 = room.get("floor_elevation_m", floor_z)
            z_values.extend((z0, z0 + room["height_m"]))
        model_span = max(width_m, height_m, max(z_values) - min(z_values), 1.0)
        c3w = max(200, self.canvas_3d.winfo_width())
        c3h = max(200, self.canvas_3d.winfo_height())
        self.layout["view"]["zoom_3d"] = max(
            0.2,
            min(5.0, 0.62 * min(c3w, c3h) / (34.0 * model_span)),
        )
        self.layout["view"]["pan_3d_x"] = 0.0
        self.layout["view"]["pan_3d_y"] = 0.0
        self._persist("Fit spatial views")

    def reset_2d(self) -> None:
        self.layout["view"]["zoom_2d"] = 1.0
        self.layout["view"]["pan_x"] = 0.0
        self.layout["view"]["pan_y"] = 0.0
        self._persist("Reset 2D view")

    def redraw(self) -> None:
        self._refresh_validation()
        self._update_metrics()
        self._draw_2d()
        self._draw_3d()

    def _pressure_relationships(self) -> list[dict[str, Any]]:
        if not self._show_relationships.get():
            return []
        return pressure_relationships(self.layout, self._analysis_getter())

    def _draw_relationships_2d(self) -> None:
        room_by_id = {room["id"]: room for room in self.layout["rooms"]}
        for relationship in self._pressure_relationships():
            high = room_by_id.get(relationship.get("higher_room_id"))
            low = room_by_id.get(relationship.get("lower_room_id"))
            if high is None or low is None:
                continue
            hx = high["x_m"] + high["length_m"] / 2.0
            hy = high["y_m"] + high["width_m"] / 2.0
            lx = low["x_m"] + low["length_m"] / 2.0
            ly = low["y_m"] + low["width_m"] / 2.0
            x0, y0 = self._world_to_canvas(hx, hy)
            x1, y1 = self._world_to_canvas(lx, ly)
            status = relationship["status"]
            color = "#15803d" if status == "pass" else ("#dc2626" if status == "warning" else "#64748b")
            self.canvas_2d.create_line(
                x0, y0, x1, y1,
                arrow="last",
                width=2,
                dash=(6, 3) if status == "unavailable" else (),
                fill=color,
                tags=("pressure_relationship",),
            )
            if self._show_labels.get():
                delta = relationship.get("delta_pa")
                minimum = relationship.get("min_delta_pa")
                label = (
                    "pressure unavailable"
                    if delta is None or minimum is None
                    else f"Δ {delta:g} Pa / ≥ {minimum:g} Pa"
                )
                self.canvas_2d.create_text(
                    (x0 + x1) / 2,
                    (y0 + y1) / 2 - 10,
                    text=label,
                    fill=color,
                    tags=("pressure_relationship",),
                )

    def _draw_2d(self) -> None:
        canvas = self.canvas_2d
        canvas.delete("all")
        w = max(1, canvas.winfo_width())
        h = max(1, canvas.winfo_height())
        if self._show_grid.get():
            grid = max(0.1, self.layout["grid_m"])
            scale = self._scale_2d()
            if grid * scale >= 8:
                x0, y0 = self._canvas_to_world(0, 0)
                x1, y1 = self._canvas_to_world(w, h)
                start_x = math.floor(min(x0, x1) / grid) * grid
                end_x = math.ceil(max(x0, x1) / grid) * grid
                start_y = math.floor(min(y0, y1) / grid) * grid
                end_y = math.ceil(max(y0, y1) / grid) * grid
                x = start_x
                while x <= end_x + 1e-9:
                    cx, _ = self._world_to_canvas(x, 0)
                    canvas.create_line(cx, 0, cx, h, fill="#e7ecf1", tags=("grid",))
                    x += grid
                y = start_y
                while y <= end_y + 1e-9:
                    _, cy = self._world_to_canvas(0, y)
                    canvas.create_line(0, cy, w, cy, fill="#e7ecf1", tags=("grid",))
                    y += grid

        pressure_by_id = mapped_pressure_values(self.layout, self._analysis_getter())
        pressures = [value for value in pressure_by_id.values() if value is not None]
        pmin = min(pressures) if pressures else None
        pmax = max(pressures) if pressures else None
        warning_ids = self._warning_item_ids()
        sync_by_id = {
            record["room_id"]: record["state"]
            for record in engineering_sync_states(self.layout, self._analysis_getter())
        }

        for room in self.layout["rooms"]:
            x0_m, y0_m, x1_m, y1_m = room_plan_bounds(room)
            x0, y0 = self._world_to_canvas(x0_m, y0_m)
            x1, y1 = self._world_to_canvas(x1_m, y1_m)
            selected = self.selected == _Hit("room", room["id"])
            hovered = self._hovered == _Hit("room", room["id"])
            sync_state = sync_by_id.get(room["id"], "unmapped")
            outline = (
                "#1d4ed8"
                if selected
                else (
                    "#0284c7"
                    if hovered
                    else (
                        "#b45309"
                        if room["id"] in warning_ids
                        else (
                            "#b91c1c"
                            if sync_state == "conflicting"
                            else (
                                "#7c3aed"
                                if sync_state == "engineering_newer"
                                else ("#0f766e" if sync_state == "geometry_newer" else "#34495e")
                            )
                        )
                    )
                )
            )
            display_pressure = pressure_by_id.get(room["id"])
            fill = (
                _pressure_fill(display_pressure, pmin, pmax)
                if self._show_pressure.get()
                else "#dfe7ef"
            )
            canvas.create_rectangle(
                x0, y0, x1, y1,
                fill=fill, outline=outline, width=3 if selected else 2,
                tags=(f"room:{room['id']}", "room"),
            )
            if self._show_labels.get():
                pressure_text = (
                    f"\n{display_pressure:g} Pa"
                    if self._show_pressure.get() and display_pressure is not None
                    else ""
                )
                canvas.create_text(
                    (x0 + x1) / 2,
                    (y0 + y1) / 2,
                    text=(
                        f"{room['name']}\n"
                        f"{room['length_m']:g} × {room['width_m']:g} × "
                        f"{room['height_m']:g} m{pressure_text}"
                    ),
                    justify="center",
                    tags=(f"room:{room['id']}", "room"),
                )
            if selected:
                handle = 6
                canvas.create_rectangle(
                    x1 - handle, y1 - handle, x1 + handle, y1 + handle,
                    fill="#1d4ed8", outline="#ffffff",
                    tags=(f"resize:{room['id']}", "resize_handle"),
                )

        self._draw_relationships_2d()

        for issue in self._validation_issues:
            if issue.get("code") != "room_overlap":
                continue
            bounds = issue.get("bounds_m")
            if not isinstance(bounds, list) or len(bounds) != 4:
                continue
            x0, y0 = self._world_to_canvas(bounds[0], bounds[1])
            x1, y1 = self._world_to_canvas(bounds[2], bounds[3])
            canvas.create_rectangle(
                x0, y0, x1, y1,
                outline="#dc2626", width=2, dash=(5, 3), tags=("validation",)
            )
            canvas.create_text(
                (x0 + x1) / 2, (y0 + y1) / 2,
                text="OVERLAP", fill="#991b1b", tags=("validation",)
            )

        if self._show_devices.get():
            symbols = {
                "door": "D",
                "supply": "S",
                "return": "R",
                "exhaust": "E",
                "ffu": "F",
                "equipment": "Q",
                "sensor": "●",
                "transfer": "T",
            }
            for device in self.layout["devices"]:
                x, y = self._world_to_canvas(device["x_m"], device["y_m"])
                selected = self.selected == _Hit("device", device["id"])
                device_outline = (
                    "#c0392b"
                    if selected
                    else ("#b45309" if device["id"] in warning_ids else "#2c3e50")
                )
                tag = f"device:{device['id']}"
                if device["type"] in {"door", "transfer"}:
                    half = device.get("width_m", 0.9) / 2.0
                    side = device.get("wall_side", "south")
                    if side in {"north", "south"}:
                        p0 = self._world_to_canvas(device["x_m"] - half, device["y_m"])
                        p1 = self._world_to_canvas(device["x_m"] + half, device["y_m"])
                    else:
                        p0 = self._world_to_canvas(device["x_m"], device["y_m"] - half)
                        p1 = self._world_to_canvas(device["x_m"], device["y_m"] + half)
                    canvas.create_line(
                        *p0, *p1,
                        fill=device_outline,
                        width=7 if selected else 5,
                        tags=(tag, "device"),
                    )
                    if self._show_labels.get():
                        canvas.create_text(
                            x, y - 10,
                            text=symbols[device["type"]],
                            tags=(tag, "device"),
                        )
                else:
                    radius = 9 if selected else 7
                    canvas.create_oval(
                        x - radius, y - radius, x + radius, y + radius,
                        fill="#ffffff", outline=device_outline,
                        width=3 if selected else 2,
                        tags=(tag, "device"),
                    )
                    canvas.create_text(
                        x, y, text=symbols.get(device["type"], "?"),
                        tags=(tag, "device"),
                    )

        if not self.layout["rooms"] and not self.layout["devices"]:
            canvas.create_text(
                w / 2,
                h / 2,
                text=(
                    "No spatial layout yet\n"
                    "Use + Room or open a verification project with room geometry."
                ),
                justify="center",
                fill="#667788",
            )

    def _project_3d(self, x: float, y: float, z: float) -> tuple[float, float]:
        az = math.radians(self.layout["view"]["azimuth_deg"])
        el = math.radians(self.layout["view"]["elevation_deg"])
        xr = x * math.cos(az) - y * math.sin(az)
        yr = x * math.sin(az) + y * math.cos(az)
        sy = yr * math.sin(el) - z * math.cos(el)
        scale = 34.0 * self.layout["view"]["zoom_3d"]
        return (
            self.canvas_3d.winfo_width() / 2 + self.layout["view"]["pan_3d_x"] + xr * scale,
            self.canvas_3d.winfo_height() * 0.66 + self.layout["view"]["pan_3d_y"] + sy * scale,
        )

    def _draw_3d(self) -> None:
        canvas = self.canvas_3d
        canvas.delete("all")
        if not self.layout["rooms"]:
            canvas.create_text(
                max(1, canvas.winfo_width()) / 2,
                max(1, canvas.winfo_height()) / 2,
                text="3D geometry appears here",
                fill="#9fb2c5",
            )
            return

        min_x, min_y, max_x, max_y = self._bounds()
        cx = (min_x + max_x) / 2
        cy = (min_y + max_y) / 2
        floor_z = self.layout["floor"]["elevation_m"]
        pad = max(0.5, self.layout["grid_m"])
        floor_points = [
            self._project_3d(min_x - cx - pad, min_y - cy - pad, floor_z),
            self._project_3d(max_x - cx + pad, min_y - cy - pad, floor_z),
            self._project_3d(max_x - cx + pad, max_y - cy + pad, floor_z),
            self._project_3d(min_x - cx - pad, max_y - cy + pad, floor_z),
        ]
        canvas.create_polygon(
            *sum(floor_points, ()),
            fill="#202b36", outline="#526577", width=1, tags=("floor3d",),
        )

        pressure_by_id = mapped_pressure_values(self.layout, self._analysis_getter())
        pressures = [value for value in pressure_by_id.values() if value is not None]
        pmin = min(pressures) if pressures else None
        pmax = max(pressures) if pressures else None
        warning_ids = self._warning_item_ids()
        sync_by_id = {
            record["room_id"]: record["state"]
            for record in engineering_sync_states(self.layout, self._analysis_getter())
        }

        az = math.radians(self.layout["view"]["azimuth_deg"])
        ordered = sorted(
            self.layout["rooms"],
            key=lambda room: (
                (room["x_m"] - cx) * math.sin(az)
                + (room["y_m"] - cy) * math.cos(az)
            ),
        )
        for room in ordered:
            prism = room_prism_vertices(room, default_floor_elevation_m=floor_z)
            z0 = prism["base"][0][2]
            z1 = prism["top"][0][2]
            base = [
                self._project_3d(x - cx, y - cy, z)
                for x, y, z in prism["base"]
            ]
            top = [
                self._project_3d(x - cx, y - cy, z)
                for x, y, z in prism["top"]
            ]
            x0_m, y0_m, x1_m, y1_m = room_plan_bounds(room)
            x0 = x0_m - cx
            y0 = y0_m - cy
            x1 = x1_m - cx
            y1 = y1_m - cy
            display_pressure = pressure_by_id.get(room["id"])
            fill = (
                _pressure_fill(display_pressure, pmin, pmax)
                if self._show_pressure.get()
                else "#dfe7ef"
            )
            selected = self.selected == _Hit("room", room["id"])
            sync_state = sync_by_id.get(room["id"], "unmapped")
            outline = (
                "#7dd3fc"
                if selected
                else (
                    "#fb7185"
                    if room["id"] in warning_ids
                    else (
                        "#f87171"
                        if sync_state == "conflicting"
                        else ("#c4b5fd" if sync_state == "engineering_newer" else ("#5eead4" if sync_state == "geometry_newer" else "#c8d5e3"))
                    )
                )
            )
            tag = f"room:{room['id']}"
            canvas.create_polygon(
                *sum(top, ()), fill=fill, outline=outline, width=2,
                tags=(tag, "room3d"),
            )
            canvas.create_polygon(
                *sum((base[1], base[2], top[2], top[1]), ()),
                fill="#6c7f92", outline=outline, tags=(tag, "room3d"),
            )
            canvas.create_polygon(
                *sum((base[2], base[3], top[3], top[2]), ()),
                fill="#53687c", outline=outline, tags=(tag, "room3d"),
            )
            for start, end in zip(base, top):
                canvas.create_line(
                    *start, *end, fill=outline, width=1, tags=(tag, "room3d")
                )
            if self._show_labels.get():
                pressure_text = (
                    "" if not self._show_pressure.get() or display_pressure is None
                    else f"\n{display_pressure:g} Pa"
                )
                canvas.create_text(
                    *self._project_3d((x0 + x1) / 2, (y0 + y1) / 2, z1 + 0.2),
                    text=f"{room['name']}{pressure_text}",
                    fill="#f0f6fc",
                    tags=(tag, "room3d"),
                )

        if self._show_devices.get():
            room_by_id = {room["id"]: room for room in self.layout["rooms"]}
            for device in self.layout["devices"]:
                room = room_by_id.get(str(device.get("room_id") or ""))
                room_floor = (
                    room.get("floor_elevation_m", floor_z)
                    if room is not None
                    else floor_z
                )
                tag = f"device:{device['id']}"
                selected = self.selected == _Hit("device", device["id"])
                device_outline = (
                    "#ffffff"
                    if selected
                    else ("#fb7185" if device["id"] in warning_ids else "#d6a20f")
                )
                if device["type"] in {"door", "transfer"}:
                    bottom = self._project_3d(
                        device["x_m"] - cx,
                        device["y_m"] - cy,
                        room_floor + device["z_m"],
                    )
                    top = self._project_3d(
                        device["x_m"] - cx,
                        device["y_m"] - cy,
                        room_floor + device["z_m"] + device.get("height_m", 0.4),
                    )
                    canvas.create_line(
                        *bottom, *top,
                        fill=device_outline,
                        width=7 if selected else 5,
                        tags=(tag, "device3d"),
                    )
                else:
                    x, y = self._project_3d(
                        device["x_m"] - cx,
                        device["y_m"] - cy,
                        room_floor + device["z_m"],
                    )
                    radius = 5 if selected else 4
                    canvas.create_oval(
                        x - radius, y - radius, x + radius, y + radius,
                        fill="#fbbf24", outline=device_outline,
                        width=2, tags=(tag, "device3d"),
                    )

    def _parse_hit(self, tags: tuple[str, ...]) -> _Hit | None:
        for tag in tags:
            if tag.startswith("room:"):
                return _Hit("room", tag.split(":", 1)[1])
            if tag.startswith("device:"):
                return _Hit("device", tag.split(":", 1)[1])
        return None

    def _on_left_down(self, event: tk.Event) -> None:
        self.canvas_2d.focus_set()
        current = self.canvas_2d.find_withtag("current")
        hit = None
        self._resize_room_id = None
        if current:
            tags = self.canvas_2d.gettags(current[0])
            resize_tag = next(
                (tag for tag in tags if tag.startswith("resize:")),
                None,
            )
            if resize_tag is not None:
                room_id = resize_tag.split(":", 1)[1]
                hit = _Hit("room", room_id)
                self._resize_room_id = room_id
            else:
                hit = self._parse_hit(tags)
        self.selected = hit
        self._drag_anchor = self._canvas_to_world(event.x, event.y) if hit else None
        self._drag_history_before = (
            (self._history_layout(), self._selection_state())
            if hit is not None
            else None
        )
        self._load_property_panel()
        self.redraw()

    def _on_left_drag(self, event: tk.Event) -> None:
        item = self._selected_object()
        if item is None or self._drag_anchor is None:
            return
        world = self._canvas_to_world(event.x, event.y)
        grid = self.layout["grid_m"]

        if self._resize_room_id is not None and self.selected is not None:
            width = max(0.1, world[0] - item["x_m"])
            depth = max(0.1, world[1] - item["y_m"])
            if self._snap_to_grid.get():
                width = max(grid, round(width / grid) * grid)
                depth = max(grid, round(depth / grid) * grid)
            item["length_m"] = width
            item["width_m"] = depth
        else:
            dx = world[0] - self._drag_anchor[0]
            dy = world[1] - self._drag_anchor[1]
            old_x = item["x_m"]
            old_y = item["y_m"]
            new_x = old_x + dx
            new_y = old_y + dy
            if self._snap_to_grid.get():
                new_x = round(new_x / grid) * grid
                new_y = round(new_y / grid) * grid
            item["x_m"] = new_x
            item["y_m"] = new_y
            actual_dx = new_x - old_x
            actual_dy = new_y - old_y
            if (
                self.selected is not None
                and self.selected.kind == "room"
                and (actual_dx or actual_dy)
            ):
                for device in self.layout["devices"]:
                    if device.get("room_id") == item["id"]:
                        device["x_m"] += actual_dx
                        device["y_m"] += actual_dy
            self._drag_anchor = world
        self._load_property_panel()
        self.redraw()

    def _on_left_up(self, event: tk.Event) -> None:
        if (
            self._drag_anchor is not None
            and self.selected is not None
            and self._drag_history_before is not None
        ):
            history_before, selection_before = self._drag_history_before
            message = (
                "Room resized"
                if self._resize_room_id is not None
                else "Spatial item moved"
            )
            self._persist(
                message,
                history_before=history_before,
                selection_before=selection_before,
            )
        self._drag_anchor = None
        self._drag_history_before = None
        self._resize_room_id = None

    def _nudge_selected(self, x_direction: int, y_direction: int):
        item = self._selected_object()
        if item is None:
            return "break"
        history_before = self._history_layout()
        selection_before = self._selection_state()
        step = self.layout["grid_m"] if self._snap_to_grid.get() else 0.1
        dx = x_direction * step
        dy = y_direction * step
        item["x_m"] += dx
        item["y_m"] += dy
        if self.selected is not None and self.selected.kind == "room":
            for device in self.layout["devices"]:
                if device.get("room_id") == item["id"]:
                    device["x_m"] += dx
                    device["y_m"] += dy
        self._load_property_panel()
        self._persist(
            "Spatial item nudged",
            history_before=history_before,
            selection_before=selection_before,
        )
        return "break"

    def _on_motion(self, event: tk.Event) -> None:
        x, y = self._canvas_to_world(event.x, event.y)
        self._coord_var.set(f"x {x:.2f} m   y {y:.2f} m")

    def _on_pan_down(self, event: tk.Event) -> None:
        self._pan_anchor = (event.x, event.y)
        self._pan_origin = (
            self.layout["view"]["pan_x"],
            self.layout["view"]["pan_y"],
        )

    def _on_pan_drag(self, event: tk.Event) -> None:
        if self._pan_anchor is None or self._pan_origin is None:
            return
        self.layout["view"]["pan_x"] = self._pan_origin[0] + event.x - self._pan_anchor[0]
        self.layout["view"]["pan_y"] = self._pan_origin[1] + event.y - self._pan_anchor[1]
        self.redraw()

    def _on_wheel(self, event: tk.Event) -> None:
        self._zoom_at(1.1 if event.delta > 0 else 1 / 1.1, event.x, event.y)

    def _zoom_at(self, factor: float, x: float, y: float) -> None:
        before = self._canvas_to_world(x, y)
        self.layout["view"]["zoom_2d"] = max(0.2, min(8.0, self.layout["view"]["zoom_2d"] * factor))
        after = self._world_to_canvas(*before)
        self.layout["view"]["pan_x"] += x - after[0]
        self.layout["view"]["pan_y"] += y - after[1]
        self.redraw()

    def _on_wheel_3d(self, event: tk.Event) -> None:
        self._zoom_3d(1.1 if event.delta > 0 else 1 / 1.1)

    def _zoom_3d(self, factor: float) -> None:
        self.layout["view"]["zoom_3d"] = max(0.2, min(8.0, self.layout["view"]["zoom_3d"] * factor))
        self._draw_3d()

    def rotate_3d(self, delta: float) -> None:
        self.layout["view"]["azimuth_deg"] = (self.layout["view"]["azimuth_deg"] + delta) % 360
        self._draw_3d()

    def tilt_3d(self, delta: float) -> None:
        self.layout["view"]["elevation_deg"] = max(
            5.0, min(75.0, self.layout["view"]["elevation_deg"] + delta)
        )
        self._draw_3d()

    def reset_3d(self) -> None:
        self.layout["view"]["azimuth_deg"] = 35.0
        self.layout["view"]["elevation_deg"] = 28.0
        self.layout["view"]["zoom_3d"] = 1.0
        self.layout["view"]["pan_3d_x"] = 0.0
        self.layout["view"]["pan_3d_y"] = 0.0
        self._draw_3d()

    def _on_pan_3d_down(self, event: tk.Event) -> None:
        self._pan_anchor = (event.x, event.y)
        self._pan_origin = (
            self.layout["view"]["pan_3d_x"],
            self.layout["view"]["pan_3d_y"],
        )

    def _on_pan_3d_drag(self, event: tk.Event) -> None:
        if self._pan_anchor is None or self._pan_origin is None:
            return
        self.layout["view"]["pan_3d_x"] = self._pan_origin[0] + event.x - self._pan_anchor[0]
        self.layout["view"]["pan_3d_y"] = self._pan_origin[1] + event.y - self._pan_anchor[1]
        self._draw_3d()

    def _on_3d_click(self, event: tk.Event) -> None:
        current = self.canvas_3d.find_withtag("current")
        if not current:
            return
        hit = self._parse_hit(self.canvas_3d.gettags(current[0]))
        if hit is None:
            return
        self.selected = hit
        self._load_property_panel()
        self.redraw()
