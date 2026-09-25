from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any


ROOM_GEOMETRY_FIELDS = ("length_m", "width_m", "height_m")
SUPPORTED_ROOM_ANALYSIS_KINDS = frozenset({"room_verification", "project_verification"})


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _geometry(value: Any) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    geometry: dict[str, float] = {}
    for field in ROOM_GEOMETRY_FIELDS:
        number = _finite(value.get(field))
        if number is None or number <= 0:
            return None
        geometry[field] = number
    return geometry


def _geometry_equal(left: dict[str, float] | None, right: dict[str, float] | None) -> bool:
    return (
        left is not None
        and right is not None
        and all(
            math.isclose(left[field], right[field], rel_tol=0.0, abs_tol=1e-9)
            for field in ROOM_GEOMETRY_FIELDS
        )
    )


@dataclass(frozen=True)
class SpatialTransform2D:
    """Pure metric-model <-> canvas transform used by the Tk editor."""

    width_px: float
    height_px: float
    pixels_per_m: float
    pan_x_px: float = 0.0
    pan_y_px: float = 0.0

    def __post_init__(self) -> None:
        for field in ("width_px", "height_px", "pixels_per_m", "pan_x_px", "pan_y_px"):
            value = float(getattr(self, field))
            if not math.isfinite(value):
                raise ValueError(f"{field} must be finite")
        if self.width_px <= 0 or self.height_px <= 0:
            raise ValueError("viewport dimensions must be greater than zero")
        if self.pixels_per_m <= 0:
            raise ValueError("pixels_per_m must be greater than zero")

    def model_to_screen(self, x_m: float, y_m: float) -> tuple[float, float]:
        return (
            self.width_px / 2.0 + self.pan_x_px + float(x_m) * self.pixels_per_m,
            self.height_px / 2.0 + self.pan_y_px + float(y_m) * self.pixels_per_m,
        )

    def screen_to_model(self, x_px: float, y_px: float) -> tuple[float, float]:
        return (
            (float(x_px) - self.width_px / 2.0 - self.pan_x_px) / self.pixels_per_m,
            (float(y_px) - self.height_px / 2.0 - self.pan_y_px) / self.pixels_per_m,
        )

    def zoom_about(
        self,
        factor: float,
        anchor_x_px: float,
        anchor_y_px: float,
        *,
        min_pixels_per_m: float = 11.0,
        max_pixels_per_m: float = 440.0,
    ) -> "SpatialTransform2D":
        number = _finite(factor)
        if number is None or number <= 0:
            raise ValueError("zoom factor must be a finite positive number")
        anchor_model = self.screen_to_model(anchor_x_px, anchor_y_px)
        scale = max(
            min_pixels_per_m,
            min(max_pixels_per_m, self.pixels_per_m * number),
        )
        provisional = SpatialTransform2D(
            self.width_px,
            self.height_px,
            scale,
            self.pan_x_px,
            self.pan_y_px,
        )
        projected = provisional.model_to_screen(*anchor_model)
        return SpatialTransform2D(
            self.width_px,
            self.height_px,
            scale,
            self.pan_x_px + float(anchor_x_px) - projected[0],
            self.pan_y_px + float(anchor_y_px) - projected[1],
        )


def room_plan_bounds(room: Any) -> tuple[float, float, float, float]:
    if not isinstance(room, dict):
        raise ValueError("room must be an object")
    x = _finite(room.get("x_m"))
    y = _finite(room.get("y_m"))
    geometry = _geometry(room)
    if x is None or y is None or geometry is None:
        raise ValueError("room geometry must be finite and positive")
    return (x, y, x + geometry["length_m"], y + geometry["width_m"])


def room_prism_vertices(
    room: Any,
    *,
    default_floor_elevation_m: float = 0.0,
) -> dict[str, tuple[tuple[float, float, float], ...]]:
    x0, y0, x1, y1 = room_plan_bounds(room)
    geometry = _geometry(room)
    if geometry is None:
        raise ValueError("room geometry must be valid")
    floor = _finite(room.get("floor_elevation_m"))
    if floor is None:
        floor = _finite(default_floor_elevation_m)
    if floor is None:
        raise ValueError("floor elevation must be finite")
    top = floor + geometry["height_m"]
    return {
        "base": ((x0, y0, floor), (x1, y0, floor), (x1, y1, floor), (x0, y1, floor)),
        "top": ((x0, y0, top), (x1, y0, top), (x1, y1, top), (x0, y1, top)),
    }


