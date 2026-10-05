from __future__ import annotations

from dataclasses import dataclass
import copy
import heapq
import math
import uuid
from typing import Any, Callable

import tkinter as tk
from tkinter import messagebox, ttk

from .gui_theme import theme_palette
from .spatial_editing import duplicate_spatial_item, update_spatial_properties

from .spatial_integrity import (
    DEVICE_TYPES,
    SPATIAL_GEOMETRY_EPSILON_M,
    SPATIAL_LAYOUT_VERSION,
    SPATIAL_METADATA_KEY,
)
from .spatial_transforms import (
    BASE_2D_PIXELS_PER_M,
    fit_3d_view,
    model_to_screen_2d,
    project_3d,
    screen_to_model_2d,
    zoom_2d_at,
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


def _drag_target_coordinate(
    *,
    item_origin: float,
    pointer_origin: float,
    pointer_current: float,
    grid_m: float,
    snap_to_grid: bool,
) -> float:
    """Return a drag coordinate computed from immutable gesture-start origins."""
    values = (item_origin, pointer_origin, pointer_current, grid_m)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("drag coordinates and grid must be finite")
    if grid_m <= 0:
        raise ValueError("drag grid must be positive")
    target = item_origin + (pointer_current - pointer_origin)
    if snap_to_grid:
        return round(target / grid_m) * grid_m
    return target


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
            "overlay_mode": "pressure",
            "projection_mode": "orthographic",
            "section_enabled": False,
            "section_height_m": 2.4,
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
            for field in ("zone", "classification", "analysis_room_name"):
                if raw.get(field) is not None:
                    text = str(raw.get(field)).strip()
                    if text:
                        room[field] = text
            rooms.append(room)
    result["rooms"] = rooms

    raw_sync = source.get("engineering_sync")
    if isinstance(raw_sync, dict):
        analysis_id = str(raw_sync.get("analysis_id") or "").strip()
        raw_records = raw_sync.get("rooms", [])
        valid_room_ids = {room["id"] for room in rooms}
        records: list[dict] = []
        seen_sync_room_ids: set[str] = set()
        if analysis_id and isinstance(raw_records, list):
            for raw_record in raw_records:
                if not isinstance(raw_record, dict):
                    continue
                room_id = str(raw_record.get("room_id") or "").strip()
                analysis_room_name = str(
                    raw_record.get("analysis_room_name") or ""
                ).strip()
                length = _finite_number(raw_record.get("length_m"), math.nan)
                width = _finite_number(raw_record.get("width_m"), math.nan)
                height = _finite_number(raw_record.get("height_m"), math.nan)
                if (
                    not room_id
                    or room_id not in valid_room_ids
                    or room_id in seen_sync_room_ids
                    or not analysis_room_name
                    or not all(
                        math.isfinite(value) and value > 0
                        for value in (length, width, height)
                    )
                ):
                    continue
                seen_sync_room_ids.add(room_id)
                records.append(
                    {
                        "room_id": room_id,
                        "analysis_room_name": analysis_room_name,
                        "length_m": length,
                        "width_m": width,
                        "height_m": height,
                    }
                )
            result["engineering_sync"] = {
                "analysis_id": analysis_id,
                "rooms": records,
            }

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
            default_width = {
                "door": 0.9,
                "window": 1.2,
                "opening": 1.0,
                "transfer": 0.6,
            }.get(device_type, 0.4)
            default_height = {
                "door": 2.1,
                "window": 1.2,
                "opening": 2.1,
                "transfer": 0.4,
            }.get(device_type, 0.2)
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
        projection_mode = str(
            view.get("projection_mode", "orthographic")
        ).strip().lower()
        if projection_mode not in {"orthographic", "perspective"}:
            projection_mode = "orthographic"
        result["view"]["projection_mode"] = projection_mode
        result["view"]["section_enabled"] = bool(
            view.get("section_enabled", False)
        )
        result["view"]["section_height_m"] = _finite_number(
            view.get("section_height_m"),
            result["floor"]["elevation_m"] + 2.4,
        )
        overlay_mode = str(
            view.get(
                "overlay_mode",
                "pressure" if view.get("show_pressure", True) else "none",
            )
        ).strip().lower()
        if overlay_mode not in ENGINEERING_OVERLAY_MODES:
            overlay_mode = "pressure"
        result["view"]["overlay_mode"] = overlay_mode
        result["view"]["show_pressure"] = overlay_mode == "pressure"
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
    analysis_id = str(getattr(analysis, "id", "") or "").strip()
    if layout["rooms"] and analysis_id:
        layout["engineering_sync"] = {
            "analysis_id": analysis_id,
            "rooms": [
                {
                    "room_id": room["id"],
                    "analysis_room_name": str(
                        room.get("analysis_room_name") or room["name"]
                    ),
                    "length_m": room["length_m"],
                    "width_m": room["width_m"],
                    "height_m": room["height_m"],
                }
                for room in layout["rooms"]
            ],
        }
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


def _geometry_number(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return math.nan
    return number if math.isfinite(number) else math.nan


def _geometry_matches(left: dict, right: dict) -> bool:
    return all(
        math.isclose(
            _geometry_number(left.get(field)),
            _geometry_number(right.get(field)),
            rel_tol=0.0,
            abs_tol=SPATIAL_GEOMETRY_EPSILON_M,
        )
        for field in ("length_m", "width_m", "height_m")
    )


def _geometry_differences(left: dict, right: dict) -> list[str]:
    return [
        field
        for field in ("length_m", "width_m", "height_m")
        if not math.isclose(
            _geometry_number(left.get(field)),
            _geometry_number(right.get(field)),
            rel_tol=0.0,
            abs_tol=SPATIAL_GEOMETRY_EPSILON_M,
        )
    ]


def _sync_baseline_by_room(layout: dict, analysis: Any) -> dict[str, dict]:
    sync = layout.get("engineering_sync")
    analysis_id = str(getattr(analysis, "id", "") or "").strip()
    if (
        not isinstance(sync, dict)
        or str(sync.get("analysis_id") or "").strip() != analysis_id
    ):
        return {}
    records = sync.get("rooms", [])
    if not isinstance(records, list):
        return {}
    return {
        str(record.get("room_id")): record
        for record in records
        if isinstance(record, dict) and str(record.get("room_id") or "").strip()
    }


def _classify_sync_state(
    spatial_room: dict,
    engineering_room: dict,
    baseline_room: dict | None,
) -> str:
    if _geometry_matches(spatial_room, engineering_room):
        return "synchronized"
    if baseline_room is None:
        # Without a common baseline, source ordering cannot be proven safely.
        return "conflicting"
    spatial_changed = not _geometry_matches(spatial_room, baseline_room)
    engineering_changed = not _geometry_matches(engineering_room, baseline_room)
    if spatial_changed and not engineering_changed:
        return "geometry_newer"
    if engineering_changed and not spatial_changed:
        return "engineering_newer"
    return "conflicting"


def engineering_sync_status(layout: dict, analysis: Any) -> dict:
    """Return deterministic room-level geometry/engineering synchronization state.

    "Newer" is reported only when a persisted last-synchronized geometry baseline
    proves which side changed. Equal geometry is synchronized even without a
    baseline. Divergent geometry without provenance is reported as conflicting.
    """

    normalized = normalize_layout(layout)
    rooms = normalized["rooms"]
    baseline_by_room = _sync_baseline_by_room(normalized, analysis)
    statuses: list[dict] = []
    kind = getattr(analysis, "kind", "")
    payload = getattr(analysis, "input", None)
    payload = payload if isinstance(payload, dict) else {}

    if kind == "room_verification":
        for index, room in enumerate(rooms):
            target = payload if index == 0 else None
            if target is None:
                statuses.append(
                    {
                        "room_id": room["id"],
                        "analysis_room_name": str(
                            room.get("analysis_room_name") or room["name"]
                        ),
                        "state": "unmapped",
                        "differences": [],
                        "message": "Only the first spatial room maps to a room-verification analysis.",
                    }
                )
                continue
            state = _classify_sync_state(
                room, target, baseline_by_room.get(room["id"])
            )
            statuses.append(
                {
                    "room_id": room["id"],
                    "analysis_room_name": str(
                        room.get("analysis_room_name") or target.get("name") or room["name"]
                    ),
                    "state": state,
                    "differences": _geometry_differences(room, target),
                    "message": "",
                }
            )
    elif kind == "project_verification":
        raw_rooms = payload.get("rooms", [])
        raw_rooms = raw_rooms if isinstance(raw_rooms, list) else []
        name_groups: dict[str, list[dict]] = {}
        for target in raw_rooms:
            if not isinstance(target, dict):
                continue
            name = str(target.get("name") or "").strip()
            if name:
                name_groups.setdefault(name.casefold(), []).append(target)

        source_groups: dict[str, list[str]] = {}
        for room in rooms:
            link = str(room.get("analysis_room_name") or room["name"]).strip()
            source_groups.setdefault(link.casefold(), []).append(room["id"])

        for room in rooms:
            link = str(room.get("analysis_room_name") or room["name"]).strip()
            key = link.casefold()
            targets = name_groups.get(key, [])
            if len(source_groups.get(key, [])) > 1:
                state = "conflicting"
                differences: list[str] = []
                message = f"Multiple spatial rooms map to analysis room {link!r}."
            elif len(targets) > 1:
                state = "conflicting"
                differences = []
                message = f"Analysis room name {link!r} is duplicated."
            elif not targets:
                state = "unmapped"
                differences = []
                message = f"Analysis room {link!r} is not available."
            else:
                target = targets[0]
                baseline_room = baseline_by_room.get(room["id"])
                baseline_link = (
                    str(baseline_room.get("analysis_room_name") or "").strip().casefold()
                    if baseline_room is not None
                    else ""
                )
                if baseline_link and baseline_link != key:
                    state = "conflicting"
                    differences = _geometry_differences(room, target)
                    message = (
                        "The engineering-room mapping changed since the last explicit "
                        "synchronization."
                    )
                else:
                    state = _classify_sync_state(room, target, baseline_room)
                    differences = _geometry_differences(room, target)
                    message = ""
            statuses.append(
                {
                    "room_id": room["id"],
                    "analysis_room_name": link,
                    "state": state,
                    "differences": differences,
                    "message": message,
                }
            )
    else:
        statuses = [
            {
                "room_id": room["id"],
                "analysis_room_name": str(
                    room.get("analysis_room_name") or room["name"]
                ),
                "state": "unmapped",
                "differences": [],
                "message": "The active analysis has no room-geometry synchronization contract.",
            }
            for room in rooms
        ]

    states = [item["state"] for item in statuses]
    if not states:
        overall = "unmapped"
    elif all(state == "synchronized" for state in states):
        overall = "synchronized"
    elif "conflicting" in states:
        overall = "conflicting"
    elif "unmapped" in states:
        overall = "unmapped"
    elif "geometry_newer" in states and "engineering_newer" in states:
        overall = "conflicting"
    elif "geometry_newer" in states:
        overall = "geometry_newer"
    elif "engineering_newer" in states:
        overall = "engineering_newer"
    else:
        overall = "conflicting"

    counts = {
        state: sum(1 for item in statuses if item["state"] == state)
        for state in (
            "synchronized",
            "geometry_newer",
            "engineering_newer",
            "conflicting",
            "unmapped",
        )
    }
    return {"overall": overall, "rooms": statuses, "counts": counts}


def _record_sync_baseline(
    layout: dict,
    analysis: Any,
    mapped_pairs: list[tuple[dict, dict]],
) -> None:
    analysis_id = str(getattr(analysis, "id", "") or "").strip()
    if not isinstance(layout, dict) or not analysis_id:
        return
    records = [
        {
            "room_id": source["id"],
            "analysis_room_name": str(target.get("name") or source.get("analysis_room_name") or source["name"]),
            "length_m": source["length_m"],
            "width_m": source["width_m"],
            "height_m": source["height_m"],
        }
        for source, target in mapped_pairs
    ]
    if records:
        layout["engineering_sync"] = {
            "analysis_id": analysis_id,
            "rooms": records,
        }


def sync_layout_to_analysis(layout: dict, analysis: Any) -> bool:
    if analysis is None or not isinstance(getattr(analysis, "input", None), dict):
        return False
    rooms = normalize_layout(layout)["rooms"]
    if not rooms:
        return False

    changed = False
    if getattr(analysis, "kind", "") == "room_verification":
        source = rooms[0]
        target = analysis.input
        for key in ("length_m", "width_m", "height_m"):
            value = source[key]
            if target.get(key) != value:
                target[key] = value
                changed = True
        _record_sync_baseline(layout, analysis, [(source, target)])
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

    # Resolve and validate every mapping before mutating engineering inputs so a
    # later mapping error can never leave a partially synchronized domain object.
    mapped_pairs: list[tuple[dict, dict]] = []
    used_source_links: set[str] = set()
    for source in rooms:
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
        mapped_pairs.append((source, target))

    for source, target in mapped_pairs:
        for key in ("length_m", "width_m", "height_m"):
            if target.get(key) != source[key]:
                target[key] = source[key]
                changed = True

    _record_sync_baseline(layout, analysis, mapped_pairs)
    return changed


def sync_analysis_to_layout(layout: dict, analysis: Any) -> bool:
    """Pull engineering room dimensions into mapped spatial rooms explicitly.

    Geometry synchronization is dimension-only in both directions. The complete
    mapping and all dimensions are validated before mutation; spatial X/Y placement,
    pressure evidence, and unrelated metadata are preserved.
    """
    if analysis is None or not isinstance(getattr(analysis, "input", None), dict):
        return False
    raw_spatial_rooms = layout.get("rooms") if isinstance(layout, dict) else None
    if not isinstance(raw_spatial_rooms, list) or not raw_spatial_rooms:
        return False

    normalized_rooms = normalize_layout(layout)["rooms"]
    original_by_id = {
        str(room.get("id")): room
        for room in raw_spatial_rooms
        if isinstance(room, dict) and str(room.get("id") or "").strip()
    }
    kind = getattr(analysis, "kind", "")
    mapped_pairs: list[tuple[dict, dict]] = []

    if kind == "room_verification":
        source = original_by_id.get(normalized_rooms[0]["id"])
        if source is None:
            return False
        mapped_pairs = [(source, analysis.input)]
    elif kind == "project_verification":
        engineering_rooms = analysis.input.get("rooms")
        if not isinstance(engineering_rooms, list):
            return False
        _require_unique_sync_names(normalized_rooms, source="the spatial layout")
        _require_unique_sync_names(engineering_rooms, source="the active analysis")
        by_name = {
            str(room.get("name")).strip().casefold(): room
            for room in engineering_rooms
            if isinstance(room, dict) and str(room.get("name") or "").strip()
        }
        used_links: set[str] = set()
        for normalized in normalized_rooms:
            link = str(
                normalized.get("analysis_room_name") or normalized["name"]
            ).strip()
            key = link.casefold()
            if key in used_links:
                raise SpatialSyncError(
                    "Cannot pull engineering geometry because multiple layout rooms "
                    f"map to analysis room {link!r}."
                )
            used_links.add(key)
            target = by_name.get(key)
            if target is None:
                if normalized.get("analysis_room_name"):
                    raise SpatialSyncError(
                        f"Linked analysis room {link!r} does not exist in the active analysis."
                    )
                continue
            source = original_by_id.get(normalized["id"])
            if source is not None:
                mapped_pairs.append((source, target))
    else:
        return False

    prepared: list[tuple[dict, dict, dict[str, float]]] = []
    for source, target in mapped_pairs:
        geometry: dict[str, float] = {}
        for field in ("length_m", "width_m", "height_m"):
            value = _geometry_number(target.get(field))
            if not math.isfinite(value) or value <= 0:
                raise SpatialSyncError(
                    f"Engineering room {target.get('name')!r} has invalid {field}."
                )
            geometry[field] = value
        prepared.append((source, target, geometry))

    changed = False
    prior_baseline = copy.deepcopy(layout.get("engineering_sync"))
    for source, _target, geometry in prepared:
        for field, value in geometry.items():
            if not math.isclose(
                _geometry_number(source.get(field)),
                value,
                rel_tol=0.0,
                abs_tol=SPATIAL_GEOMETRY_EPSILON_M,
            ):
                source[field] = value
                changed = True

    _record_sync_baseline(layout, analysis, mapped_pairs)
    return changed or layout.get("engineering_sync") != prior_baseline


def _room_overlap_records(
    rooms: list[dict],
) -> list[tuple[int, int, list[float]]]:
    """Return deterministic room-overlap records using an adaptive broad phase.

    The sweep axis is chosen from projected room density. Expired candidates are
    removed through an end-coordinate heap, avoiding a full active-list rebuild
    for every room. Exact two-dimensional overlap checks still use the same
    explicit engineering tolerance as before. Results are sorted by original room
    order to preserve validation/report order.
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
    start_index = 1 if sweep_x else 2
    end_index = 3 if sweep_x else 4

    ordered = sorted(bounds, key=lambda item: (item[start_index], item[0]))
    active_by_index: dict[
        int, tuple[int, float, float, float, float]
    ] = {}
    expiry_heap: list[tuple[float, int]] = []
    overlaps: list[tuple[int, int, list[float]]] = []

    for current in ordered:
        expiry_threshold = (
            current[start_index] + SPATIAL_GEOMETRY_EPSILON_M
        )
        while expiry_heap and expiry_heap[0][0] <= expiry_threshold:
            _axis_end, expired_index = heapq.heappop(expiry_heap)
            active_by_index.pop(expired_index, None)

        for other in active_by_index.values():
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

        active_by_index[current[0]] = current
        heapq.heappush(expiry_heap, (current[end_index], current[0]))

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


def _validate_normalized_layout(layout: dict) -> list[dict]:
    """Validate one canonical normalized layout without allocating a second copy."""
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
        if device["type"] in {"door", "window", "opening", "transfer"}:
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


def validate_layout(value: Any) -> list[dict]:
    """Return advisory spatial-edit warnings without mutating persisted layout data."""
    return _validate_normalized_layout(normalize_layout(value))


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


def _result_room_reports(result: dict | None) -> list[dict]:
    if not isinstance(result, dict):
        return []
    if isinstance(result.get("room"), str) and isinstance(result.get("findings"), list):
        return [result]
    rooms = result.get("rooms")
    return [room for room in rooms if isinstance(room, dict)] if isinstance(rooms, list) else []


def pressure_overlay_state(
    layout: dict,
    analysis: Any = None,
    result: dict | None = None,
) -> dict:
    """Describe pressure rendering from explicit fresh-result or spatial evidence."""
    normalized = normalize_layout(layout)
    sync = engineering_sync_status(normalized, analysis)
    mapping_by_room = {
        record["room_id"]: record for record in sync["rooms"]
    }
    report_by_name = {
        str(report.get("room") or "").strip().casefold(): report
        for report in _result_room_reports(result)
        if str(report.get("room") or "").strip()
    }

    evidence: list[dict] = []
    for room in normalized["rooms"]:
        mapping = mapping_by_room.get(room["id"], {})
        linked_name = str(
            mapping.get("analysis_room_name")
            or room.get("analysis_room_name")
            or room.get("name")
            or ""
        ).strip()
        pressure_value = None
        source = "unavailable"
        status = "unavailable"

        report = report_by_name.get(linked_name.casefold()) if linked_name else None
        if report is not None:
            findings = report.get("findings")
            if isinstance(findings, list):
                finding = next(
                    (
                        item for item in findings
                        if isinstance(item, dict) and item.get("code") == "PRESSURE"
                    ),
                    None,
                )
                if finding is not None:
                    actual = _geometry_number(finding.get("actual"))
                    if math.isfinite(actual):
                        pressure_value = actual
                        source = "result"
                        status = str(finding.get("status") or "unavailable")

        if pressure_value is None:
            spatial = _geometry_number(room.get("pressure_pa"))
            if math.isfinite(spatial):
                pressure_value = spatial
                source = "spatial"
                status = "spatial"

        evidence.append(
            {
                "room_id": room["id"],
                "availability": "available" if pressure_value is not None else "unavailable",
                "pressure_pa": pressure_value,
                "source": source,
                "status": status,
                "engineering_state": mapping.get("state", "unmapped"),
            }
        )

    pressures = [
        item["pressure_pa"] for item in evidence if item["pressure_pa"] is not None
    ]
    minimum = min(pressures) if pressures else None
    maximum = max(pressures) if pressures else None
    for item in evidence:
        item["fill"] = _pressure_fill(item["pressure_pa"], minimum, maximum)

    return {
        "minimum_pressure_pa": minimum,
        "maximum_pressure_pa": maximum,
        "rooms": evidence,
    }


ENGINEERING_OVERLAY_MODES = ("none", "pressure", "ach", "airflow", "status")


def _engineering_status(value: Any) -> str:
    token = str(value or "").strip().lower().replace(" ", "_")
    aliases = {
        "passed": "pass",
        "verified": "pass",
        "failed": "fail",
        "error": "fail",
        "warn": "warning",
        "not_verified": "not_checked",
        "missing_evidence": "not_checked",
        "unverified": "not_checked",
    }
    return aliases.get(token, token or "unavailable")


def _status_fill(status: str) -> str:
    normalized = _engineering_status(status)
    if normalized == "pass":
        return "#dcfce7"
    if normalized == "fail":
        return "#fee2e2"
    if normalized == "warning":
        return "#fef3c7"
    if normalized == "not_checked":
        return "#e2e8f0"
    return "#dfe7ef"


def _scalar_fill(
    value: float | None,
    minimum: float | None,
    maximum: float | None,
    *,
    low_rgb: tuple[int, int, int] = (224, 242, 254),
    high_rgb: tuple[int, int, int] = (14, 116, 144),
) -> str:
    if value is None or minimum is None or maximum is None:
        return "#dfe7ef"
    ratio = 0.5 if maximum <= minimum else (value - minimum) / (maximum - minimum)
    ratio = max(0.0, min(1.0, ratio))
    rgb = tuple(
        int(round(low + (high - low) * ratio))
        for low, high in zip(low_rgb, high_rgb)
    )
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def engineering_overlay_state(
    layout: dict,
    analysis: Any = None,
    result: dict | None = None,
    *,
    mode: str = "pressure",
) -> dict:
    """Project canonical run/spatial results into display-only room overlays.

    This function never evaluates engineering requirements. It only maps values and
    statuses already present in fresh analysis results or explicit spatial evidence.
    """
    normalized_mode = str(mode or "none").strip().lower()
    if normalized_mode not in ENGINEERING_OVERLAY_MODES:
        normalized_mode = "none"

    normalized = normalize_layout(layout)
    result_dict = result if isinstance(result, dict) else {}

    if normalized_mode == "pressure":
        pressure = pressure_overlay_state(normalized, analysis, result_dict)
        rooms = []
        for item in pressure["rooms"]:
            value = item.get("pressure_pa")
            status = _engineering_status(item.get("status"))
            label = (
                "Pressure: unavailable"
                if value is None
                else f"Pressure: {value:+g} Pa"
            )
            if status not in {"unavailable", "spatial"}:
                label += f" · {status.upper()}"
            rooms.append({**item, "label": label})
        return {
            "mode": "pressure",
            "title": "Pressure",
            "unit": "Pa",
            "minimum": pressure.get("minimum_pressure_pa"),
            "maximum": pressure.get("maximum_pressure_pa"),
            "rooms": rooms,
        }

    raw_reports = _result_room_reports(result_dict)
    report_by_name: dict[str, dict] = {}
    for report in raw_reports:
        name = str(report.get("room") or report.get("name") or "").strip().casefold()
        if name:
            report_by_name[name] = report
    node_by_name = {
        str(node.get("name") or "").strip().casefold(): node
        for node in result_dict.get("nodes", [])
        if isinstance(node, dict) and str(node.get("name") or "").strip()
    }

    rooms: list[dict] = []
    scalar_values: list[float] = []
    for room in normalized["rooms"]:
        linked_name = str(
            room.get("analysis_room_name") or room.get("name") or ""
        ).strip()
        report = report_by_name.get(linked_name.casefold()) if linked_name else None
        node = node_by_name.get(linked_name.casefold()) if linked_name else None

        value: float | None = None
        status = "unavailable"
        label = f"{normalized_mode.title()}: unavailable"
        details: dict[str, Any] = {}

        if normalized_mode == "ach" and isinstance(report, dict):
            raw_ach = _geometry_number(report.get("ach"))
            if math.isfinite(raw_ach):
                value = raw_ach
                scalar_values.append(raw_ach)
                findings = report.get("findings")
                if isinstance(findings, list):
                    ach_finding = next(
                        (
                            item
                            for item in findings
                            if isinstance(item, dict)
                            and str(item.get("code") or "").upper() == "ACH"
                        ),
                        None,
                    )
                    if ach_finding is not None:
                        status = _engineering_status(ach_finding.get("status"))
                label = f"ACH: {raw_ach:.2f} 1/h"
                if status != "unavailable":
                    label += f" · {status.upper()}"

        elif normalized_mode == "airflow":
            source = report if isinstance(report, dict) else node
            if isinstance(source, dict):
                air_balance = source.get("air_balance")
                if not isinstance(air_balance, dict):
                    air_balance = source
                supply = _geometry_number(
                    air_balance.get("supply_airflow_m3_h")
                    if "supply_airflow_m3_h" in air_balance
                    else air_balance.get("supply_m3_h")
                )
                if not math.isfinite(supply):
                    supply = _geometry_number(source.get("governing_airflow_m3_h"))
                returned = _geometry_number(
                    air_balance.get("return_airflow_m3_h")
                    if "return_airflow_m3_h" in air_balance
                    else air_balance.get("return_m3_h")
                )
                exhausted = _geometry_number(
                    air_balance.get("exhaust_airflow_m3_h")
                    if "exhaust_airflow_m3_h" in air_balance
                    else air_balance.get("exhaust_m3_h")
                )
                if math.isfinite(supply):
                    value = supply
                    scalar_values.append(supply)
                    details["supply_m3_h"] = supply
                if math.isfinite(returned):
                    details["return_m3_h"] = returned
                if math.isfinite(exhausted):
                    details["exhaust_m3_h"] = exhausted
                if "passes_minimum_surplus" in air_balance:
                    status = "pass" if air_balance.get("passes_minimum_surplus") else "fail"
                if details:
                    parts = []
                    if "supply_m3_h" in details:
                        parts.append(f"S {details['supply_m3_h']:.0f}")
                    if "return_m3_h" in details:
                        parts.append(f"R {details['return_m3_h']:.0f}")
                    if "exhaust_m3_h" in details:
                        parts.append(f"E {details['exhaust_m3_h']:.0f}")
                    label = "Airflow: " + " / ".join(parts) + " m³/h"
                    if status != "unavailable":
                        label += f" · {status.upper()}"

        elif normalized_mode == "status":
            if isinstance(report, dict):
                status = _engineering_status(report.get("status"))
                if status == "unavailable":
                    air_balance = report.get("air_balance")
                    if isinstance(air_balance, dict) and "passes_minimum_surplus" in air_balance:
                        status = (
                            "pass"
                            if air_balance.get("passes_minimum_surplus")
                            else "fail"
                        )
            if status == "unavailable" and isinstance(node, dict):
                raw_status = node.get("status")
                if raw_status is not None:
                    status = _engineering_status(raw_status)
            label = (
                "Status: NOT VERIFIED"
                if status in {"unavailable", "not_checked"}
                else f"Status: {status.upper()}"
            )

        rooms.append(
            {
                "room_id": room["id"],
                "value": value,
                "status": status,
                "label": label,
                "fill": "#dfe7ef",
                "details": details,
            }
        )

    minimum = min(scalar_values) if scalar_values else None
    maximum = max(scalar_values) if scalar_values else None
    for item in rooms:
        if normalized_mode == "status":
            item["fill"] = _status_fill(item["status"])
        elif normalized_mode in {"ach", "airflow"}:
            item["fill"] = _scalar_fill(item["value"], minimum, maximum)

    return {
        "mode": normalized_mode,
        "title": {
            "none": "No overlay",
            "ach": "Air Changes per Hour",
            "airflow": "Airflow",
            "status": "Verification Status",
        }.get(normalized_mode, normalized_mode.title()),
        "unit": {"ach": "1/h", "airflow": "m³/h"}.get(normalized_mode, ""),
        "minimum": minimum,
        "maximum": maximum,
        "rooms": rooms,
    }


def validated_floor_settings(
    *,
    name: str,
    elevation_m: str | float,
    default_ceiling_height_m: str | float,
    grid_m: str | float,
    fallback_name: str,
) -> dict[str, float | str]:
    """Validate floor-dialog values without mutating the spatial model."""
    floor_name = str(name).strip() or str(fallback_name)
    if not floor_name:
        raise ValueError("Floor name must not be empty.")

    try:
        elevation = float(elevation_m)
        ceiling = float(default_ceiling_height_m)
        grid = float(grid_m)
    except (TypeError, ValueError) as exc:
        raise ValueError("Elevation, ceiling height, and grid spacing must be numbers.") from exc

    if not math.isfinite(elevation):
        raise ValueError("Floor elevation must be a finite number.")
    if not math.isfinite(ceiling) or ceiling <= 0:
        raise ValueError("Default ceiling height must be greater than 0 m.")
    if not math.isfinite(grid) or grid <= 0:
        raise ValueError("Grid spacing must be greater than 0 m.")

    return {
        "name": floor_name,
        "elevation_m": elevation,
        "default_ceiling_height_m": ceiling,
        "grid_m": grid,
    }


class FloorPropertiesDialog(tk.Toplevel):
    """Atomic floor/grid editor with inline validation."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        name: str,
        elevation_m: float,
        default_ceiling_height_m: float,
        grid_m: float,
    ):
        super().__init__(parent)
        self.title("Floor Properties")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result: dict[str, float | str] | None = None
        self._fallback_name = name

        self.name_var = tk.StringVar(value=name)
        self.elevation_var = tk.StringVar(value=f"{elevation_m:g}")
        self.ceiling_var = tk.StringVar(value=f"{default_ceiling_height_m:g}")
        self.grid_var = tk.StringVar(value=f"{grid_m:g}")
        self.error_var = tk.StringVar()

        shell = ttk.Frame(self, padding=14)
        shell.pack(fill="both", expand=True)
        ttk.Label(
            shell,
            text="FLOOR / GRID",
            style="CX.Section.TLabel",
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))

        fields = (
            ("Floor name", self.name_var, ""),
            ("Elevation", self.elevation_var, "m"),
            ("Default ceiling height", self.ceiling_var, "m"),
            ("Grid spacing", self.grid_var, "m"),
        )
        self._entries: list[ttk.Entry] = []
        for row, (label, variable, unit) in enumerate(fields, start=1):
            ttk.Label(shell, text=label).grid(
                row=row, column=0, sticky="w", padx=(0, 10), pady=4
            )
            entry = ttk.Entry(shell, textvariable=variable, width=28)
            entry.grid(row=row, column=1, sticky="ew", pady=4)
            self._entries.append(entry)
            ttk.Label(shell, text=unit, width=3).grid(
                row=row, column=2, sticky="w", padx=(6, 0), pady=4
            )

        ttk.Label(
            shell,
            textvariable=self.error_var,
            wraplength=410,
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(8, 2))

        buttons = ttk.Frame(shell)
        buttons.grid(row=6, column=0, columnspan=3, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(
            buttons,
            text="Apply",
            style="CX.Primary.TButton",
            command=self._accept,
        ).pack(side="right", padx=(0, 6))

        shell.columnconfigure(1, weight=1)
        self.bind("<Escape>", lambda _event: self.destroy())
        self.bind("<Return>", lambda _event: self._accept())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._entries[0].focus_set()
        self._entries[0].selection_range(0, "end")

    def _accept(self) -> None:
        try:
            result = validated_floor_settings(
                name=self.name_var.get(),
                elevation_m=self.elevation_var.get(),
                default_ceiling_height_m=self.ceiling_var.get(),
                grid_m=self.grid_var.get(),
                fallback_name=self._fallback_name,
            )
        except ValueError as exc:
            self.error_var.set(str(exc))
            return
        self.result = result
        self.destroy()


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
        on_pull_requested: Callable[[], None] | None = None,
        result_getter: Callable[[], Any] | None = None,
        on_history_record: Callable[
            [dict, tuple[str, str] | None, dict, tuple[str, str] | None, str],
            bool,
        ] | None = None,
        on_undo_requested: Callable[[], bool] | None = None,
        on_redo_requested: Callable[[], bool] | None = None,
        on_selection_change: Callable[[str, str], None] | None = None,
        on_view_status_change: Callable[[str], None] | None = None,
    ):
        super().__init__(master)
        self._project_getter = project_getter
        self._analysis_getter = analysis_getter
        self._on_change = on_change
        self._on_sync_requested = on_sync_requested
        self._on_pull_requested = on_pull_requested
        self._result_getter = result_getter or (lambda: None)
        self._status_setter = status_setter
        self._on_history_record = on_history_record
        self._on_undo_requested = on_undo_requested
        self._on_redo_requested = on_redo_requested
        self._on_selection_change = on_selection_change
        self._on_view_status_change = on_view_status_change

        self.layout = empty_layout()
        self.selected: _Hit | None = None
        self._hovered: _Hit | None = None
        self._snap_indicator_world: tuple[float, float] | None = None
        self._drag_anchor: tuple[float, float] | None = None
        self._drag_item_origin: tuple[float, float] | None = None
        self._pan_anchor: tuple[int, int] | None = None
        self._pan_origin: tuple[float, float] | None = None
        self._orbit_anchor: tuple[int, int] | None = None
        self._orbit_origin: tuple[float, float] | None = None
        self._show_grid = tk.BooleanVar(value=True)
        self._snap_to_grid = tk.BooleanVar(value=True)
        self._show_pressure = tk.BooleanVar(value=True)
        self._show_labels = tk.BooleanVar(value=True)
        self._show_devices = tk.BooleanVar(value=True)
        self._show_relationships = tk.BooleanVar(value=True)
        self._overlay_mode = tk.StringVar(value="Pressure")
        self._overlay_summary_var = tk.StringVar(value="Overlay: Pressure")
        self._coord_var = tk.StringVar(value="x 0.00 m   y 0.00 m")
        self._selection_var = tk.StringVar(value="No selection")
        self._validation_var = tk.StringVar(value="Spatial checks: PASS")
        self._sync_var = tk.StringVar(value="Engineering sync: unmapped")
        self._metrics_var = tk.StringVar(value="0 rooms")
        self._zoom_var = tk.StringVar(value="Zoom 100%")
        self._validation_issues: list[dict] = []
        self._last_validation_key: tuple | None = None
        self._property_vars: dict[str, tk.StringVar] = {}
        self._property_rows: dict[str, ttk.Frame] = {}
        self._property_entries: dict[str, ttk.Entry] = {}
        self._workspace_mode = tk.StringVar(value="split")
        self._inspector_visible = tk.BooleanVar(value=True)
        self._history_can_undo = False
        self._history_can_redo = False
        self._drag_history_before: tuple[dict, tuple[str, str] | None] | None = None
        self._resize_room_id: str | None = None
        self._tool_mode = tk.StringVar(value="select")
        self._measurement_points: list[tuple[float, float]] = []
        self._measurement_result_var = tk.StringVar(value="Ready")
        self._hidden_item_ids: set[str] = set()
        self._isolated_item: _Hit | None = None
        self._hovered_3d: _Hit | None = None
        self._xray_3d = tk.BooleanVar(value=False)
        self._projection_mode = tk.StringVar(value="Orthographic")
        self._section_enabled = tk.BooleanVar(value=False)
        self._section_height_var = tk.StringVar(value="2.40")
        self._theme_palette = theme_palette("light")

        self._build()
        self.refresh()

    def _build(self) -> None:
        commandbar = ttk.Frame(self, padding=(8, 7, 8, 4))
        commandbar.pack(fill="x")

        ttk.Label(
            commandbar,
            text="DESIGN",
            style="CX.Section.TLabel",
        ).pack(side="left", padx=(0, 8))
        ttk.Button(commandbar, text="+ Room", width=8, command=self.add_room).pack(
            side="left", padx=2
        )
        device_button = ttk.Menubutton(commandbar, text="+ Device / opening")
        device_menu = tk.Menu(device_button, tearoff=False)
        device_button.configure(menu=device_menu)
        device_button.pack(side="left", padx=2)
        for device_type, label in (
            ("door", "Door"),
            ("window", "Window"),
            ("opening", "Opening"),
            ("ffu", "FFU"),
            ("supply", "Supply"),
            ("return", "Return"),
            ("exhaust", "Exhaust"),
            ("equipment", "Equipment"),
            ("sensor", "Sensor"),
            ("transfer", "Transfer"),
        ):
            device_menu.add_command(
                label=label,
                command=lambda t=device_type: self.add_device(t),
            )
        ttk.Button(commandbar, text="Duplicate", command=self.duplicate_selected).pack(
            side="left", padx=2
        )
        ttk.Button(commandbar, text="Delete", width=7, command=self.delete_selected).pack(
            side="left", padx=2
        )
        ttk.Separator(commandbar, orient="vertical").pack(
            side="left", fill="y", padx=7
        )
        self._undo_button = ttk.Button(
            commandbar, text="Undo", width=7, command=self.undo_edit, state="disabled"
        )
        self._undo_button.pack(side="left", padx=2)
        self._redo_button = ttk.Button(
            commandbar, text="Redo", width=7, command=self.redo_edit, state="disabled"
        )
        self._redo_button.pack(side="left", padx=2)

        modebar = ttk.Frame(self, padding=(8, 0, 8, 4))
        modebar.pack(fill="x")
        ttk.Label(modebar, text="Workspace").pack(side="left", padx=(0, 6))
        for value, label in (("2d", "2D"), ("3d", "3D"), ("split", "Split")):
            ttk.Radiobutton(
                modebar,
                text=label,
                value=value,
                variable=self._workspace_mode,
                command=self._apply_workspace_mode,
            ).pack(side="left", padx=1)
        ttk.Separator(modebar, orient="vertical").pack(
            side="left", fill="y", padx=8
        )
        ttk.Button(modebar, text="Fit", width=6, command=self.fit_views).pack(
            side="left", padx=2
        )
        ttk.Button(modebar, text="Reset 2D", width=9, command=self.reset_2d).pack(
            side="left", padx=2
        )
        ttk.Button(modebar, text="Floor…", width=7, command=self.edit_floor).pack(
            side="left", padx=2
        )
        ttk.Button(
            modebar,
            text="Push to analysis",
            command=self._on_sync_requested,
        ).pack(side="right", padx=2)
        ttk.Button(
            modebar,
            text="Pull from analysis",
            command=self._on_pull_requested or (lambda: None),
            state="normal" if self._on_pull_requested is not None else "disabled",
        ).pack(side="right", padx=2)

        viewbar = ttk.Frame(self, padding=(8, 0, 8, 4))
        viewbar.pack(fill="x")
        ttk.Checkbutton(
            viewbar, text="Grid", variable=self._show_grid, command=self.redraw
        ).pack(side="left", padx=(2, 6))
        for label, variable, key in (
            ("Snap", self._snap_to_grid, "snap_to_grid"),
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
        ttk.Label(viewbar, textvariable=self._zoom_var).pack(side="left", padx=(10, 2))
        ttk.Button(viewbar, text="Validate", command=self.report_validation).pack(
            side="left", padx=(10, 2)
        )
        ttk.Label(viewbar, textvariable=self._validation_var).pack(
            side="right", padx=(10, 2)
        )

        overlaybar = ttk.Frame(self, padding=(8, 0, 8, 4))
        overlaybar.pack(fill="x")
        ttk.Label(
            overlaybar,
            text="ENGINEERING OVERLAY",
            style="CX.Section.TLabel",
        ).pack(side="left", padx=(0, 8))
        overlay_picker = ttk.Combobox(
            overlaybar,
            textvariable=self._overlay_mode,
            values=("None", "Pressure", "ACH", "Airflow", "Status"),
            state="readonly",
            width=13,
        )
        overlay_picker.pack(side="left")
        overlay_picker.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._set_overlay_mode(self._overlay_mode.get()),
        )
        ttk.Label(
            overlaybar,
            textvariable=self._overlay_summary_var,
        ).pack(side="left", padx=(12, 0))

        self._body = ttk.Panedwindow(self, orient="horizontal")
        self._body.pack(fill="both", expand=True, padx=8, pady=(2, 6))

        views = ttk.Frame(self._body)
        self._views_frame = views
        self._body.add(views, weight=6)

        self._view_panes = ttk.Panedwindow(views, orient="horizontal")
        self._view_panes.pack(fill="both", expand=True)

        self._two_d_frame = ttk.Frame(self._view_panes)
        header2 = ttk.Frame(self._two_d_frame)
        header2.pack(fill="x", padx=4, pady=(3, 4))
        ttk.Label(
            header2, text="2D PLAN", style="CX.ViewTitle.TLabel"
        ).pack(side="left")
        view2_button = ttk.Menubutton(header2, text="View")
        view2_menu = tk.Menu(view2_button, tearoff=False)
        view2_menu.add_command(label="Fit selected", command=self.fit_selected)
        view2_menu.add_command(label="Reset 2D", command=self.reset_2d)
        view2_menu.add_separator()
        view2_menu.add_command(label="Isolate selected", command=self.isolate_selected)
        view2_menu.add_command(label="Hide selected", command=self.hide_selected)
        view2_menu.add_command(label="Show all", command=self.show_all)
        view2_button.configure(menu=view2_menu)
        view2_button.pack(side="left", padx=(8, 2))
        measure_button = ttk.Menubutton(header2, text="Measure")
        measure_menu = tk.Menu(measure_button, tearoff=False)
        measure_menu.add_command(
            label="Distance",
            command=lambda: self.set_measurement_tool("distance"),
        )
        measure_menu.add_command(
            label="Area (rectangle)",
            command=lambda: self.set_measurement_tool("area"),
        )
        measure_menu.add_separator()
        measure_menu.add_command(label="Clear measurement", command=self.clear_measurement)
        measure_button.configure(menu=measure_menu)
        measure_button.pack(side="left", padx=2)
        ttk.Label(header2, textvariable=self._coord_var).pack(side="right")
        self.canvas_2d = tk.Canvas(
            self._two_d_frame,
            background=self._theme_palette["canvas_2d"],
            highlightthickness=1,
            highlightbackground=self._theme_palette["border"],
        )
        self.canvas_2d.pack(fill="both", expand=True)
        footer2 = ttk.Frame(self._two_d_frame)
        footer2.pack(fill="x", padx=4, pady=(3, 0))
        ttk.Label(footer2, textvariable=self._metrics_var, anchor="w").pack(
            side="left", fill="x", expand=True
        )
        ttk.Label(
            footer2,
            textvariable=self._measurement_result_var,
            anchor="e",
        ).pack(side="right", padx=(8, 0))

        self._three_d_frame = ttk.Frame(self._view_panes)
        header3 = ttk.Frame(self._three_d_frame)
        header3.pack(fill="x", padx=4, pady=(3, 4))
        ttk.Label(
            header3, text="3D MODEL", style="CX.ViewTitle.TLabel"
        ).pack(side="left")
        camera_button = ttk.Menubutton(header3, text="Views")
        camera_menu = tk.Menu(camera_button, tearoff=False)
        camera_button.configure(menu=camera_menu)
        for preset, label in (
            ("top", "Top"),
            ("front", "Front"),
            ("back", "Back"),
            ("left", "Left"),
            ("right", "Right"),
            ("iso", "Isometric"),
        ):
            camera_menu.add_command(
                label=label,
                command=lambda p=preset: self.set_3d_view_preset(p),
            )
        camera_button.pack(side="left", padx=(5, 2))
        ttk.Button(header3, text="Fit", width=4, command=self.fit_3d).pack(
            side="left", padx=2
        )
        projection_picker = ttk.Combobox(
            header3,
            textvariable=self._projection_mode,
            values=("Orthographic", "Perspective"),
            state="readonly",
            width=12,
        )
        projection_picker.pack(side="left", padx=(4, 2))
        projection_picker.bind(
            "<<ComboboxSelected>>",
            lambda _event: self.set_3d_projection(self._projection_mode.get()),
        )
        ttk.Checkbutton(
            header3,
            text="Section",
            variable=self._section_enabled,
            command=self._toggle_section_plane,
        ).pack(side="left", padx=(4, 2))
        section_height = ttk.Spinbox(
            header3,
            textvariable=self._section_height_var,
            from_=-100.0,
            to=1000.0,
            increment=0.25,
            width=6,
            command=self._apply_section_height,
        )
        section_height.pack(side="left", padx=(0, 2))
        section_height.bind("<Return>", self._apply_section_height)
        section_height.bind("<FocusOut>", self._apply_section_height)
        ttk.Label(header3, text="Z m").pack(side="left", padx=(0, 4))
        ttk.Checkbutton(
            header3,
            text="X-Ray",
            variable=self._xray_3d,
            command=self._draw_3d,
        ).pack(side="left", padx=(4, 2))
        for label, delta in (("↺", -15), ("↻", 15)):
            ttk.Button(
                header3,
                text=label,
                width=3,
                command=lambda d=delta: self.rotate_3d(d),
            ).pack(side="right", padx=2)
        ttk.Button(
            header3, text="↓", width=3, command=lambda: self.tilt_3d(-5)
        ).pack(side="right", padx=2)
        ttk.Button(
            header3, text="↑", width=3, command=lambda: self.tilt_3d(5)
        ).pack(side="right", padx=2)
        ttk.Button(header3, text="Reset", command=self.reset_3d).pack(
            side="right", padx=2
        )
        self.canvas_3d = tk.Canvas(
            self._three_d_frame,
            background=self._theme_palette["canvas_3d"],
            highlightthickness=1,
            highlightbackground=self._theme_palette["border"],
        )
        self.canvas_3d.pack(fill="both", expand=True)

        inspector = ttk.Frame(self._body, padding=(10, 8))
        self._inspector_frame = inspector
        self._body.add(inspector, weight=2)
        inspector_header = ttk.Frame(
            inspector,
            style="CX.PanelHeader.TFrame",
        )
        inspector_header.pack(fill="x", pady=(0, 5))
        ttk.Label(
            inspector_header,
            text="PROPERTIES",
            style="CX.PanelHeader.TLabel",
        ).pack(side="left")
        self._inspector_close_button = ttk.Button(
            inspector_header,
            text="×",
            width=3,
            style="CX.Compact.TButton",
            command=lambda: self.set_inspector_visible(False),
        )
        self._inspector_close_button.pack(side="right")
        ttk.Label(
            inspector,
            textvariable=self._selection_var,
            wraplength=310,
        ).pack(fill="x", pady=(3, 8))

        property_groups = (
            (
                "Geometry",
                (
                    ("x_m", "X", "m"),
                    ("y_m", "Y", "m"),
                    ("z_m", "Elevation / Z", "m"),
                    ("length_m", "Length", "m"),
                    ("width_m", "Width", "m"),
                    ("height_m", "Height", "m"),
                    ("floor_elevation_m", "Floor elevation", "m"),
                ),
            ),
            (
                "Cleanroom",
                (
                    ("zone", "Zone", ""),
                    ("classification", "Classification", ""),
                    ("pressure_pa", "Design pressure", "Pa"),
                    ("analysis_room_name", "Analysis link", ""),
                ),
            ),
            (
                "Identity",
                (
                    ("name", "Name", ""),
                    ("room_id", "Room ID", ""),
                ),
            ),
            (
                "Opening / placement",
                (
                    ("orientation_deg", "Orientation", "deg"),
                    ("wall_side", "Wall side", ""),
                    ("swing", "Swing", ""),
                ),
            ),
        )
        for group_name, fields in property_groups:
            section = ttk.LabelFrame(inspector, text=group_name, padding=(8, 6))
            section.pack(fill="x", pady=(0, 7))
            for key, label, unit in fields:
                row = ttk.Frame(section)
                row.pack(fill="x", pady=2)
                ttk.Label(row, text=label).pack(side="left")
                value_frame = ttk.Frame(row)
                value_frame.pack(side="right")
                var = tk.StringVar()
                self._property_vars[key] = var
                entry = ttk.Entry(value_frame, textvariable=var, width=16)
                entry.pack(side="left")
                self._property_entries[key] = entry
                if unit:
                    ttk.Label(value_frame, text=unit, width=4).pack(
                        side="left", padx=(4, 0)
                    )
                self._property_rows[key] = row
        ttk.Button(
            inspector,
            text="Apply properties",
            command=self.apply_properties,
        ).pack(anchor="e", pady=(2, 6))
        ttk.Separator(inspector, orient="horizontal").pack(fill="x", pady=5)
        ttk.Label(inspector, textvariable=self._sync_var, wraplength=310).pack(
            fill="x", pady=(3, 0)
        )

        self._apply_workspace_mode()

        self.canvas_2d.bind("<Configure>", lambda event: self.redraw())
        self.canvas_3d.bind("<Configure>", lambda event: self._draw_3d())
        self.canvas_2d.bind("<Motion>", self._on_motion)
        self.canvas_2d.bind("<Button-1>", self._on_left_down)
        self.canvas_2d.bind("<Escape>", self._on_escape)
        self.canvas_2d.bind("<B1-Motion>", self._on_left_drag)
        self.canvas_2d.bind("<ButtonRelease-1>", self._on_left_up)
        self.canvas_2d.bind("<Button-2>", self._on_pan_down)
        self.canvas_2d.bind("<B2-Motion>", self._on_pan_drag)
        self.canvas_2d.bind("<Button-3>", self._on_context_menu_2d)
        self.canvas_2d.bind("<Control-Button-1>", self._on_context_menu_2d)
        self.canvas_2d.bind("<Leave>", self._on_canvas_leave)
        self.canvas_2d.bind("<MouseWheel>", self._on_wheel)
        self.canvas_2d.bind(
            "<Button-4>", lambda event: self._zoom_at(1.1, event.x, event.y)
        )
        self.canvas_2d.bind(
            "<Button-5>", lambda event: self._zoom_at(1 / 1.1, event.x, event.y)
        )
        self.canvas_3d.bind("<Motion>", self._on_3d_motion)
        self.canvas_3d.bind("<Leave>", self._on_3d_leave)
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
            canvas.bind("<Control-d>", self._on_duplicate_shortcut)
            canvas.bind("<Delete>", lambda event: self.delete_selected())
            canvas.bind("<Left>", lambda event: self._nudge_selected(-1, 0))
            canvas.bind("<Right>", lambda event: self._nudge_selected(1, 0))
            canvas.bind("<Up>", lambda event: self._nudge_selected(0, -1))
            canvas.bind("<Down>", lambda event: self._nudge_selected(0, 1))

    def _apply_workspace_mode(self) -> None:
        mode = self._workspace_mode.get()
        if mode not in {"2d", "3d", "split"}:
            mode = "split"
            self._workspace_mode.set(mode)
        for frame in (self._two_d_frame, self._three_d_frame):
            try:
                self._view_panes.forget(frame)
            except tk.TclError:
                pass
        if mode in {"2d", "split"}:
            self._view_panes.add(self._two_d_frame, weight=5 if mode == "split" else 1)
        if mode in {"3d", "split"}:
            self._view_panes.add(self._three_d_frame, weight=5 if mode == "split" else 1)
        self.redraw()

    def set_workspace_mode(self, mode: str) -> None:
        if mode not in {"2d", "3d", "split"}:
            raise ValueError("workspace mode must be '2d', '3d', or 'split'")
        self._workspace_mode.set(mode)
        self._apply_workspace_mode()

    def apply_theme(self, value: str, *, redraw: bool = True) -> None:
        """Apply presentation colors without modifying spatial/project state."""
        self._theme_palette = theme_palette(value)
        palette = self._theme_palette
        self.canvas_2d.configure(
            background=palette["canvas_2d"],
            highlightbackground=palette["border"],
        )
        self.canvas_3d.configure(
            background=palette["canvas_3d"],
            highlightbackground=palette["border"],
        )
        if redraw:
            self.redraw()

    def inspector_visible(self) -> bool:
        frame = getattr(self, "_inspector_frame", None)
        body = getattr(self, "_body", None)
        if frame is None or body is None:
            return False
        return str(frame) in {str(item) for item in body.panes()}

    def set_inspector_visible(self, visible: bool) -> None:
        frame = getattr(self, "_inspector_frame", None)
        body = getattr(self, "_body", None)
        if frame is None or body is None:
            return
        requested = bool(visible)
        present = self.inspector_visible()
        self._inspector_visible.set(requested)
        if requested and not present:
            body.add(frame, weight=2)
        elif not requested and present:
            body.forget(frame)
        state = "shown" if requested else "hidden"
        self._status_setter(f"Design Inspector {state}")

    def toggle_inspector(self) -> None:
        self.set_inspector_visible(not self.inspector_visible())

    def show_inspector(self) -> None:
        self.set_inspector_visible(True)

    @staticmethod
    def _hit_key(kind: str, item_id: str) -> str:
        return f"{kind}:{item_id}"

    def _current_tool_mode(self) -> str:
        variable = getattr(self, "_tool_mode", None)
        return variable.get() if variable is not None else "select"

    def _is_item_visible(self, kind: str, item_id: str) -> bool:
        hidden_item_ids = getattr(self, "_hidden_item_ids", set())
        isolated_item = getattr(self, "_isolated_item", None)
        if self._hit_key(kind, item_id) in hidden_item_ids:
            return False

        if kind == "device":
            device = next(
                (item for item in self.layout["devices"] if item["id"] == item_id),
                None,
            )
            room_id = str(device.get("room_id") or "") if device else ""
            if room_id and self._hit_key("room", room_id) in hidden_item_ids:
                return False

        if isolated_item is None:
            return True
        if isolated_item == _Hit(kind, item_id):
            return True

        if isolated_item.kind == "room" and kind == "device":
            device = next(
                (item for item in self.layout["devices"] if item["id"] == item_id),
                None,
            )
            return bool(
                device
                and str(device.get("room_id") or "") == isolated_item.item_id
            )

        if isolated_item.kind == "device" and kind == "room":
            device = next(
                (
                    item
                    for item in self.layout["devices"]
                    if item["id"] == isolated_item.item_id
                ),
                None,
            )
            return bool(device and str(device.get("room_id") or "") == item_id)

        return False

    def hide_selected(self) -> None:
        if self.selected is None:
            self._status_setter("Select a room or device to hide")
            return
        self._hidden_item_ids.add(
            self._hit_key(self.selected.kind, self.selected.item_id)
        )
        if self._isolated_item == self.selected:
            self._isolated_item = None
        self._status_setter("Selection hidden from spatial views")
        self.redraw()

    def isolate_selected(self) -> None:
        if self.selected is None:
            self._status_setter("Select a room or device to isolate")
            return
        self._hidden_item_ids.discard(
            self._hit_key(self.selected.kind, self.selected.item_id)
        )
        self._isolated_item = _Hit(self.selected.kind, self.selected.item_id)
        self._status_setter("Selection isolated in spatial views")
        self.redraw()

    def show_all(self) -> None:
        self._hidden_item_ids.clear()
        self._isolated_item = None
        self._status_setter("All spatial objects visible")
        self.redraw()

    def set_measurement_tool(self, mode: str) -> None:
        if mode not in {"select", "distance", "area"}:
            raise ValueError("measurement tool must be 'select', 'distance', or 'area'")
        self._tool_mode.set(mode)
        self._measurement_points.clear()
        if mode == "distance":
            self._measurement_result_var.set("Distance: pick start point")
        elif mode == "area":
            self._measurement_result_var.set("Area: pick first rectangle corner")
        else:
            self._measurement_result_var.set("Ready")
        self.redraw()

    def clear_measurement(self) -> None:
        self._tool_mode.set("select")
        self._measurement_points.clear()
        self._measurement_result_var.set("Ready")
        self.redraw()

    def _on_escape(self, event=None):
        self.clear_measurement()
        return "break"

    def _handle_measure_click(self, x: float, y: float) -> None:
        world = self._canvas_to_world(x, y)
        mode = self._current_tool_mode()
        if mode not in {"distance", "area"}:
            return
        if len(self._measurement_points) >= 2:
            self._measurement_points = []
        self._measurement_points.append(world)
        if len(self._measurement_points) == 1:
            if mode == "distance":
                self._measurement_result_var.set("Distance: pick end point")
            else:
                self._measurement_result_var.set("Area: pick opposite rectangle corner")
        else:
            (x0, y0), (x1, y1) = self._measurement_points
            if mode == "distance":
                distance = math.hypot(x1 - x0, y1 - y0)
                self._measurement_result_var.set(f"Distance {distance:.3f} m")
            else:
                area = abs((x1 - x0) * (y1 - y0))
                self._measurement_result_var.set(f"Area {area:.3f} m²")
        self.redraw()

    def _draw_measurement_overlay(self) -> None:
        measurement_points = getattr(self, "_measurement_points", None)
        if not measurement_points:
            return
        canvas = self.canvas_2d
        points = [self._world_to_canvas(x, y) for x, y in measurement_points]
        for px, py in points:
            canvas.create_line(
                px - 5, py, px + 5, py,
                fill="#7c3aed", width=2, tags=("measurement",),
            )
            canvas.create_line(
                px, py - 5, px, py + 5,
                fill="#7c3aed", width=2, tags=("measurement",),
            )
        if len(points) != 2:
            return
        (x0, y0), (x1, y1) = points
        if self._current_tool_mode() == "area":
            canvas.create_rectangle(
                x0, y0, x1, y1,
                outline="#7c3aed", width=2, dash=(5, 3), tags=("measurement",),
            )
        else:
            canvas.create_line(
                x0, y0, x1, y1,
                fill="#7c3aed", width=2, dash=(5, 3), tags=("measurement",),
            )
        canvas.create_text(
            (x0 + x1) / 2,
            (y0 + y1) / 2 - 10,
            text=self._measurement_result_var.get(),
            fill="#5b21b6",
            tags=("measurement",),
        )

    def select_item(self, kind: str, item_id: str, *, notify: bool = False) -> bool:
        if kind not in {"room", "device"}:
            return False
        collection = self.layout["rooms"] if kind == "room" else self.layout["devices"]
        if not any(str(item.get("id")) == item_id for item in collection):
            return False
        self.selected = _Hit(kind, item_id)
        self._load_property_panel()
        self.redraw()
        if notify:
            self._notify_selection_change()
        return True

    def selection_status_text(self) -> str:
        item = self._selected_object()
        if item is None or self.selected is None:
            return "Selected: —"

        name = str(item.get("name") or self.selected.item_id)
        if self.selected.kind == "room":
            parts = [f"Room: {name}"]
            zone = str(item.get("zone") or "").strip()
            if zone:
                parts.append(f"Zone: {zone}")
            classification = str(item.get("classification") or "").strip()
            if classification:
                parts.append(classification)
            pressure = item.get("pressure_pa")
            if isinstance(pressure, (int, float)) and math.isfinite(float(pressure)):
                parts.append(f"{float(pressure):g} Pa")
            return " · ".join(parts)

        device_type = str(item.get("type") or "device").replace("_", " ").title()
        parts = [f"{device_type}: {name}"]
        room_id = str(item.get("room_id") or "")
        room = next(
            (
                candidate
                for candidate in self.layout["rooms"]
                if str(candidate.get("id") or "") == room_id
            ),
            None,
        )
        if room is not None:
            parts.append(str(room.get("name") or room_id))
        return " · ".join(parts)

    def viewport_status_text(self) -> str:
        mode = self._workspace_mode.get()
        mode_label = {"2d": "2D", "3d": "3D", "split": "Split"}.get(
            mode,
            "Split",
        )
        view = self.layout.get("view", {})
        zoom_2d = _finite_number(view.get("zoom_2d"), 1.0) * 100.0
        zoom_3d = _finite_number(view.get("zoom_3d"), 1.0) * 100.0
        projection = str(view.get("projection_mode") or "orthographic").strip().lower()
        projection_label = "Perspective" if projection == "perspective" else "Ortho"
        return (
            f"{mode_label} · 2D {zoom_2d:.0f}% · "
            f"3D {zoom_3d:.0f}% · {projection_label}"
        )

    def _notify_view_status(self) -> None:
        callback = self._on_view_status_change
        if callback is not None:
            callback(self.viewport_status_text())

    def _notify_selection_change(self) -> None:
        if self.selected is None or self._on_selection_change is None:
            return
        self._on_selection_change(self.selected.kind, self.selected.item_id)

    def refresh(self) -> None:
        # A refresh may replace the canonical project/layout beneath an active
        # gesture. Never let stale drag origins mutate the refreshed model.
        self._drag_anchor = None
        self._drag_item_origin = None
        self._drag_history_before = None
        self._resize_room_id = None
        self._tool_mode.set("select")
        self._measurement_points.clear()
        self._measurement_result_var.set("Ready")
        self._hidden_item_ids.clear()
        self._isolated_item = None
        self._hovered_3d = None
        project = self._project_getter()
        analysis = self._analysis_getter()
        self.layout = ensure_project_layout(project, analysis)
        view = self.layout.get("view", {})
        self._snap_to_grid.set(bool(view.get("snap_to_grid", True)))
        self._show_pressure.set(bool(view.get("show_pressure", True)))
        self._show_labels.set(bool(view.get("show_labels", True)))
        self._show_devices.set(bool(view.get("show_devices", True)))
        self._show_relationships.set(bool(view.get("show_relationships", True)))
        overlay_mode = str(view.get("overlay_mode") or "pressure").strip().lower()
        if overlay_mode not in ENGINEERING_OVERLAY_MODES:
            overlay_mode = "pressure"
        self._overlay_mode.set(
            {
                "none": "None",
                "pressure": "Pressure",
                "ach": "ACH",
                "airflow": "Airflow",
                "status": "Status",
            }[overlay_mode]
        )
        self._show_pressure.set(overlay_mode == "pressure")
        projection_mode = str(
            view.get("projection_mode") or "orthographic"
        ).strip().lower()
        if projection_mode not in {"orthographic", "perspective"}:
            projection_mode = "orthographic"
        self._projection_mode.set(
            "Perspective" if projection_mode == "perspective" else "Orthographic"
        )
        self._section_enabled.set(bool(view.get("section_enabled", False)))
        self._section_height_var.set(
            f"{_finite_number(view.get('section_height_m'), self.layout['floor']['elevation_m'] + 2.4):.2f}"
        )
        if self.selected and not self._selected_object():
            self.selected = None
        self._load_property_panel()
        self._update_history_controls()
        self.redraw()

    def set_3d_projection(self, value: str) -> None:
        mode = str(value or "orthographic").strip().lower()
        if mode not in {"orthographic", "perspective"}:
            raise ValueError(
                "3D projection must be orthographic or perspective"
            )
        self.layout.setdefault("view", {})["projection_mode"] = mode
        self._projection_mode.set(
            "Perspective" if mode == "perspective" else "Orthographic"
        )
        project = self._project_getter()
        project.metadata[SPATIAL_METADATA_KEY] = normalize_layout(self.layout)
        self.layout = project.metadata[SPATIAL_METADATA_KEY]
        self._on_change()
        self._status_setter(f"3D projection: {mode.title()}")
        self.fit_3d()

    def _active_section_height(self) -> float | None:
        if not self._section_enabled.get():
            return None
        value = _finite_number(
            self.layout.get("view", {}).get("section_height_m"),
            self.layout["floor"]["elevation_m"] + 2.4,
        )
        return value

    def _toggle_section_plane(self) -> None:
        enabled = bool(self._section_enabled.get())
        self.layout.setdefault("view", {})["section_enabled"] = enabled
        project = self._project_getter()
        project.metadata[SPATIAL_METADATA_KEY] = normalize_layout(self.layout)
        self.layout = project.metadata[SPATIAL_METADATA_KEY]
        self._on_change()
        self._status_setter(
            "3D section plane enabled" if enabled else "3D section plane disabled"
        )
        self.redraw()

    def _apply_section_height(self, _event=None):
        current = _finite_number(
            self.layout.get("view", {}).get("section_height_m"),
            self.layout["floor"]["elevation_m"] + 2.4,
        )
        try:
            value = float(self._section_height_var.get())
        except (TypeError, ValueError):
            value = current
        if not math.isfinite(value):
            value = current
        self.layout.setdefault("view", {})["section_height_m"] = value
        self._section_height_var.set(f"{value:.2f}")
        project = self._project_getter()
        project.metadata[SPATIAL_METADATA_KEY] = normalize_layout(self.layout)
        self.layout = project.metadata[SPATIAL_METADATA_KEY]
        self._on_change()
        self._status_setter(f"3D section plane: Z {value:.2f} m")
        self.redraw()
        return "break" if _event is not None else None

    def _set_overlay_mode(self, value: str) -> None:
        mode = str(value or "none").strip().lower()
        if mode not in ENGINEERING_OVERLAY_MODES:
            mode = "none"
        view = self.layout.setdefault("view", {})
        view["overlay_mode"] = mode
        view["show_pressure"] = mode == "pressure"
        self._show_pressure.set(mode == "pressure")
        project = self._project_getter()
        project.metadata[SPATIAL_METADATA_KEY] = normalize_layout(self.layout)
        self.layout = project.metadata[SPATIAL_METADATA_KEY]
        self._on_change()
        self._status_setter(f"Engineering overlay: {mode.title()}")
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
        dialog = FloorPropertiesDialog(
            self,
            name=str(floor["name"]),
            elevation_m=float(floor["elevation_m"]),
            default_ceiling_height_m=float(floor["default_ceiling_height_m"]),
            grid_m=float(self.layout["grid_m"]),
        )
        self.wait_window(dialog)
        if dialog.result is None:
            return

        history_before = self._history_layout()
        selection_before = self._selection_state()
        floor["name"] = str(dialog.result["name"])
        floor["elevation_m"] = float(dialog.result["elevation_m"])
        floor["default_ceiling_height_m"] = float(
            dialog.result["default_ceiling_height_m"]
        )
        self.layout["grid_m"] = float(dialog.result["grid_m"])
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

    def _on_duplicate_shortcut(self, event=None):
        self.duplicate_selected()
        return "break"

    def _persist(
        self,
        message: str,
        *,
        history_before: dict | None = None,
        selection_before: tuple[str, str] | None = None,
    ) -> None:
        if history_before is not None and history_before == self._history_layout():
            self._status_setter("Spatial edit unchanged")
            self._update_history_controls()
            self.redraw()
            return

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
        warning_ids = {
            str(item_id)
            for issue in self._validation_issues
            for item_id in issue.get("item_ids", [])
        }
        sync = engineering_sync_status(self.layout, self._analysis_getter())
        warning_ids.update(
            item["room_id"]
            for item in sync["rooms"]
            if item["state"] != "synchronized"
        )
        return warning_ids

    def _update_sync_summary(self) -> None:
        sync = engineering_sync_status(self.layout, self._analysis_getter())
        overall = sync["overall"].replace("_", " ")
        if overall == "synchronized":
            self._sync_var.set("Engineering sync: synchronized")
            return
        parts = [
            f"{state.replace('_', ' ')} {count}"
            for state, count in sync["counts"].items()
            if count and state != "synchronized"
        ]
        suffix = ", ".join(parts) if parts else overall
        self._sync_var.set(f"Engineering sync: {suffix}")

    def _update_validation_summary(self) -> None:
        count = len(self._validation_issues)
        self._validation_var.set(
            "Spatial checks: PASS" if count == 0 else f"Spatial checks: {count} warning(s)"
        )

    def _refresh_validation(self, *, force: bool = False) -> None:
        validation_key = _spatial_validation_key(self.layout)
        if force or validation_key != self._last_validation_key:
            self._validation_issues = _validate_normalized_layout(self.layout)
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
            for key, var in self._property_vars.items():
                var.set("")
                row = self._property_rows.get(key)
                if row is not None:
                    row.pack_forget()
            return
        prefix = "Room" if self.selected and self.selected.kind == "room" else item.get("type", "Device").title()
        selection_text = f"{prefix}: {item.get('name', '')}"
        if self.selected and self.selected.kind == "room":
            sync = engineering_sync_status(self.layout, self._analysis_getter())
            room_sync = next(
                (
                    record
                    for record in sync["rooms"]
                    if record["room_id"] == self.selected.item_id
                ),
                None,
            )
            if room_sync is not None:
                selection_text += " — " + room_sync["state"].replace("_", " ")
        self._selection_var.set(selection_text)
        room_fields = {
            "name",
            "x_m",
            "y_m",
            "length_m",
            "width_m",
            "height_m",
            "floor_elevation_m",
            "pressure_pa",
            "zone",
            "classification",
            "analysis_room_name",
        }
        device_fields = {
            "name",
            "x_m",
            "y_m",
            "z_m",
            "width_m",
            "height_m",
            "room_id",
            "orientation_deg",
            "wall_side",
            "swing",
        }
        visible_fields = (
            room_fields
            if self.selected and self.selected.kind == "room"
            else device_fields
        )
        for key, var in self._property_vars.items():
            row = self._property_rows.get(key)
            if row is not None:
                if key in visible_fields:
                    row.pack(fill="x", pady=2)
                else:
                    row.pack_forget()
            value = item.get(key, "")
            var.set("" if value is None else str(value))

    def apply_properties(self) -> None:
        item = self._selected_object()
        if item is None:
            return
        try:
            candidate = update_spatial_properties(
                self.layout,
                self.selected.kind,
                self.selected.item_id,
                {key: variable.get() for key, variable in self._property_vars.items()},
            )
        except ValueError as exc:
            messagebox.showerror("Invalid spatial properties", str(exc), parent=self)
            self._status_setter("Properties not applied: " + str(exc))
            return
        history_before = self._history_layout()
        selection_before = self._selection_state()
        if candidate != self.layout:
            self.layout = candidate
        self._load_property_panel()
        self._persist(
            "Spatial properties updated",
            history_before=history_before,
            selection_before=selection_before,
        )

    def duplicate_selected(self) -> None:
        if self._selected_object() is None:
            self._status_setter("Select a room or device to duplicate")
            return
        try:
            candidate, item_id = duplicate_spatial_item(
                self.layout, self.selected.kind, self.selected.item_id,
            )
        except ValueError as exc:
            messagebox.showerror("Cannot duplicate selection", str(exc), parent=self)
            return
        history_before = self._history_layout()
        selection_before = self._selection_state()
        kind = self.selected.kind
        self.layout = candidate
        self.selected = _Hit(kind, item_id)
        self._load_property_panel()
        message = (
            "Duplicated room and devices; enter pressure and link analysis for the new room"
            if kind == "room" else "Duplicated device"
        )
        self._persist(
            message,
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
            if device_type in {"door", "window", "opening", "transfer"}:
                y = room["y_m"]
                z = (
                    0.0
                    if device_type in {"door", "opening"}
                    else min(1.0, room["height_m"] / 2.0)
                )
        else:
            x = y = z = 0.0
            room_id = None
        default_width = {
            "door": 0.9,
            "window": 1.2,
            "opening": 1.0,
            "transfer": 0.6,
        }.get(device_type, 0.4)
        default_height = {
            "door": 2.1,
            "window": 1.2,
            "opening": 2.1,
            "transfer": 0.4,
        }.get(device_type, 0.2)
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
        if device_type in {"door", "window", "opening", "transfer"}:
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
        return BASE_2D_PIXELS_PER_M * self.layout["view"]["zoom_2d"]

    def _world_to_canvas(self, x: float, y: float) -> tuple[float, float]:
        return model_to_screen_2d(
            x,
            y,
            width_px=self.canvas_2d.winfo_width(),
            height_px=self.canvas_2d.winfo_height(),
            zoom=self.layout["view"]["zoom_2d"],
            pan_x_px=self.layout["view"]["pan_x"],
            pan_y_px=self.layout["view"]["pan_y"],
        )

    def _canvas_to_world(self, x: float, y: float) -> tuple[float, float]:
        return screen_to_model_2d(
            x,
            y,
            width_px=self.canvas_2d.winfo_width(),
            height_px=self.canvas_2d.winfo_height(),
            zoom=self.layout["view"]["zoom_2d"],
            pan_x_px=self.layout["view"]["pan_x"],
            pan_y_px=self.layout["view"]["pan_y"],
        )

    def fit_selected(self) -> None:
        item = self._selected_object()
        if item is None or self.selected is None:
            self._status_setter("Select a room or device to fit")
            return

        if self.selected.kind == "room":
            min_x = item["x_m"]
            min_y = item["y_m"]
            max_x = min_x + item["length_m"]
            max_y = min_y + item["width_m"]
        else:
            half = max(0.5, float(item.get("width_m", 0.4)))
            min_x = item["x_m"] - half
            min_y = item["y_m"] - half
            max_x = item["x_m"] + half
            max_y = item["y_m"] + half

        width_m = max(0.5, max_x - min_x)
        height_m = max(0.5, max_y - min_y)
        cw = max(200, self.canvas_2d.winfo_width())
        ch = max(200, self.canvas_2d.winfo_height())
        self.layout["view"]["zoom_2d"] = max(
            0.2,
            min(
                8.0,
                0.72
                * min(
                    cw / (BASE_2D_PIXELS_PER_M * width_m),
                    ch / (BASE_2D_PIXELS_PER_M * height_m),
                ),
            ),
        )
        scale = self._scale_2d()
        self.layout["view"]["pan_x"] = -((min_x + max_x) / 2.0) * scale
        self.layout["view"]["pan_y"] = -((min_y + max_y) / 2.0) * scale

        all_min_x, all_min_y, all_max_x, all_max_y = self._bounds()
        model_cx = (all_min_x + all_max_x) / 2.0
        model_cy = (all_min_y + all_max_y) / 2.0
        floor_z = self.layout["floor"]["elevation_m"]
        points_3d: list[tuple[float, float, float]] = []
        if self.selected.kind == "room":
            z0 = item.get("floor_elevation_m", floor_z)
            z1 = z0 + item["height_m"]
            for x in (min_x - model_cx, max_x - model_cx):
                for y in (min_y - model_cy, max_y - model_cy):
                    points_3d.append((x, y, z0))
                    points_3d.append((x, y, z1))
        else:
            room = next(
                (
                    room
                    for room in self.layout["rooms"]
                    if room["id"] == item.get("room_id")
                ),
                None,
            )
            z = (
                (room.get("floor_elevation_m", floor_z) if room else floor_z)
                + item.get("z_m", 0.0)
            )
            for x in (min_x - model_cx, max_x - model_cx):
                for y in (min_y - model_cy, max_y - model_cy):
                    points_3d.append((x, y, z))
                    points_3d.append((x, y, z + max(0.5, item.get("height_m", 0.2))))

        if points_3d:
            zoom_3d, pan_3d_x, pan_3d_y = fit_3d_view(
                points_3d,
                width_px=max(200, self.canvas_3d.winfo_width()),
                height_px=max(200, self.canvas_3d.winfo_height()),
                azimuth_deg=self.layout["view"]["azimuth_deg"],
                elevation_deg=self.layout["view"]["elevation_deg"],
                projection_mode=self.layout["view"].get(
                    "projection_mode", "orthographic"
                ),
            )
            self.layout["view"]["zoom_3d"] = zoom_3d
            self.layout["view"]["pan_3d_x"] = pan_3d_x
            self.layout["view"]["pan_3d_y"] = pan_3d_y

        self._status_setter("View fitted to selected object")
        self.redraw()

    def _visible_3d_points(self) -> list[tuple[float, float, float]]:
        min_x, min_y, max_x, max_y = self._bounds()
        center_x = (min_x + max_x) / 2.0
        center_y = (min_y + max_y) / 2.0
        points: list[tuple[float, float, float]] = []
        for room in self.layout["rooms"]:
            if not self._is_item_visible("room", room["id"]):
                continue
            x0 = room["x_m"] - center_x
            x1 = x0 + room["length_m"]
            y0 = room["y_m"] - center_y
            y1 = y0 + room["width_m"]
            z0 = room.get(
                "floor_elevation_m",
                self.layout["floor"]["elevation_m"],
            )
            z1 = z0 + room["height_m"]
            section_height = self._active_section_height()
            if section_height is not None:
                if z0 >= section_height:
                    continue
                z1 = min(z1, section_height)
            for x in (x0, x1):
                for y in (y0, y1):
                    for z in (z0, z1):
                        points.append((x, y, z))
        return points

    def fit_3d(self) -> None:
        points = self._visible_3d_points()
        if not points:
            self._status_setter("No visible 3D geometry to fit")
            return
        zoom, pan_x, pan_y = fit_3d_view(
            points,
            width_px=max(200, self.canvas_3d.winfo_width()),
            height_px=max(200, self.canvas_3d.winfo_height()),
            azimuth_deg=self.layout["view"]["azimuth_deg"],
            elevation_deg=self.layout["view"]["elevation_deg"],
            projection_mode=self.layout["view"].get(
                "projection_mode", "orthographic"
            ),
        )
        self.layout["view"]["zoom_3d"] = zoom
        self.layout["view"]["pan_3d_x"] = pan_x
        self.layout["view"]["pan_3d_y"] = pan_y
        self._status_setter("3D model fitted to visible geometry")
        self._draw_3d()

    def fit_views(self) -> None:
        min_x, min_y, max_x, max_y = self._bounds()
        width_m = max(1.0, max_x - min_x)
        height_m = max(1.0, max_y - min_y)
        cw = max(200, self.canvas_2d.winfo_width())
        ch = max(200, self.canvas_2d.winfo_height())
        self.layout["view"]["zoom_2d"] = max(
            0.2,
            min(
                5.0,
                0.78
                * min(
                    cw / (BASE_2D_PIXELS_PER_M * width_m),
                    ch / (BASE_2D_PIXELS_PER_M * height_m),
                ),
            ),
        )
        scale = self._scale_2d()
        cx = (min_x + max_x) / 2
        cy = (min_y + max_y) / 2
        self.layout["view"]["pan_x"] = -cx * scale
        self.layout["view"]["pan_y"] = -cy * scale

        points_3d: list[tuple[float, float, float]] = []
        for room in self.layout["rooms"]:
            x0 = room["x_m"] - cx
            x1 = x0 + room["length_m"]
            y0 = room["y_m"] - cy
            y1 = y0 + room["width_m"]
            z0 = room.get(
                "floor_elevation_m",
                self.layout["floor"]["elevation_m"],
            )
            z1 = z0 + room["height_m"]
            for x in (x0, x1):
                for y in (y0, y1):
                    points_3d.append((x, y, z0))
                    points_3d.append((x, y, z1))

        zoom_3d, pan_3d_x, pan_3d_y = fit_3d_view(
            points_3d,
            width_px=max(200, self.canvas_3d.winfo_width()),
            height_px=max(200, self.canvas_3d.winfo_height()),
            azimuth_deg=self.layout["view"]["azimuth_deg"],
            elevation_deg=self.layout["view"]["elevation_deg"],
            projection_mode=self.layout["view"].get(
                "projection_mode", "orthographic"
            ),
        )
        self.layout["view"]["zoom_3d"] = zoom_3d
        self.layout["view"]["pan_3d_x"] = pan_3d_x
        self.layout["view"]["pan_3d_y"] = pan_3d_y
        self._persist("Fit spatial views")

    def reset_2d(self) -> None:
        """Restore the 2D viewport without changing model geometry."""
        self.layout["view"]["zoom_2d"] = 1.0
        self.layout["view"]["pan_x"] = 0.0
        self.layout["view"]["pan_y"] = 0.0
        self._persist("Reset 2D view")

    def redraw(self) -> None:
        self._refresh_validation()
        self._update_sync_summary()
        self._update_metrics()
        self._draw_2d()
        self._draw_3d()

    def _pressure_relationships(
        self,
    ) -> list[tuple[dict, dict, float | None, float | None, str]]:
        if not self._show_relationships.get():
            return []
        analysis = self._analysis_getter()
        payload = getattr(analysis, "input", None)
        if not isinstance(payload, dict):
            return []
        raw = payload.get("pressure_cascade")
        if not isinstance(raw, list):
            return []

        rooms_by_name: dict[str, dict] = {}
        for room in self.layout["rooms"]:
            for name in (room.get("name"), room.get("analysis_room_name")):
                key = str(name or "").strip().casefold()
                if key and key not in rooms_by_name:
                    rooms_by_name[key] = room

        overlay = pressure_overlay_state(
            self.layout,
            analysis,
            getattr(self, "_result_getter", lambda: None)(),
        )
        pressure_by_room = {
            item["room_id"]: item.get("pressure_pa") for item in overlay["rooms"]
        }

        relationships: list[
            tuple[dict, dict, float | None, float | None, str]
        ] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            high = rooms_by_name.get(
                str(item.get("higher_pressure_room") or "").strip().casefold()
            )
            low = rooms_by_name.get(
                str(item.get("lower_pressure_room") or "").strip().casefold()
            )
            if high is None or low is None:
                continue
            raw_minimum = item.get("min_delta_pa")
            minimum = (
                _finite_number(raw_minimum, 0.0)
                if raw_minimum is not None
                else None
            )
            observed_delta = None
            high_pressure = pressure_by_room.get(high["id"])
            low_pressure = pressure_by_room.get(low["id"])
            if high_pressure is not None and low_pressure is not None:
                observed_delta = high_pressure - low_pressure
            if observed_delta is None:
                state = "unavailable"
            elif minimum is None:
                state = "available"
            elif observed_delta >= minimum:
                state = "pass"
            else:
                state = "fail"
            relationships.append((high, low, minimum, observed_delta, state))
        return relationships

    @staticmethod
    def _relationship_style(state: str) -> tuple[str, tuple[int, ...]]:
        if state == "pass":
            return "#15803d", ()
        if state == "fail":
            return "#b91c1c", ()
        if state == "available":
            return "#7c3aed", (6, 3)
        return "#64748b", (5, 4)

    @staticmethod
    def _relationship_label(
        minimum: float | None,
        observed_delta: float | None,
    ) -> str:
        if observed_delta is None and minimum is not None:
            return f"Δ unavailable / target ≥ {minimum:g} Pa"
        if observed_delta is not None and minimum is not None:
            return f"Δ {observed_delta:g} Pa / target ≥ {minimum:g} Pa"
        if observed_delta is not None:
            return f"Δ {observed_delta:g} Pa"
        return "Pressure unavailable"

    def _draw_relationships_2d(self) -> None:
        for high, low, minimum, observed_delta, state in self._pressure_relationships():
            if not self._is_item_visible("room", high["id"]):
                continue
            if not self._is_item_visible("room", low["id"]):
                continue
            hx = high["x_m"] + high["length_m"] / 2.0
            hy = high["y_m"] + high["width_m"] / 2.0
            lx = low["x_m"] + low["length_m"] / 2.0
            ly = low["y_m"] + low["width_m"] / 2.0
            x0, y0 = self._world_to_canvas(hx, hy)
            x1, y1 = self._world_to_canvas(lx, ly)
            color, dash = self._relationship_style(state)
            self.canvas_2d.create_line(
                x0,
                y0,
                x1,
                y1,
                arrow="last",
                width=3,
                dash=dash,
                fill=color,
                tags=("pressure_relationship",),
            )
            if self._show_labels.get():
                self.canvas_2d.create_text(
                    (x0 + x1) / 2,
                    (y0 + y1) / 2 - 10,
                    text=self._relationship_label(minimum, observed_delta),
                    fill=color,
                    tags=("pressure_relationship",),
                )

    def _draw_relationships_3d(
        self,
        *,
        center_x_m: float,
        center_y_m: float,
        floor_z_m: float,
    ) -> None:
        for high, low, minimum, observed_delta, state in self._pressure_relationships():
            if not self._is_item_visible("room", high["id"]):
                continue
            if not self._is_item_visible("room", low["id"]):
                continue
            high_z = (
                high.get("floor_elevation_m", floor_z_m)
                + high["height_m"]
                + 0.35
            )
            low_z = (
                low.get("floor_elevation_m", floor_z_m)
                + low["height_m"]
                + 0.35
            )
            start = self._project_3d(
                high["x_m"] - center_x_m + high["length_m"] / 2.0,
                high["y_m"] - center_y_m + high["width_m"] / 2.0,
                high_z,
            )
            end = self._project_3d(
                low["x_m"] - center_x_m + low["length_m"] / 2.0,
                low["y_m"] - center_y_m + low["width_m"] / 2.0,
                low_z,
            )
            color, dash = self._relationship_style(state)
            self.canvas_3d.create_line(
                *start,
                *end,
                arrow="last",
                width=3,
                dash=dash,
                fill=color,
                tags=("pressure_relationship_3d",),
            )
            if self._show_labels.get():
                self.canvas_3d.create_text(
                    (start[0] + end[0]) / 2.0,
                    (start[1] + end[1]) / 2.0 - 10,
                    text=self._relationship_label(minimum, observed_delta),
                    fill=color,
                    tags=("pressure_relationship_3d",),
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
                    canvas.create_line(
                        cx, 0, cx, h,
                        fill=self._theme_palette["grid"],
                        tags=("grid",),
                    )
                    x += grid
                y = start_y
                while y <= end_y + 1e-9:
                    _, cy = self._world_to_canvas(0, y)
                    canvas.create_line(
                        0, cy, w, cy,
                        fill=self._theme_palette["grid"],
                        tags=("grid",),
                    )
                    y += grid

        overlay_mode = self._overlay_mode.get().strip().lower()
        overlay = engineering_overlay_state(
            self.layout,
            self._analysis_getter(),
            getattr(self, "_result_getter", lambda: None)(),
            mode=overlay_mode,
        )
        overlay_by_room = {item["room_id"]: item for item in overlay["rooms"]}
        self._update_overlay_summary(overlay)
        warning_ids = self._warning_item_ids()

        for room in self.layout["rooms"]:
            if not self._is_item_visible("room", room["id"]):
                continue
            x0, y0 = self._world_to_canvas(room["x_m"], room["y_m"])
            x1, y1 = self._world_to_canvas(
                room["x_m"] + room["length_m"],
                room["y_m"] + room["width_m"],
            )
            selected = self.selected == _Hit("room", room["id"])
            hovered = self._hovered == _Hit("room", room["id"])
            outline = (
                "#1d4ed8"
                if selected
                else (
                    "#0ea5e9"
                    if hovered
                    else ("#b45309" if room["id"] in warning_ids else "#34495e")
                )
            )
            fill = (
                overlay_by_room[room["id"]]["fill"]
                if overlay_mode != "none"
                else self._theme_palette["surface_alt"]
            )
            canvas.create_rectangle(
                x0, y0, x1, y1,
                fill=fill,
                outline=outline,
                width=3 if (selected or hovered) else 2,
                tags=(f"room:{room['id']}", "room"),
            )
            if self._show_labels.get():
                overlay_room = overlay_by_room[room["id"]]
                overlay_text = (
                    ""
                    if overlay_mode == "none"
                    else "\n" + str(overlay_room.get("label") or "")
                )
                canvas.create_text(
                    (x0 + x1) / 2,
                    (y0 + y1) / 2,
                    text=(
                        f"{room['name']}\n"
                        f"{room['length_m']:g} × {room['width_m']:g} × "
                        f"{room['height_m']:g} m{overlay_text}"
                    ),
                    justify="center",
                    fill=self._theme_palette["text"],
                    tags=(f"room:{room['id']}", "room"),
                )
            if selected:
                self._draw_room_dimensions_2d(room, x0, y0, x1, y1)
                handle = 6
                canvas.create_rectangle(
                    x1 - handle, y1 - handle, x1 + handle, y1 + handle,
                    fill=self._theme_palette["accent"],
                    outline=self._theme_palette["panel"],
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
                "window": "W",
                "opening": "O",
                "supply": "S",
                "return": "R",
                "exhaust": "E",
                "ffu": "F",
                "equipment": "Q",
                "sensor": "●",
                "transfer": "T",
            }
            for device in self.layout["devices"]:
                if not self._is_item_visible("device", device["id"]):
                    continue
                x, y = self._world_to_canvas(device["x_m"], device["y_m"])
                selected = self.selected == _Hit("device", device["id"])
                hovered = self._hovered == _Hit("device", device["id"])
                device_outline = (
                    "#c0392b"
                    if selected
                    else (
                        "#0ea5e9"
                        if hovered
                        else ("#b45309" if device["id"] in warning_ids else "#2c3e50")
                    )
                )
                tag = f"device:{device['id']}"
                if device["type"] in {"door", "window", "opening", "transfer"}:
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
                        width=7 if (selected or hovered) else 5,
                        tags=(tag, "device"),
                    )
                    if self._show_labels.get():
                        canvas.create_text(
                            x, y - 10,
                            text=symbols[device["type"]],
                            fill=self._theme_palette["text"],
                            tags=(tag, "device"),
                        )
                else:
                    radius = 9 if (selected or hovered) else 7
                    canvas.create_oval(
                        x - radius, y - radius, x + radius, y + radius,
                        fill=self._theme_palette["panel"], outline=device_outline,
                        width=3 if (selected or hovered) else 2,
                        tags=(tag, "device"),
                    )
                    canvas.create_text(
                        x, y, text=symbols.get(device["type"], "?"),
                        fill=self._theme_palette["text"],
                        tags=(tag, "device"),
                    )

        self._draw_engineering_legend(canvas, overlay)
        self._draw_measurement_overlay()

        if not self.layout["rooms"] and not self.layout["devices"]:
            canvas.create_text(
                w / 2,
                h / 2,
                text=(
                    "No spatial layout yet\n"
                    "Use + Room or open a verification project with room geometry."
                ),
                justify="center",
                fill=self._theme_palette["muted"],
            )

    def _draw_room_dimensions_2d(
        self,
        room: dict,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
    ) -> None:
        """Draw engineering dimensions for the selected room without changing geometry."""
        canvas = self.canvas_2d
        offset = 18
        tick = 4
        color = self._theme_palette["muted"]
        tags = ("room_dimension", f"room:{room['id']}")

        y = min(y0, y1) - offset
        left, right = sorted((x0, x1))
        canvas.create_line(left, y, right, y, fill=color, tags=tags)
        canvas.create_line(left, y - tick, left, y + tick, fill=color, tags=tags)
        canvas.create_line(right, y - tick, right, y + tick, fill=color, tags=tags)
        canvas.create_line(
            left, min(y0, y1), left, y + tick,
            fill=self._theme_palette["border"], tags=tags,
        )
        canvas.create_line(
            right, min(y0, y1), right, y + tick,
            fill=self._theme_palette["border"], tags=tags,
        )
        canvas.create_text(
            (left + right) / 2,
            y - 9,
            text=f"{room['length_m']:g} m",
            fill=color,
            tags=tags,
        )

        x = min(x0, x1) - offset
        top, bottom = sorted((y0, y1))
        canvas.create_line(x, top, x, bottom, fill=color, tags=tags)
        canvas.create_line(x - tick, top, x + tick, top, fill=color, tags=tags)
        canvas.create_line(x - tick, bottom, x + tick, bottom, fill=color, tags=tags)
        canvas.create_line(
            min(x0, x1), top, x + tick, top,
            fill=self._theme_palette["border"], tags=tags,
        )
        canvas.create_line(
            min(x0, x1), bottom, x + tick, bottom,
            fill=self._theme_palette["border"], tags=tags,
        )
        canvas.create_text(
            x - 11,
            (top + bottom) / 2,
            text=f"{room['width_m']:g} m",
            fill=color,
            angle=90,
            tags=tags,
        )

    def _draw_snap_indicator_2d(self, event_x: float, event_y: float) -> None:
        canvas = self.canvas_2d
        canvas.delete("snap_indicator")
        self._snap_indicator_world = None
        if not self._snap_to_grid.get():
            return
        grid = max(0.01, float(self.layout["grid_m"]))
        world_x, world_y = self._canvas_to_world(event_x, event_y)
        snapped = (
            round(world_x / grid) * grid,
            round(world_y / grid) * grid,
        )
        self._snap_indicator_world = snapped
        x, y = self._world_to_canvas(*snapped)
        radius = 6
        canvas.create_line(
            x - radius,
            y,
            x + radius,
            y,
            fill="#0284c7",
            width=2,
            tags=("snap_indicator",),
        )
        canvas.create_line(
            x,
            y - radius,
            x,
            y + radius,
            fill="#0284c7",
            width=2,
            tags=("snap_indicator",),
        )

    def _focus_property(self, key: str) -> None:
        self.show_inspector()
        entry = self._property_entries.get(key)
        if entry is not None and entry.winfo_manager():
            entry.focus_set()
            entry.selection_range(0, "end")

    def _build_context_menu_2d(self, hit: _Hit) -> tk.Menu:
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="Properties", command=lambda: self._focus_property("name"))
        menu.add_command(label="Fit selected", command=self.fit_selected)
        menu.add_separator()
        menu.add_command(label="Isolate", command=self.isolate_selected)
        menu.add_command(label="Hide", command=self.hide_selected)
        menu.add_command(label="Show all", command=self.show_all)
        menu.add_separator()
        menu.add_command(label="Duplicate", command=self.duplicate_selected)
        menu.add_command(label="Delete", command=self.delete_selected)
        if hit.kind == "room":
            menu.add_separator()
            menu.add_command(label="Add Door", command=lambda: self.add_device("door"))
            menu.add_command(label="Add Opening", command=lambda: self.add_device("opening"))
            device_menu = tk.Menu(menu, tearoff=False)
            for device_type, label in (
                ("window", "Window"),
                ("ffu", "FFU"),
                ("supply", "Supply"),
                ("return", "Return"),
                ("exhaust", "Exhaust"),
                ("equipment", "Equipment"),
                ("sensor", "Sensor"),
                ("transfer", "Transfer"),
            ):
                device_menu.add_command(
                    label=label,
                    command=lambda t=device_type: self.add_device(t),
                )
            menu.add_cascade(label="Add Device", menu=device_menu)
            menu.add_separator()
            menu.add_command(
                label="Link Analysis…",
                command=lambda: self._focus_property("analysis_room_name"),
            )
        return menu

    def _on_context_menu_2d(self, event: tk.Event) -> str:
        self.canvas_2d.focus_set()
        current = self.canvas_2d.find_withtag("current")
        hit = self._parse_hit(self.canvas_2d.gettags(current[0])) if current else None
        if hit is None:
            return "break"
        self.selected = hit
        self._load_property_panel()
        self._notify_selection_change()
        self.redraw()
        menu = self._build_context_menu_2d(hit)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _on_canvas_leave(self, event: tk.Event | None = None) -> None:
        if self._hovered is not None:
            self._hovered = None
            self._draw_2d()
        self._snap_indicator_world = None
        self.canvas_2d.delete("snap_indicator")

    def _project_3d(self, x: float, y: float, z: float) -> tuple[float, float]:
        return project_3d(
            x,
            y,
            z,
            width_px=self.canvas_3d.winfo_width(),
            height_px=self.canvas_3d.winfo_height(),
            azimuth_deg=self.layout["view"]["azimuth_deg"],
            elevation_deg=self.layout["view"]["elevation_deg"],
            zoom=self.layout["view"]["zoom_3d"],
            pan_x_px=self.layout["view"]["pan_3d_x"],
            pan_y_px=self.layout["view"]["pan_3d_y"],
            projection_mode=self.layout["view"].get(
                "projection_mode", "orthographic"
            ),
        )

    def _draw_3d(self) -> None:
        self._notify_view_status()
        canvas = self.canvas_3d
        canvas.delete("all")
        if not self.layout["rooms"]:
            canvas.create_text(
                max(1, canvas.winfo_width()) / 2,
                max(1, canvas.winfo_height()) / 2,
                text="3D geometry appears here",
                fill=self._theme_palette["muted"],
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

        section_height = self._active_section_height()
        if section_height is not None:
            section_points = [
                self._project_3d(min_x - cx - pad, min_y - cy - pad, section_height),
                self._project_3d(max_x - cx + pad, min_y - cy - pad, section_height),
                self._project_3d(max_x - cx + pad, max_y - cy + pad, section_height),
                self._project_3d(min_x - cx - pad, max_y - cy + pad, section_height),
            ]
            canvas.create_polygon(
                *sum(section_points, ()),
                fill="#334155",
                outline="#38bdf8",
                stipple="gray50",
                width=1,
                tags=("section_plane",),
            )

        overlay_mode = self._overlay_mode.get().strip().lower()
        overlay = engineering_overlay_state(
            self.layout,
            self._analysis_getter(),
            getattr(self, "_result_getter", lambda: None)(),
            mode=overlay_mode,
        )
        overlay_by_room = {item["room_id"]: item for item in overlay["rooms"]}
        self._update_overlay_summary(overlay)
        warning_ids = self._warning_item_ids()

        az = math.radians(self.layout["view"]["azimuth_deg"])
        ordered = sorted(
            (
                room
                for room in self.layout["rooms"]
                if self._is_item_visible("room", room["id"])
            ),
            key=lambda room: (
                (room["x_m"] - cx) * math.sin(az)
                + (room["y_m"] - cy) * math.cos(az)
            ),
        )
        for room in ordered:
            x0 = room["x_m"] - cx
            y0 = room["y_m"] - cy
            x1 = x0 + room["length_m"]
            y1 = y0 + room["width_m"]
            z0 = room.get("floor_elevation_m", floor_z)
            z1 = z0 + room["height_m"]
            if section_height is not None:
                if z0 >= section_height:
                    continue
                z1 = min(z1, section_height)
            base = [
                self._project_3d(x0, y0, z0),
                self._project_3d(x1, y0, z0),
                self._project_3d(x1, y1, z0),
                self._project_3d(x0, y1, z0),
            ]
            top = [
                self._project_3d(x0, y0, z1),
                self._project_3d(x1, y0, z1),
                self._project_3d(x1, y1, z1),
                self._project_3d(x0, y1, z1),
            ]
            fill = (
                overlay_by_room[room["id"]]["fill"]
                if overlay_mode != "none"
                else "#dfe7ef"
            )
            selected = self.selected == _Hit("room", room["id"])
            hovered = self._hovered_3d == _Hit("room", room["id"])
            outline = (
                "#7dd3fc"
                if selected
                else (
                    "#38bdf8"
                    if hovered
                    else ("#fb7185" if room["id"] in warning_ids else "#c8d5e3")
                )
            )
            tag = f"room:{room['id']}"
            stipple = "gray50" if self._xray_3d.get() else ""
            polygon_width = 3 if selected else (2 if hovered else 1)
            canvas.create_polygon(
                *sum(top, ()),
                fill=fill,
                outline=outline,
                width=polygon_width,
                stipple=stipple,
                tags=(tag, "room3d"),
            )
            canvas.create_polygon(
                *sum((base[1], base[2], top[2], top[1]), ()),
                fill="#6c7f92",
                outline=outline,
                width=polygon_width,
                stipple=stipple,
                tags=(tag, "room3d"),
            )
            canvas.create_polygon(
                *sum((base[2], base[3], top[3], top[2]), ()),
                fill="#53687c",
                outline=outline,
                width=polygon_width,
                stipple=stipple,
                tags=(tag, "room3d"),
            )
            for start, end in zip(base, top):
                canvas.create_line(
                    *start, *end, fill=outline, width=1, tags=(tag, "room3d")
                )
            if self._show_labels.get():
                overlay_room = overlay_by_room[room["id"]]
                overlay_text = (
                    ""
                    if overlay_mode == "none"
                    else "\n" + str(overlay_room.get("label") or "")
                )
                canvas.create_text(
                    *self._project_3d((x0 + x1) / 2, (y0 + y1) / 2, z1 + 0.2),
                    text=room["name"] + overlay_text,
                    fill="#f0f6fc",
                    tags=(tag, "room3d"),
                )

        self._draw_relationships_3d(
            center_x_m=cx,
            center_y_m=cy,
            floor_z_m=floor_z,
        )

        if self._show_devices.get():
            room_by_id = {room["id"]: room for room in self.layout["rooms"]}
            for device in self.layout["devices"]:
                if not self._is_item_visible("device", device["id"]):
                    continue
                room = room_by_id.get(str(device.get("room_id") or ""))
                room_floor = (
                    room.get("floor_elevation_m", floor_z)
                    if room is not None
                    else floor_z
                )
                tag = f"device:{device['id']}"
                selected = self.selected == _Hit("device", device["id"])
                hovered = self._hovered_3d == _Hit("device", device["id"])
                device_outline = (
                    "#ffffff"
                    if selected
                    else (
                        "#38bdf8"
                        if hovered
                        else ("#fb7185" if device["id"] in warning_ids else "#d6a20f")
                    )
                )
                device_bottom_z = room_floor + device["z_m"]
                if section_height is not None and device_bottom_z >= section_height:
                    continue
                if device["type"] in {"door", "window", "opening", "transfer"}:
                    device_top_z = (
                        device_bottom_z + device.get("height_m", 0.4)
                    )
                    if section_height is not None:
                        device_top_z = min(device_top_z, section_height)
                    bottom = self._project_3d(
                        device["x_m"] - cx,
                        device["y_m"] - cy,
                        device_bottom_z,
                    )
                    top = self._project_3d(
                        device["x_m"] - cx,
                        device["y_m"] - cy,
                        device_top_z,
                    )
                    canvas.create_line(
                        *bottom, *top,
                        fill=device_outline,
                        width=7 if (selected or hovered) else 5,
                        tags=(tag, "device3d"),
                    )
                else:
                    x, y = self._project_3d(
                        device["x_m"] - cx,
                        device["y_m"] - cy,
                        device_bottom_z,
                    )
                    radius = 5 if (selected or hovered) else 4
                    canvas.create_oval(
                        x - radius, y - radius, x + radius, y + radius,
                        fill="#fbbf24", outline=device_outline,
                        width=2, tags=(tag, "device3d"),
                    )

        self._draw_engineering_legend(canvas, overlay)

    def _update_overlay_summary(self, overlay: dict) -> None:
        mode = str(overlay.get("mode") or "none")
        if mode == "none":
            self._overlay_summary_var.set("Overlay: None")
            return
        title = str(overlay.get("title") or mode.title())
        minimum = overlay.get("minimum")
        maximum = overlay.get("maximum")
        unit = str(overlay.get("unit") or "")
        if isinstance(minimum, (int, float)) and isinstance(maximum, (int, float)):
            suffix = f" {unit}" if unit else ""
            self._overlay_summary_var.set(
                f"Overlay: {title} · {minimum:.2f}–{maximum:.2f}{suffix}"
            )
        else:
            self._overlay_summary_var.set(f"Overlay: {title}")

    def _draw_engineering_legend(self, canvas: tk.Canvas, overlay: dict) -> None:
        mode = str(overlay.get("mode") or "none")
        if mode == "none":
            return
        x0, y0 = 12, 12
        width = 188
        if mode == "status":
            height = 104
            canvas.create_rectangle(
                x0, y0, x0 + width, y0 + height,
                fill="#ffffff", outline="#94a3b8", tags=("overlay_legend",),
            )
            canvas.create_text(
                x0 + 8, y0 + 8, anchor="nw",
                text="Verification Status", fill="#0f172a",
                tags=("overlay_legend",),
            )
            for index, (label, fill) in enumerate(
                (
                    ("PASS", "#dcfce7"),
                    ("WARNING", "#fef3c7"),
                    ("FAIL", "#fee2e2"),
                    ("NOT VERIFIED", "#e2e8f0"),
                )
            ):
                y = y0 + 30 + index * 17
                canvas.create_rectangle(
                    x0 + 8, y, x0 + 20, y + 10,
                    fill=fill, outline="#64748b", tags=("overlay_legend",),
                )
                canvas.create_text(
                    x0 + 28, y + 5, anchor="w",
                    text=label, fill="#334155", tags=("overlay_legend",),
                )
        else:
            minimum = overlay.get("minimum")
            maximum = overlay.get("maximum")
            unit = str(overlay.get("unit") or "")
            title = str(overlay.get("title") or mode.title())
            canvas.create_rectangle(
                x0, y0, x0 + width, y0 + 64,
                fill="#ffffff", outline="#94a3b8", tags=("overlay_legend",),
            )
            canvas.create_text(
                x0 + 8, y0 + 8, anchor="nw",
                text=title, fill="#0f172a", tags=("overlay_legend",),
            )
            if isinstance(minimum, (int, float)) and isinstance(maximum, (int, float)):
                suffix = f" {unit}" if unit else ""
                text = f"{minimum:.2f}{suffix}  →  {maximum:.2f}{suffix}"
            else:
                text = "No result values available"
            canvas.create_text(
                x0 + 8, y0 + 34, anchor="nw",
                text=text, fill="#334155", tags=("overlay_legend",),
            )
        canvas.tag_raise("overlay_legend")

    def _parse_hit(self, tags: tuple[str, ...]) -> _Hit | None:
        for tag in tags:
            if tag.startswith("room:"):
                return _Hit("room", tag.split(":", 1)[1])
            if tag.startswith("device:"):
                return _Hit("device", tag.split(":", 1)[1])
        return None

    def _on_left_down(self, event: tk.Event) -> None:
        self.canvas_2d.focus_set()
        if self._current_tool_mode() in {"distance", "area"}:
            self._handle_measure_click(event.x, event.y)
            return
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
        item = self._selected_object()
        if hit is not None and item is not None:
            self._drag_anchor = self._canvas_to_world(event.x, event.y)
            self._drag_item_origin = (item["x_m"], item["y_m"])
            self._drag_history_before = (
                self._history_layout(),
                self._selection_state(),
            )
        else:
            self._drag_anchor = None
            self._drag_item_origin = None
            self._drag_history_before = None
        self._load_property_panel()
        self._notify_selection_change()
        self.redraw()

    def _on_left_drag(self, event: tk.Event) -> None:
        if self._current_tool_mode() != "select":
            return
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
            if self._drag_item_origin is None:
                return
            old_x = item["x_m"]
            old_y = item["y_m"]
            snap_to_grid = bool(self._snap_to_grid.get())
            new_x = _drag_target_coordinate(
                item_origin=self._drag_item_origin[0],
                pointer_origin=self._drag_anchor[0],
                pointer_current=world[0],
                grid_m=grid,
                snap_to_grid=snap_to_grid,
            )
            new_y = _drag_target_coordinate(
                item_origin=self._drag_item_origin[1],
                pointer_origin=self._drag_anchor[1],
                pointer_current=world[1],
                grid_m=grid,
                snap_to_grid=snap_to_grid,
            )
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
        self._load_property_panel()
        self.redraw()

    def _on_left_up(self, event: tk.Event) -> None:
        if self._current_tool_mode() != "select":
            return
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
        self._drag_item_origin = None
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
        current = self.canvas_2d.find_withtag("current")
        hovered = (
            self._parse_hit(self.canvas_2d.gettags(current[0]))
            if current
            else None
        )
        if hovered != self._hovered:
            self._hovered = hovered
            self._draw_2d()
        self._draw_snap_indicator_2d(event.x, event.y)

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
        zoom, pan_x, pan_y = zoom_2d_at(
            factor,
            x,
            y,
            width_px=self.canvas_2d.winfo_width(),
            height_px=self.canvas_2d.winfo_height(),
            zoom=self.layout["view"]["zoom_2d"],
            pan_x_px=self.layout["view"]["pan_x"],
            pan_y_px=self.layout["view"]["pan_y"],
        )
        self.layout["view"]["zoom_2d"] = zoom
        self.layout["view"]["pan_x"] = pan_x
        self.layout["view"]["pan_y"] = pan_y
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

    def set_3d_view_preset(self, preset: str) -> None:
        presets = {
            "top": (0.0, 90.0),
            "front": (0.0, 0.0),
            "back": (180.0, 0.0),
            "left": (270.0, 0.0),
            "right": (90.0, 0.0),
            "iso": (35.0, 28.0),
        }
        if preset not in presets:
            raise ValueError(
                "3D preset must be top, front, back, left, right, or iso"
            )
        azimuth, elevation = presets[preset]
        self.layout["view"]["azimuth_deg"] = azimuth
        self.layout["view"]["elevation_deg"] = elevation
        self._status_setter(f"3D view: {preset.title()}")
        self._draw_3d()

    def reset_3d(self) -> None:
        self.layout["view"]["azimuth_deg"] = 35.0
        self.layout["view"]["elevation_deg"] = 28.0
        self.layout["view"]["zoom_3d"] = 1.0
        self.layout["view"]["pan_3d_x"] = 0.0
        self.layout["view"]["pan_3d_y"] = 0.0
        self._draw_3d()

    def _on_orbit_3d_down(self, event: tk.Event) -> str:
        self._orbit_anchor = (event.x, event.y)
        self._orbit_origin = (
            self.layout["view"]["azimuth_deg"],
            self.layout["view"]["elevation_deg"],
        )
        return "break"

    def _on_orbit_3d_drag(self, event: tk.Event) -> str:
        if self._orbit_anchor is None or self._orbit_origin is None:
            return "break"
        dx = event.x - self._orbit_anchor[0]
        dy = event.y - self._orbit_anchor[1]
        self.layout["view"]["azimuth_deg"] = (
            self._orbit_origin[0] + dx * 0.5
        ) % 360
        self.layout["view"]["elevation_deg"] = max(
            5.0,
            min(75.0, self._orbit_origin[1] - dy * 0.35),
        )
        self._draw_3d()
        return "break"

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

    def _on_3d_motion(self, event: tk.Event) -> None:
        current = self.canvas_3d.find_withtag("current")
        hovered = (
            self._parse_hit(self.canvas_3d.gettags(current[0]))
            if current
            else None
        )
        if hovered != self._hovered_3d:
            self._hovered_3d = hovered
            self._draw_3d()

    def _on_3d_leave(self, event: tk.Event | None = None) -> None:
        if self._hovered_3d is None:
            return
        self._hovered_3d = None
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
        self._notify_selection_change()
        self.redraw()
