from __future__ import annotations

import math
from typing import Any


SUPPORTED_ROOM_ANALYSES = {"room_verification", "project_verification"}
DIMENSION_FIELDS = ("length_m", "width_m", "height_m")
GEOMETRY_TOLERANCE_M = 1e-9


def _analysis_id(analysis: Any) -> str:
    return str(getattr(analysis, "id", "") or "").strip()


def _analysis_kind(analysis: Any) -> str:
    return str(getattr(analysis, "kind", "") or "").strip()


def _analysis_input(analysis: Any) -> dict[str, Any] | None:
    payload = getattr(analysis, "input", None)
    return payload if isinstance(payload, dict) else None


def analysis_rooms(analysis: Any) -> list[dict[str, Any]]:
    payload = _analysis_input(analysis)
    if payload is None:
        return []
    kind = _analysis_kind(analysis)
    if kind == "room_verification":
        return [payload]
    if kind == "project_verification":
        rooms = payload.get("rooms", [])
        return [room for room in rooms if isinstance(room, dict)] if isinstance(rooms, list) else []
    return []


def room_reference(analysis: Any, room: dict[str, Any]) -> dict[str, str] | None:
    """Return the stable analysis + engineering-room reference for a mapped room."""
    analysis_id = _analysis_id(analysis)
    name = str(room.get("name") or "").strip()
    if not analysis_id or not name:
        return None
    return {"analysis_id": analysis_id, "room_name": name}


def _candidate_name(spatial_room: dict[str, Any], analysis: Any) -> tuple[str, str]:
    ref = spatial_room.get("engineering_ref")
    if isinstance(ref, dict):
        ref_analysis_id = str(ref.get("analysis_id") or "").strip()
        ref_room_name = str(ref.get("room_name") or "").strip()
        if ref_analysis_id and ref_analysis_id != _analysis_id(analysis):
            return "", "different_analysis"
        if ref_room_name:
            return ref_room_name, "explicit"
    name = str(spatial_room.get("name") or "").strip()
    return name, "name"


