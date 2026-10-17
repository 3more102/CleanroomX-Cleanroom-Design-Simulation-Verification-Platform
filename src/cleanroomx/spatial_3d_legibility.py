"""Responsive, presentation-only 3D room chips and selected-room inspector HUD.

The camera projection, canonical spatial layout, engineering overlay values and
persistence stay in their existing modules. Nothing in this module simulates CFD.
"""
from __future__ import annotations

import math
from typing import Any, Iterable

CHIP_H = 23
CHIP_PAD_X = 9


def _intersects(a: tuple[float, float, float, float],
                b: tuple[float, float, float, float], gap: float = 4) -> bool:
    return not (
        a[2] + gap <= b[0] or b[2] + gap <= a[0]
        or a[3] + gap <= b[1] or b[3] + gap <= a[1]
    )


def _short(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > limit:
        return text[:limit - 1].rstrip() + "\u2026"
    return text


def room_hud_bounds(width: int, height: int, *, active: bool) -> tuple[int, int, int, int] | None:
    """Reserve space for the floating inspector only on a readable viewport."""
    if not active or width < 530 or height < 275:
        return None
    return width - 324, 12, width - 12, 180


def place_room_label_chips(
    entries: Iterable[dict],
    *,
    width: int,
    height: int,
    reserved: Iterable[tuple[float, float, float, float]] = (),
) -> list[dict]:
    """Place at most one chip per room without overlapping other chips or HUDs.

    Selected and hovered room labels take precedence. This is viewport-only:
    clipped/out-of-space labels are intentionally omitted, not moved into the
    model. Stable ordering keeps redraws predictable while the camera moves.
    """
    width, height = int(width), int(height)
    if width < 90 or height < 70:
        return []
    occupied = [tuple(map(float, rect)) for rect in reserved]
    placed: list[dict] = []
    seen: set[str] = set()
    options = ((0, -25), (0, -47), (0, 18), (0, -69),
               (-70, -35), (70, -35), (-100, 6), (100, 6),
               (0, -94), (-105, -70), (105, -70))
    ordered = sorted(
        entries,
        key=lambda e: (-int(e.get("priority", 0)), str(e.get("room_id", "")))
    )
    for entry in ordered:
        room_id = str(entry.get("room_id", "")).strip()
        if not room_id or room_id in seen:
            continue
        seen.add(room_id)
        try:
            ax, ay = float(entry["anchor"][0]), float(entry["anchor"][1])
        except (TypeError, KeyError, IndexError, ValueError):
            continue
        if not math.isfinite(ax) or not math.isfinite(ay):
            continue
        label = _short(entry.get("text"), 25)
        if not label:
            continue
        chip_w = min(190, max(65, 7.15 * len(label) + CHIP_PAD_X * 2))
        if chip_w > width - 12:
            continue
        for dx, dy in options:
            x = max(chip_w / 2 + 6, min(width - chip_w / 2 - 6, ax + dx))
            y = max(CHIP_H / 2 + 6, min(height - CHIP_H / 2 - 6, ay + dy))
            box = (x - chip_w / 2, y - CHIP_H / 2, x + chip_w / 2, y + CHIP_H / 2)
            if any(_intersects(box, other) for other in occupied):
                continue
            occupied.append(box)
            placed.append({
                "room_id": room_id, "text": label,
                "x": x, "y": y, "box": box,
                "anchor": (ax, ay), "priority": int(entry.get("priority", 0)),
            })
            break
    return placed


def draw_room_label_chips(
    canvas: Any, placements: list[dict], colors: dict[str, str],
) -> None:
    """Paint readable click-through room-label cards above devices and arrows."""
    for entry in placements:
        room_id = entry["room_id"]
        x0, y0, x1, y1 = entry["box"]
        anchor = entry["anchor"]
        tags = (f"room:{room_id}", "room3d", "room_label3d")
        accent = colors.get(room_id, "#7dd3fc")
        if abs(entry["x"] - anchor[0]) > 24 or abs(entry["y"] - anchor[1]) > 36:
            canvas.create_line(
                *anchor, entry["x"], entry["y"],
                fill="#7b91a9", width=1, dash=(3, 3), tags=tags,
            )
        canvas.create_rectangle(
            x0, y0, x1, y1,
            fill="#102235", outline=accent, width=2 if entry["priority"] else 1,
            tags=tags,
        )
        canvas.create_text(
            entry["x"], entry["y"], text=entry["text"],
            font=("TkDefaultFont", 9, "bold"),
            fill="#eef7ff", justify="center", tags=tags,
        )
    canvas.tag_raise("room_label3d")


def room_area_volume(room: dict) -> tuple[float, float]:
    """Exact dimensions-derived quantities, not solver predictions."""
    length = float(room["length_m"])
    width = float(room["width_m"])
    height = float(room["height_m"])
    if not all(math.isfinite(value) and value > 0 for value in (
        length, width, height,
    )):
        raise ValueError("Room dimensions must be finite and positive")
    return length * width, length * width * height


def _draw_details_card(
    canvas: Any, bounds: tuple[int, int, int, int],
    rows: list[tuple[str, str]],
) -> None:
    x0, y0, x1, y1 = bounds
    tags = ("room_details_hud",)
    canvas.create_rectangle(
        x0, y0, x1, y1,
        fill="#102235", outline="#4e6c8c", width=1, tags=tags,
    )
    for index, (text, color) in enumerate(rows[:7]):
        canvas.create_text(
            x0 + 10, y0 + 9 + index * 23, text=_short(text, 46),
            anchor="nw", fill=color,
            font=("TkDefaultFont", 9, "bold" if index < 2 else "normal"),
            tags=tags,
        )
    canvas.tag_raise("room_details_hud")


def draw_room_details_hud(
    canvas: Any, room: dict | None, *, width: int, height: int,
    selected: bool, overlay_title: str, overlay_label: str,
    device_count: int | None = None,
) -> tuple[int, int, int, int] | None:
    """Show room geometry, design inputs, and supplied engineering data."""
    bounds = room_hud_bounds(width, height, active=room is not None)
    if room is None or bounds is None:
        return None
    area, volume = room_area_volume(room)
    rows = [
        ("SELECTED ROOM" if selected else "ROOM UNDER CURSOR", "#70d8f8"),
        (_short(room.get("name", "Room"), 36), "#f4f8ff"),
    ]
    classification = str(room.get("classification") or "").strip()
    if classification:
        rows.append(("Project class: " + _short(classification, 27), "#afc2d7"))
    rows.append((
        f"L {room['length_m']:g}  W {room['width_m']:g}  H {room['height_m']:g} m",
        "#b8cce0",
    ))
    rows.append((f"Floor area {area:g} m²  |  Volume {volume:g} m³", "#b8cce0"))
    if device_count is not None:
        rows.append((f"Placed devices: {device_count}", "#b8cce0"))
    # Overlay values may come from a project design or a real analysis, so
    # never silently call these values verified or measured.
    if overlay_title.strip().lower() != "none":
        evidence = _short(overlay_label or "No result values available", 31)
        rows.append((_short(overlay_title, 12) + ": " + evidence, "#e3bd7c"))
    _draw_details_card(canvas, bounds, rows)
    return bounds


def draw_device_details_hud(
    canvas: Any, device: dict | None, *, width: int, height: int,
    selected: bool, room_name: str | None,
) -> tuple[int, int, int, int] | None:
    """Inspect a placed device without generating airflows or solver values."""
    bounds = room_hud_bounds(width, height, active=device is not None)
    if device is None or bounds is None:
        return None
    kind = str(device.get("type") or "device").replace("_", " ").title()
    rows = [
        ("SELECTED DEVICE" if selected else "DEVICE UNDER CURSOR", "#70d8f8"),
        (_short(device.get("name") or kind, 36), "#f4f8ff"),
        (f"Type: {kind}", "#b8cce0"),
        ("Room: " + _short(room_name or "Unassigned", 30), "#b8cce0"),
    ]
    coords = (
        device.get("x_m"), device.get("y_m"), device.get("z_m")
    )
    if all(isinstance(value, (int, float)) and not isinstance(value, bool)
           and math.isfinite(value) for value in coords):
        rows.append((
            f"X {coords[0]:g}   Y {coords[1]:g}   Z {coords[2]:g} m",
            "#b8cce0",
        ))
    dimensions = [
        f"{key[0].upper()} {device[key]:g}"
        for key in ("width_m", "height_m")
        if isinstance(device.get(key), (float, int))
        and not isinstance(device[key], bool) and math.isfinite(device[key])
    ]
    if dimensions:
        rows.append(("Size " + "  ".join(dimensions) + " m", "#b8cce0"))
    rows.append(("Placement only — no CFD result inferred", "#e3bd7c"))
    _draw_details_card(canvas, bounds, rows)
    return bounds
