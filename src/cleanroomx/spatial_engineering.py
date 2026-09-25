from __future__ import annotations

import copy
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


def _same(left: Any, right: Any, *, epsilon: float = SYNC_EPSILON) -> bool:
    left_number = _finite(left)
    right_number = _finite(right)
    if left_number is None or right_number is None:
        return left == right
    return math.isclose(left_number, right_number, rel_tol=0.0, abs_tol=epsilon)


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


def engineering_room_name(room: dict, index: int = 0) -> str:
    value = room.get("name")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return f"Room {index + 1}"


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
        else engineering_room_name(engineering_room)
    )
    return {
        "analysis_id": _analysis_id(analysis),
        "room_name": target_name,
        "baseline_geometry": geometry_snapshot(engineering_room),
    }


def _linked_target(
    room: dict,
    analysis: Any,
    *,
    allow_legacy_name_match: bool = True,
) -> tuple[dict | None, str | None, str]:
    candidates = engineering_rooms(analysis)
    if not candidates:
        return None, None, "unsupported_analysis"

    ref = room.get("engineering_ref")
    if isinstance(ref, dict):
        ref_analysis_id = ref.get("analysis_id")
        active_id = _analysis_id(analysis)
        if ref_analysis_id not in (None, "", active_id):
            return None, None, "analysis_mismatch"
        linked_name = ref.get("room_name")
        if isinstance(linked_name, str) and linked_name.strip():
            linked_name = linked_name.strip()
            for index, target in enumerate(candidates):
                if engineering_room_name(target, index) == linked_name:
                    return target, linked_name, "explicit"
            return None, linked_name, "missing_target"

    if allow_legacy_name_match:
        room_name = room.get("name")
        if isinstance(room_name, str):
            for index, target in enumerate(candidates):
                target_name = engineering_room_name(target, index)
                if target_name == room_name:
                    return target, target_name, "implicit_name"

    if _analysis_kind(analysis) == "room_verification" and len(candidates) == 1:
        target = candidates[0]
        return target, engineering_room_name(target), "implicit_single"

    return None, None, "unmapped"


def _field_differences(room: dict, target: dict) -> list[dict]:
    differences: list[dict] = []
    for field in GEOMETRY_FIELDS:
        spatial_value = room.get(field)
        engineering_value = target.get(field)
        if not _same(spatial_value, engineering_value):
            differences.append(
                {
                    "field": field,
                    "geometry": spatial_value,
                    "engineering": engineering_value,
                }
            )
    return differences


