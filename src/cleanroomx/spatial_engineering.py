from __future__ import annotations

import math
from typing import Any


SUPPORTED_ROOM_ANALYSES = {"room_verification", "project_verification"}
DIMENSION_FIELDS = ("length_m", "width_m", "height_m")
GEOMETRY_TOLERANCE_M = 1e-9


def _kind(analysis: Any) -> str:
    return str(getattr(analysis, "kind", "") or "")


def _input(analysis: Any) -> dict[str, Any] | None:
    value = getattr(analysis, "input", None)
    return value if isinstance(value, dict) else None


def analysis_rooms(analysis: Any) -> list[dict[str, Any]]:
    payload = _input(analysis)
    if payload is None:
        return []
    if _kind(analysis) == "room_verification":
        return [payload]
    if _kind(analysis) == "project_verification":
        rooms = payload.get("rooms", [])
        return [room for room in rooms if isinstance(room, dict)] if isinstance(rooms, list) else []
    return []


def resolve_room_mapping(
    spatial_room: dict[str, Any],
    analysis: Any,
) -> tuple[dict[str, Any] | None, str]:
    if _kind(analysis) not in SUPPORTED_ROOM_ANALYSES:
        return None, "unsupported"
    explicit_name = str(spatial_room.get("analysis_room_name") or "").strip()
    candidate = explicit_name or str(spatial_room.get("name") or "").strip()
    if not candidate:
        return None, "unmapped"
    matches = [
        room
        for room in analysis_rooms(analysis)
        if str(room.get("name") or "").strip().casefold() == candidate.casefold()
    ]
    if len(matches) == 1:
        return matches[0], "mapped"
    if len(matches) > 1:
        return None, "ambiguous"
    return None, "missing_target" if explicit_name else "unmapped"


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def room_pressure_value(
    spatial_room: dict[str, Any],
    analysis: Any,
) -> tuple[float | None, str]:
    target, state = resolve_room_mapping(spatial_room, analysis)
    if target is not None and state == "mapped":
        pressure = _finite(target.get("observed_pressure_pa"))
        if pressure is not None:
            return pressure, "engineering_observed"
    pressure = _finite(spatial_room.get("pressure_pa"))
    if pressure is not None:
        return pressure, "spatial_configured"
    return None, "unavailable"


def engineering_mapping_diagnostics(
    layout: dict[str, Any],
    analysis: Any,
) -> list[dict[str, Any]]:
    rooms = layout.get("rooms", []) if isinstance(layout, dict) else []
    result: list[dict[str, Any]] = []
    for room in rooms if isinstance(rooms, list) else []:
        if not isinstance(room, dict):
            continue
        target, mapping_state = resolve_room_mapping(room, analysis)
        item: dict[str, Any] = {
            "room_id": str(room.get("id") or ""),
            "room_name": str(room.get("name") or ""),
            "mapping_state": mapping_state,
            "state": mapping_state,
            "differences": [],
        }
        if target is None:
            messages = {
                "unsupported": "Active analysis does not expose room geometry.",
                "ambiguous": "Engineering room mapping is ambiguous.",
                "missing_target": "Linked engineering room is missing.",
                "unmapped": "No engineering room mapping is available.",
            }
            item["message"] = messages.get(mapping_state, "Engineering mapping is unresolved.")
            result.append(item)
            continue
        differences: list[dict[str, Any]] = []
        for field in DIMENSION_FIELDS:
            spatial_value = _finite(room.get(field))
            engineering_value = _finite(target.get(field))
            if spatial_value is None or engineering_value is None:
                differences.append(
                    {
                        "field": field,
                        "spatial": room.get(field),
                        "engineering": target.get(field),
                        "reason": "unresolved",
                    }
                )
            elif not math.isclose(
                spatial_value,
                engineering_value,
                rel_tol=0.0,
                abs_tol=GEOMETRY_TOLERANCE_M,
            ):
                differences.append(
                    {
                        "field": field,
                        "spatial": spatial_value,
                        "engineering": engineering_value,
                        "reason": "different",
                    }
                )
        spatial_pressure = _finite(room.get("pressure_pa"))
        engineering_pressure = _finite(target.get("observed_pressure_pa"))
        if spatial_pressure is not None and engineering_pressure is not None:
            if not math.isclose(spatial_pressure, engineering_pressure, rel_tol=0.0, abs_tol=1e-9):
                differences.append(
                    {
                        "field": "pressure_pa",
                        "spatial": spatial_pressure,
                        "engineering": engineering_pressure,
                        "reason": "different",
                    }
                )
        item["state"] = "synchronized" if not differences else "conflicting"
        item["differences"] = differences
        item["engineering_room_name"] = str(target.get("name") or "")
        item["message"] = (
            "Spatial and engineering room data are synchronized."
            if not differences
            else "Spatial and engineering room data differ; synchronize explicitly if intended."
        )
        result.append(item)
    return result


def pressure_relationships(
    layout: dict[str, Any],
    analysis: Any,
) -> list[dict[str, Any]]:
    if _kind(analysis) != "project_verification":
        return []
    payload = _input(analysis)
    if payload is None:
        return []
    cascade = payload.get("pressure_cascade", [])
    if not isinstance(cascade, list):
        return []

    mapped: dict[str, dict[str, Any]] = {}
    rooms = layout.get("rooms", []) if isinstance(layout, dict) else []
    for room in rooms if isinstance(rooms, list) else []:
        if not isinstance(room, dict):
            continue
        target, state = resolve_room_mapping(room, analysis)
        if target is None or state != "mapped":
            continue
        name = str(target.get("name") or "").strip()
        if name:
            mapped.setdefault(name.casefold(), room)

    result: list[dict[str, Any]] = []
    for index, raw in enumerate(cascade):
        if not isinstance(raw, dict):
            continue
        high_name = str(raw.get("higher_pressure_room") or "").strip()
        low_name = str(raw.get("lower_pressure_room") or "").strip()
        high = mapped.get(high_name.casefold())
        low = mapped.get(low_name.casefold())
        minimum = _finite(raw.get("min_delta_pa"))
        record: dict[str, Any] = {
            "index": index,
            "higher_pressure_room": high_name,
            "lower_pressure_room": low_name,
            "higher_room_id": high.get("id") if high else None,
            "lower_room_id": low.get("id") if low else None,
            "min_delta_pa": minimum,
            "actual_delta_pa": None,
            "status": "unavailable",
        }
        if high is not None and low is not None and minimum is not None:
            high_pressure, high_source = room_pressure_value(high, analysis)
            low_pressure, low_source = room_pressure_value(low, analysis)
            record["higher_pressure_pa"] = high_pressure
            record["lower_pressure_pa"] = low_pressure
            record["higher_pressure_source"] = high_source
            record["lower_pressure_source"] = low_source
            if high_pressure is not None and low_pressure is not None:
                delta = high_pressure - low_pressure
                record["actual_delta_pa"] = delta
                record["status"] = "pass" if delta + 1e-9 >= minimum else "fail"
        result.append(record)
    return result
