from __future__ import annotations

import math
from typing import Any


GEOMETRY_FIELDS = ("length_m", "width_m", "height_m")
SYNC_STATES = (
    "synchronized",
    "geometry_newer",
    "engineering_newer",
    "conflicting",
    "unmapped",
)
SYNC_EPSILON = 1e-9


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _same(left: Any, right: Any) -> bool:
    left_number = _finite(left)
    right_number = _finite(right)
    if left_number is None or right_number is None:
        return left == right
    return math.isclose(
        left_number,
        right_number,
        rel_tol=0.0,
        abs_tol=SYNC_EPSILON,
    )


def _analysis_id(analysis: Any) -> str | None:
    value = getattr(analysis, "id", None)
    return str(value) if value is not None else None


def _analysis_kind(analysis: Any) -> str:
    return str(getattr(analysis, "kind", "") or "")


def _analysis_input(analysis: Any) -> dict:
    value = getattr(analysis, "input", None)
    return value if isinstance(value, dict) else {}


def engineering_rooms(analysis: Any) -> list[dict]:
    payload = _analysis_input(analysis)
    kind = _analysis_kind(analysis)
    if kind == "room_verification":
        return [payload]
    if kind == "project_verification":
        rooms = payload.get("rooms")
        if isinstance(rooms, list):
            return [room for room in rooms if isinstance(room, dict)]
    return []


def _room_name(room: dict, index: int = 0) -> str:
    value = room.get("name")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return f"Room {index + 1}"


def _target_name_for_spatial_room(room: dict) -> str:
    linked = room.get("analysis_room_name")
    if isinstance(linked, str) and linked.strip():
        return linked.strip()
    value = room.get("name")
    return value.strip() if isinstance(value, str) else ""


def geometry_snapshot(engineering_room: dict) -> dict[str, float]:
    snapshot: dict[str, float] = {}
    for field in GEOMETRY_FIELDS:
        value = _finite(engineering_room.get(field))
        if value is not None:
            snapshot[field] = value
    return snapshot


def create_engineering_ref(
    analysis: Any,
    engineering_room: dict,
    *,
    room_name: str | None = None,
) -> dict:
    target_name = (
        room_name.strip()
        if isinstance(room_name, str) and room_name.strip()
        else _room_name(engineering_room)
    )
    return {
        "analysis_id": _analysis_id(analysis),
        "room_name": target_name,
        "baseline_geometry": geometry_snapshot(engineering_room),
    }


def _linked_target(
    room: dict,
    analysis: Any,
) -> tuple[dict | None, str | None, str]:
    candidates = engineering_rooms(analysis)
    if not candidates:
        return None, None, "unsupported_analysis"

    requested_name = _target_name_for_spatial_room(room)
    ref = room.get("engineering_ref")
    if isinstance(ref, dict):
        ref_analysis_id = ref.get("analysis_id")
        active_id = _analysis_id(analysis)
        if ref_analysis_id not in (None, "", active_id):
            return None, requested_name or None, "analysis_mismatch"
        ref_name = ref.get("room_name")
        if isinstance(ref_name, str) and ref_name.strip():
            requested_name = ref_name.strip()

    if requested_name:
        key = requested_name.casefold()
        matches = [
            target
            for index, target in enumerate(candidates)
            if _room_name(target, index).casefold() == key
        ]
        if len(matches) == 1:
            return matches[0], _room_name(matches[0]), (
                "explicit" if isinstance(ref, dict) else "analysis_room_name"
            )
        if len(matches) > 1:
            return None, requested_name, "ambiguous_target"
        if isinstance(ref, dict) or room.get("analysis_room_name"):
            return None, requested_name, "missing_target"

    if _analysis_kind(analysis) == "room_verification" and len(candidates) == 1:
        target = candidates[0]
        return target, _room_name(target), "implicit_single"
    return None, requested_name or None, "unmapped"


def _differences(room: dict, target: dict) -> list[dict]:
    return [
        {
            "field": field,
            "geometry": room.get(field),
            "engineering": target.get(field),
        }
        for field in GEOMETRY_FIELDS
        if not _same(room.get(field), target.get(field))
    ]


