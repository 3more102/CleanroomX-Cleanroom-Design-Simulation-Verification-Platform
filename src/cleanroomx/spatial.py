from __future__ import annotations

from dataclasses import dataclass
import copy
import math
import uuid
from typing import Any, Callable

import tkinter as tk
from tkinter import ttk

from .spatial_integrity import (
    DEVICE_TYPES,
    SPATIAL_GEOMETRY_EPSILON_M,
    SPATIAL_LAYOUT_VERSION,
    SPATIAL_METADATA_KEY,
)
from .spatial_transform import Viewport2D, fit_viewport


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


def _optional_finite(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _engineering_baseline(raw: dict) -> dict:
    baseline = {
        "length_m": _positive(raw.get("length_m"), 4.0),
        "width_m": _positive(raw.get("width_m"), 4.0),
        "height_m": _positive(raw.get("height_m"), 3.0),
    }
    pressure = _optional_finite(raw.get("observed_pressure_pa"))
    if pressure is not None:
        baseline["pressure_pa"] = pressure
    return baseline


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
    """Return the current spatial schema without mutating the supplied document.

    Spatial-v1 data is upgraded additively. Invalid interactive values are repaired
    to safe editor defaults; the project persistence boundary remains strict and
    rejects malformed persisted documents before this function is reached.
    """

    source = value if isinstance(value, dict) else {}
    source_version = source.get("version", 1)
    result = empty_layout()
    result["grid_m"] = _positive(source.get("grid_m"), 0.5)

    rooms: list[dict] = []
    used_ids: set[str] = set()
    raw_rooms = source.get("rooms", [])
    if isinstance(raw_rooms, list):
        for index, raw in enumerate(raw_rooms):
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name") or f"Room {index + 1}").strip() or f"Room {index + 1}"
            room_id = _unique_id(raw.get("id"), used_ids, fallback=_room_id(name))
            room = {
                "id": room_id,
                "name": name,
                "x_m": _finite_number(raw.get("x_m"), 0.0),
                "y_m": _finite_number(raw.get("y_m"), 0.0),
                "length_m": _positive(raw.get("length_m"), 4.0),
                "width_m": _positive(raw.get("width_m"), 4.0),
                "height_m": _positive(raw.get("height_m"), 3.0),
                "elevation_m": _finite_number(raw.get("elevation_m"), 0.0),
            }
            pressure = _optional_finite(raw.get("pressure_pa"))
            if pressure is not None:
                room["pressure_pa"] = pressure
            for field in (
                "pressure_target_pa",
                "temperature_target_c",
                "humidity_target_rh_pct",
            ):
                number = _optional_finite(raw.get(field))
                if number is not None:
                    room[field] = number
            for field in ("classification", "notes"):
                text = _optional_string(raw.get(field))
                if text is not None:
                    room[field] = text
            engineering_ref = _optional_string(raw.get("engineering_ref"))
            if engineering_ref is None and source_version == 1:
                # v1 synchronization was name-based. Preserve that behavior while
                # making the inferred mapping explicit in the v2 document.
                engineering_ref = name
            if engineering_ref is not None:
                room["engineering_ref"] = engineering_ref
            metadata = raw.get("metadata")
            if isinstance(metadata, dict):
                room["metadata"] = copy.deepcopy(metadata)
            baseline = raw.get("engineering_baseline")
            if isinstance(baseline, dict):
                normalized_baseline: dict[str, float] = {}
                for field in ("length_m", "width_m", "height_m"):
                    if field in baseline:
                        normalized_baseline[field] = _positive(
                            baseline.get(field), room[field]
                        )
                baseline_pressure = _optional_finite(baseline.get("pressure_pa"))
                if baseline_pressure is not None:
                    normalized_baseline["pressure_pa"] = baseline_pressure
                if normalized_baseline:
                    room["engineering_baseline"] = normalized_baseline
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
                raw.get("id"), used_device_ids, fallback=f"device-{index + 1}"
            )
            room_id = raw.get("room_id")
            if room_id is not None:
                room_id = str(room_id).strip() or None
            device = {
                "id": device_id,
                "type": device_type,
                "name": str(raw.get("name") or device_type.upper()),
                "room_id": room_id,
                "x_m": _finite_number(raw.get("x_m"), 0.0),
                "y_m": _finite_number(raw.get("y_m"), 0.0),
                "z_m": _finite_number(raw.get("z_m"), 0.0),
            }
            for field in ("engineering_ref", "notes"):
                text = _optional_string(raw.get(field))
                if text is not None:
                    device[field] = text
            metadata = raw.get("metadata")
            if isinstance(metadata, dict):
                device["metadata"] = copy.deepcopy(metadata)
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
                "elevation_deg": max(
                    5.0, min(75.0, _finite_number(view.get("elevation_deg"), 28.0))
                ),
                "zoom_3d": max(0.2, min(8.0, _positive(view.get("zoom_3d"), 1.0))),
                "pan_3d_x": _finite_number(view.get("pan_3d_x"), 0.0),
                "pan_3d_y": _finite_number(view.get("pan_3d_y"), 0.0),
            }
        )
    return result


