from __future__ import annotations

import math
from typing import Any


SPATIAL_METADATA_KEY = "spatial_layout"
SPATIAL_LAYOUT_VERSION = 1
SPATIAL_GEOMETRY_EPSILON_M = 1e-9
DEVICE_TYPES = ("door", "supply", "return", "exhaust", "ffu", "equipment", "sensor", "transfer")


class SpatialLayoutFormatError(ValueError):
    """Raised when persisted spatial metadata violates the supported layout contract."""


def _require_non_empty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SpatialLayoutFormatError(f"{field} must be a non-empty string")
    return value.strip()


def _require_finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SpatialLayoutFormatError(f"{field} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise SpatialLayoutFormatError(f"{field} must be a finite number")
    return number


def _require_positive_number(value: Any, field: str) -> float:
    number = _require_finite_number(value, field)
    if number <= 0:
        raise SpatialLayoutFormatError(f"{field} must be greater than zero")
    return number


def _validate_floor(floor: Any) -> None:
    if floor is None:
        return
    if not isinstance(floor, dict):
        raise SpatialLayoutFormatError("spatial_layout.floor must be an object")
    if "id" in floor:
        _require_non_empty_string(floor["id"], "spatial_layout.floor.id")
    if "name" in floor:
        _require_non_empty_string(floor["name"], "spatial_layout.floor.name")
    if "elevation_m" in floor:
        _require_finite_number(floor["elevation_m"], "spatial_layout.floor.elevation_m")
    if "default_ceiling_height_m" in floor:
        _require_positive_number(
            floor["default_ceiling_height_m"],
            "spatial_layout.floor.default_ceiling_height_m",
        )
    if "units" in floor:
        units = _require_non_empty_string(floor["units"], "spatial_layout.floor.units")
        if units != "m":
            raise SpatialLayoutFormatError("spatial_layout.floor.units must be 'm'")


def _validate_view(view: Any) -> None:
    if view is None:
        return
    if not isinstance(view, dict):
        raise SpatialLayoutFormatError("spatial_layout.view must be an object")

    bounded_fields = {
        "zoom_2d": (0.2, 8.0),
        "zoom_3d": (0.2, 8.0),
        "elevation_deg": (5.0, 75.0),
    }
    finite_fields = {
        "pan_x",
        "pan_y",
        "azimuth_deg",
        "pan_3d_x",
        "pan_3d_y",
    }
    boolean_fields = {
        "snap_to_grid",
        "show_pressure",
        "show_labels",
        "show_devices",
        "show_relationships",
    }

    for field, (minimum, maximum) in bounded_fields.items():
        if field in view:
            number = _require_finite_number(view[field], f"spatial_layout.view.{field}")
            if number < minimum or number > maximum:
                raise SpatialLayoutFormatError(
                    f"spatial_layout.view.{field} must be between {minimum:g} and {maximum:g}"
                )
    for field in finite_fields:
        if field in view:
            _require_finite_number(view[field], f"spatial_layout.view.{field}")
    for field in boolean_fields:
        if field in view and not isinstance(view[field], bool):
            raise SpatialLayoutFormatError(
                f"spatial_layout.view.{field} must be a boolean"
            )


def validate_spatial_layout_document(value: Any) -> None:
    """Validate persisted spatial data without repairing or silently rewriting it.

    The GUI keeps a forgiving normalization path for interactive editing, but the
    project persistence boundary must fail closed on ambiguous identity, invalid
    geometry, dangling references, or unsupported future layout versions.
    """

    if not isinstance(value, dict):
        raise SpatialLayoutFormatError("spatial_layout must be an object")

    version = value.get("version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise SpatialLayoutFormatError("spatial_layout.version must be an integer")
    if version > SPATIAL_LAYOUT_VERSION:
        raise SpatialLayoutFormatError(
            f"unsupported future spatial layout version {version}; "
            f"this build supports up to {SPATIAL_LAYOUT_VERSION}"
        )
    if version < SPATIAL_LAYOUT_VERSION:
        raise SpatialLayoutFormatError(
            f"unsupported legacy spatial layout version {version}; "
            f"this build supports version {SPATIAL_LAYOUT_VERSION}"
        )

    if "grid_m" in value:
        _require_positive_number(value["grid_m"], "spatial_layout.grid_m")
    _validate_floor(value.get("floor"))

    rooms = value.get("rooms", [])
    if not isinstance(rooms, list):
        raise SpatialLayoutFormatError("spatial_layout.rooms must be an array")

    room_ids: set[str] = set()
    for index, room in enumerate(rooms):
        prefix = f"spatial_layout.rooms[{index}]"
        if not isinstance(room, dict):
            raise SpatialLayoutFormatError(f"{prefix} must be an object")
        room_id = _require_non_empty_string(room.get("id"), f"{prefix}.id")
        if room_id in room_ids:
            raise SpatialLayoutFormatError(
                f"{prefix}.id duplicates room id {room_id!r}"
            )
        room_ids.add(room_id)
        _require_non_empty_string(room.get("name"), f"{prefix}.name")
        _require_finite_number(room.get("x_m"), f"{prefix}.x_m")
        _require_finite_number(room.get("y_m"), f"{prefix}.y_m")
        _require_positive_number(room.get("length_m"), f"{prefix}.length_m")
        _require_positive_number(room.get("width_m"), f"{prefix}.width_m")
        _require_positive_number(room.get("height_m"), f"{prefix}.height_m")
        if room.get("floor_elevation_m") is not None:
            _require_finite_number(
                room.get("floor_elevation_m"), f"{prefix}.floor_elevation_m"
            )
        if room.get("pressure_pa") is not None:
            _require_finite_number(room.get("pressure_pa"), f"{prefix}.pressure_pa")
        for field in ("classification", "analysis_room_name"):
            if room.get(field) is not None:
                _require_non_empty_string(room.get(field), f"{prefix}.{field}")

    devices = value.get("devices", [])
    if not isinstance(devices, list):
        raise SpatialLayoutFormatError("spatial_layout.devices must be an array")

    device_ids: set[str] = set()
    for index, device in enumerate(devices):
        prefix = f"spatial_layout.devices[{index}]"
        if not isinstance(device, dict):
            raise SpatialLayoutFormatError(f"{prefix} must be an object")
        device_id = _require_non_empty_string(device.get("id"), f"{prefix}.id")
        if device_id in device_ids:
            raise SpatialLayoutFormatError(
                f"{prefix}.id duplicates device id {device_id!r}"
            )
        device_ids.add(device_id)

        device_type = _require_non_empty_string(device.get("type"), f"{prefix}.type")
        if device_type not in DEVICE_TYPES:
            raise SpatialLayoutFormatError(
                f"{prefix}.type must be one of {', '.join(DEVICE_TYPES)}"
            )
        _require_non_empty_string(device.get("name"), f"{prefix}.name")

        room_id = device.get("room_id")
        if room_id is not None:
            room_id = _require_non_empty_string(room_id, f"{prefix}.room_id")
            if room_id not in room_ids:
                raise SpatialLayoutFormatError(
                    f"{prefix}.room_id references missing room id {room_id!r}"
                )

        _require_finite_number(device.get("x_m"), f"{prefix}.x_m")
        _require_finite_number(device.get("y_m"), f"{prefix}.y_m")
        _require_finite_number(device.get("z_m"), f"{prefix}.z_m")
        if device.get("width_m") is not None:
            _require_positive_number(device.get("width_m"), f"{prefix}.width_m")
        if device.get("height_m") is not None:
            _require_positive_number(device.get("height_m"), f"{prefix}.height_m")
        if device.get("orientation_deg") is not None:
            _require_finite_number(
                device.get("orientation_deg"), f"{prefix}.orientation_deg"
            )
        if device.get("wall_side") is not None:
            wall_side = _require_non_empty_string(
                device.get("wall_side"), f"{prefix}.wall_side"
            )
            if wall_side not in {"north", "south", "east", "west"}:
                raise SpatialLayoutFormatError(
                    f"{prefix}.wall_side must be north, south, east, or west"
                )
        if device.get("swing") is not None:
            _require_non_empty_string(device.get("swing"), f"{prefix}.swing")

    _validate_view(value.get("view"))


def validate_project_spatial_metadata(metadata: dict[str, Any]) -> None:
    """Validate spatial metadata when present in a project document."""

    if SPATIAL_METADATA_KEY not in metadata:
        return
    validate_spatial_layout_document(metadata[SPATIAL_METADATA_KEY])
