"""Read-only, model-derived data for the integrated Design Studio.

These functions do not import Tk, mutate project state or claim to provide
simulation results. All dimensional values are geometric calculations.
Inputs are the canonical layouts returned by normalize_layout.
"""

from __future__ import annotations

from typing import Any


def _device_groups(devices: list[dict]) -> dict[str, int]:
    groups = {"ffu": 0, "supply": 0, "return_exhaust": 0, "other": 0}
    for device in devices:
        device_type = str(device.get("type") or "").lower()
        if device_type in {"return", "exhaust"}:
            groups["return_exhaust"] += 1
        elif device_type in {"ffu", "supply"}:
            groups[device_type] += 1
        else:
            # Includes doors, windows, openings, sensors and equipment.
            groups["other"] += 1
    return groups


def dashboard_snapshot(layout: dict, selected_room_id: str | None = None) -> dict[str, Any]:
    """Compute live room/device cards and selected-room facts from the layout."""
    rooms = layout.get("rooms", [])
    devices = layout.get("devices", [])
    groups = _device_groups(devices)

    floor_area = sum(float(r["length_m"]) * float(r["width_m"]) for r in rooms)
    volume = sum(
        float(r["length_m"]) * float(r["width_m"]) * float(r["height_m"])
        for r in rooms
    )
    selected = next(
        (r for r in rooms if r["id"] == selected_room_id),
        None,
    )
    selected_details = None
    if selected is not None:
        length = float(selected["length_m"])
        width = float(selected["width_m"])
        height = float(selected["height_m"])
        selected_details = {
            "id": selected["id"],
            "name": selected["name"],
            "classification": selected.get("classification") or "Not specified",
            "length_m": length,
            "width_m": width,
            "height_m": height,
            "floor_area_m2": length * width,
            "volume_m3": length * width * height,
            "device_count": sum(d.get("room_id") == selected["id"] for d in devices),
            "device_groups": _device_groups(
                [d for d in devices if d.get("room_id") == selected["id"]]
            ),
            # A configured setpoint is NOT a solver-computed pressure.
            "pressure_setpoint_pa": selected.get("pressure_pa"),
        }

    return {
        "room_count": len(rooms),
        "floor_area_m2": floor_area,
        "volume_m3": volume,
        "placed_devices": len(devices),
        "device_groups": groups,
        "selected_room": selected_details,
    }


def navigator_rectangles(
    layout: dict,
    *,
    width_px: int = 240,
    height_px: int = 150,
    padding_px: int = 12,
    header_px: int = 26,
) -> list[dict[str, Any]]:
    """Fit top-down room rectangles into a miniature plan without distortion."""
    rooms = layout.get("rooms", [])
    if not rooms:
        return []

    left = min(float(r["x_m"]) for r in rooms)
    top = min(float(r["y_m"]) for r in rooms)
    right = max(float(r["x_m"]) + float(r["length_m"]) for r in rooms)
    bottom = max(float(r["y_m"]) + float(r["width_m"]) for r in rooms)
    span_x = max(right - left, 1e-9)
    span_y = max(bottom - top, 1e-9)
    available_w = max(1, width_px - 2 * padding_px)
    available_h = max(1, height_px - header_px - 2 * padding_px)
    scale = min(available_w / span_x, available_h / span_y)
    origin_x = (width_px - span_x * scale) / 2
    origin_y = header_px + (height_px - header_px - span_y * scale) / 2

    result = []
    for room in rooms:
        x = origin_x + (float(room["x_m"]) - left) * scale
        y = origin_y + (float(room["y_m"]) - top) * scale
        result.append(
            {
                "id": room["id"],
                "name": room["name"],
                "floor_area_m2": float(room["length_m"]) * float(room["width_m"]),
                "rect": (
                    x,
                    y,
                    x + float(room["length_m"]) * scale,
                    y + float(room["width_m"]) * scale,
                ),
            }
        )
    return result


def device_snapshot(layout: dict, device_id: str | None) -> dict[str, Any] | None:
    """Read-only selected-device facts for design inspection, never CFD output.

    Device x/y positions use the global plan coordinate system; device z_m is
    the configured relative floor offset from the spatial editor.
    """
    if device_id is None:
        return None
    device = next(
        (item for item in layout.get("devices", []) if item.get("id") == device_id),
        None,
    )
    if device is None:
        return None
    room_id = device.get("room_id")
    room = next(
        (item for item in layout.get("rooms", []) if item.get("id") == room_id),
        None,
    )
    return {
        "id": device["id"],
        "name": str(device.get("name") or device["id"]),
        "type": str(device.get("type") or "Unspecified"),
        "room_id": room_id,
        "room_name": str(room["name"]) if room else "Unassigned",
        "x_m": float(device["x_m"]),
        "y_m": float(device["y_m"]),
        "z_above_floor_m": float(device["z_m"]),
    }

def device_layer_category(device: dict) -> str:
    """Classify display-only equipment layers from canonical device types."""
    kind = str(device.get("type") or "").strip().lower()
    if kind in {"door", "window", "opening", "transfer"}:
        return "opening"
    if kind in {"ffu", "supply", "return", "exhaust"}:
        return "air"
    return "other"


def navigator_device_markers(
    layout: dict,
    *,
    width_px: int = 240,
    height_px: int = 150,
    padding_px: int = 12,
    header_px: int = 26,
) -> list[dict[str, Any]]:
    """Locate real devices using exactly the room navigator's model-to-pixel fit.

    This read-only transform deliberately derives its scale and origin from the
    same room rectangles shown on screen. It never alters room/device geometry
    or treats a device position as a CFD simulation result.
    """
    rectangles = navigator_rectangles(
        layout, width_px=width_px, height_px=height_px,
        padding_px=padding_px, header_px=header_px,
    )
    if not rectangles:
        return []
    room = layout["rooms"][0]
    length, width = float(room["length_m"]), float(room["width_m"])
    if length <= 0 or width <= 0:
        return []
    x0, y0, x1, y1 = rectangles[0]["rect"]
    x_scale = (x1 - x0) / length
    y_scale = (y1 - y0) / width
    markers = []
    for device in layout.get("devices", []):
        px = x0 + (float(device["x_m"]) - float(room["x_m"])) * x_scale
        py = y0 + (float(device["y_m"]) - float(room["y_m"])) * y_scale
        # Do not paint markers beyond the fitted plan into the navigator header
        # or room list. Such devices remain selectable from 2D/3D and search.
        if not (padding_px <= px <= width_px - padding_px
                and header_px <= py <= height_px - padding_px):
            continue
        kind = str(device.get("type") or "").strip().lower()
        category = device_layer_category(device)
        markers.append({
            "id": device["id"], "name": device.get("name") or device["id"],
            "room_id": device.get("room_id"),
            "type": kind, "category": category, "point": (px, py),
        })
    return markers