def resolve_room_mapping(
    spatial_room: dict[str, Any],
    analysis: Any,
) -> tuple[dict[str, Any] | None, str]:
    """Resolve one spatial room without mutating either model.

    States are deterministic and intentionally conservative:
    mapped, unsupported, different_analysis, unmapped, missing_target, ambiguous.
    """
    if _analysis_kind(analysis) not in SUPPORTED_ROOM_ANALYSES:
        return None, "unsupported"
    rooms = analysis_rooms(analysis)
    candidate, source = _candidate_name(spatial_room, analysis)
    if not candidate:
        return None, "unmapped"

    matches = [
        room
        for room in rooms
        if str(room.get("name") or "").strip().casefold() == candidate.casefold()
    ]
    if len(matches) == 1:
        return matches[0], "mapped"
    if len(matches) > 1:
        return None, "ambiguous"
    if source == "explicit":
        return None, "missing_target"
    return None, "unmapped"


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _dimension_differences(
    spatial_room: dict[str, Any],
    engineering_room: dict[str, Any],
) -> list[dict[str, Any]]:
    differences: list[dict[str, Any]] = []
    for field in DIMENSION_FIELDS:
        spatial_value = _finite(spatial_room.get(field))
        engineering_value = _finite(engineering_room.get(field))
        if spatial_value is None or engineering_value is None:
            differences.append(
                {
                    "field": field,
                    "spatial": spatial_room.get(field),
                    "engineering": engineering_room.get(field),
                    "reason": "unresolved",
                }
            )
            continue
        if not math.isclose(
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
    spatial_pressure = _finite(spatial_room.get("pressure_pa"))
    engineering_pressure = _finite(engineering_room.get("observed_pressure_pa"))
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
    return differences


def engineering_mapping_diagnostics(
    layout: dict[str, Any],
    analysis: Any,
) -> list[dict[str, Any]]:
    """Return deterministic room mapping/synchronization diagnostics."""
    rooms = layout.get("rooms", []) if isinstance(layout, dict) else []
    diagnostics: list[dict[str, Any]] = []
    for room in rooms if isinstance(rooms, list) else []:
        if not isinstance(room, dict):
            continue
        target, resolution = resolve_room_mapping(room, analysis)
        room_id = str(room.get("id") or "")
        room_name = str(room.get("name") or "")
        if target is None:
            messages = {
                "unsupported": "Active analysis does not expose room geometry.",
                "different_analysis": "Room is explicitly mapped to a different analysis.",
                "ambiguous": "Engineering room name is ambiguous in the active analysis.",
                "missing_target": "Mapped engineering room is missing from the active analysis.",
                "unmapped": "No engineering room mapping is available.",
            }
            diagnostics.append(
                {
                    "room_id": room_id,
                    "room_name": room_name,
                    "state": resolution,
                    "message": messages.get(resolution, "Engineering mapping is unresolved."),
                    "differences": [],
                }
            )
            continue

        differences = _dimension_differences(room, target)
        state = "synchronized" if not differences else "conflicting"
        diagnostics.append(
            {
                "room_id": room_id,
                "room_name": room_name,
                "state": state,
                "message": (
                    "Spatial and engineering room data are synchronized."
                    if state == "synchronized"
                    else "Spatial and engineering room data differ; synchronize explicitly if intended."
                ),
                "engineering_room_name": str(target.get("name") or ""),
                "differences": differences,
            }
        )
    return diagnostics


def room_pressure_value(
    spatial_room: dict[str, Any],
    analysis: Any,
) -> tuple[float | None, str]:
    """Return pressure without inventing a solver value.

    Mapped engineering observed pressure takes precedence because it is the authoritative
    verification input. Spatial configured pressure is used only when no mapped observed
    value is available.
    """
    target, state = resolve_room_mapping(spatial_room, analysis)
    if target is not None and state == "mapped":
        pressure = _finite(target.get("observed_pressure_pa"))
        if pressure is not None:
            return pressure, "engineering_observed"
    pressure = _finite(spatial_room.get("pressure_pa"))
    if pressure is not None:
        return pressure, "spatial_configured"
    return None, "unavailable"


def pressure_relationships(
    layout: dict[str, Any],
    analysis: Any,
) -> list[dict[str, Any]]:
    """Return pressure-cascade relationships backed by project-verification inputs."""
    if _analysis_kind(analysis) != "project_verification":
        return []
    payload = _analysis_input(analysis)
    if payload is None:
        return []
    cascade = payload.get("pressure_cascade", [])
    if not isinstance(cascade, list):
        return []

    rooms = [
        room
        for room in (layout.get("rooms", []) if isinstance(layout, dict) else [])
        if isinstance(room, dict)
    ]
    mapped_by_name: dict[str, dict[str, Any]] = {}
    for room in rooms:
        target, state = resolve_room_mapping(room, analysis)
        if target is None or state != "mapped":
            continue
        target_name = str(target.get("name") or "").strip()
        if target_name:
            mapped_by_name.setdefault(target_name.casefold(), room)

    relationships: list[dict[str, Any]] = []
    for index, raw in enumerate(cascade):
        if not isinstance(raw, dict):
            continue
        higher_name = str(raw.get("higher_pressure_room") or "").strip()
        lower_name = str(raw.get("lower_pressure_room") or "").strip()
        higher = mapped_by_name.get(higher_name.casefold())
        lower = mapped_by_name.get(lower_name.casefold())
        minimum = _finite(raw.get("min_delta_pa"))
        record: dict[str, Any] = {
            "index": index,
            "higher_pressure_room": higher_name,
            "lower_pressure_room": lower_name,
            "min_delta_pa": minimum,
            "higher_room_id": higher.get("id") if higher else None,
            "lower_room_id": lower.get("id") if lower else None,
            "status": "unavailable",
            "actual_delta_pa": None,
        }
        if higher is not None and lower is not None and minimum is not None:
            high_pressure, high_source = room_pressure_value(higher, analysis)
            low_pressure, low_source = room_pressure_value(lower, analysis)
            record["higher_pressure_pa"] = high_pressure
            record["lower_pressure_pa"] = low_pressure
            record["higher_pressure_source"] = high_source
            record["lower_pressure_source"] = low_source
            if high_pressure is not None and low_pressure is not None:
                delta = high_pressure - low_pressure
                record["actual_delta_pa"] = delta
                record["status"] = "pass" if delta + 1e-9 >= minimum else "fail"
        relationships.append(record)
    return relationships