def _analysis_room_payloads(analysis: Any) -> list[dict]:
    if analysis is None or not isinstance(getattr(analysis, "input", None), dict):
        return []
    payload = analysis.input
    kind = getattr(analysis, "kind", "")
    if kind == "room_verification":
        return [payload]
    if kind == "project_verification":
        rooms = payload.get("rooms", [])
        return [room for room in rooms if isinstance(room, dict)] if isinstance(rooms, list) else []
    return []


def derive_layout_from_analysis(analysis: Any) -> dict:
    """Create spatial geometry from real verification inputs without inventing values."""

    layout = empty_layout()
    raw_rooms = _analysis_room_payloads(analysis)
    x_cursor = 0.0
    used_ids: set[str] = set()
    for index, raw in enumerate(raw_rooms):
        name = str(raw.get("name") or f"Room {index + 1}")
        length = _positive(raw.get("length_m"), 4.0)
        width = _positive(raw.get("width_m"), 4.0)
        height = _positive(raw.get("height_m"), 3.0)
        room = {
            "id": _unique_id(None, used_ids, fallback=_room_id(name)),
            "name": name,
            "x_m": x_cursor,
            "y_m": 0.0,
            "length_m": length,
            "width_m": width,
            "height_m": height,
            "elevation_m": 0.0,
            "engineering_ref": name,
            "engineering_baseline": _engineering_baseline(raw),
        }
        pressure = _optional_finite(raw.get("observed_pressure_pa"))
        if pressure is not None:
            room["pressure_pa"] = pressure
        pressure_target = _optional_finite(raw.get("min_pressure_pa"))
        if pressure_target is not None:
            room["pressure_target_pa"] = pressure_target
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


def _room_mapping_ref(room: dict) -> str | None:
    return _optional_string(room.get("engineering_ref"))


def _engineering_lookup(analysis: Any) -> dict[str, dict]:
    rooms = _analysis_room_payloads(analysis)
    _require_unique_sync_names(rooms, source="the active analysis")
    return {
        str(room.get("name") or "").strip().casefold(): room
        for room in rooms
        if str(room.get("name") or "").strip()
    }


def _geometry_snapshot(room: dict, target: dict | None = None) -> dict:
    snapshot = {
        "length_m": _positive(room.get("length_m"), 4.0),
        "width_m": _positive(room.get("width_m"), 4.0),
        "height_m": _positive(room.get("height_m"), 3.0),
    }
    if target is not None and "observed_pressure_pa" in target:
        pressure = _optional_finite(room.get("pressure_pa"))
        if pressure is not None:
            snapshot["pressure_pa"] = pressure
    return snapshot


def _engineering_snapshot(target: dict) -> dict:
    return _engineering_baseline(target)


def _snapshots_equal(left: dict, right: dict) -> bool:
    if set(left) != set(right):
        return False
    return all(
        math.isclose(
            float(left[key]),
            float(right[key]),
            rel_tol=0.0,
            abs_tol=SPATIAL_GEOMETRY_EPSILON_M,
        )
        for key in left
    )