def engineering_sync_report(layout: Any, analysis: Any) -> dict:
    rooms = layout.get("rooms", []) if isinstance(layout, dict) else []
    entries: list[dict] = []
    counts = {state: 0 for state in SYNC_STATES}

    for room in rooms if isinstance(rooms, list) else []:
        if not isinstance(room, dict):
            continue
        target, target_name, mapping_mode = _linked_target(room, analysis)
        room_id = str(room.get("id") or "")
        room_name = str(room.get("name") or "")
        if target is None:
            entry = {
                "room_id": room_id,
                "room_name": room_name,
                "engineering_room_name": target_name,
                "mapping_mode": mapping_mode,
                "status": "unmapped",
                "differences": [],
                "message": (
                    "Mapped engineering room is missing."
                    if mapping_mode == "missing_target"
                    else "No compatible engineering room mapping is available."
                ),
            }
            entries.append(entry)
            counts["unmapped"] += 1
            continue

        differences = _field_differences(room, target)
        ref = room.get("engineering_ref")
        baseline = (
            ref.get("baseline_geometry")
            if isinstance(ref, dict) and isinstance(ref.get("baseline_geometry"), dict)
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


def _copy_geometry(source: dict, target: dict) -> bool:
    changed = False
    for field in GEOMETRY_FIELDS:
        value = _finite(source.get(field))
        if value is None or value <= 0:
            continue
        if not _same(target.get(field), value):
            target[field] = value
            changed = True
    return changed


def synchronize_layout_to_analysis(layout: dict, analysis: Any) -> bool:
    """Explicitly push mapped spatial geometry to engineering inputs.

    This function is deliberately never called as a side effect of drawing/editing.
    It also refreshes the stored baseline so subsequent changes can be classified.
    """

    if not isinstance(layout, dict):
        return False
    rooms = layout.get("rooms")
    if not isinstance(rooms, list) or not rooms:
        return False
    changed = False
    for room in rooms:
        if not isinstance(room, dict):
            continue
        target, target_name, _mode = _linked_target(room, analysis)
        if target is None:
            continue
        changed = _copy_geometry(room, target) or changed
        if "observed_pressure_pa" in target and room.get("pressure_pa") is not None:
            pressure = _finite(room.get("pressure_pa"))
            if pressure is not None and not _same(target.get("observed_pressure_pa"), pressure):
                target["observed_pressure_pa"] = pressure
                changed = True
        room["engineering_ref"] = create_engineering_ref(
            analysis, target, room_name=target_name
        )
    return changed


def synchronize_analysis_to_layout(layout: dict, analysis: Any) -> bool:
    """Explicitly pull engineering dimensions into mapped spatial rooms."""

    if not isinstance(layout, dict):
        return False
    rooms = layout.get("rooms")
    if not isinstance(rooms, list) or not rooms:
        return False
    changed = False
    for room in rooms:
        if not isinstance(room, dict):
            continue
        target, target_name, _mode = _linked_target(room, analysis)
        if target is None:
            continue
        changed = _copy_geometry(target, room) or changed
        pressure = _finite(target.get("observed_pressure_pa"))
        if pressure is not None and not _same(room.get("pressure_pa"), pressure):
            room["pressure_pa"] = pressure
            changed = True
        room["engineering_ref"] = create_engineering_ref(
            analysis, target, room_name=target_name
        )
    return changed


def link_layout_to_analysis(layout: dict, analysis: Any) -> bool:
    """Create deterministic room mappings without changing engineering values."""

    if not isinstance(layout, dict):
        return False
    rooms = layout.get("rooms")
    if not isinstance(rooms, list):
        return False
    changed = False
    for room in rooms:
        if not isinstance(room, dict):
            continue
        target, target_name, _mode = _linked_target(room, analysis)
        if target is None:
            continue
        new_ref = create_engineering_ref(analysis, target, room_name=target_name)
        if room.get("engineering_ref") != new_ref:
            room["engineering_ref"] = new_ref
            changed = True
    return changed


def _pressure_finding_from_result(
    result: dict | None, room_name: str
) -> dict | None:
    if not isinstance(result, dict):
        return None
    if result.get("room") == room_name and isinstance(result.get("findings"), list):
        reports = [result]
    else:
        raw_reports = result.get("rooms")
        reports = raw_reports if isinstance(raw_reports, list) else []
    for report in reports:
        if not isinstance(report, dict) or report.get("room") != room_name:
            continue
        findings = report.get("findings")
        if not isinstance(findings, list):
            continue
        for finding in findings:
            if isinstance(finding, dict) and finding.get("code") == "PRESSURE":
                return finding
    return None


def pressure_overlay(
    layout: dict,
    analysis: Any,
    result: dict | None = None,
) -> dict:
    """Project authoritative engineering pressure evidence onto spatial rooms.

    A completed result is preferred. If no result exists, configured observed
    pressure is shown as configured input. No pressure value is calculated here.
    """

    rooms = layout.get("rooms", []) if isinstance(layout, dict) else []
    room_entries: list[dict] = []
    target_name_to_room_id: dict[str, str] = {}

    for room in rooms if isinstance(rooms, list) else []:
        if not isinstance(room, dict):
            continue
        target, target_name, mapping_mode = _linked_target(room, analysis)
        value = None
        source = "unavailable"
        status = "unavailable"
        target_pressure = None
        ach = None
        if target is not None and target_name is not None:
            target_name_to_room_id[target_name] = str(room.get("id") or "")
            finding = _pressure_finding_from_result(result, target_name)
            if finding is not None and _finite(finding.get("actual")) is not None:
                value = _finite(finding.get("actual"))
                source = "result"
                status = str(finding.get("status") or "unavailable")
                target_pressure = _finite(finding.get("limit"))
            else:
                configured = _finite(target.get("observed_pressure_pa"))
                if configured is not None:
                    value = configured
                    source = "configured"
                    status = "configured"
                target_pressure = _finite(target.get("min_pressure_pa"))
            supplied = _finite(target.get("supply_airflow_m3_h"))
            length = _finite(target.get("length_m"))
            width = _finite(target.get("width_m"))
            height = _finite(target.get("height_m"))
            if (
                supplied is not None
                and length is not None
                and width is not None
                and height is not None
                and length > 0
                and width > 0
                and height > 0
            ):
                ach = supplied / (length * width * height)
        elif _finite(room.get("pressure_pa")) is not None:
            value = _finite(room.get("pressure_pa"))
            source = "spatial"
            status = "unmapped"

        room_entries.append(
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

    relationships: list[dict] = []
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
    for requirement in requirements if isinstance(requirements, list) else []:
        if not isinstance(requirement, dict):
            continue
        higher = str(requirement.get("higher_pressure_room") or "")
        lower = str(requirement.get("lower_pressure_room") or "")
        finding = next(
            (
                item
                for item in result_findings
                if isinstance(item, dict)
                and item.get("higher_pressure_room") == higher
                and item.get("lower_pressure_room") == lower
            ),
            None,
        )
        relationships.append(
            {
                "higher_room_id": target_name_to_room_id.get(higher),
                "lower_room_id": target_name_to_room_id.get(lower),
                "higher_pressure_room": higher,
                "lower_pressure_room": lower,
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

    return {"rooms": room_entries, "relationships": relationships}


def clone_layout_for_sync(layout: dict) -> dict:
    """Return a detached layout for dry-run/conflict tooling."""

    return copy.deepcopy(layout)
