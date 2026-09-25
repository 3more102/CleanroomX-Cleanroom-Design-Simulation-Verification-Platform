from __future__ import annotations

import math
from typing import Any


SPATIAL_METADATA_KEY = "spatial_layout"
SPATIAL_LAYOUT_VERSION = 1
DEVICE_TYPES = (
    "door",
    "supply",
    "return",
    "exhaust",
    "ffu",
    "equipment",
    "sensor",
)


class SpatialLayoutFormatError(ValueError):
    """Raised when persisted spatial metadata violates the layout contract."""


def _require_mapping(value: Any, path: str) -> dict:
    if not isinstance(value, dict):
        raise SpatialLayoutFormatError(f"{path} must be an object")
    return value


def _require_list(value: Any, path: str) -> list:
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
    if positive and number <= 0.0:
        raise SpatialLayoutFormatError(f"{path} must be greater than zero")
    return number


def validate_spatial_layout_document(value: Any) -> None:
    """Validate persisted spatial layout data without repairing or mutating it.

    This validator intentionally checks storage integrity only. Geometric design
    advisories such as room overlap or an assigned device lying outside its room
    remain editor-level warnings so valid-but-incomplete design work can still be
    saved.
    """

    layout = _require_mapping(value, SPATIAL_METADATA_KEY)

    version = layout.get("version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise SpatialLayoutFormatError(
            f"{SPATIAL_METADATA_KEY}.version must be an integer"
        )
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

    rooms = _require_list(layout.get("rooms"), f"{SPATIAL_METADATA_KEY}.rooms")
    room_ids: set[str] = set()
    for index, raw_room in enumerate(rooms):
        path = f"{SPATIAL_METADATA_KEY}.rooms[{index}]"
        room = _require_mapping(raw_room, path)
        room_id = _require_string(room.get("id"), f"{path}.id")
        if room_id in room_ids:
            raise SpatialLayoutFormatError(
                f"duplicate room id in {SPATIAL_METADATA_KEY}: {room_id!r}"
            )
        room_ids.add(room_id)

        _require_string(room.get("name"), f"{path}.name")
        _require_number(room.get("x_m"), f"{path}.x_m")
        _require_number(room.get("y_m"), f"{path}.y_m")
        _require_number(room.get("length_m"), f"{path}.length_m", positive=True)
        _require_number(room.get("width_m"), f"{path}.width_m", positive=True)
        _require_number(room.get("height_m"), f"{path}.height_m", positive=True)
        if room.get("pressure_pa") is not None:
            _require_number(room.get("pressure_pa"), f"{path}.pressure_pa")

    devices = _require_list(layout.get("devices"), f"{SPATIAL_METADATA_KEY}.devices")
    device_ids: set[str] = set()
    for index, raw_device in enumerate(devices):
        path = f"{SPATIAL_METADATA_KEY}.devices[{index}]"
        device = _require_mapping(raw_device, path)
        device_id = _require_string(device.get("id"), f"{path}.id")
        if device_id in device_ids:
            raise SpatialLayoutFormatError(
                f"duplicate device id in {SPATIAL_METADATA_KEY}: {device_id!r}"
            )
        device_ids.add(device_id)

        device_type = _require_string(device.get("type"), f"{path}.type").lower()
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

    view = _require_mapping(layout.get("view"), f"{SPATIAL_METADATA_KEY}.view")
    for key in (
        "pan_x",
        "pan_y",
        "azimuth_deg",
        "elevation_deg",
        "pan_3d_x",
        "pan_3d_y",
    ):
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
    validate_spatial_layout_document(metadata[SPATIAL_METADATA_KEY])