def spatial_sync_status(layout: dict, analysis: Any) -> list[dict]:
    """Describe mapping and edit provenance without changing either source."""

    normalized = normalize_layout(layout)
    if getattr(analysis, "kind", "") not in {"room_verification", "project_verification"}:
        return [
            {
                "room_id": room["id"],
                "engineering_ref": _room_mapping_ref(room),
                "state": "unmapped",
                "reason": "active analysis has no room-geometry synchronization contract",
            }
            for room in normalized["rooms"]
        ]

    try:
        targets = _engineering_lookup(analysis)
    except SpatialSyncError as exc:
        return [
            {
                "room_id": room["id"],
                "engineering_ref": _room_mapping_ref(room),
                "state": "conflicting",
                "reason": str(exc),
            }
            for room in normalized["rooms"]
        ]

    records: list[dict] = []
    for room in normalized["rooms"]:
        ref = _room_mapping_ref(room)
        if ref is None:
            records.append(
                {
                    "room_id": room["id"],
                    "engineering_ref": None,
                    "state": "unmapped",
                    "reason": "room has no engineering mapping",
                }
            )
            continue
        target = targets.get(ref.casefold())
        if target is None:
            records.append(
                {
                    "room_id": room["id"],
                    "engineering_ref": ref,
                    "state": "missing_target",
                    "reason": f"engineering room {ref!r} is not present in the active analysis",
                }
            )
            continue

        geometry = _geometry_snapshot(room, target)
        engineering = _engineering_snapshot(target)
        baseline = room.get("engineering_baseline")
        if _snapshots_equal(geometry, engineering):
            state = "synchronized"
            reason = "geometry matches the mapped engineering input"
        elif not isinstance(baseline, dict) or not baseline:
            state = "conflicting"
            reason = "geometry and engineering differ and no synchronization baseline exists"
        else:
            baseline_normalized = {
                key: float(value)
                for key, value in baseline.items()
                if key in {"length_m", "width_m", "height_m", "pressure_pa"}
                and _optional_finite(value) is not None
            }
            geometry_matches_baseline = _snapshots_equal(geometry, baseline_normalized)
            engineering_matches_baseline = _snapshots_equal(engineering, baseline_normalized)
            if geometry_matches_baseline and not engineering_matches_baseline:
                state = "engineering_data_newer"
                reason = "engineering input changed since the last synchronization"
            elif engineering_matches_baseline and not geometry_matches_baseline:
                state = "geometry_newer"
                reason = "spatial geometry changed since the last synchronization"
            else:
                state = "conflicting"
                reason = "both geometry and engineering changed since the last synchronization"
        records.append(
            {
                "room_id": room["id"],
                "engineering_ref": ref,
                "state": state,
                "reason": reason,
                "geometry": geometry,
                "engineering": engineering,
                "baseline": copy.deepcopy(baseline) if isinstance(baseline, dict) else None,
            }
        )
    return records


def sync_layout_to_analysis(layout: dict, analysis: Any) -> bool:
    """Deliberately copy mapped spatial dimensions into supported engineering inputs."""

    if analysis is None or not isinstance(getattr(analysis, "input", None), dict):
        return False
    kind = getattr(analysis, "kind", "")
    if kind not in {"room_verification", "project_verification"}:
        return False

    normalized = normalize_layout(layout)
    rooms = normalized["rooms"]
    if not rooms:
        return False

    changed = False
    if kind == "room_verification":
        source = rooms[0]
        target = analysis.input
        for key in ("name", "length_m", "width_m", "height_m"):
            value = source[key]
            if target.get(key) != value:
                target[key] = value
                changed = True
        if "observed_pressure_pa" in target and "pressure_pa" in source:
            if target.get("observed_pressure_pa") != source["pressure_pa"]:
                target["observed_pressure_pa"] = source["pressure_pa"]
                changed = True
        source["engineering_ref"] = str(target.get("name") or source["name"])
        if changed:
            source["engineering_baseline"] = _engineering_baseline(target)
        if isinstance(layout, dict):
            layout.clear()
            layout.update(normalized)
        return changed

    raw_rooms = analysis.input.get("rooms")
    if not isinstance(raw_rooms, list):
        return False
    _require_unique_sync_names(rooms, source="the spatial layout")
    targets = _engineering_lookup(analysis)
    mapped_refs: set[str] = set()
    for source in rooms:
        ref = _room_mapping_ref(source) or source["name"]
        ref_key = ref.casefold()
        if ref_key in mapped_refs:
            raise SpatialSyncError(
                f"Cannot synchronize spatial geometry because multiple rooms map to {ref!r}."
            )
        target = targets.get(ref_key)
        if target is None:
            continue
        mapped_refs.add(ref_key)
        source["engineering_ref"] = str(target.get("name") or ref)
        target_changed = False
        for key in ("length_m", "width_m", "height_m"):
            if target.get(key) != source[key]:
                target[key] = source[key]
                changed = True
                target_changed = True
        if "observed_pressure_pa" in target and "pressure_pa" in source:
            if target.get("observed_pressure_pa") != source["pressure_pa"]:
                target["observed_pressure_pa"] = source["pressure_pa"]
                changed = True
                target_changed = True
        if target_changed:
            source["engineering_baseline"] = _engineering_baseline(target)
    if isinstance(layout, dict):
        layout.clear()
        layout.update(normalized)
    return changed


