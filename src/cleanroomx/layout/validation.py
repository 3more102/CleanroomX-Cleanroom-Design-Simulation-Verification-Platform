from __future__ import annotations

from dataclasses import dataclass
import math

from .model import LayoutObject, Room, SpatialLayout


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    code: str
    message: str
    entity_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "entity_id": self.entity_id,
        }


def rooms_overlap(a: Room, b: Room, *, tolerance_m: float = 1e-9) -> bool:
    overlap_x = min(a.x2_m, b.x2_m) - max(a.x_m, b.x_m)
    overlap_y = min(a.y2_m, b.y2_m) - max(a.y_m, b.y_m)
    return overlap_x > tolerance_m and overlap_y > tolerance_m


def _object_center_inside_room(obj: LayoutObject, room: Room) -> bool:
    return room.contains(obj.x_m, obj.y_m, tolerance_m=1e-9)


def validate_layout(layout: SpatialLayout) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    seen_ids: set[str] = set()
    for floor in layout.floors:
        if floor.id in seen_ids:
            issues.append(ValidationIssue("ERROR", "duplicate_id", f"duplicate ID {floor.id}", floor.id))
        seen_ids.add(floor.id)
        if not math.isfinite(floor.elevation_m):
            issues.append(ValidationIssue("ERROR", "non_finite", "floor elevation is not finite", floor.id))
        if not math.isfinite(floor.default_ceiling_height_m) or floor.default_ceiling_height_m <= 0:
            issues.append(ValidationIssue("ERROR", "invalid_height", "floor ceiling height must be > 0", floor.id))

        room_ids = {room.id for room in floor.rooms}
        for room in floor.rooms:
            if room.id in seen_ids:
                issues.append(ValidationIssue("ERROR", "duplicate_id", f"duplicate ID {room.id}", room.id))
            seen_ids.add(room.id)
            numeric = (room.x_m, room.y_m, room.width_m, room.depth_m, room.height_m, room.floor_elevation_m)
            if not all(math.isfinite(value) for value in numeric):
                issues.append(ValidationIssue("ERROR", "non_finite", f"room {room.name} contains non-finite geometry", room.id))
            if room.width_m <= 0 or room.depth_m <= 0 or room.height_m <= 0:
                issues.append(ValidationIssue("ERROR", "invalid_dimensions", f"room {room.name} dimensions must be > 0", room.id))
            if room.pressure_pa is not None and not math.isfinite(room.pressure_pa):
                issues.append(ValidationIssue("ERROR", "non_finite_pressure", f"room {room.name} pressure is not finite", room.id))
            if room.pressure_pa is None:
                issues.append(ValidationIssue(
                    "INFO", "pressure_unavailable",
                    f"room {room.name!r} has no pressure value to visualize", room.id
                ))

        for i, room in enumerate(floor.rooms):
            for other in floor.rooms[i + 1 :]:
                if rooms_overlap(room, other):
                    issues.append(ValidationIssue(
                        "WARNING",
                        "room_overlap",
                        f"rooms {room.name!r} and {other.name!r} overlap",
                        room.id,
                    ))

        for obj in floor.objects:
            if obj.id in seen_ids:
                issues.append(ValidationIssue("ERROR", "duplicate_id", f"duplicate ID {obj.id}", obj.id))
            seen_ids.add(obj.id)
            numeric = (obj.x_m, obj.y_m, obj.z_m, obj.width_m, obj.depth_m, obj.height_m, obj.orientation_deg)
            if not all(math.isfinite(value) for value in numeric):
                issues.append(ValidationIssue("ERROR", "non_finite", f"object {obj.name} contains non-finite geometry", obj.id))
            if obj.width_m <= 0 or obj.depth_m <= 0 or obj.height_m <= 0:
                issues.append(ValidationIssue("ERROR", "invalid_dimensions", f"object {obj.name} dimensions must be > 0", obj.id))
            if obj.room_id is not None:
                if obj.room_id not in room_ids:
                    issues.append(ValidationIssue(
                        "ERROR",
                        "invalid_room_reference",
                        f"object {obj.name!r} references unknown room {obj.room_id!r}",
                        obj.id,
                    ))
                else:
                    room = floor.room_by_id(obj.room_id)
                    if not _object_center_inside_room(obj, room) and obj.kind != "door":
                        issues.append(ValidationIssue(
                            "WARNING",
                            "object_outside_room",
                            f"object {obj.name!r} is outside associated room {room.name!r}",
                            obj.id,
                        ))
                    if obj.kind == "door" and obj.properties.get("wall") not in {"north", "south", "east", "west"}:
                        issues.append(ValidationIssue(
                            "WARNING",
                            "door_wall_missing",
                            f"door {obj.name!r} has no valid wall association",
                            obj.id,
                        ))
            elif obj.kind in {"door", "supply_diffuser", "return_grille", "exhaust_grille", "ffu", "sensor", "transfer_opening"}:
                issues.append(ValidationIssue(
                    "WARNING",
                    "missing_room_reference",
                    f"{obj.kind.replace('_', ' ')} {obj.name!r} is not associated with a room",
                    obj.id,
                ))

    if layout.active_floor_id is not None and layout.active_floor_id not in {f.id for f in layout.floors}:
        issues.append(ValidationIssue("ERROR", "invalid_active_floor", "active floor reference is invalid", layout.active_floor_id))
    return issues


def layout_is_valid(layout: SpatialLayout) -> bool:
    return not any(issue.severity == "ERROR" for issue in validate_layout(layout))
