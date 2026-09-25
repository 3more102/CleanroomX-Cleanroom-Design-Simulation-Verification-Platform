from __future__ import annotations

import math
from typing import Any


DIMENSION_KEYS = ("length_m", "width_m", "height_m")
SYNC_STATES = (
    "synchronized",
    "geometry_newer",
    "engineering_data_newer",
    "conflicting",
    "unmapped",
)


class SpatialMappingError(ValueError):
    """Raised when a requested engineering/spatial synchronization is ambiguous."""


def _analysis_id(analysis: Any) -> str:
    value = getattr(analysis, "id", "")
    return str(value).strip() if value is not None else ""


def _analysis_rooms(analysis: Any) -> list[dict]:
    payload = getattr(analysis, "input", None)
    if not isinstance(payload, dict):
        return []
    kind = getattr(analysis, "kind", "")
    if kind == "room_verification":
        return [payload]
    if kind == "project_verification":
        rooms = payload.get("rooms", [])
        return [room for room in rooms if isinstance(room, dict)] if isinstance(rooms, list) else []
    return []


def _room_name(room: dict) -> str:
    return str(room.get("name") or "").strip()


def _room_ref(room: dict) -> str:
    return str(room.get("engineering_ref") or room.get("name") or "").strip()


def _target_index(analysis: Any) -> dict[str, list[dict]]:
    index: dict[str, list[dict]] = {}
    for target in _analysis_rooms(analysis):
        name = _room_name(target)
        if name:
            index.setdefault(name, []).append(target)
    return index


def _dimensions(room: dict) -> tuple[float, float, float] | None:
    values: list[float] = []
    for key in DIMENSION_KEYS:
        value = room.get(key)
        if isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(number) or number <= 0:
            return None
        values.append(number)
    return tuple(values)  # type: ignore[return-value]


def _same_dimensions(
    left: tuple[float, float, float] | None,
    right: tuple[float, float, float] | None,
    *,
    tolerance: float = 1e-9,
) -> bool:
    if left is None or right is None:
        return False
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))


def _snapshot_dimensions(room: dict, *, analysis_id: str, room_ref: str):
    snapshot = room.get("engineering_snapshot")
    if not isinstance(snapshot, dict):
        return None
    if str(snapshot.get("analysis_id") or "") != analysis_id:
        return None
    if str(snapshot.get("room_ref") or "") != room_ref:
        return None
    return _dimensions(snapshot)


def _stamp_snapshot(room: dict, analysis: Any, target: dict, room_ref: str) -> None:
    snapshot = {
        "analysis_id": _analysis_id(analysis),
        "room_ref": room_ref,
    }
    for key in DIMENSION_KEYS:
        snapshot[key] = float(target[key])
    if target.get("observed_pressure_pa") is not None:
        snapshot["observed_pressure_pa"] = float(target["observed_pressure_pa"])
    room["engineering_snapshot"] = snapshot