def sync_analysis_to_layout(layout: dict, analysis: Any) -> bool:
    """Deliberately accept mapped engineering dimensions into the spatial model."""

    if analysis is None or getattr(analysis, "kind", "") not in {
        "room_verification",
        "project_verification",
    }:
        return False
    normalized = normalize_layout(layout)
    rooms = normalized["rooms"]
    if not rooms:
        return False
    targets = _engineering_lookup(analysis)
    changed = False

    for index, room in enumerate(rooms):
        if getattr(analysis, "kind", "") == "room_verification" and index == 0:
            target = analysis.input
            ref = str(target.get("name") or room["name"])
        else:
            ref = _room_mapping_ref(room) or ""
            target = targets.get(ref.casefold()) if ref else None
        if not isinstance(target, dict):
            continue
        room["engineering_ref"] = str(target.get("name") or ref)
        for key in ("length_m", "width_m", "height_m"):
            value = _positive(target.get(key), room[key])
            if room[key] != value:
                room[key] = value
                changed = True
        if "observed_pressure_pa" in target:
            pressure = _optional_finite(target.get("observed_pressure_pa"))
            if pressure is not None and room.get("pressure_pa") != pressure:
                room["pressure_pa"] = pressure
                changed = True
        target_pressure = _optional_finite(target.get("min_pressure_pa"))
        if target_pressure is not None and room.get("pressure_target_pa") != target_pressure:
            room["pressure_target_pa"] = target_pressure
            changed = True
        room["engineering_baseline"] = _engineering_baseline(target)

    if isinstance(layout, dict):
        before = normalize_layout(layout)
        layout.clear()
        layout.update(normalized)
        return changed or before != normalized
    return changed


def pressure_relationships(layout: dict, analysis: Any) -> list[dict]:
    """Resolve pressure-cascade intent against configured observed pressures.

    This never synthesizes a pressure result. A relationship is unresolved unless
    both mapped engineering rooms provide finite observed-pressure values.
    """

    if getattr(analysis, "kind", "") != "project_verification":
        return []
    payload = getattr(analysis, "input", None)
    if not isinstance(payload, dict):
        return []
    requirements = payload.get("pressure_cascade", [])
    if not isinstance(requirements, list):
        return []

    normalized = normalize_layout(layout)
    room_by_ref = {
        ref.casefold(): room
        for room in normalized["rooms"]
        if (ref := _room_mapping_ref(room)) is not None
    }
    try:
        engineering = _engineering_lookup(analysis)
    except SpatialSyncError:
        engineering = {}

    records: list[dict] = []
    for index, requirement in enumerate(requirements):
        if not isinstance(requirement, dict):
            continue
        high_name = str(requirement.get("higher_pressure_room") or "").strip()
        low_name = str(requirement.get("lower_pressure_room") or "").strip()
        minimum = _optional_finite(requirement.get("min_delta_pa"))
        high_room = room_by_ref.get(high_name.casefold())
        low_room = room_by_ref.get(low_name.casefold())
        high_engineering = engineering.get(high_name.casefold())
        low_engineering = engineering.get(low_name.casefold())
        high_pressure = (
            _optional_finite(high_engineering.get("observed_pressure_pa"))
            if isinstance(high_engineering, dict)
            else None
        )
        low_pressure = (
            _optional_finite(low_engineering.get("observed_pressure_pa"))
            if isinstance(low_engineering, dict)
            else None
        )
        delta = (
            high_pressure - low_pressure
            if high_pressure is not None and low_pressure is not None
            else None
        )
        if high_room is None or low_room is None or delta is None or minimum is None:
            state = "unavailable"
        else:
            state = "pass" if delta + SPATIAL_GEOMETRY_EPSILON_M >= minimum else "fail"
        records.append(
            {
                "index": index,
                "higher_pressure_room": high_name,
                "lower_pressure_room": low_name,
                "higher_room_id": high_room["id"] if high_room else None,
                "lower_room_id": low_room["id"] if low_room else None,
                "higher_pressure_pa": high_pressure,
                "lower_pressure_pa": low_pressure,
                "delta_pa": delta,
                "min_delta_pa": minimum,
                "state": state,
            }
        )
    return records


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


