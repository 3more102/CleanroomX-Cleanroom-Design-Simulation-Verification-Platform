from __future__ import annotations

import math
from typing import Any


SPATIAL_METADATA_KEY = "spatial_layout"
SPATIAL_LAYOUT_VERSION = 1
SPATIAL_GEOMETRY_EPSILON_M = 1e-9
DEVICE_TYPES = (
    "door",
    "window",
    "opening",
    "supply",
    "return",
    "exhaust",
    "ffu",
    "equipment",
    "sensor",
)


class SpatialLayoutFormatError(ValueError):
    """Raised when persisted spatial metadata violates the supported layout contract."""


def _require_non_empty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SpatialLayoutFormatError(f"{field} must be a non-empty string")
    return value.strip()


def _require_optional_string(value: Any, field: str) -> None:
    if value is not None and not isinstance(value, str):
        raise SpatialLayoutFormatError(f"{field} must be a string or null")


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


def _validate_engineering_ref(value: Any, field: str) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        raise SpatialLayoutFormatError(f"{field} must be an object or null")
    analysis_id = value.get("analysis_id")
    if analysis_id is not None:
        _require_non_empty_string(analysis_id, f"{field}.analysis_id")
    _require_non_empty_string(value.get("room_name"), f"{field}.room_name")
    baseline = value.get("baseline_geometry", {})
    if not isinstance(baseline, dict):
        raise SpatialLayoutFormatError(f"{field}.baseline_geometry must be an object")
    for name in ("length_m", "width_m", "height_m"):
        if name in baseline:
            _require_positive_number(baseline[name], f"{field}.baseline_geometry.{name}")


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


def validate_spatial_layout_document(value: Any) -> None:
    """Validate persisted spatial data without repairing or silently rewriting it.

    Spatial schema version 1 is intentionally additive: v0.100/v0.101 projects
    containing only the original geometry fields remain valid while newer
    optional design metadata can be persisted without changing the outer project
    schema.
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

        if "elevation_m" in room:
            _require_finite_number(room.get("elevation_m"), f"{prefix}.elevation_m")
        for field in (
            "pressure_pa",
            "pressure_target_pa",
            "temperature_target_c",
        ):
            if room.get(field) is not None:
                _require_finite_number(room.get(field), f"{prefix}.{field}")
        if room.get("humidity_target_rh_pct") is not None:
            humidity = _require_finite_number(
                room.get("humidity_target_rh_pct"),
                f"{prefix}.humidity_target_rh_pct",
            )
            if humidity < 0 or humidity > 100:
                raise SpatialLayoutFormatError(
                    f"{prefix}.humidity_target_rh_pct must be between 0 and 100"
                )

        for field in (
            "classification",
            "airflow_ref",
            "engineering_zone_id",
            "notes",
        ):
            _require_optional_string(room.get(field), f"{prefix}.{field}")

        metadata = room.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            raise SpatialLayoutFormatError(f"{prefix}.metadata must be an object")
        _validate_engineering_ref(room.get("engineering_ref"), f"{prefix}.engineering_ref")

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
            _require_finite_number(device.get("orientation_deg"), f"{prefix}.orientation_deg")
        metadata = device.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            raise SpatialLayoutFormatError(f"{prefix}.metadata must be an object")

    _validate_view(value.get("view"))


def validate_project_spatial_metadata(metadata: dict[str, Any]) -> None:
    """Validate spatial metadata when present in a project document."""

    if SPATIAL_METADATA_KEY not in metadata:
        return
    validate_spatial_layout_document(metadata[SPATIAL_METADATA_KEY])