def engineering_sync_status(layout: dict, analysis: Any) -> dict[str, dict]:
    """Return deterministic per-room mapping and synchronization state.

    A persisted engineering snapshot makes directional changes distinguishable:
    geometry-only edits are geometry_newer; engineering-only edits are
    engineering_data_newer; divergent edits on both sides are conflicting.
    """

    result: dict[str, dict] = {}
    rooms = layout.get("rooms", []) if isinstance(layout, dict) else []
    analysis_id = _analysis_id(analysis)
    targets = _target_index(analysis)
    supported = bool(_analysis_rooms(analysis))

    for room in rooms if isinstance(rooms, list) else []:
        if not isinstance(room, dict):
            continue
        room_id = str(room.get("id") or "")
        room_ref = _room_ref(room)
        expected_analysis_id = str(room.get("engineering_analysis_id") or "").strip()
        base = {
            "room_id": room_id,
            "engineering_ref": room_ref or None,
            "analysis_id": analysis_id or None,
            "state": "unmapped",
            "message": "No compatible active engineering room is mapped.",
        }
        if not supported or not room_ref:
            result[room_id] = base
            continue
        if expected_analysis_id and analysis_id and expected_analysis_id != analysis_id:
            base["message"] = (
                f"Mapped to analysis {expected_analysis_id!r}, not active analysis {analysis_id!r}."
            )
            result[room_id] = base
            continue

        matches = targets.get(room_ref, [])
        if not matches:
            base["message"] = f"Engineering room {room_ref!r} is missing from the active analysis."
            result[room_id] = base
            continue
        if len(matches) > 1:
            base["state"] = "conflicting"
            base["message"] = f"Engineering room reference {room_ref!r} is ambiguous."
            result[room_id] = base
            continue

        target = matches[0]
        geometry_dims = _dimensions(room)
        engineering_dims = _dimensions(target)
        if geometry_dims is None or engineering_dims is None:
            base["state"] = "conflicting"
            base["message"] = "Geometry or engineering dimensions are invalid."
            result[room_id] = base
            continue

        if _same_dimensions(geometry_dims, engineering_dims):
            base["state"] = "synchronized"
            base["message"] = "Geometry and engineering dimensions match."
            result[room_id] = base
            continue

        snapshot_dims = _snapshot_dimensions(
            room, analysis_id=analysis_id, room_ref=room_ref
        )
        if snapshot_dims is None:
            base["state"] = "conflicting"
            base["message"] = "Geometry and engineering dimensions differ with no common sync baseline."
            result[room_id] = base
            continue

        geometry_changed = not _same_dimensions(geometry_dims, snapshot_dims)
        engineering_changed = not _same_dimensions(engineering_dims, snapshot_dims)
        if geometry_changed and not engineering_changed:
            base["state"] = "geometry_newer"
            base["message"] = "Spatial geometry changed since the last engineering synchronization."
        elif engineering_changed and not geometry_changed:
            base["state"] = "engineering_data_newer"
            base["message"] = "Engineering dimensions changed since the last spatial synchronization."
        else:
            base["state"] = "conflicting"
            base["message"] = "Geometry and engineering dimensions changed independently and conflict."
        result[room_id] = base
    return result


def _require_unique_room_refs(layout: dict) -> None:
    seen: set[str] = set()
    duplicates: list[str] = []
    for room in layout.get("rooms", []):
        if not isinstance(room, dict):
            continue
        ref = _room_ref(room)
        if not ref:
            continue
        if ref in seen and ref not in duplicates:
            duplicates.append(ref)
        seen.add(ref)
    if duplicates:
        labels = ", ".join(repr(item) for item in duplicates)
        raise SpatialMappingError(
            f"Cannot synchronize spatial geometry because engineering room reference(s) "
            f"are duplicated: {labels}."
        )


def push_layout_to_analysis(layout: dict, analysis: Any) -> bool:
    """Explicitly push mapped room geometry into a compatible verification analysis."""

    targets = _target_index(analysis)
    if not targets:
        return False
    duplicate_targets = sorted(name for name, rows in targets.items() if len(rows) > 1)
    if duplicate_targets:
        labels = ", ".join(repr(item) for item in duplicate_targets)
        raise SpatialMappingError(
            f"Cannot synchronize because the active analysis contains duplicate room name(s): {labels}."
        )
    _require_unique_room_refs(layout)

    changed = False
    analysis_id = _analysis_id(analysis)
    for room in layout.get("rooms", []):
        if not isinstance(room, dict):
            continue
        ref = _room_ref(room)
        if not ref:
            continue
        expected_analysis_id = str(room.get("engineering_analysis_id") or "").strip()
        if expected_analysis_id and analysis_id and expected_analysis_id != analysis_id:
            continue
        matches = targets.get(ref, [])
        if len(matches) != 1:
            continue
        target = matches[0]
        for key in DIMENSION_KEYS:
            value = float(room[key])
            if target.get(key) != value:
                target[key] = value
                changed = True
        if "observed_pressure_pa" in target and room.get("pressure_pa") is not None:
            pressure = float(room["pressure_pa"])
            if target.get("observed_pressure_pa") != pressure:
                target["observed_pressure_pa"] = pressure
                changed = True
        room["engineering_ref"] = ref
        if analysis_id:
            room["engineering_analysis_id"] = analysis_id
        _stamp_snapshot(room, analysis, target, ref)
    return changed