def _analysis_rooms(analysis: Any) -> list[dict]:
    if analysis is None or getattr(analysis, "kind", "") not in SUPPORTED_ROOM_ANALYSIS_KINDS:
        return []
    payload = getattr(analysis, "input", None)
    if not isinstance(payload, dict):
        return []
    if analysis.kind == "room_verification":
        return [payload]
    rooms = payload.get("rooms")
    return [room for room in rooms if isinstance(room, dict)] if isinstance(rooms, list) else []


def room_target_pairs(layout: Any, analysis: Any) -> list[tuple[dict, dict | None]]:
    rooms = layout.get("rooms", []) if isinstance(layout, dict) else []
    spatial_rooms = [room for room in rooms if isinstance(room, dict)]
    targets = _analysis_rooms(analysis)
    if not targets:
        return [(room, None) for room in spatial_rooms]

    analysis_id = str(getattr(analysis, "id", "") or "")
    if getattr(analysis, "kind", "") == "room_verification":
        target = targets[0]
        pairs: list[tuple[dict, dict | None]] = []
        for index, room in enumerate(spatial_rooms):
            ref = room.get("engineering_ref")
            if isinstance(ref, dict) and str(ref.get("analysis_id") or "") not in {"", analysis_id}:
                pairs.append((room, None))
            else:
                pairs.append((room, target if index == 0 else None))
        return pairs

    by_name = {
        str(target.get("name") or "").strip().casefold(): target
        for target in targets
        if str(target.get("name") or "").strip()
    }
    pairs = []
    for room in spatial_rooms:
        ref = room.get("engineering_ref")
        if isinstance(ref, dict):
            if str(ref.get("analysis_id") or "") != analysis_id:
                pairs.append((room, None))
                continue
            target_name = str(ref.get("room_name") or "").strip()
        else:
            target_name = str(room.get("analysis_room_name") or room.get("name") or "").strip()
        pairs.append((room, by_name.get(target_name.casefold())))
    return pairs


def engineering_sync_states(layout: Any, analysis: Any) -> list[dict[str, Any]]:
    """Classify mapped geometry without choosing which side is authoritative."""

    analysis_id = str(getattr(analysis, "id", "") or "")
    records: list[dict[str, Any]] = []
    for room, target in room_target_pairs(layout, analysis):
        room_id = str(room.get("id") or "")
        if target is None:
            records.append(
                {
                    "room_id": room_id,
                    "state": "unmapped",
                    "analysis_id": analysis_id or None,
                    "engineering_room_name": None,
                    "differences": {},
                }
            )
            continue

        spatial = _geometry(room)
        engineering = _geometry(target)
        differences = {
            field: {
                "geometry": None if spatial is None else spatial[field],
                "engineering": None if engineering is None else engineering[field],
            }
            for field in ROOM_GEOMETRY_FIELDS
            if spatial is None
            or engineering is None
            or not math.isclose(
                spatial[field], engineering[field], rel_tol=0.0, abs_tol=1e-9
            )
        }
        if _geometry_equal(spatial, engineering):
            state = "synchronized"
        else:
            baseline = None
            ref = room.get("engineering_ref")
            if (
                isinstance(ref, dict)
                and str(ref.get("analysis_id") or "") == analysis_id
                and str(ref.get("room_name") or "").strip().casefold()
                == str(target.get("name") or "").strip().casefold()
            ):
                baseline = _geometry(ref.get("synced_geometry"))
            if baseline is None:
                state = "conflicting"
            else:
                geometry_changed = not _geometry_equal(spatial, baseline)
                engineering_changed = not _geometry_equal(engineering, baseline)
                if geometry_changed and not engineering_changed:
                    state = "geometry_newer"
                elif engineering_changed and not geometry_changed:
                    state = "engineering_newer"
                else:
                    state = "conflicting"

        records.append(
            {
                "room_id": room_id,
                "state": state,
                "analysis_id": analysis_id or None,
                "engineering_room_name": str(target.get("name") or "") or None,
                "differences": differences,
            }
        )
    return records


def mark_layout_synchronized(layout: Any, analysis: Any) -> bool:
    if not isinstance(layout, dict):
        return False
    analysis_id = str(getattr(analysis, "id", "") or "")
    if not analysis_id:
        return False
    changed = False
    for room, target in room_target_pairs(layout, analysis):
        if target is None:
            continue
        spatial = _geometry(room)
        engineering = _geometry(target)
        if not _geometry_equal(spatial, engineering):
            continue
        ref = {
            "analysis_id": analysis_id,
            "room_name": str(target.get("name") or ""),
            "synced_geometry": spatial,
        }
        if room.get("engineering_ref") != ref:
            room["engineering_ref"] = ref
            changed = True
        if room.get("analysis_room_name") != ref["room_name"]:
            room["analysis_room_name"] = ref["room_name"]
            changed = True
    return changed