def engineering_sync_report(layout: Any, analysis: Any) -> dict:
    raw_rooms = layout.get("rooms", []) if isinstance(layout, dict) else []
    rooms = raw_rooms if isinstance(raw_rooms, list) else []
    entries: list[dict] = []
    counts = {state: 0 for state in SYNC_STATES}

    for room in rooms:
        if not isinstance(room, dict):
            continue
        target, target_name, mapping_mode = _linked_target(room, analysis)
        room_id = str(room.get("id") or "")
        room_name = str(room.get("name") or "")
        if target is None:
            message = {
                "missing_target": "Linked engineering room is missing.",
                "ambiguous_target": "Engineering room mapping is ambiguous.",
                "analysis_mismatch": "Room is linked to a different engineering analysis.",
            }.get(mapping_mode, "No compatible engineering room mapping is available.")
            entry = {
                "room_id": room_id,
                "room_name": room_name,
                "engineering_room_name": target_name,
                "mapping_mode": mapping_mode,
                "status": "unmapped",
                "differences": [],
                "message": message,
            }
            entries.append(entry)
            counts["unmapped"] += 1
            continue

        differences = _differences(room, target)
        ref = room.get("engineering_ref")
        baseline = (
            ref.get("baseline_geometry")
            if isinstance(ref, dict)
            and isinstance(ref.get("baseline_geometry"), dict)
            else None
        )
        if not differences:
            status = "synchronized"
        elif baseline is None:
            status = "conflicting"
        else:
            geometry_changed = any(
                field in baseline and not _same(room.get(field), baseline.get(field))
                for field in GEOMETRY_FIELDS
            )
            engineering_changed = any(
                field in baseline and not _same(target.get(field), baseline.get(field))
                for field in GEOMETRY_FIELDS
            )
            if geometry_changed and not engineering_changed:
                status = "geometry_newer"
            elif engineering_changed and not geometry_changed:
                status = "engineering_newer"
            else:
                status = "conflicting"

        entries.append(
            {
                "room_id": room_id,
                "room_name": room_name,
                "engineering_room_name": target_name,
                "mapping_mode": mapping_mode,
                "status": status,
                "differences": differences,
                "message": {
                    "synchronized": "Spatial and engineering room dimensions agree.",
                    "geometry_newer": "Spatial geometry changed since the last synchronization.",
                    "engineering_newer": "Engineering room dimensions changed since the last synchronization.",
                    "conflicting": "Spatial and engineering room dimensions conflict.",
                }[status],
            }
        )
        counts[status] += 1

    overall = "synchronized"
    for candidate in ("conflicting", "unmapped", "engineering_newer", "geometry_newer"):
        if counts[candidate]:
            overall = candidate
            break
    return {"status": overall, "counts": counts, "rooms": entries}


def establish_sync_baselines(layout: dict, analysis: Any) -> bool:
    """Record a baseline only where geometry already agrees with engineering data."""

    rooms = layout.get("rooms", []) if isinstance(layout, dict) else []
    changed = False
    for room in rooms if isinstance(rooms, list) else []:
        if not isinstance(room, dict):
            continue
        target, target_name, _mapping_mode = _linked_target(room, analysis)
        if target is None or _differences(room, target):
            continue
        new_ref = create_engineering_ref(analysis, target, room_name=target_name)
        if room.get("engineering_ref") != new_ref:
            room["engineering_ref"] = new_ref
            changed = True
    return changed


def refresh_sync_baselines(layout: dict, analysis: Any) -> bool:
    """Refresh baselines for mapped rooms after an explicit successful push/pull."""

    rooms = layout.get("rooms", []) if isinstance(layout, dict) else []
    changed = False
    for room in rooms if isinstance(rooms, list) else []:
        if not isinstance(room, dict):
            continue
        target, target_name, _mapping_mode = _linked_target(room, analysis)
        if target is None:
            continue
        new_ref = create_engineering_ref(analysis, target, room_name=target_name)
        if room.get("engineering_ref") != new_ref:
            room["engineering_ref"] = new_ref
            changed = True
    return changed


def synchronize_analysis_to_layout(layout: dict, analysis: Any) -> bool:
    """Explicitly pull mapped engineering dimensions into spatial geometry."""

    rooms = layout.get("rooms", []) if isinstance(layout, dict) else []
    changed = False
    for room in rooms if isinstance(rooms, list) else []:
        if not isinstance(room, dict):
            continue
        target, target_name, _mapping_mode = _linked_target(room, analysis)
        if target is None:
            continue
        for field in GEOMETRY_FIELDS:
            value = _finite(target.get(field))
            if value is None or value <= 0:
                continue
            if not _same(room.get(field), value):
                room[field] = value
                changed = True
        pressure = _finite(target.get("observed_pressure_pa"))
        if pressure is not None and not _same(room.get("pressure_pa"), pressure):
            room["pressure_pa"] = pressure
            changed = True
        new_ref = create_engineering_ref(analysis, target, room_name=target_name)
        if room.get("engineering_ref") != new_ref:
            room["engineering_ref"] = new_ref
            changed = True
    return changed


