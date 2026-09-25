from __future__ import annotations

import copy
import math
from typing import Any


SPATIAL_METADATA_KEY = "spatial_layout"
SPATIAL_LAYOUT_VERSION = 1
DEVICE_TYPES = ("door", "supply", "return", "exhaust", "ffu", "equipment", "sensor")


class SpatialLayoutFormatError(ValueError):
    """Raised when persisted spatial engineering data is structurally unsafe."""


def _finite_number(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _positive(value: Any, default: float) -> float:
    number = _finite_number(value, default)
    return number if number > 0 else default


def _room_id(name: str, index: int = 0) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in name).strip("-")
    return slug or f"room-{index + 1}"


def _explicit_ids(raw_items: Any) -> set[str]:
    if not isinstance(raw_items, list):
        return set()
    values: set[str] = set()
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        value = raw.get("id")
        if isinstance(value, str) and value.strip():
            values.add(value.strip())
    return values


def _generated_unique_id(base: str, used: set[str], reserved: set[str]) -> str:
    candidate = base
    suffix = 2
    while candidate in used or candidate in reserved:
        candidate = f"{base}-{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


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
    """Return a canonical, JSON-safe spatial layout.

    This function is intentionally tolerant for interactive/editor callers. It never
    uses randomness: malformed or legacy identifiers are repaired deterministically.
    Persisted project data must pass :func:`normalize_persisted_layout` first, which
    rejects unsafe engineering geometry instead of silently defaulting it.
    """

    source = value if isinstance(value, dict) else {}
    result = empty_layout()
    result["grid_m"] = _positive(source.get("grid_m"), 0.5)

    raw_rooms = source.get("rooms", [])
    room_items = raw_rooms if isinstance(raw_rooms, list) else []
    reserved_room_ids = _explicit_ids(room_items)
    used_room_ids: set[str] = set()
    rooms: list[dict] = []
    for index, raw in enumerate(room_items):
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or f"Room {index + 1}").strip() or f"Room {index + 1}"
        explicit_id = raw.get("id")
        if isinstance(explicit_id, str) and explicit_id.strip() and explicit_id.strip() not in used_room_ids:
            room_id = explicit_id.strip()
            used_room_ids.add(room_id)
        else:
            base = (
                f"{explicit_id.strip()}-copy"
                if isinstance(explicit_id, str) and explicit_id.strip()
                else _room_id(name, index)
            )
            room_id = _generated_unique_id(base, used_room_ids, reserved_room_ids)
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

    raw_devices = source.get("devices", [])
    device_items = raw_devices if isinstance(raw_devices, list) else []
    reserved_device_ids = _explicit_ids(device_items)
    used_device_ids: set[str] = set()
    devices: list[dict] = []
    for index, raw in enumerate(device_items):
        if not isinstance(raw, dict):
            continue
        device_type = str(raw.get("type") or "equipment").lower()
        if device_type not in DEVICE_TYPES:
            device_type = "equipment"
        explicit_id = raw.get("id")
        if isinstance(explicit_id, str) and explicit_id.strip() and explicit_id.strip() not in used_device_ids:
            device_id = explicit_id.strip()
            used_device_ids.add(device_id)
        else:
            base = (
                f"{explicit_id.strip()}-copy"
                if isinstance(explicit_id, str) and explicit_id.strip()
                else f"device-{device_type}-{index + 1}"
            )
            device_id = _generated_unique_id(base, used_device_ids, reserved_device_ids)
        room_id = raw.get("room_id")
        if room_id is not None:
            room_id = str(room_id).strip() or None
        devices.append(
            {
                "id": device_id,
                "type": device_type,
                "name": str(raw.get("name") or device_type.upper()),
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


def _require_object(value: Any, path: str) -> dict:
    if not isinstance(value, dict):
        raise SpatialLayoutFormatError(f"{path} must be an object")
    return value


def _require_array(value: Any, path: str) -> list:
    if not isinstance(value, list):
        raise SpatialLayoutFormatError(f"{path} must be an array")
    return value


def _require_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SpatialLayoutFormatError(f"{path} must be a non-empty string")
    return value.strip()


def _require_number(value: Any, path: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SpatialLayoutFormatError(f"{path} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise SpatialLayoutFormatError(f"{path} must be a finite number")
    if positive and number <= 0:
        raise SpatialLayoutFormatError(f"{path} must be greater than zero")
    return number


def _validate_view(view: Any) -> None:
    if view is None:
        return
    view_data = _require_object(view, "spatial_layout.view")
    positive_keys = {"zoom_2d", "zoom_3d"}
    for key in (
        "zoom_2d",
        "pan_x",
        "pan_y",
        "azimuth_deg",
        "elevation_deg",
        "zoom_3d",
        "pan_3d_x",
        "pan_3d_y",
    ):
        if key in view_data:
            _require_number(
                view_data[key],
                f"spatial_layout.view.{key}",
                positive=key in positive_keys,
            )


def validate_persisted_layout(value: Any) -> int:
    """Validate persisted spatial data and return its source layout version.

    Version 1 is strict. Unversioned/version-0 layouts are treated as a legacy
    migration source, but engineering dimensions and coordinates are still required
    and validated; only IDs and editor/view defaults may be synthesized.
    """

    source = _require_object(value, "spatial_layout")
    raw_version = source.get("version", 0)
    if isinstance(raw_version, bool) or not isinstance(raw_version, int):
        raise SpatialLayoutFormatError("spatial_layout.version must be an integer")
    if raw_version < 0:
        raise SpatialLayoutFormatError("spatial_layout.version must not be negative")
    if raw_version > SPATIAL_LAYOUT_VERSION:
        raise SpatialLayoutFormatError(
            f"unsupported future spatial layout version {raw_version}; "
            f"this build supports up to {SPATIAL_LAYOUT_VERSION}"
        )

    if "grid_m" in source:
        _require_number(source["grid_m"], "spatial_layout.grid_m", positive=True)

    rooms = _require_array(source.get("rooms", []), "spatial_layout.rooms")
    explicit_room_ids: set[str] = set()
    normalized_room_ids: set[str] = set()
    reserved_room_ids = _explicit_ids(rooms)
    for index, raw in enumerate(rooms):
        room = _require_object(raw, f"spatial_layout.rooms[{index}]")
        if raw_version >= 1:
            room_id = _require_string(room.get("id"), f"spatial_layout.rooms[{index}].id")
            if room_id in explicit_room_ids:
                raise SpatialLayoutFormatError(f"duplicate spatial room id {room_id!r}")
            explicit_room_ids.add(room_id)
            normalized_room_ids.add(room_id)
        else:
            explicit = room.get("id")
            if explicit is not None:
                room_id = _require_string(explicit, f"spatial_layout.rooms[{index}].id")
                if room_id in explicit_room_ids:
                    raise SpatialLayoutFormatError(f"duplicate spatial room id {room_id!r}")
                explicit_room_ids.add(room_id)
                normalized_room_ids.add(room_id)

        if raw_version >= 1:
            _require_string(room.get("name"), f"spatial_layout.rooms[{index}].name")
        elif "name" in room:
            _require_string(room["name"], f"spatial_layout.rooms[{index}].name")
        for key in ("x_m", "y_m", "length_m", "width_m", "height_m"):
            if key not in room:
                raise SpatialLayoutFormatError(
                    f"spatial_layout.rooms[{index}].{key} is required"
                )
            _require_number(
                room[key],
                f"spatial_layout.rooms[{index}].{key}",
                positive=key in {"length_m", "width_m", "height_m"},
            )
        if room.get("pressure_pa") is not None:
            _require_number(
                room["pressure_pa"],
                f"spatial_layout.rooms[{index}].pressure_pa",
            )

    if raw_version == 0:
        used = set(explicit_room_ids)
        for index, raw in enumerate(rooms):
            if isinstance(raw, dict) and not (
                isinstance(raw.get("id"), str) and raw.get("id", "").strip()
            ):
                name = str(raw.get("name") or f"Room {index + 1}").strip() or f"Room {index + 1}"
                generated = _generated_unique_id(
                    _room_id(name, index),
                    used,
                    reserved_room_ids,
                )
                normalized_room_ids.add(generated)

    devices = _require_array(source.get("devices", []), "spatial_layout.devices")
    explicit_device_ids: set[str] = set()
    for index, raw in enumerate(devices):
        device = _require_object(raw, f"spatial_layout.devices[{index}]")
        if raw_version >= 1:
            device_id = _require_string(
                device.get("id"), f"spatial_layout.devices[{index}].id"
            )
            if device_id in explicit_device_ids:
                raise SpatialLayoutFormatError(f"duplicate spatial device id {device_id!r}")
            explicit_device_ids.add(device_id)
        elif device.get("id") is not None:
            device_id = _require_string(
                device.get("id"), f"spatial_layout.devices[{index}].id"
            )
            if device_id in explicit_device_ids:
                raise SpatialLayoutFormatError(f"duplicate spatial device id {device_id!r}")
            explicit_device_ids.add(device_id)

        device_type = _require_string(
            device.get("type"), f"spatial_layout.devices[{index}].type"
        ).lower()
        if device_type not in DEVICE_TYPES:
            raise SpatialLayoutFormatError(
                f"spatial_layout.devices[{index}].type {device_type!r} is unsupported"
            )
        if raw_version >= 1:
            _require_string(
                device.get("name"), f"spatial_layout.devices[{index}].name"
            )
        elif "name" in device:
            _require_string(device["name"], f"spatial_layout.devices[{index}].name")
        for key in ("x_m", "y_m", "z_m"):
            if key not in device:
                raise SpatialLayoutFormatError(
                    f"spatial_layout.devices[{index}].{key} is required"
                )
            _require_number(device[key], f"spatial_layout.devices[{index}].{key}")

        room_id = device.get("room_id")
        if room_id is not None:
            room_id = _require_string(
                room_id, f"spatial_layout.devices[{index}].room_id"
            )
            if room_id not in normalized_room_ids:
                raise SpatialLayoutFormatError(
                    f"spatial_layout.devices[{index}].room_id references "
                    f"missing room id {room_id!r}"
                )

    _validate_view(source.get("view"))
    return raw_version


def normalize_persisted_layout(value: Any) -> dict:
    """Validate project-persisted spatial metadata without losing v1 extensions.

    Unversioned/version-0 data is migrated to the canonical v1 shape. Valid v1
    layouts are deep-copied unchanged so load/save does not strip unknown
    forward-compatible metadata owned by another extension.
    """

    version = validate_persisted_layout(value)
    if version == 0:
        return normalize_layout(value)
    return copy.deepcopy(value)
