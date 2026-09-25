from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable


SPATIAL_METADATA_KEY = "spatial_layout"
SPATIAL_LAYOUT_VERSION = 1
DEVICE_TYPES = ("door", "supply", "return", "exhaust", "ffu", "equipment", "sensor")


class SpatialLayoutFormatError(ValueError):
    """Raised when persisted spatial metadata cannot be interpreted safely."""


def _identifier_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _slug(value: Any) -> str:
    text = str(value or "")
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in text)
    return "-".join(part for part in slug.split("-") if part)


def preferred_room_id(name: Any) -> str:
    """Return a deterministic room-id base without allocating uniqueness."""
    return _slug(name) or "room"


def preferred_device_id(device_type: Any, name: Any) -> str:
    """Return a deterministic device-id base without allocating uniqueness."""
    label = _slug(name)
    kind = _slug(device_type) or "equipment"
    return f"device-{label or kind}"


def allocate_unique_identifier(
    preferred: Any,
    used_ids: set[str],
    *,
    reserved_ids: Iterable[str] = (),
) -> str:
    """Allocate a stable identifier while preserving explicitly reserved ids.

    The result depends only on the preferred id and the supplied identity sets.
    No clock, randomness, process state, or hash randomization participates.
    """
    base = _identifier_text(preferred) or "item"
    blocked = set(reserved_ids)
    if base not in used_ids and base not in blocked:
        used_ids.add(base)
        return base

    suffix = 2
    while True:
        candidate = f"{base}-{suffix}"
        if candidate not in used_ids and candidate not in blocked:
            used_ids.add(candidate)
            return candidate
        suffix += 1


def _raw_sequence(
    source: dict,
    key: str,
    *,
    strict: bool,
) -> list:
    value = source.get(key, [])
    if isinstance(value, list):
        return value
    if strict:
        raise SpatialLayoutFormatError(f"spatial_layout.{key} must be an array")
    return []


def _validate_version(source: dict) -> None:
    version = source.get("version", SPATIAL_LAYOUT_VERSION)
    if isinstance(version, bool) or not isinstance(version, int):
        raise SpatialLayoutFormatError("spatial_layout.version must be an integer")
    if version > SPATIAL_LAYOUT_VERSION:
        raise SpatialLayoutFormatError(
            f"unsupported future spatial layout version {version}; "
            f"this build supports up to {SPATIAL_LAYOUT_VERSION}"
        )
    if version < SPATIAL_LAYOUT_VERSION:
        raise SpatialLayoutFormatError(
            f"unsupported legacy spatial layout version {version}"
        )


def migrate_spatial_layout(value: Any, *, strict: bool) -> dict:
    """Return a version-1 layout with deterministic, unique persistent identities.

    Unknown top-level and per-item fields are preserved. In strict mode malformed
    persisted collection shapes and duplicate explicit identities are rejected
    instead of being silently discarded or ambiguously rebound. Missing identities,
    and duplicates in tolerant in-memory normalization, are repaired deterministically
    so repeated normalization of the same bytes produces the same identity graph.
    """
    if not isinstance(value, dict):
        if strict:
            raise SpatialLayoutFormatError("spatial_layout must be an object")
        value = {}

    source = deepcopy(value)
    _validate_version(source)
    source["version"] = SPATIAL_LAYOUT_VERSION

    raw_rooms = _raw_sequence(source, "rooms", strict=strict)
    room_records: list[dict] = []
    room_reserved: set[str] = set()
    for index, raw in enumerate(raw_rooms):
        if not isinstance(raw, dict):
            if strict:
                raise SpatialLayoutFormatError(
                    f"spatial_layout.rooms[{index}] must be an object"
                )
            continue
        record = deepcopy(raw)
        explicit = _identifier_text(record.get("id"))
        if explicit is not None:
            if strict and explicit in room_reserved:
                raise SpatialLayoutFormatError(
                    f"spatial_layout room ids must be unique; duplicate id {explicit!r}"
                )
            room_reserved.add(explicit)
        room_records.append(record)

    room_used: set[str] = set()
    migrated_rooms: list[dict] = []
    for index, record in enumerate(room_records):
        name = str(record.get("name") or f"Room {index + 1}").strip() or f"Room {index + 1}"
        explicit = _identifier_text(record.get("id"))
        if explicit is not None and explicit not in room_used:
            room_id = explicit
            room_used.add(room_id)
        else:
            preferred = explicit or preferred_room_id(name)
            room_id = allocate_unique_identifier(
                preferred,
                room_used,
                reserved_ids=room_reserved,
            )
        record["id"] = room_id
        migrated_rooms.append(record)
    source["rooms"] = migrated_rooms

    raw_devices = _raw_sequence(source, "devices", strict=strict)
    device_records: list[dict] = []
    device_reserved: set[str] = set()
    for index, raw in enumerate(raw_devices):
        if not isinstance(raw, dict):
            if strict:
                raise SpatialLayoutFormatError(
                    f"spatial_layout.devices[{index}] must be an object"
                )
            continue
        record = deepcopy(raw)
        explicit = _identifier_text(record.get("id"))
        if explicit is not None:
            if strict and explicit in device_reserved:
                raise SpatialLayoutFormatError(
                    f"spatial_layout device ids must be unique; duplicate id {explicit!r}"
                )
            device_reserved.add(explicit)
        device_records.append(record)

    device_used: set[str] = set()
    migrated_devices: list[dict] = []
    for record in device_records:
        device_type = str(record.get("type") or "equipment").lower()
        name = str(record.get("name") or device_type.upper())
        explicit = _identifier_text(record.get("id"))
        if explicit is not None and explicit not in device_used:
            device_id = explicit
            device_used.add(device_id)
        else:
            preferred = explicit or preferred_device_id(device_type, name)
            device_id = allocate_unique_identifier(
                preferred,
                device_used,
                reserved_ids=device_reserved,
            )
        record["id"] = device_id
        room_id = _identifier_text(record.get("room_id"))
        record["room_id"] = room_id
        migrated_devices.append(record)
    source["devices"] = migrated_devices

    if "view" in source and not isinstance(source["view"], dict):
        if strict:
            raise SpatialLayoutFormatError("spatial_layout.view must be an object")
        source["view"] = {}

    return source