def _pressure_finding(result: dict | None, room_name: str) -> tuple[dict | None, dict | None]:
    if not isinstance(result, dict):
        return None, None
    if result.get("room") == room_name and isinstance(result.get("findings"), list):
        reports = [result]
    else:
        raw = result.get("rooms")
        reports = raw if isinstance(raw, list) else []
    for report in reports:
        if not isinstance(report, dict) or report.get("room") != room_name:
            continue
        findings = report.get("findings")
        if isinstance(findings, list):
            for finding in findings:
                if isinstance(finding, dict) and finding.get("code") == "PRESSURE":
                    return finding, report
    return None, None


def pressure_overlay(
    layout: dict,
    analysis: Any,
    result: dict | None = None,
) -> dict:
    """Project real configured/result pressure evidence onto the spatial model."""

    raw_rooms = layout.get("rooms", []) if isinstance(layout, dict) else []
    rooms = raw_rooms if isinstance(raw_rooms, list) else []
    entries: list[dict] = []
    target_to_room_id: dict[str, str] = {}

    for room in rooms:
        if not isinstance(room, dict):
            continue
        target, target_name, mapping_mode = _linked_target(room, analysis)
        value = None
        target_pressure = None
        source = "unavailable"
        status = "unavailable"
        ach = None
        if target is not None and target_name is not None:
            target_to_room_id[target_name] = str(room.get("id") or "")
            finding, report = _pressure_finding(result, target_name)
            actual = _finite(finding.get("actual")) if isinstance(finding, dict) else None
            if actual is not None:
                value = actual
                target_pressure = _finite(finding.get("limit"))
                source = "result"
                status = str(finding.get("status") or "unavailable")
                ach = _finite(report.get("ach")) if isinstance(report, dict) else None
            else:
                configured = _finite(target.get("observed_pressure_pa"))
                if configured is not None:
                    value = configured
                    source = "configured"
                    status = "configured"
                target_pressure = _finite(target.get("min_pressure_pa"))
        elif _finite(room.get("pressure_pa")) is not None:
            value = _finite(room.get("pressure_pa"))
            source = "spatial"
            status = "unmapped"

        entries.append(
            {
                "room_id": str(room.get("id") or ""),
                "room_name": str(room.get("name") or ""),
                "engineering_room_name": target_name,
                "mapping_mode": mapping_mode,
                "pressure_pa": value,
                "pressure_target_pa": target_pressure,
                "source": source,
                "status": status,
                "ach": ach,
            }
        )

    payload = _analysis_input(analysis)
    requirements = (
        payload.get("pressure_cascade", [])
        if _analysis_kind(analysis) == "project_verification"
        else []
    )
    result_findings = (
        result.get("pressure_cascade", [])
        if isinstance(result, dict) and isinstance(result.get("pressure_cascade"), list)
        else []
    )
    relationships: list[dict] = []
    for requirement in requirements if isinstance(requirements, list) else []:
        if not isinstance(requirement, dict):
            continue
        high = str(requirement.get("higher_pressure_room") or "")
        low = str(requirement.get("lower_pressure_room") or "")
        finding = next(
            (
                item for item in result_findings
                if isinstance(item, dict)
                and item.get("higher_pressure_room") == high
                and item.get("lower_pressure_room") == low
            ),
            None,
        )
        relationships.append(
            {
                "higher_room_id": target_to_room_id.get(high),
                "lower_room_id": target_to_room_id.get(low),
                "higher_pressure_room": high,
                "lower_pressure_room": low,
                "limit_pa": _finite(requirement.get("min_delta_pa")),
                "actual_delta_pa": (
                    _finite(finding.get("actual_delta_pa"))
                    if isinstance(finding, dict)
                    else None
                ),
                "status": (
                    str(finding.get("status") or "unavailable")
                    if isinstance(finding, dict)
                    else "unavailable"
                ),
                "source": "result" if isinstance(finding, dict) else "configured_requirement",
            }
        )
    return {"rooms": entries, "relationships": relationships}