def pull_analysis_to_layout(layout: dict, analysis: Any) -> bool:
    """Explicitly pull mapped engineering dimensions into the authoritative layout."""

    targets = _target_index(analysis)
    if not targets:
        return False
    duplicate_targets = sorted(name for name, rows in targets.items() if len(rows) > 1)
    if duplicate_targets:
        labels = ", ".join(repr(item) for item in duplicate_targets)
        raise SpatialMappingError(
            f"Cannot synchronize because the active analysis contains duplicate room name(s): {labels}."
        )
    _require_unique_room_refs(layout)

    changed = False
    analysis_id = _analysis_id(analysis)
    for room in layout.get("rooms", []):
        if not isinstance(room, dict):
            continue
        ref = _room_ref(room)
        matches = targets.get(ref, []) if ref else []
        if len(matches) != 1:
            continue
        target = matches[0]
        for key in DIMENSION_KEYS:
            value = float(target[key])
            if room.get(key) != value:
                room[key] = value
                changed = True
        if target.get("observed_pressure_pa") is not None:
            pressure = float(target["observed_pressure_pa"])
            if room.get("pressure_pa") != pressure:
                room["pressure_pa"] = pressure
                changed = True
        room["engineering_ref"] = ref
        if analysis_id:
            room["engineering_analysis_id"] = analysis_id
        _stamp_snapshot(room, analysis, target, ref)
    return changed


def pressure_relationships(layout: dict, analysis: Any) -> list[dict]:
    """Map pressure-cascade intent onto spatial rooms without inventing values."""

    payload = getattr(analysis, "input", None)
    if getattr(analysis, "kind", "") != "project_verification" or not isinstance(payload, dict):
        return []
    cascade = payload.get("pressure_cascade", [])
    if not isinstance(cascade, list):
        return []

    by_ref: dict[str, list[dict]] = {}
    for room in layout.get("rooms", []):
        if isinstance(room, dict):
            ref = _room_ref(room)
            if ref:
                by_ref.setdefault(ref, []).append(room)

    relationships: list[dict] = []
    for item in cascade:
        if not isinstance(item, dict):
            continue
        higher_ref = str(item.get("higher_pressure_room") or "").strip()
        lower_ref = str(item.get("lower_pressure_room") or "").strip()
        if not higher_ref or not lower_ref:
            continue
        higher_matches = by_ref.get(higher_ref, [])
        lower_matches = by_ref.get(lower_ref, [])
        if len(higher_matches) != 1 or len(lower_matches) != 1:
            continue
        higher = higher_matches[0]
        lower = lower_matches[0]
        minimum = item.get("min_delta_pa")
        try:
            minimum_pa = float(minimum)
        except (TypeError, ValueError):
            minimum_pa = None
        if minimum_pa is not None and not math.isfinite(minimum_pa):
            minimum_pa = None
        higher_pressure = higher.get("pressure_pa")
        lower_pressure = lower.get("pressure_pa")
        actual_delta = None
        try:
            if higher_pressure is not None and lower_pressure is not None:
                actual_delta = float(higher_pressure) - float(lower_pressure)
        except (TypeError, ValueError):
            actual_delta = None
        status = "unavailable"
        if actual_delta is not None and minimum_pa is not None:
            status = "pass" if actual_delta >= minimum_pa else "conflict"
        relationships.append(
            {
                "higher_room_id": higher.get("id"),
                "lower_room_id": lower.get("id"),
                "higher_ref": higher_ref,
                "lower_ref": lower_ref,
                "min_delta_pa": minimum_pa,
                "actual_delta_pa": actual_delta,
                "status": status,
            }
        )
    return relationships
