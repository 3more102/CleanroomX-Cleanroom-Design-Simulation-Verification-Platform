from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any


ROOM_GEOMETRY_FIELDS = ("length_m", "width_m", "height_m")
SUPPORTED_ROOM_ANALYSIS_KINDS = frozenset({"room_verification", "project_verification"})
SYNC_STATES = frozenset({
    "synchronized",
    "geometry_newer",
    "engineering_newer",
    "conflicting",
    "unmapped",
})


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
    result: dict[str, float] = {}
    for field in ROOM_GEOMETRY_FIELDS:
        number = _finite(value.get(field))
        if number is None or number <= 0:
            return None
        result[field] = number
    return result


def _geometry_equal(left: dict[str, float] | None, right: dict[str, float] | None) -> bool:
    if left is None or right is None:
        return False
    return all(
        math.isclose(left[field], right[field], rel_tol=0.0, abs_tol=1e-9)
        for field in ROOM_GEOMETRY_FIELDS
    )


@dataclass(frozen=True)
class SpatialTransform2D:
    """Deterministic metric-model <-> canvas transform.

    Pan is expressed in pixels and the model origin is centered in the viewport.
    This object deliberately contains no Tk state so transforms can be verified
    independently of GUI automation.
    """

    width_px: float
    height_px: float
    pixels_per_m: float
    pan_x_px: float = 0.0
    pan_y_px: float = 0.0

    def __post_init__(self) -> None:
        for name in ("width_px", "height_px", "pixels_per_m", "pan_x_px", "pan_y_px"):
            value = float(getattr(self, name))
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
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
        factor_number = _finite(factor)
        if factor_number is None or factor_number <= 0:
            raise ValueError("zoom factor must be a finite positive number")
        anchor_model = self.screen_to_model(anchor_x_px, anchor_y_px)
        scale = max(
            min_pixels_per_m,
            min(max_pixels_per_m, self.pixels_per_m * factor_number),
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


def _analysis_rooms(analysis: Any) -> list[dict]:
    if analysis is None or getattr(analysis, "kind", "") not in SUPPORTED_ROOM_ANALYSIS_KINDS:
        return []
    payload = getattr(analysis, "input", None)
    if not isinstance(payload, dict):
        return []
    if getattr(analysis, "kind", "") == "room_verification":
        return [payload]
    rooms = payload.get("rooms")
    return [item for item in rooms if isinstance(item, dict)] if isinstance(rooms, list) else []


def _target_pairs(layout: Any, analysis: Any) -> list[tuple[dict, dict | None]]:
    rooms = layout.get("rooms", []) if isinstance(layout, dict) else []
    spatial_rooms = [item for item in rooms if isinstance(item, dict)]
    targets = _analysis_rooms(analysis)
    if not targets:
        return [(room, None) for room in spatial_rooms]

    analysis_id = str(getattr(analysis, "id", "") or "")
    if getattr(analysis, "kind", "") == "room_verification":
        target = targets[0]
        pairs: list[tuple[dict, dict | None]] = []
        for index, room in enumerate(spatial_rooms):
            ref = room.get("engineering_ref")
            if isinstance(ref, dict):
                if str(ref.get("analysis_id") or "") != analysis_id:
                    pairs.append((room, None))
                    continue
                # A room-verification analysis has exactly one engineering room.
                # The analysis id is therefore the stable mapping identity; the
                # stored room name is descriptive and may legitimately change
                # during an explicit rename/synchronization transaction.
                pairs.append((room, target))
                continue
            pairs.append((room, target if index == 0 else None))
        return pairs

    by_name = {
        str(target.get("name") or ""): target
        for target in targets
        if str(target.get("name") or "")
    }
    pairs = []
    for room in spatial_rooms:
        ref = room.get("engineering_ref")
        if isinstance(ref, dict):
            if str(ref.get("analysis_id") or "") != analysis_id:
                pairs.append((room, None))
                continue
            target_name = str(ref.get("room_name") or "")
            pairs.append((room, by_name.get(target_name)))
            continue
        pairs.append((room, by_name.get(str(room.get("name") or ""))))
    return pairs


def engineering_sync_states(layout: Any, analysis: Any) -> list[dict[str, Any]]:
    """Return deterministic room-to-engineering synchronization states.

    A stored synchronized-geometry baseline allows later edits to be classified
    without silently deciding which side is authoritative.
    """

    analysis_id = str(getattr(analysis, "id", "") or "")
    records: list[dict[str, Any]] = []
    for room, target in _target_pairs(layout, analysis):
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

        spatial_geometry = _geometry(room)
        engineering_geometry = _geometry(target)
        differences = {
            field: {
                "geometry": None if spatial_geometry is None else spatial_geometry[field],
                "engineering": None if engineering_geometry is None else engineering_geometry[field],
            }
            for field in ROOM_GEOMETRY_FIELDS
            if spatial_geometry is None
            or engineering_geometry is None
            or not math.isclose(
                spatial_geometry[field],
                engineering_geometry[field],
                rel_tol=0.0,
                abs_tol=1e-9,
            )
        }
        if _geometry_equal(spatial_geometry, engineering_geometry):
            state = "synchronized"
        else:
            ref = room.get("engineering_ref")
            baseline = None
            if isinstance(ref, dict):
                if (
                    str(ref.get("analysis_id") or "") == analysis_id
                    and str(ref.get("room_name") or "") == str(target.get("name") or "")
                ):
                    baseline = _geometry(ref.get("synced_geometry"))
            if baseline is None:
                state = "conflicting"
            else:
                geometry_changed = not _geometry_equal(spatial_geometry, baseline)
                engineering_changed = not _geometry_equal(engineering_geometry, baseline)
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
    """Record an explicit synchronization baseline in spatial metadata."""

    if not isinstance(layout, dict):
        return False
    analysis_id = str(getattr(analysis, "id", "") or "")
    if not analysis_id:
        return False

    changed = False
    for room, target in _target_pairs(layout, analysis):
        if target is None:
            continue
        spatial_geometry = _geometry(room)
        engineering_geometry = _geometry(target)
        if not _geometry_equal(spatial_geometry, engineering_geometry):
            continue
        ref = {
            "analysis_id": analysis_id,
            "room_name": str(target.get("name") or ""),
            "synced_geometry": spatial_geometry,
        }
        if room.get("engineering_ref") != ref:
            room["engineering_ref"] = ref
            changed = True
    return changed


def pressure_relationships(layout: Any, analysis: Any) -> list[dict[str, Any]]:
    """Project configured pressure-cascade evidence onto spatial rooms.

    Only explicit project-verification inputs are used. Missing observations remain
    unavailable; no pressure or relationship is inferred from geometry.
    """

    if getattr(analysis, "kind", "") != "project_verification":
        return []
    payload = getattr(analysis, "input", None)
    if not isinstance(payload, dict):
        return []
    requirements = payload.get("pressure_cascade")
    if not isinstance(requirements, list):
        return []

    pairs = _target_pairs(layout, analysis)
    target_to_room: dict[str, dict] = {}
    target_by_name: dict[str, dict] = {}
    for room, target in pairs:
        if target is None:
            continue
        name = str(target.get("name") or "")
        if name:
            target_to_room[name] = room
            target_by_name[name] = target

    records: list[dict[str, Any]] = []
    for requirement in requirements:
        if not isinstance(requirement, dict):
            continue
        higher_name = str(requirement.get("higher_pressure_room") or "")
        lower_name = str(requirement.get("lower_pressure_room") or "")
        minimum = _finite(requirement.get("min_delta_pa"))
        higher_room = target_to_room.get(higher_name)
        lower_room = target_to_room.get(lower_name)
        higher_target = target_by_name.get(higher_name)
        lower_target = target_by_name.get(lower_name)
        higher_pressure = (
            _finite(higher_target.get("observed_pressure_pa"))
            if higher_target is not None
            else None
        )
        lower_pressure = (
            _finite(lower_target.get("observed_pressure_pa"))
            if lower_target is not None
            else None
        )

        status = "unavailable"
        delta = None
        if higher_pressure is not None and lower_pressure is not None and minimum is not None:
            delta = higher_pressure - lower_pressure
            status = "pass" if delta + 1e-12 >= minimum else "warning"

        records.append(
            {
                "higher_room_name": higher_name,
                "lower_room_name": lower_name,
                "higher_room_id": None if higher_room is None else str(higher_room.get("id") or ""),
                "lower_room_id": None if lower_room is None else str(lower_room.get("id") or ""),
                "higher_pressure_pa": higher_pressure,
                "lower_pressure_pa": lower_pressure,
                "delta_pa": delta,
                "min_delta_pa": minimum,
                "status": status,
            }
        )
    return records


def engineering_fields_for_room(layout: Any, analysis: Any, room_id: str) -> dict[str, Any]:
    """Return existing engineering-room values for a mapped spatial room."""

    interesting = (
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
    for room, target in _target_pairs(layout, analysis):
        if str(room.get("id") or "") != str(room_id):
            continue
        if target is None:
            return {}
        return {key: target[key] for key in interesting if key in target}
    return {}


def engineering_mapping_issues(layout: Any, analysis: Any) -> list[dict[str, Any]]:
    """Return deterministic advisory mapping/conflict diagnostics."""

    if getattr(analysis, "kind", "") not in SUPPORTED_ROOM_ANALYSIS_KINDS:
        return []
    issues: list[dict[str, Any]] = []
    for record in engineering_sync_states(layout, analysis):
        state = record["state"]
        room_id = record["room_id"]
        if state == "unmapped":
            issues.append(
                {
                    "code": "missing_engineering_mapping",
                    "severity": "warning",
                    "item_ids": [room_id],
                    "message": (
                        f"Spatial room {room_id!r} is not mapped to a room in "
                        f"analysis {record.get('analysis_id')!r}."
                    ),
                }
            )
        elif state == "conflicting":
            fields = ", ".join(record.get("differences", {})) or "geometry"
            issues.append(
                {
                    "code": "engineering_geometry_conflict",
                    "severity": "warning",
                    "item_ids": [room_id],
                    "message": (
                        f"Spatial room {room_id!r} conflicts with mapped engineering "
                        f"geometry ({fields}); synchronize deliberately before analysis."
                    ),
                }
            )
    return issues


def mapped_pressure_values(layout: Any, analysis: Any) -> dict[str, float | None]:
    """Return display pressure by spatial room, preferring current engineering input."""

    result: dict[str, float | None] = {}
    for room, target in _target_pairs(layout, analysis):
        room_id = str(room.get("id") or "")
        value = None
        if target is not None:
            value = _finite(target.get("observed_pressure_pa"))
        if value is None:
            value = _finite(room.get("pressure_pa"))
        result[room_id] = value
    return result


def room_plan_bounds(room: Any) -> tuple[float, float, float, float]:
    """Return canonical plan bounds (x0, y0, x1, y1) for one valid room."""

    if not isinstance(room, dict):
        raise ValueError("room must be an object")
    x = _finite(room.get("x_m"))
    y = _finite(room.get("y_m"))
    geometry = _geometry(room)
    if x is None or y is None or geometry is None:
        raise ValueError("room geometry must contain finite coordinates and positive dimensions")
    return (
        x,
        y,
        x + geometry["length_m"],
        y + geometry["width_m"],
    )


def room_prism_vertices(
    room: Any,
) -> dict[str, tuple[tuple[float, float, float], ...]]:
    """Return deterministic 3D prism vertices from the same canonical room state."""

    x0, y0, x1, y1 = room_plan_bounds(room)
    geometry = _geometry(room)
    if geometry is None:
        raise ValueError("room geometry must be valid")
    elevation = _finite(room.get("elevation_m"))
    base_z = 0.0 if elevation is None else elevation
    top_z = base_z + geometry["height_m"]
    return {
        "base": (
            (x0, y0, base_z),
            (x1, y0, base_z),
            (x1, y1, base_z),
            (x0, y1, base_z),
        ),
        "top": (
            (x0, y0, top_z),
            (x1, y0, top_z),
            (x1, y1, top_z),
            (x0, y1, top_z),
        ),
    }


def translated_position(
    x_m: float,
    y_m: float,
    dx_m: float,
    dy_m: float,
    *,
    grid_m: float | None = None,
) -> tuple[float, float]:
    """Translate a plan point, optionally snapping the result to a metric grid."""

    values = [_finite(value) for value in (x_m, y_m, dx_m, dy_m)]
    if any(value is None for value in values):
        raise ValueError("translation coordinates must be finite")
    x, y, dx, dy = (float(value) for value in values if value is not None)
    result_x = x + dx
    result_y = y + dy
    if grid_m is not None:
        grid = _finite(grid_m)
        if grid is None or grid <= 0:
            raise ValueError("grid_m must be a finite positive number")
        result_x = round(result_x / grid) * grid
        result_y = round(result_y / grid) * grid
    return result_x, result_y


def resized_room_dimensions(
    room: Any,
    pointer_x_m: float,
    pointer_y_m: float,
    *,
    grid_m: float | None = None,
    minimum_m: float = 0.1,
) -> tuple[float, float]:
    """Return positive room plan dimensions for a lower-right resize handle."""

    if not isinstance(room, dict):
        raise ValueError("room must be an object")
    x = _finite(room.get("x_m"))
    y = _finite(room.get("y_m"))
    pointer_x = _finite(pointer_x_m)
    pointer_y = _finite(pointer_y_m)
    minimum = _finite(minimum_m)
    if None in (x, y, pointer_x, pointer_y, minimum) or minimum <= 0:
        raise ValueError("resize coordinates and minimum must be finite and valid")
    length = max(float(minimum), float(pointer_x) - float(x))
    width = max(float(minimum), float(pointer_y) - float(y))
    if grid_m is not None:
        grid = _finite(grid_m)
        if grid is None or grid <= 0:
            raise ValueError("grid_m must be a finite positive number")
        length = max(float(grid), round(length / float(grid)) * float(grid))
        width = max(float(grid), round(width / float(grid)) * float(grid))
    return length, width
