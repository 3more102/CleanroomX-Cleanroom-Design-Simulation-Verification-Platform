from __future__ import annotations

import copy
import math
from typing import Any


SYNC_EPSILON = 1e-9
BASELINE_KEY = "engineering_baseline"


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def engineering_rooms(analysis: Any) -> list[dict]:
    payload = getattr(analysis, "input", None)
    if not isinstance(payload, dict):
        return []
    kind = getattr(analysis, "kind", "")
    if kind == "room_verification":
        return [payload]
    if kind == "project_verification":
        rooms = payload.get("rooms", [])
        if isinstance(rooms, list):
            return [room for room in rooms if isinstance(room, dict)]
    return []


def engineering_snapshot(room: dict) -> dict[str, float]:
    snapshot: dict[str, float] = {}
    for key in ("length_m", "width_m", "height_m"):
        value = _finite(room.get(key))
        if value is not None:
            snapshot[key] = value
    pressure = _finite(room.get("observed_pressure_pa"))
    if pressure is not None:
        snapshot["pressure_pa"] = pressure
    return snapshot


def spatial_snapshot(room: dict, engineering_room: dict) -> dict[str, float]:
    snapshot: dict[str, float] = {}
    for key in ("length_m", "width_m", "height_m"):
        value = _finite(room.get(key))
        if value is not None:
            snapshot[key] = value
    if "observed_pressure_pa" in engineering_room:
        pressure = _finite(room.get("pressure_pa"))
        if pressure is not None:
            snapshot["pressure_pa"] = pressure
    return snapshot


def snapshots_equal(left: dict, right: dict) -> bool:
    if set(left) != set(right):
        return False
    return all(
        math.isclose(
            float(left[key]),
            float(right[key]),
            rel_tol=0.0,
            abs_tol=SYNC_EPSILON,
        )
        for key in left
    )


def baseline_from_engineering(room: dict) -> dict[str, float]:
    return engineering_snapshot(room)


def _name_index(rooms: list[dict]) -> tuple[dict[str, dict], set[str]]:
    index: dict[str, dict] = {}
    duplicates: set[str] = set()
    for room in rooms:
        name = str(room.get("name") or "").strip()
        if not name:
            continue
        key = name.casefold()
        if key in index:
            duplicates.add(key)
        else:
            index[key] = room
    return index, duplicates


def _mapping_target(
    room: dict,
    analysis: Any,
    *,
    room_index: int,
    index: dict[str, dict],
    duplicate_keys: set[str],
) -> tuple[dict | None, str | None, str | None]:
    kind = getattr(analysis, "kind", "")
    if kind == "room_verification":
        rooms = engineering_rooms(analysis)
        if room_index != 0 or not rooms:
            return None, None, "single-room verification maps only the first spatial room"
        target = rooms[0]
        return target, str(target.get("name") or room.get("name") or "").strip() or None, None

    if kind != "project_verification":
        return None, None, "active analysis does not support room geometry synchronization"

    ref = str(room.get("analysis_room_name") or "").strip()
    if not ref:
        return None, None, "room has no analysis-room mapping"
    key = ref.casefold()
    if key in duplicate_keys:
        return None, ref, f"analysis room name {ref!r} is duplicated"
    target = index.get(key)
    if target is None:
        return None, ref, f"linked analysis room {ref!r} does not exist"
    return target, ref, None


def spatial_sync_status(layout: dict, analysis: Any) -> list[dict]:
    """Return deterministic room mapping/freshness state without mutating either side."""

    rooms = layout.get("rooms", []) if isinstance(layout, dict) else []
    engineering = engineering_rooms(analysis)
    index, duplicate_keys = _name_index(engineering)
    records: list[dict] = []

    for room_index, room in enumerate(rooms):
        if not isinstance(room, dict):
            continue
        target, ref, mapping_error = _mapping_target(
            room,
            analysis,
            room_index=room_index,
            index=index,
            duplicate_keys=duplicate_keys,
        )
        if target is None:
            state = "unmapped" if ref is None else "missing_target"
            if mapping_error and "duplicated" in mapping_error:
                state = "conflicting"
            records.append(
                {
                    "room_id": room.get("id"),
                    "analysis_room_name": ref,
                    "state": state,
                    "reason": mapping_error or "room is not mapped",
                }
            )
            continue

        geometry = spatial_snapshot(room, target)
        engineering_state = engineering_snapshot(target)
        baseline = room.get(BASELINE_KEY)
        if snapshots_equal(geometry, engineering_state):
            state = "synchronized"
            reason = "spatial geometry matches the mapped engineering input"
        elif not isinstance(baseline, dict) or not baseline:
            state = "conflicting"
            reason = (
                "geometry and engineering differ but no prior synchronization baseline "
                "exists to determine which side is newer"
            )
        else:
            clean_baseline = {
                key: value
                for key, raw in baseline.items()
                if key in {"length_m", "width_m", "height_m", "pressure_pa"}
                and (value := _finite(raw)) is not None
            }
            geometry_matches = snapshots_equal(geometry, clean_baseline)
            engineering_matches = snapshots_equal(engineering_state, clean_baseline)
            if engineering_matches and not geometry_matches:
                state = "geometry_newer"
                reason = "spatial geometry changed since the last synchronization"
            elif geometry_matches and not engineering_matches:
                state = "engineering_data_newer"
                reason = "engineering input changed since the last synchronization"
            else:
                state = "conflicting"
                reason = "both geometry and engineering changed since the last synchronization"

        records.append(
            {
                "room_id": room.get("id"),
                "analysis_room_name": ref,
                "state": state,
                "reason": reason,
                "geometry": geometry,
                "engineering": engineering_state,
                "baseline": copy.deepcopy(baseline) if isinstance(baseline, dict) else None,
            }
        )
    return records