def engineering_mapping_issues(layout: Any, analysis: Any) -> list[dict[str, Any]]:
    if getattr(analysis, "kind", "") not in SUPPORTED_ROOM_ANALYSIS_KINDS:
        return []
    issues: list[dict[str, Any]] = []
    for record in engineering_sync_states(layout, analysis):
        if record["state"] == "unmapped":
            issues.append(
                {
                    "code": "missing_engineering_mapping",
                    "severity": "warning",
                    "item_ids": [record["room_id"]],
                    "message": (
                        f"Spatial room {record['room_id']!r} is not mapped to a room "
                        f"in active analysis {record.get('analysis_id')!r}."
                    ),
                }
            )
        elif record["state"] == "conflicting":
            fields = ", ".join(record.get("differences", {})) or "geometry"
            issues.append(
                {
                    "code": "engineering_geometry_conflict",
                    "severity": "warning",
                    "item_ids": [record["room_id"]],
                    "message": (
                        f"Spatial room {record['room_id']!r} conflicts with engineering "
                        f"geometry ({fields}); synchronize deliberately."
                    ),
                }
            )
    return issues


def mapped_pressure_values(layout: Any, analysis: Any) -> dict[str, float | None]:
    values: dict[str, float | None] = {}
    for room, target in room_target_pairs(layout, analysis):
        pressure = None
        if target is not None:
            pressure = _finite(target.get("observed_pressure_pa"))
        if pressure is None:
            pressure = _finite(room.get("pressure_pa"))
        values[str(room.get("id") or "")] = pressure
    return values


def pressure_relationships(layout: Any, analysis: Any) -> list[dict[str, Any]]:
    if getattr(analysis, "kind", "") != "project_verification":
        return []
    payload = getattr(analysis, "input", None)
    if not isinstance(payload, dict) or not isinstance(payload.get("pressure_cascade"), list):
        return []

    target_to_room: dict[str, dict] = {}
    targets_by_name: dict[str, dict] = {}
    for room, target in room_target_pairs(layout, analysis):
        if target is None:
            continue
        name = str(target.get("name") or "")
        if name:
            target_to_room[name] = room
            targets_by_name[name] = target

    result: list[dict[str, Any]] = []
    for requirement in payload["pressure_cascade"]:
        if not isinstance(requirement, dict):
            continue
        higher_name = str(requirement.get("higher_pressure_room") or "")
        lower_name = str(requirement.get("lower_pressure_room") or "")
        minimum = _finite(requirement.get("min_delta_pa"))
        high_room = target_to_room.get(higher_name)
        low_room = target_to_room.get(lower_name)
        high_target = targets_by_name.get(higher_name)
        low_target = targets_by_name.get(lower_name)
        high_pressure = _finite(high_target.get("observed_pressure_pa")) if high_target else None
        low_pressure = _finite(low_target.get("observed_pressure_pa")) if low_target else None
        delta = None
        status = "unavailable"
        if high_pressure is not None and low_pressure is not None and minimum is not None:
            delta = high_pressure - low_pressure
            status = "pass" if delta + 1e-12 >= minimum else "warning"
        result.append(
            {
                "higher_room_id": None if high_room is None else str(high_room.get("id") or ""),
                "lower_room_id": None if low_room is None else str(low_room.get("id") or ""),
                "higher_room_name": higher_name,
                "lower_room_name": lower_name,
                "higher_pressure_pa": high_pressure,
                "lower_pressure_pa": low_pressure,
                "delta_pa": delta,
                "min_delta_pa": minimum,
                "status": status,
            }
        )
    return result


def engineering_fields_for_room(layout: Any, analysis: Any, room_id: str) -> dict[str, Any]:
    keys = (
        "classification",
        "cleanliness_class",
        "target_temperature_c",
        "temperature_target_c",
        "target_relative_humidity_percent",
        "humidity_target_percent",
        "supply_airflow_m3_h",
        "min_ach",
        "min_pressure_pa",
        "observed_pressure_pa",
    )
    for room, target in room_target_pairs(layout, analysis):
        if str(room.get("id") or "") != str(room_id):
            continue
        if target is None:
            return {}
        return {key: target[key] for key in keys if key in target}
    return {}
