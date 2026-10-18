"""Model-backed design-studio metrics; never reports configured values as CFD results."""
from __future__ import annotations

import math
from typing import Any, Mapping


def _dimension(value: Any) -> float:
    """Ignore malformed geometry instead of displaying fabricated measurements."""
    if isinstance(value, bool):
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return number if math.isfinite(number) and number > 0 else 0.0


def design_studio_snapshot(
    layout: Mapping[str, Any], *, selected_room_id: str | None = None
) -> dict[str, Any]:
    """Compute UI-only measurements from the live spatial model.

    Every object in ``devices`` (including doors, windows, and openings) counts
    exactly once as a placed object. Returned pressure is a *configured setpoint*,
    not a solver-computed value. Empty/invalid selections do not invent results.
    """
    raw_rooms = layout.get("rooms", [])
    raw_devices = layout.get("devices", [])
    rooms = [r for r in raw_rooms if isinstance(r, dict)] if isinstance(raw_rooms, list) else []
    devices = [d for d in raw_devices if isinstance(d, dict)] if isinstance(raw_devices, list) else []
    counts = {"FFU": 0, "Supply": 0, "Return / exhaust": 0, "Other": 0}
    room_device_counts: dict[str, int] = {}
    for device in devices:
        kind = str(device.get("type") or "").strip().lower()
        category = (
            "FFU" if kind == "ffu" else
            "Supply" if kind == "supply" else
            "Return / exhaust" if kind in {"return", "exhaust"} else
            "Other"
        )
        counts[category] += 1
        room_id = str(device.get("room_id") or "")
        room_device_counts[room_id] = room_device_counts.get(room_id, 0) + 1

    room_cards = []
    for room in rooms:
        length = _dimension(room.get("length_m"))
        width = _dimension(room.get("width_m"))
        height = _dimension(room.get("height_m"))
        room_id = str(room.get("id") or "")
        area = length * width
        volume = area * height
        pressure = room.get("pressure_pa")
        if isinstance(pressure, bool) or pressure is None:
            pressure = None
        else:
            try:
                pressure = float(pressure)
            except (TypeError, ValueError, OverflowError):
                pressure = None
            if pressure is not None and not math.isfinite(pressure):
                pressure = None
        room_cards.append({
            "id": room_id,
            "name": str(room.get("name") or room_id),
            "classification": str(room.get("classification") or ""),
            "x_m": float(room.get("x_m", 0.0)),
            "y_m": float(room.get("y_m", 0.0)),
            "length_m": length,
            "width_m": width,
            "height_m": height,
            "floor_area_m2": area,
            "volume_m3": volume,
            "device_count": room_device_counts.get(room_id, 0),
            "configured_pressure_pa": pressure,
        })
    selected = next((r for r in room_cards if r["id"] == selected_room_id), None)
    return {
        "room_count": len(room_cards),
        "floor_area_m2": sum(r["floor_area_m2"] for r in room_cards),
        "volume_m3": sum(r["volume_m3"] for r in room_cards),
        "placed_device_count": len(devices),
        "device_categories": counts,
        "rooms": room_cards,
        "selected_room": selected,
    }
