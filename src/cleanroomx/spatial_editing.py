"""Atomic spatial editing operations shared by the desktop workspace.

These operations return a validated replacement layout. They never mutate the
caller's layout or copy engineering evidence onto a newly created room.
"""
from __future__ import annotations

import copy
import math
import uuid
from collections.abc import Mapping

from .spatial_integrity import validate_spatial_layout_document


_FIELD_LABELS = {
    "x_m": "X (m)",
    "y_m": "Y (m)",
    "z_m": "Z (m)",
    "length_m": "Length (m)",
    "width_m": "Width (m)",
    "height_m": "Height (m)",
    "floor_elevation_m": "Floor elevation (m)",
    "pressure_pa": "Pressure (Pa)",
    "orientation_deg": "Orientation (degrees)",
}


def _selected_item(layout: dict, kind: str, item_id: str) -> dict:
    if kind not in {"room", "device"}:
        raise ValueError("Select a room or device first")
    collection = layout["rooms" if kind == "room" else "devices"]
    for item in collection:
        if item["id"] == item_id:
            return item
    raise ValueError("The selected item no longer exists")


def _number(text: str, field: str, *, positive: bool = False) -> float:
    label = _FIELD_LABELS[field]
    try:
        number = float(text)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number")
    if positive and number <= 0:
        raise ValueError(f"{label} must be greater than zero")
    return number


def update_spatial_properties(
    layout: dict, kind: str, item_id: str, values: Mapping[str, str]
) -> dict:
    """Apply supplied inspector fields together, or leave the layout untouched.

    Blank optional text/pressure removes that property. Numeric geometry fields
    cannot be blank. Moving a room translates its assigned devices in X/Y;
    device Z remains relative to the room floor.
    """
    candidate = copy.deepcopy(layout)
    item = _selected_item(candidate, kind, item_id)
    old_x, old_y = item["x_m"], item["y_m"]
    if "name" in values:
        name = values["name"].strip()
        if not name:
            raise ValueError("Name must not be blank")
        item["name"] = name

    fields = ("x_m", "y_m")
    if kind == "room":
        fields += ("length_m", "width_m", "height_m", "floor_elevation_m")
    else:
        fields += ("z_m", "width_m", "height_m", "orientation_deg")
    for field in fields:
        if field in values:
            item[field] = _number(
                values[field].strip(), field,
                positive=field in {"length_m", "width_m", "height_m"},
            )

    if kind == "room":
        if "pressure_pa" in values:
            pressure = values["pressure_pa"].strip()
            if pressure:
                item["pressure_pa"] = _number(pressure, "pressure_pa")
            else:
                item.pop("pressure_pa", None)
        for field in ("classification", "analysis_room_name"):
            if field in values:
                text = values[field].strip()
                if text:
                    item[field] = text
                else:
                    item.pop(field, None)
        dx, dy = item["x_m"] - old_x, item["y_m"] - old_y
        for device in candidate["devices"]:
            if device.get("room_id") == item_id:
                device["x_m"] += dx
                device["y_m"] += dy
    else:
        if "room_id" in values:
            room_id = values["room_id"].strip()
            if room_id and not any(room["id"] == room_id for room in candidate["rooms"]):
                raise ValueError("Room ID must identify an existing room, or be blank")
            item["room_id"] = room_id or None
        for field in ("wall_side", "swing"):
            if field in values:
                text = values[field].strip()
                if field == "wall_side":
                    text = text.lower()
                    if text and text not in {"north", "south", "east", "west"}:
                        raise ValueError("Wall side must be north, south, east, west, or blank")
                if text:
                    item[field] = text
                else:
                    item.pop(field, None)

    validate_spatial_layout_document(candidate)
    return candidate


def _copy_name(name: str, items: list[dict]) -> str:
    names = {item["name"].strip().casefold() for item in items}
    base = f"{name} copy"
    candidate = base
    index = 2
    while candidate.casefold() in names:
        candidate = f"{base} {index}"
        index += 1
    return candidate


def _new_id(kind: str, used: set[str]) -> str:
    while True:
        candidate = f"{kind}-{uuid.uuid4().hex}"
        if candidate not in used:
            used.add(candidate)
            return candidate


def _offset_device(device: dict, layout: dict) -> None:
    """Separate a device copy while keeping valid anchors inside its room."""
    room = next(
        (room for room in layout["rooms"] if room["id"] == device.get("room_id")),
        None,
    )
    side = device.get("wall_side")
    axes = [("x_m", "length_m"), ("y_m", "width_m")]
    if device["type"] in {"door", "window", "opening", "transfer"}:
        if side in {"north", "south"}:
            axes = axes[:1]
        elif side in {"east", "west"}:
            axes = axes[1:]
    for axis, dimension in axes:
        current = device[axis]
        step = layout["grid_m"]
        if room is None:
            device[axis] += step
        elif room[axis] <= current <= room[axis] + room[dimension]:
            if current + step <= room[axis] + room[dimension]:
                device[axis] += step
            elif current - step >= room[axis]:
                device[axis] -= step


def duplicate_spatial_item(layout: dict, kind: str, item_id: str) -> tuple[dict, str]:
    """Duplicate a room with its devices, or one device, with fresh identities.

    Room copies are placed to the right of the existing layout. Pressure,
    analysis-room links and synchronization records are not duplicated: those
    describe the original room's engineering evidence, not the new room.
    """
    candidate = copy.deepcopy(layout)
    source = _selected_item(candidate, kind, item_id)
    duplicate = copy.deepcopy(source)
    used = {item["id"] for item in candidate["rooms"] + candidate["devices"]}
    duplicate["id"] = _new_id(kind, used)
    collection = candidate["rooms" if kind == "room" else "devices"]
    duplicate["name"] = _copy_name(source["name"], collection)

    if kind == "room":
        right = max(room["x_m"] + room["length_m"] for room in candidate["rooms"])
        duplicate["x_m"] = right + max(candidate["grid_m"], 1.0)
        if not math.isfinite(duplicate["x_m"]) or duplicate["x_m"] <= right:
            raise ValueError("Room copy cannot be placed at these coordinate magnitudes")
        dx = duplicate["x_m"] - source["x_m"]
        duplicate.pop("pressure_pa", None)
        duplicate.pop("analysis_room_name", None)
        for device in list(candidate["devices"]):
            if device.get("room_id") == item_id:
                child = copy.deepcopy(device)
                child["id"] = _new_id("device", used)
                child["room_id"] = duplicate["id"]
                child["x_m"] += dx
                candidate["devices"].append(child)
    else:
        _offset_device(duplicate, candidate)

    collection.append(duplicate)
    validate_spatial_layout_document(candidate)
    return candidate, duplicate["id"]
