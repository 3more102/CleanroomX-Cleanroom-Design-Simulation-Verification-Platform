from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .model import Room, SpatialLayout


@dataclass(frozen=True)
class GeometryConflict:
    analysis_id: str
    room_name: str
    field: str
    analysis_value: Any
    geometry_value: float


def geometry_summary(layout: SpatialLayout) -> dict[str, float | int]:
    rooms = list(layout.iter_rooms())
    objects = list(layout.iter_objects())
    return {
        "room_count": len(rooms),
        "total_floor_area_m2": sum(room.area_m2 for room in rooms),
        "total_room_volume_m3": sum(room.volume_m3 for room in rooms),
        "door_count": sum(obj.kind == "door" for obj in objects),
        "supply_diffuser_count": sum(obj.kind == "supply_diffuser" for obj in objects),
        "return_grille_count": sum(obj.kind == "return_grille" for obj in objects),
        "exhaust_grille_count": sum(obj.kind == "exhaust_grille" for obj in objects),
        "ffu_count": sum(obj.kind == "ffu" for obj in objects),
        "equipment_count": sum(obj.kind == "equipment" for obj in objects),
        "sensor_count": sum(obj.kind == "sensor" for obj in objects),
        "transfer_opening_count": sum(obj.kind == "transfer_opening" for obj in objects),
    }


def _analysis_room_candidates(analysis_input: dict, room: Room) -> list[dict]:
    rooms = analysis_input.get("rooms")
    if not isinstance(rooms, list):
        return []
    by_ref = []
    by_name = []
    for item in rooms:
        if not isinstance(item, dict):
            continue
        if room.analysis_room_ref and item.get("id") == room.analysis_room_ref:
            by_ref.append(item)
        if item.get("name") == room.name:
            by_name.append(item)
    return by_ref or by_name


def dimension_conflicts(project: Any, room: Room, analysis_id: str | None = None) -> list[GeometryConflict]:
    conflicts: list[GeometryConflict] = []
    mapping = {
        "length_m": room.width_m,
        "width_m": room.depth_m,
        "height_m": room.height_m,
    }
    analyses = project.analyses
    if analysis_id is not None:
        analyses = [item for item in analyses if item.id == analysis_id]
    for analysis in analyses:
        for candidate in _analysis_room_candidates(analysis.input, room):
            for field, geometry_value in mapping.items():
                if field in candidate and candidate[field] != geometry_value:
                    conflicts.append(GeometryConflict(
                        analysis.id, room.name, field, candidate[field], geometry_value
                    ))
    return conflicts


def sync_room_geometry_to_analysis(project: Any, room: Room, analysis_id: str) -> dict[str, Any]:
    analysis = project.analysis_by_id(analysis_id)
    candidates = _analysis_room_candidates(analysis.input, room)
    if not candidates:
        raise ValueError(
            f"analysis {analysis.name!r} has no room matching layout room {room.name!r}"
        )
    if len(candidates) > 1:
        raise ValueError(
            f"analysis {analysis.name!r} has multiple rooms matching {room.name!r}; "
            "set a unique room name or analysis_room_ref"
        )
    target = candidates[0]
    before = {key: target.get(key) for key in ("length_m", "width_m", "height_m")}
    target["length_m"] = room.width_m
    target["width_m"] = room.depth_m
    target["height_m"] = room.height_m
    room.analysis_room_ref = str(target.get("id") or target.get("name") or room.name)
    return {
        "analysis_id": analysis.id,
        "analysis_name": analysis.name,
        "room_name": room.name,
        "before": before,
        "after": {
            "length_m": room.width_m,
            "width_m": room.depth_m,
            "height_m": room.height_m,
        },
        "mapping": {
            "layout.width_m": "analysis.length_m",
            "layout.depth_m": "analysis.width_m",
            "layout.height_m": "analysis.height_m",
        },
    }


def pressure_relationships(project: Any, floor: Any) -> list[dict[str, Any]]:
    name_to_room = {room.name: room for room in floor.rooms}
    links: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for analysis in project.analyses:
        raw_links = analysis.input.get("pressure_cascade") if isinstance(analysis.input, dict) else None
        if not isinstance(raw_links, list):
            continue
        for item in raw_links:
            if not isinstance(item, dict):
                continue
            high_name = item.get("higher_pressure_room")
            low_name = item.get("lower_pressure_room")
            if high_name not in name_to_room or low_name not in name_to_room:
                continue
            key = (analysis.id, str(high_name), str(low_name))
            if key in seen:
                continue
            seen.add(key)
            links.append({
                "analysis_id": analysis.id,
                "higher_room_id": name_to_room[high_name].id,
                "lower_room_id": name_to_room[low_name].id,
                "min_delta_pa": item.get("min_delta_pa"),
            })
    return links