def sync_analysis_to_layout(layout: dict, analysis: Any) -> bool:
    """Explicitly accept mapped engineering dimensions/pressure into spatial geometry."""

    rooms = layout.get("rooms", []) if isinstance(layout, dict) else []
    engineering = engineering_rooms(analysis)
    index, duplicate_keys = _name_index(engineering)
    changed = False

    for room_index, room in enumerate(rooms):
        if not isinstance(room, dict):
            continue
        target, ref, mapping_error = _mapping_target(
            room,
            analysis,
            room_index=room_index,
            index=index,
            duplicate_keys=duplicate_keys,
        )
        if target is None or mapping_error:
            continue

        if getattr(analysis, "kind", "") == "project_verification" and ref:
            room["analysis_room_name"] = ref
        for key in ("length_m", "width_m", "height_m"):
            value = _finite(target.get(key))
            if value is not None and value > 0 and room.get(key) != value:
                room[key] = value
                changed = True
        if "observed_pressure_pa" in target:
            pressure = _finite(target.get("observed_pressure_pa"))
            if pressure is not None and room.get("pressure_pa") != pressure:
                room["pressure_pa"] = pressure
                changed = True
        baseline = baseline_from_engineering(target)
        if room.get(BASELINE_KEY) != baseline:
            room[BASELINE_KEY] = baseline
            changed = True
    return changed


def pressure_relationship_records(layout: dict, analysis: Any) -> list[dict]:
    """Resolve explicit pressure-cascade intent against configured observed pressures."""

    payload = getattr(analysis, "input", None)
    if getattr(analysis, "kind", "") != "project_verification" or not isinstance(payload, dict):
        return []
    requirements = payload.get("pressure_cascade", [])
    if not isinstance(requirements, list):
        return []

    engineering = engineering_rooms(analysis)
    index, duplicate_keys = _name_index(engineering)
    rooms = layout.get("rooms", []) if isinstance(layout, dict) else []
    spatial_by_ref: dict[str, dict] = {}
    for room in rooms:
        if not isinstance(room, dict):
            continue
        for raw_name in (room.get("analysis_room_name"), room.get("name")):
            name = str(raw_name or "").strip()
            if name:
                spatial_by_ref.setdefault(name.casefold(), room)

    records: list[dict] = []
    for position, requirement in enumerate(requirements):
        if not isinstance(requirement, dict):
            continue
        high_name = str(requirement.get("higher_pressure_room") or "").strip()
        low_name = str(requirement.get("lower_pressure_room") or "").strip()
        high_key = high_name.casefold()
        low_key = low_name.casefold()
        high_target = None if high_key in duplicate_keys else index.get(high_key)
        low_target = None if low_key in duplicate_keys else index.get(low_key)
        high_pressure = (
            _finite(high_target.get("observed_pressure_pa"))
            if isinstance(high_target, dict)
            else None
        )
        low_pressure = (
            _finite(low_target.get("observed_pressure_pa"))
            if isinstance(low_target, dict)
            else None
        )
        minimum = _finite(requirement.get("min_delta_pa"))
        delta = (
            high_pressure - low_pressure
            if high_pressure is not None and low_pressure is not None
            else None
        )
        high_room = spatial_by_ref.get(high_key)
        low_room = spatial_by_ref.get(low_key)
        if (
            high_room is None
            or low_room is None
            or minimum is None
            or delta is None
        ):
            state = "unavailable"
        else:
            state = "pass" if delta + SYNC_EPSILON >= minimum else "fail"
        records.append(
            {
                "index": position,
                "higher_pressure_room": high_name,
                "lower_pressure_room": low_name,
                "higher_room_id": high_room.get("id") if high_room else None,
                "lower_room_id": low_room.get("id") if low_room else None,
                "higher_pressure_pa": high_pressure,
                "lower_pressure_pa": low_pressure,
                "delta_pa": delta,
                "min_delta_pa": minimum,
                "state": state,
            }
        )
    return records