def _spatial_validation_key(layout: dict, analysis: Any = None) -> tuple:
    """Return validation-relevant state, deliberately excluding camera/view data."""

    rooms = layout.get("rooms", []) if isinstance(layout, dict) else []
    devices = layout.get("devices", []) if isinstance(layout, dict) else []
    analysis_key: tuple = ()
    if getattr(analysis, "kind", "") in {"room_verification", "project_verification"}:
        analysis_key = tuple(
            (
                room.get("name"),
                room.get("length_m"),
                room.get("width_m"),
                room.get("height_m"),
                room.get("observed_pressure_pa"),
                room.get("min_pressure_pa"),
            )
            for room in _analysis_room_payloads(analysis)
        )
        payload = getattr(analysis, "input", {})
        cascades = payload.get("pressure_cascade", []) if isinstance(payload, dict) else []
        analysis_key += tuple(
            (
                item.get("higher_pressure_room"),
                item.get("lower_pressure_room"),
                item.get("min_delta_pa"),
            )
            for item in cascades
            if isinstance(item, dict)
        )
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
                room.get("elevation_m"),
                room.get("engineering_ref"),
                room.get("pressure_pa"),
                room.get("pressure_target_pa"),
                repr(room.get("engineering_baseline")),
            )
            for room in rooms
            if isinstance(room, dict)
        ),
        tuple(
            (
                device.get("id"),
                device.get("name"),
                device.get("room_id"),
                device.get("x_m"),
                device.get("y_m"),
                device.get("z_m"),
                device.get("engineering_ref"),
            )
            for device in devices
            if isinstance(device, dict)
        ),
        analysis_key,
    )


