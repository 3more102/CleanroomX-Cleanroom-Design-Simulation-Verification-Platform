from __future__ import annotations

import math
from typing import Any

SPATIAL_METADATA_KEY = "spatial_layout"
SPATIAL_LAYOUT_VERSION = 1
DEVICE_TYPES = ("door", "supply", "return", "exhaust", "ffu", "equipment", "sensor")


class SpatialLayoutFormatError(ValueError):
    """Raised when persisted spatial metadata violates the versioned layout contract."""


def _finite_number(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _positive(value: Any, default: float) -> float:
    number = _finite_number(value, default)
    return number if number > 0 else default


def _slug(value: str, *, fallback: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")
    return slug or fallback


def _unique_id(raw_value: Any, *, fallback: str, used: set[str]) -> str:
    candidate = str(raw_value).strip() if raw_value is not None else ""
    base = candidate or fallback
    result = base
    suffix = 2
    while result in used:
        result = f"{base}-{suffix}"
        suffix += 1
    used.add(result)
    return result


def _room_id(name: str, index: int = 0) -> str:
    return _slug(name, fallback=f"room-{index + 1}")


def empty_layout() -> dict:
    return {
        "version": SPATIAL_LAYOUT_VERSION,
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
        },
    }


def normalize_layout(value: Any) -> dict:
    """Return a deterministic, GUI-safe layout without mutating the source object.

    This permissive normalizer is for interactive/editing state. Persisted project
    metadata is validated separately so malformed project files are never silently
    repaired during load or save.
    """
    source = value if isinstance(value, dict) else {}
    result = empty_layout()
    result["grid_m"] = _positive(source.get("grid_m"), 0.5)

    rooms: list[dict] = []
    used_room_ids: set[str] = set()
    raw_rooms = source.get("rooms", [])
    if isinstance(raw_rooms, list):
        for index, raw in enumerate(raw_rooms):
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name") or f"Room {index + 1}").strip() or f"Room {index + 1}"
            room_id = _unique_id(
                raw.get("id"),
                fallback=_room_id(name, index),
                used=used_room_ids,
            )
            room = {
                "id": room_id,
                "name": name,
                "x_m": _finite_number(raw.get("x_m"), 0.0),
                "y_m": _finite_number(raw.get("y_m"), 0.0),
                "length_m": _positive(raw.get("length_m"), 4.0),
                "width_m": _positive(raw.get("width_m"), 4.0),
                "height_m": _positive(raw.get("height_m"), 3.0),
            }
            if raw.get("pressure_pa") is not None:
                room["pressure_pa"] = _finite_number(raw.get("pressure_pa"), 0.0)
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
                fallback=f"device-{index + 1}",
                used=used_device_ids,
            )
            raw_room_id = raw.get("room_id")
            room_id = None if raw_room_id is None else str(raw_room_id).strip() or None
            devices.append(
                {
                    "id": device_id,
                    "type": device_type,
                    "name": str(raw.get("name") or device_type.upper()).strip()
                    or device_type.upper(),
                    "room_id": room_id,
                    "x_m": _finite_number(raw.get("x_m"), 0.0),
                    "y_m": _finite_number(raw.get("y_m"), 0.0),
                    "z_m": _finite_number(raw.get("z_m"), 0.0),
                }
            )
    result["devices"] = devices

    view = source.get("view", {})
    if isinstance(view, dict):
        result["view"].update(
            {
                "zoom_2d": max(0.2, min(8.0, _positive(view.get("zoom_2d"), 1.0))),
                "pan_x": _finite_number(view.get("pan_x"), 0.0),
                "pan_y": _finite_number(view.get("pan_y"), 0.0),
                "azimuth_deg": _finite_number(view.get("azimuth_deg"), 35.0),
                "elevation_deg": max(
                    5.0,
                    min(75.0, _finite_number(view.get("elevation_deg"), 28.0)),
                ),
                "zoom_3d": max(0.2, min(8.0, _positive(view.get("zoom_3d"), 1.0))),
                "pan_3d_x": _finite_number(view.get("pan_3d_x"), 0.0),
                "pan_3d_y": _finite_number(view.get("pan_3d_y"), 0.0),
            }
        )
    return result


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

    used_ids: set[str] = set()
    x_cursor = 0.0
    for index, raw in enumerate(raw_rooms):
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or f"Room {index + 1}")
        length = _positive(raw.get("length_m"), 4.0)
        width = _positive(raw.get("width_m"), 4.0)
        height = _positive(raw.get("height_m"), 3.0)
        room_id = _unique_id(
            None,
            fallback=_room_id(name, index),
            used=used_ids,
        )
        room = {
            "id": room_id,
            "name": name,
            "x_m": x_cursor,
            "y_m": 0.0,
            "length_m": length,
            "width_m": width,
            "height_m": height,
        }
        if raw.get("observed_pressure_pa") is not None:
            room["pressure_pa"] = _finite_number(raw.get("observed_pressure_pa"), 0.0)
        layout["rooms"].append(room)
        x_cursor += length + 1.0
    return layout


