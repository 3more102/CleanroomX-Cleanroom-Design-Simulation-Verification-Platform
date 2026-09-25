from __future__ import annotations

import copy
import math
from typing import Any


SPATIAL_METADATA_KEY = "spatial_layout"
SPATIAL_LAYOUT_VERSION = 1
DEVICE_TYPES = ("door", "supply", "return", "exhaust", "ffu", "equipment", "sensor")


class SpatialLayoutFormatError(ValueError):
    """Raised when persisted spatial metadata violates the supported schema."""


def _finite_number(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _positive(value: Any, default: float) -> float:
    number = _finite_number(value, default)
    return number if number > 0 else default


def _slug(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")


def _room_id(name: str) -> str:
    return _slug(name) or "room"


def _unique_identifier(
    raw_id: Any,
    *,
    prefix: str,
    index: int,
    name: str,
    used_ids: set[str],
) -> str:
    """Return a deterministic identifier for lenient in-memory normalization."""
    candidate = str(raw_id).strip() if raw_id is not None else ""
    if not candidate:
        candidate = _room_id(name) if prefix == "room" else f"{prefix}-{index + 1}"

    if candidate in used_ids:
        base = candidate
        suffix = 2
        while f"{base}-{suffix}" in used_ids:
            suffix += 1
        candidate = f"{base}-{suffix}"

    used_ids.add(candidate)
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
    """Normalize ad-hoc workspace data deterministically.

    This helper is intentionally forgiving for interactive/editor callers.
    Persisted project data is checked separately by
    validate_persisted_spatial_layout() before normalization is allowed.
    Unknown extension fields are retained.
    """
    source = value if isinstance(value, dict) else {}
    result = copy.deepcopy(source)
    defaults = empty_layout()
    result["version"] = SPATIAL_LAYOUT_VERSION
    result["grid_m"] = _positive(source.get("grid_m"), defaults["grid_m"])

    rooms: list[dict] = []
    used_room_ids: set[str] = set()
    raw_rooms = source.get("rooms", [])
    if isinstance(raw_rooms, list):
        for index, raw in enumerate(raw_rooms):
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name") or f"Room {index + 1}").strip() or f"Room {index + 1}"
            room_id = _unique_identifier(
                raw.get("id"),
                prefix="room",
                index=index,
                name=name,
                used_ids=used_room_ids,
            )
            room = copy.deepcopy(raw)
            room.update(
                {
                    "id": room_id,
                    "name": name,
                    "x_m": _finite_number(raw.get("x_m"), 0.0),
                    "y_m": _finite_number(raw.get("y_m"), 0.0),
                    "length_m": _positive(raw.get("length_m"), 4.0),
                    "width_m": _positive(raw.get("width_m"), 4.0),
                    "height_m": _positive(raw.get("height_m"), 3.0),
                }
            )
            if raw.get("pressure_pa") is not None:
                room["pressure_pa"] = _finite_number(raw.get("pressure_pa"), 0.0)
            else:
                room.pop("pressure_pa", None)
            rooms.append(room)
    result["rooms"] = rooms

    devices: list[dict] = []
    used_device_ids: set[str] = set()
    raw_devices = source.get("devices", [])
    if isinstance(raw_devices, list):
        for index, raw in enumerate(raw_devices):
            if not isinstance(raw, dict):
                continue
            device_type = str(raw.get("type") or "equipment").strip().lower()
            if device_type not in DEVICE_TYPES:
                device_type = "equipment"
            name = str(raw.get("name") or device_type.upper()).strip() or device_type.upper()
            device_id = _unique_identifier(
                raw.get("id"),
                prefix="device",
                index=index,
                name=name,
                used_ids=used_device_ids,
            )
            raw_room_id = raw.get("room_id")
            room_id = None
            if raw_room_id is not None:
                room_id = str(raw_room_id).strip() or None
            device = copy.deepcopy(raw)
            device.update(
                {
                    "id": device_id,
                    "type": device_type,
                    "name": name,
                    "room_id": room_id,
                    "x_m": _finite_number(raw.get("x_m"), 0.0),
                    "y_m": _finite_number(raw.get("y_m"), 0.0),
                    "z_m": _finite_number(raw.get("z_m"), 0.0),
                }
            )
            devices.append(device)
    result["devices"] = devices

    raw_view = source.get("view", {})
    view = copy.deepcopy(raw_view) if isinstance(raw_view, dict) else {}
    default_view = defaults["view"]
    view.update(
        {
            "zoom_2d": max(0.2, min(8.0, _positive(view.get("zoom_2d"), default_view["zoom_2d"]))),
            "pan_x": _finite_number(view.get("pan_x"), default_view["pan_x"]),
            "pan_y": _finite_number(view.get("pan_y"), default_view["pan_y"]),
            "azimuth_deg": _finite_number(view.get("azimuth_deg"), default_view["azimuth_deg"]),
            "elevation_deg": max(
                5.0,
                min(75.0, _finite_number(view.get("elevation_deg"), default_view["elevation_deg"])),
            ),
            "zoom_3d": max(0.2, min(8.0, _positive(view.get("zoom_3d"), default_view["zoom_3d"]))),
            "pan_3d_x": _finite_number(view.get("pan_3d_x"), default_view["pan_3d_x"]),
            "pan_3d_y": _finite_number(view.get("pan_3d_y"), default_view["pan_3d_y"]),
        }
    )
    result["view"] = view
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
    stripped = value.strip()
    if stripped != value:
        raise SpatialLayoutFormatError(
            f"{path} must not have leading or trailing whitespace"
        )
    return value


def _require_number(value: Any, path: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SpatialLayoutFormatError(f"{path} must be a finite number")
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise SpatialLayoutFormatError(f"{path} must be a finite number") from exc
    if not math.isfinite(number):
        raise SpatialLayoutFormatError(f"{path} must be a finite number")
    if positive and number <= 0:
        raise SpatialLayoutFormatError(f"{path} must be greater than zero")
    return number


def validate_persisted_spatial_layout(value: Any) -> None:
    """Validate persisted spatial v1 data without repairing or mutating it.

    This is a storage-integrity contract. Geometric design advisories such as
    room overlap or an assigned device lying outside its room remain workspace
    warnings so incomplete design work can still be saved intentionally.
    """
    layout = _require_object(value, SPATIAL_METADATA_KEY)

    version = layout.get("version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise SpatialLayoutFormatError(f"{SPATIAL_METADATA_KEY}.version must be an integer")
    if version > SPATIAL_LAYOUT_VERSION:
        raise SpatialLayoutFormatError(
            f"unsupported future {SPATIAL_METADATA_KEY} version {version}; "
            f"this build supports up to {SPATIAL_LAYOUT_VERSION}"
        )
    if version < SPATIAL_LAYOUT_VERSION:
        raise SpatialLayoutFormatError(
            f"unsupported legacy {SPATIAL_METADATA_KEY} version {version}"
        )

    _require_number(
        layout.get("grid_m"),
        f"{SPATIAL_METADATA_KEY}.grid_m",
        positive=True,
    )

    rooms = _require_array(layout.get("rooms"), f"{SPATIAL_METADATA_KEY}.rooms")
    room_ids: set[str] = set()
    for index, raw_room in enumerate(rooms):
        path = f"{SPATIAL_METADATA_KEY}.rooms[{index}]"
        room = _require_object(raw_room, path)
        room_id = _require_string(room.get("id"), f"{path}.id")
        if room_id in room_ids:
            raise SpatialLayoutFormatError(f"{path}.id duplicates room id {room_id!r}")
        room_ids.add(room_id)
        _require_string(room.get("name"), f"{path}.name")
        _require_number(room.get("x_m"), f"{path}.x_m")
        _require_number(room.get("y_m"), f"{path}.y_m")
        _require_number(room.get("length_m"), f"{path}.length_m", positive=True)
        _require_number(room.get("width_m"), f"{path}.width_m", positive=True)
        _require_number(room.get("height_m"), f"{path}.height_m", positive=True)
        if "pressure_pa" in room:
            _require_number(room["pressure_pa"], f"{path}.pressure_pa")

    devices = _require_array(layout.get("devices"), f"{SPATIAL_METADATA_KEY}.devices")
    device_ids: set[str] = set()
    for index, raw_device in enumerate(devices):
        path = f"{SPATIAL_METADATA_KEY}.devices[{index}]"
        device = _require_object(raw_device, path)
        device_id = _require_string(device.get("id"), f"{path}.id")
        if device_id in device_ids:
            raise SpatialLayoutFormatError(f"{path}.id duplicates device id {device_id!r}")
        device_ids.add(device_id)
        device_type = _require_string(device.get("type"), f"{path}.type")
        if device_type not in DEVICE_TYPES:
            raise SpatialLayoutFormatError(
                f"{path}.type must be one of {', '.join(DEVICE_TYPES)}"
            )
        _require_string(device.get("name"), f"{path}.name")
        room_id = device.get("room_id")
        if room_id is not None:
            room_id = _require_string(room_id, f"{path}.room_id")
            if room_id not in room_ids:
                raise SpatialLayoutFormatError(
                    f"{path}.room_id references missing room id {room_id!r}"
                )
        _require_number(device.get("x_m"), f"{path}.x_m")
        _require_number(device.get("y_m"), f"{path}.y_m")
        _require_number(device.get("z_m"), f"{path}.z_m")

    view = _require_object(layout.get("view"), f"{SPATIAL_METADATA_KEY}.view")
    for key in ("pan_x", "pan_y", "azimuth_deg", "elevation_deg", "pan_3d_x", "pan_3d_y"):
        if key in view:
            _require_number(view[key], f"{SPATIAL_METADATA_KEY}.view.{key}")
    for key in ("zoom_2d", "zoom_3d"):
        if key in view:
            _require_number(
                view[key],
                f"{SPATIAL_METADATA_KEY}.view.{key}",
                positive=True,
            )


def validate_spatial_metadata(metadata: dict[str, Any]) -> None:
    """Validate the spatial sub-document when it is present in project metadata."""
    if SPATIAL_METADATA_KEY not in metadata:
        return
    validate_persisted_spatial_layout(metadata[SPATIAL_METADATA_KEY])