def validate_layout(value: Any, analysis: Any = None) -> list[dict]:
    """Return deterministic advisory spatial warnings without mutating source data."""

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
            room["x_m"] - SPATIAL_GEOMETRY_EPSILON_M
            <= x
            <= room["x_m"] + room["length_m"] + SPATIAL_GEOMETRY_EPSILON_M
            and room["y_m"] - SPATIAL_GEOMETRY_EPSILON_M
            <= y
            <= room["y_m"] + room["width_m"] + SPATIAL_GEOMETRY_EPSILON_M
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
        if (
            z < -SPATIAL_GEOMETRY_EPSILON_M
            or z > room["height_m"] + SPATIAL_GEOMETRY_EPSILON_M
        ):
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

    if getattr(analysis, "kind", "") in {"room_verification", "project_verification"}:
        for record in spatial_sync_status(layout, analysis):
            if record["state"] == "synchronized":
                continue
            issues.append(
                {
                    "code": f"engineering_mapping_{record['state']}",
                    "severity": "warning",
                    "item_ids": [record["room_id"]],
                    "message": (
                        f"Room mapping is {record['state'].replace('_', ' ')}: "
                        f"{record['reason']}."
                    ),
                }
            )

        for relationship in pressure_relationships(layout, analysis):
            if relationship["state"] == "pass":
                continue
            high_id = relationship.get("higher_room_id")
            low_id = relationship.get("lower_room_id")
            item_ids = [item_id for item_id in (high_id, low_id) if item_id]
            if relationship["state"] == "fail":
                message = (
                    f"Pressure cascade {relationship['higher_pressure_room']} → "
                    f"{relationship['lower_pressure_room']} is "
                    f"{relationship['delta_pa']:g} Pa; "
                    f"minimum is {relationship['min_delta_pa']:g} Pa."
                )
                code = "pressure_cascade_conflict"
            else:
                message = (
                    f"Pressure cascade {relationship['higher_pressure_room']} → "
                    f"{relationship['lower_pressure_room']} is unresolved because mapped "
                    "observed pressure data is unavailable."
                )
                code = "pressure_cascade_unavailable"
            issues.append(
                {
                    "code": code,
                    "severity": "warning",
                    "item_ids": item_ids,
                    "message": message,
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
        self._show_grid = tk.BooleanVar(value=True)
        self._coord_var = tk.StringVar(value="x 0.00 m   y 0.00 m")
        self._selection_var = tk.StringVar(value="No selection")
        self._validation_var = tk.StringVar(value="Spatial checks: PASS")
        self._validation_issues: list[dict] = []
        self._last_validation_key: tuple | None = None
        self._property_vars: dict[str, tk.StringVar] = {}
        self._history_can_undo = False
        self._history_can_redo = False
        self._drag_history_before: tuple[dict, tuple[str, str] | None] | None = None

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
        ttk.Checkbutton(toolbar, text="Grid", variable=self._show_grid, command=self.redraw).pack(
            side="left", padx=6
        )
        ttk.Button(toolbar, text="Validate", command=self.report_validation).pack(side="left", padx=2)
        ttk.Label(toolbar, textvariable=self._validation_var).pack(side="left", padx=(8, 2))
        ttk.Button(
            toolbar,
            text="Sync dimensions to active analysis",
            command=self._on_sync_requested,
        ).pack(side="right", padx=2)

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=6, pady=(3, 6))

        two_d = ttk.Frame(body)
        body.add(two_d, weight=4)
        ttk.Label(two_d, text="2D Layout", font=("TkDefaultFont", 10, "bold")).pack(
            anchor="w", padx=4, pady=(2, 4)
        )
        self.canvas_2d = tk.Canvas(two_d, background="#f7f9fb", highlightthickness=1)
        self.canvas_2d.pack(fill="both", expand=True)
        ttk.Label(two_d, textvariable=self._coord_var, anchor="w").pack(fill="x", padx=4, pady=2)

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
            ("length_m", "Length (m)"),
            ("width_m", "Width (m)"),
            ("height_m", "Height (m)"),
            ("pressure_pa", "Pressure (Pa)"),
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
        ttk.Button(inspector, text="Apply", command=self.apply_properties).grid(
            row=button_row, column=3, sticky="e", pady=(8, 0)
        )
        inspector.columnconfigure(1, weight=1)
        inspector.columnconfigure(3, weight=1)

        self.canvas_2d.bind("<Configure>", lambda event: self.redraw())
        self.canvas_3d.bind("<Configure>", lambda event: self._draw_3d())
        self.canvas_2d.bind("<Motion>", self._on_motion)
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
        self.canvas_3d.bind("<Button-2>", self._on_pan_3d_down)
        self.canvas_3d.bind("<B2-Motion>", self._on_pan_3d_drag)
        self.canvas_3d.bind("<Button-3>", self._on_pan_3d_down)
        self.canvas_3d.bind("<B3-Motion>", self._on_pan_3d_drag)
        for canvas in (self.canvas_2d, self.canvas_3d):
            canvas.bind("<Control-z>", self._on_undo_shortcut)
            canvas.bind("<Control-y>", self._on_redo_shortcut)
            canvas.bind("<Control-Shift-Z>", self._on_redo_shortcut)
            canvas.bind("<Delete>", lambda event: self.delete_selected())

    def refresh(self) -> None:
        project = self._project_getter()
        analysis = self._analysis_getter()
        self.layout = ensure_project_layout(project, analysis)
        if self.selected and not self._selected_object():
            self.selected = None
        self._load_property_panel()
        self._update_history_controls()
        self.redraw()

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
        validation_key = _spatial_validation_key(self.layout)
        if force or validation_key != self._last_validation_key:
            self._validation_issues = validate_layout(self.layout)
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
            for var in self._property_vars.values():
                var.set("")
            return
        prefix = "Room" if self.selected and self.selected.kind == "room" else item.get("type", "Device").title()
        self._selection_var.set(f"{prefix}: {item.get('name', '')}")
        for key, var in self._property_vars.items():
            value = item.get(key, "")
            var.set("" if value is None else str(value))

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
            pressure = self._property_vars["pressure_pa"].get().strip()
            if pressure:
                item["pressure_pa"] = _finite_number(pressure, item.get("pressure_pa", 0.0))
            elif "pressure_pa" in item:
                item.pop("pressure_pa", None)
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
            "height_m": 3.0,
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
        else:
            x = y = z = 0.0
            room_id = None
        device = {
            "id": f"device-{uuid.uuid4().hex[:8]}",
            "type": device_type,
            "name": device_type.upper(),
            "room_id": room_id,
            "x_m": x,
            "y_m": y,
            "z_m": z,
        }
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
        return 55.0 * self.layout["view"]["zoom_2d"]

    def _world_to_canvas(self, x: float, y: float) -> tuple[float, float]:
        scale = self._scale_2d()
        return (
            self.canvas_2d.winfo_width() / 2 + self.layout["view"]["pan_x"] + x * scale,
            self.canvas_2d.winfo_height() / 2 + self.layout["view"]["pan_y"] + y * scale,
        )

    def _canvas_to_world(self, x: float, y: float) -> tuple[float, float]:
        scale = self._scale_2d()
        return (
            (x - self.canvas_2d.winfo_width() / 2 - self.layout["view"]["pan_x"]) / scale,
            (y - self.canvas_2d.winfo_height() / 2 - self.layout["view"]["pan_y"]) / scale,
        )

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
        self.layout["view"]["zoom_3d"] = 1.0
        self._persist("Fit spatial views")

    def redraw(self) -> None:
        self._refresh_validation()
        self._draw_2d()
        self._draw_3d()

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

        pressures = [room.get("pressure_pa") for room in self.layout["rooms"] if room.get("pressure_pa") is not None]
        pmin = min(pressures) if pressures else None
        pmax = max(pressures) if pressures else None
        warning_ids = self._warning_item_ids()

        for room in self.layout["rooms"]:
            x0, y0 = self._world_to_canvas(room["x_m"], room["y_m"])
            x1, y1 = self._world_to_canvas(room["x_m"] + room["length_m"], room["y_m"] + room["width_m"])
            selected = self.selected == _Hit("room", room["id"])
            outline = (
                "#1d4ed8"
                if selected
                else ("#b45309" if room["id"] in warning_ids else "#34495e")
            )
            fill = _pressure_fill(room.get("pressure_pa"), pmin, pmax)
            canvas.create_rectangle(
                x0, y0, x1, y1,
                fill=fill, outline=outline, width=3 if selected else 2,
                tags=(f"room:{room['id']}", "room"),
            )
            pressure_text = "" if room.get("pressure_pa") is None else f"\n{room['pressure_pa']:g} Pa"
            canvas.create_text(
                (x0 + x1) / 2,
                (y0 + y1) / 2,
                text=f"{room['name']}\n{room['length_m']:g} × {room['width_m']:g} m{pressure_text}",
                justify="center",
                tags=(f"room:{room['id']}", "room"),
            )

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

        symbols = {
            "door": "D",
            "supply": "S",
            "return": "R",
            "exhaust": "E",
            "ffu": "F",
            "equipment": "Q",
            "sensor": "●",
        }
        for device in self.layout["devices"]:
            x, y = self._world_to_canvas(device["x_m"], device["y_m"])
            selected = self.selected == _Hit("device", device["id"])
            radius = 9 if selected else 7
            device_outline = (
                "#c0392b"
                if selected
                else ("#b45309" if device["id"] in warning_ids else "#2c3e50")
            )
            canvas.create_oval(
                x - radius, y - radius, x + radius, y + radius,
                fill="#ffffff", outline=device_outline,
                width=3 if selected else 2,
                tags=(f"device:{device['id']}", "device"),
            )
            canvas.create_text(
                x, y, text=symbols.get(device["type"], "?"),
                tags=(f"device:{device['id']}", "device"),
            )

        if not self.layout["rooms"] and not self.layout["devices"]:
            canvas.create_text(
                w / 2,
                h / 2,
                text="No spatial layout yet\nUse + Room or open a verification project with room geometry.",
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
        pressures = [room.get("pressure_pa") for room in self.layout["rooms"] if room.get("pressure_pa") is not None]
        pmin = min(pressures) if pressures else None
        pmax = max(pressures) if pressures else None
        warning_ids = self._warning_item_ids()

        # Draw farther rooms first to improve visual depth.
        az = math.radians(self.layout["view"]["azimuth_deg"])
        ordered = sorted(
            self.layout["rooms"],
            key=lambda room: (room["x_m"] - cx) * math.sin(az) + (room["y_m"] - cy) * math.cos(az),
        )
        for room in ordered:
            x0 = room["x_m"] - cx
            y0 = room["y_m"] - cy
            x1 = x0 + room["length_m"]
            y1 = y0 + room["width_m"]
            z = room["height_m"]
            base = [
                self._project_3d(x0, y0, 0),
                self._project_3d(x1, y0, 0),
                self._project_3d(x1, y1, 0),
                self._project_3d(x0, y1, 0),
            ]
            top = [
                self._project_3d(x0, y0, z),
                self._project_3d(x1, y0, z),
                self._project_3d(x1, y1, z),
                self._project_3d(x0, y1, z),
            ]
            fill = _pressure_fill(room.get("pressure_pa"), pmin, pmax)
            selected = self.selected == _Hit("room", room["id"])
            outline = (
                "#7dd3fc"
                if selected
                else ("#fb7185" if room["id"] in warning_ids else "#c8d5e3")
            )
            tag = f"room:{room['id']}"
            canvas.create_polygon(*sum(top, ()), fill=fill, outline=outline, width=2, tags=(tag, "room3d"))
            canvas.create_polygon(
                *sum((base[1], base[2], top[2], top[1]), ()),
                fill="#6c7f92", outline=outline, tags=(tag, "room3d")
            )
            canvas.create_polygon(
                *sum((base[2], base[3], top[3], top[2]), ()),
                fill="#53687c", outline=outline, tags=(tag, "room3d")
            )
            canvas.create_text(
                *self._project_3d((x0 + x1) / 2, (y0 + y1) / 2, z + 0.2),
                text=room["name"],
                fill="#f0f6fc",
                tags=(tag, "room3d"),
            )

        for device in self.layout["devices"]:
            x, y = self._project_3d(device["x_m"] - cx, device["y_m"] - cy, device["z_m"])
            tag = f"device:{device['id']}"
            selected = self.selected == _Hit("device", device["id"])
            radius = 5 if selected else 4
            device_outline = (
                "#ffffff"
                if selected
                else ("#fb7185" if device["id"] in warning_ids else "#d6a20f")
            )
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
        current = self.canvas_2d.find_withtag("current")
        hit = None
        if current:
            hit = self._parse_hit(self.canvas_2d.gettags(current[0]))
        self.selected = hit
        self._drag_anchor = self._canvas_to_world(event.x, event.y) if hit else None
        self._drag_history_before = (
            (self._history_layout(), self._selection_state()) if hit is not None else None
        )
        self._load_property_panel()
        self.redraw()

    def _on_left_drag(self, event: tk.Event) -> None:
        item = self._selected_object()
        if item is None or self._drag_anchor is None:
            return
        world = self._canvas_to_world(event.x, event.y)
        dx = world[0] - self._drag_anchor[0]
        dy = world[1] - self._drag_anchor[1]
        grid = self.layout["grid_m"]
        item["x_m"] = round((item["x_m"] + dx) / grid) * grid
        item["y_m"] = round((item["y_m"] + dy) / grid) * grid
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
            self._persist(
                "Spatial item moved",
                history_before=history_before,
                selection_before=selection_before,
            )
        self._drag_anchor = None
        self._drag_history_before = None

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