def ensure_project_layout(project: Any, analysis: Any = None) -> dict:
    """Return current or derived layout without mutating project metadata."""
    metadata = getattr(project, "metadata", None)
    if not isinstance(metadata, dict):
        metadata = {}

    raw = metadata.get(SPATIAL_METADATA_KEY)
    if isinstance(raw, dict):
        return normalize_layout(raw)

    normalized = derive_layout_from_analysis(analysis)
    if normalized["rooms"]:
        return normalized
    for candidate in getattr(project, "analyses", []):
        normalized = derive_layout_from_analysis(candidate)
        if normalized["rooms"]:
            return normalized
    return normalized


def sync_layout_to_analysis(layout: dict, analysis: Any) -> bool:
    if analysis is None or not isinstance(getattr(analysis, "input", None), dict):
        return False
    rooms = normalize_layout(layout)["rooms"]
    if not rooms:
        return False

    changed = False
    if getattr(analysis, "kind", "") == "room_verification":
        source = rooms[0]
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

    by_name = {str(room.get("name")): room for room in raw_rooms if isinstance(room, dict)}
    for source in rooms:
        target = by_name.get(source["name"])
        if target is None:
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

    for left_index, left in enumerate(rooms):
        left_x1 = left["x_m"] + left["length_m"]
        left_y1 = left["y_m"] + left["width_m"]
        for right in rooms[left_index + 1 :]:
            right_x1 = right["x_m"] + right["length_m"]
            right_y1 = right["y_m"] + right["width_m"]
            x0 = max(left["x_m"], right["x_m"])
            y0 = max(left["y_m"], right["y_m"])
            x1 = min(left_x1, right_x1)
            y1 = min(left_y1, right_y1)
            if x1 > x0 + 1e-9 and y1 > y0 + 1e-9:
                issues.append(
                    {
                        "code": "room_overlap",
                        "severity": "warning",
                        "item_ids": [left["id"], right["id"]],
                        "bounds_m": [x0, y0, x1, y1],
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
            room["x_m"] - 1e-9 <= x <= room["x_m"] + room["length_m"] + 1e-9
            and room["y_m"] - 1e-9 <= y <= room["y_m"] + room["width_m"] + 1e-9
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
        if z < -1e-9 or z > room["height_m"] + 1e-9:
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

    return issues


def _require_object(value: Any, path: str) -> dict:
    if not isinstance(value, dict):
        raise SpatialLayoutFormatError(f"{path} must be an object")
    return value


def _require_array(value: Any, path: str) -> list:
    if not isinstance(value, list):
        raise SpatialLayoutFormatError(f"{path} must be an array")
    return value


def _require_nonempty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SpatialLayoutFormatError(f"{path} must be a non-empty string")
    return value.strip()


def _require_finite_number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SpatialLayoutFormatError(f"{path} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise SpatialLayoutFormatError(f"{path} must be a finite number")
    return number


def _require_positive_number(value: Any, path: str) -> float:
    number = _require_finite_number(value, path)
    if number <= 0:
        raise SpatialLayoutFormatError(f"{path} must be greater than zero")
    return number


def validate_persisted_spatial_layout(value: Any) -> None:
    """Validate the persisted spatial-layout v1 contract without rewriting it."""
    root = "$.project.metadata.spatial_layout"
    layout = _require_object(value, root)

    version = layout.get("version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise SpatialLayoutFormatError(f"{root}.version must be an integer")
    if version != SPATIAL_LAYOUT_VERSION:
        raise SpatialLayoutFormatError(
            f"{root}.version must be {SPATIAL_LAYOUT_VERSION}; got {version}"
        )

    if "grid_m" in layout:
        _require_positive_number(layout["grid_m"], f"{root}.grid_m")

    raw_rooms = _require_array(layout.get("rooms", []), f"{root}.rooms")
    room_ids: set[str] = set()
    for index, raw in enumerate(raw_rooms):
        path = f"{root}.rooms[{index}]"
        room = _require_object(raw, path)
        room_id = _require_nonempty_string(room.get("id"), f"{path}.id")
        if room_id in room_ids:
            raise SpatialLayoutFormatError(
                f"{path}.id duplicates spatial room id {room_id!r}"
            )
        room_ids.add(room_id)
        _require_nonempty_string(room.get("name"), f"{path}.name")
        for key in ("x_m", "y_m"):
            _require_finite_number(room.get(key), f"{path}.{key}")
        for key in ("length_m", "width_m", "height_m"):
            _require_positive_number(room.get(key), f"{path}.{key}")
        if "pressure_pa" in room:
            _require_finite_number(room["pressure_pa"], f"{path}.pressure_pa")

    raw_devices = _require_array(layout.get("devices", []), f"{root}.devices")
    device_ids: set[str] = set()
    for index, raw in enumerate(raw_devices):
        path = f"{root}.devices[{index}]"
        device = _require_object(raw, path)
        device_id = _require_nonempty_string(device.get("id"), f"{path}.id")
        if device_id in device_ids:
            raise SpatialLayoutFormatError(
                f"{path}.id duplicates spatial device id {device_id!r}"
            )
        device_ids.add(device_id)
        device_type = _require_nonempty_string(device.get("type"), f"{path}.type")
        if device_type not in DEVICE_TYPES:
            raise SpatialLayoutFormatError(
                f"{path}.type must be one of {', '.join(DEVICE_TYPES)}"
            )
        _require_nonempty_string(device.get("name"), f"{path}.name")
        room_id = device.get("room_id")
        if room_id is not None:
            room_id = _require_nonempty_string(room_id, f"{path}.room_id")
            if room_id not in room_ids:
                raise SpatialLayoutFormatError(
                    f"{path}.room_id references missing spatial room id {room_id!r}"
                )
        for key in ("x_m", "y_m", "z_m"):
            _require_finite_number(device.get(key), f"{path}.{key}")

    if "view" in layout:
        view = _require_object(layout["view"], f"{root}.view")
        for key in ("pan_x", "pan_y", "azimuth_deg", "pan_3d_x", "pan_3d_y"):
            if key in view:
                _require_finite_number(view[key], f"{root}.view.{key}")
        for key in ("zoom_2d", "zoom_3d"):
            if key in view:
                zoom = _require_positive_number(view[key], f"{root}.view.{key}")
                if not 0.2 <= zoom <= 8.0:
                    raise SpatialLayoutFormatError(
                        f"{root}.view.{key} must be between 0.2 and 8.0"
                    )
        if "elevation_deg" in view:
            elevation = _require_finite_number(
                view["elevation_deg"], f"{root}.view.elevation_deg"
            )
            if not 5.0 <= elevation <= 75.0:
                raise SpatialLayoutFormatError(
                    f"{root}.view.elevation_deg must be between 5 and 75 degrees"
                )
