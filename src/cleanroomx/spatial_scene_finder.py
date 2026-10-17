"""Deterministic read-only index used by the 3D room/device finder."""
from __future__ import annotations

from typing import Any


def scene_entries(layout: dict[str, Any], query: str = "", limit: int = 250) -> list[dict[str, str]]:
    """Search room/device names, kinds, IDs and assigned parent room names.

    No CAD values, verification state, or solver results are modified or inferred.
    A bounded list prevents expensive Tk updates for unusually large projects.
    """
    if limit < 1:
        raise ValueError("limit must be positive")
    rooms = list(layout.get("rooms", []))
    devices = list(layout.get("devices", []))
    room_names = {
        str(room["id"]): str(room.get("name") or room["id"])
        for room in rooms
    }
    search = " ".join(str(query).casefold().split())
    rows: list[dict[str, str]] = []
    for kind, items in (("room", rooms), ("device", devices)):
        for item in items:
            item_id = str(item["id"])
            name = str(item.get("name") or item_id)
            item_type = (
                "Room" if kind == "room"
                else str(item.get("type") or "device").replace("_", " ").title()
            )
            parent = (
                "" if kind == "room" else
                room_names.get(str(item.get("room_id") or ""), "Unassigned")
            )
            haystack = " ".join((kind, item_type, name, item_id, parent)).casefold()
            if search and not all(word in haystack for word in search.split()):
                continue
            rows.append({
                "kind": kind,
                "id": item_id,
                "name": name,
                "type": item_type,
                "room": parent,
            })
    rows.sort(key=lambda x: (x["kind"] != "room", x["name"].casefold(), x["id"]))
    return rows[:limit]
