from __future__ import annotations

from dataclasses import dataclass
from html import escape
import copy
import csv
import io
import math
import uuid
from typing import Any, Callable

import tkinter as tk
from tkinter import filedialog, messagebox, ttk


SPATIAL_METADATA_KEY = "spatial_layout"
SPATIAL_LAYOUT_VERSION = 1
SPATIAL_HISTORY_LIMIT = 100
DEVICE_TYPES = ("door", "supply", "return", "exhaust", "ffu", "equipment", "sensor")
RESIZE_HANDLES = ("nw", "n", "ne", "e", "se", "s", "sw", "w")
SMART_ALIGN_TOLERANCE_PX = 8.0


def _finite_number(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _positive(value: Any, default: float) -> float:
    number = _finite_number(value, default)
    return number if number > 0 else default


def _room_id(name: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in name).strip("-")
    return slug or f"room-{uuid.uuid4().hex[:8]}"


def empty_layout() -> dict:
    return {
        "version": SPATIAL_LAYOUT_VERSION,
        "grid_m": 0.5,
        "rooms": [],
        "devices": [],
        "view": {
            "zoom_2d": 1.0,
            "pan_x": 0.0,
            "pan_y": 0.0,
            "azimuth_deg": 35.0,
            "elevation_deg": 28.0,
            "zoom_3d": 1.0,
            "pan_3d_x": 0.0,
            "pan_3d_y": 0.0,
        },
    }


def normalize_layout(value: Any) -> dict:
    source = value if isinstance(value, dict) else {}
    result = empty_layout()
    result["grid_m"] = _positive(source.get("grid_m"), 0.5)

    rooms: list[dict] = []
    used_ids: set[str] = set()
    raw_rooms = source.get("rooms", [])
    if isinstance(raw_rooms, list):
        for index, raw in enumerate(raw_rooms):
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name") or f"Room {index + 1}").strip() or f"Room {index + 1}"
            room_id = str(raw.get("id") or _room_id(name)).strip()
            if not room_id or room_id in used_ids:
                room_id = f"room-{uuid.uuid4().hex[:8]}"
            used_ids.add(room_id)
            room = {
                "id": room_id,
                "name": name,
                "x_m": _finite_number(raw.get("x_m"), 0.0),
                "y_m": _finite_number(raw.get("y_m"), 0.0),
                "length_m": _positive(raw.get("length_m"), 4.0),
                "width_m": _positive(raw.get("width_m"), 4.0),
                "height_m": _positive(raw.get("height_m"), 3.0),
            }
            if raw.get("pressure_pa") is not None:
                room["pressure_pa"] = _finite_number(raw.get("pressure_pa"), 0.0)
            rooms.append(room)
    result["rooms"] = rooms

    devices: list[dict] = []
    raw_devices = source.get("devices", [])
    if isinstance(raw_devices, list):
        for raw in raw_devices:
            if not isinstance(raw, dict):
                continue
            device_type = str(raw.get("type") or "equipment").lower()
            if device_type not in DEVICE_TYPES:
                device_type = "equipment"
            device_id = str(raw.get("id") or f"device-{uuid.uuid4().hex[:8]}")
            devices.append(
                {
                    "id": device_id,
                    "type": device_type,
                    "name": str(raw.get("name") or device_type.upper()),
                    "room_id": raw.get("room_id"),
                    "x_m": _finite_number(raw.get("x_m"), 0.0),
                    "y_m": _finite_number(raw.get("y_m"), 0.0),
                    "z_m": _finite_number(raw.get("z_m"), 0.0),
                }
            )
    result["devices"] = devices

    view = source.get("view", {})
    if isinstance(view, dict):
        result["view"].update(
            {
                "zoom_2d": max(0.2, min(8.0, _positive(view.get("zoom_2d"), 1.0))),
                "pan_x": _finite_number(view.get("pan_x"), 0.0),
                "pan_y": _finite_number(view.get("pan_y"), 0.0),
                "azimuth_deg": _finite_number(view.get("azimuth_deg"), 35.0),
                "elevation_deg": max(5.0, min(75.0, _finite_number(view.get("elevation_deg"), 28.0))),
                "zoom_3d": max(0.2, min(8.0, _positive(view.get("zoom_3d"), 1.0))),
                "pan_3d_x": _finite_number(view.get("pan_3d_x"), 0.0),
                "pan_3d_y": _finite_number(view.get("pan_3d_y"), 0.0),
            }
        )
    return result


def room_overlap_conflicts(rooms: list[dict]) -> list[dict]:
    """Return deterministic positive-area intersections between room footprints.

    Edge/corner touching is not an overlap. Each room pair appears at most once,
    in input order, with the exact intersection rectangle and area.
    """

    conflicts: list[dict] = []
    epsilon = 1e-9
    for index, room_a in enumerate(rooms):
        if not isinstance(room_a, dict):
            continue
        ax0 = _finite_number(room_a.get("x_m"), 0.0)
        ay0 = _finite_number(room_a.get("y_m"), 0.0)
        ax1 = ax0 + _positive(room_a.get("length_m"), 0.0)
        ay1 = ay0 + _positive(room_a.get("width_m"), 0.0)

        for room_b in rooms[index + 1 :]:
            if not isinstance(room_b, dict):
                continue
            bx0 = _finite_number(room_b.get("x_m"), 0.0)
            by0 = _finite_number(room_b.get("y_m"), 0.0)
            bx1 = bx0 + _positive(room_b.get("length_m"), 0.0)
            by1 = by0 + _positive(room_b.get("width_m"), 0.0)

            x0 = max(ax0, bx0)
            y0 = max(ay0, by0)
            x1 = min(ax1, bx1)
            y1 = min(ay1, by1)
            length_m = x1 - x0
            width_m = y1 - y0
            if length_m <= epsilon or width_m <= epsilon:
                continue

            conflicts.append(
                {
                    "room_a_id": str(room_a.get("id") or ""),
                    "room_b_id": str(room_b.get("id") or ""),
                    "x_m": x0,
                    "y_m": y0,
                    "length_m": length_m,
                    "width_m": width_m,
                    "area_m2": length_m * width_m,
                }
            )
    return conflicts


def nearest_nonoverlap_room_position(
    room: dict, rooms: list[dict]
) -> tuple[float, float]:
    """Return the nearest deterministic conflict-free XY position for a room.

    Candidate positions are formed from the current coordinates and every
    neighboring room boundary. Positive-area overlap is forbidden while edge
    and corner touching remain valid. Ties are resolved deterministically.
    """

    room_id = room.get("id")
    x0 = _finite_number(room.get("x_m"), 0.0)
    y0 = _finite_number(room.get("y_m"), 0.0)
    length_m = _positive(room.get("length_m"), 0.0)
    width_m = _positive(room.get("width_m"), 0.0)
    epsilon = 1e-9

    blockers = [
        other
        for other in rooms
        if isinstance(other, dict)
        and other is not room
        and not (room_id is not None and other.get("id") == room_id)
    ]

    def overlaps_at(x_m: float, y_m: float) -> bool:
        x1 = x_m + length_m
        y1 = y_m + width_m
        for other in blockers:
            ox0 = _finite_number(other.get("x_m"), 0.0)
            oy0 = _finite_number(other.get("y_m"), 0.0)
            ox1 = ox0 + _positive(other.get("length_m"), 0.0)
            oy1 = oy0 + _positive(other.get("width_m"), 0.0)
            if (
                min(x1, ox1) - max(x_m, ox0) > epsilon
                and min(y1, oy1) - max(y_m, oy0) > epsilon
            ):
                return True
        return False

    if not overlaps_at(x0, y0):
        return x0, y0

    x_candidates = {x0}
    y_candidates = {y0}
    for other in blockers:
        ox0 = _finite_number(other.get("x_m"), 0.0)
        oy0 = _finite_number(other.get("y_m"), 0.0)
        ox1 = ox0 + _positive(other.get("length_m"), 0.0)
        oy1 = oy0 + _positive(other.get("width_m"), 0.0)
        x_candidates.update((ox0 - length_m, ox1))
        y_candidates.update((oy0 - width_m, oy1))

    best: tuple[tuple[float, float, float, float, float, float], float, float] | None = None
    for candidate_x in sorted(x_candidates):
        for candidate_y in sorted(y_candidates):
            if overlaps_at(candidate_x, candidate_y):
                continue
            dx = candidate_x - x0
            dy = candidate_y - y0
            score = (
                dx * dx + dy * dy,
                abs(dx) + abs(dy),
                abs(dx),
                abs(dy),
                candidate_x,
                candidate_y,
            )
            if best is None or score < best[0]:
                best = (score, candidate_x, candidate_y)

    if best is None:
        return x0, y0
    return best[1], best[2]


def resolve_room_overlaps(rooms: list[dict]) -> list[dict]:
    """Return deterministic moves that eliminate positive-area room overlaps.

    Rooms are processed in input order. Earlier rooms remain fixed while each
    later room moves only when required to avoid the rooms already placed.
    The input room dictionaries are never mutated.
    """

    placed: list[dict] = []
    moves: list[dict] = []
    epsilon = 1e-9

    for source in rooms:
        if not isinstance(source, dict):
            continue
        room = copy.deepcopy(source)
        source_x = _finite_number(source.get("x_m"), 0.0)
        source_y = _finite_number(source.get("y_m"), 0.0)
        target_x, target_y = nearest_nonoverlap_room_position(
            room, [*placed, room]
        )
        dx = target_x - source_x
        dy = target_y - source_y
        room["x_m"] = target_x
        room["y_m"] = target_y
        placed.append(room)

        if abs(dx) <= epsilon and abs(dy) <= epsilon:
            continue
        moves.append(
            {
                "room_id": str(source.get("id") or ""),
                "x_m": target_x,
                "y_m": target_y,
                "dx_m": dx,
                "dy_m": dy,
            }
        )

    return moves


def next_room_overlap_conflict(
    rooms: list[dict], cursor: Any = -1
) -> dict | None:
    """Return the next overlap conflict in stable pair order for operator review.

    The returned record is a copy enriched with a zero-based cursor, total
    conflict count, and human-readable room names. The input is never mutated.
    """

    conflicts = room_overlap_conflicts(rooms)
    if not conflicts:
        return None

    try:
        previous = int(cursor)
    except (TypeError, ValueError):
        previous = -1
    index = (previous + 1) % len(conflicts)

    room_names = {
        str(room.get("id") or ""): str(
            room.get("name") or room.get("id") or "Unnamed room"
        )
        for room in rooms
        if isinstance(room, dict)
    }
    conflict = copy.deepcopy(conflicts[index])
    conflict.update(
        {
            "index": index,
            "count": len(conflicts),
            "room_a_name": room_names.get(
                conflict["room_a_id"], conflict["room_a_id"] or "Unnamed room"
            ),
            "room_b_name": room_names.get(
                conflict["room_b_id"], conflict["room_b_id"] or "Unnamed room"
            ),
        }
    )
    return conflict


def spatial_layout_summary(value: Any) -> dict:
    """Return operator-facing spatial metrics without changing the stored model."""
    layout = normalize_layout(value)
    rooms = layout["rooms"]
    devices = layout["devices"]
    room_ids = {room["id"] for room in rooms}
    footprint_m2 = sum(room["length_m"] * room["width_m"] for room in rooms)
    volume_m3 = sum(
        room["length_m"] * room["width_m"] * room["height_m"] for room in rooms
    )
    pressures = [
        room["pressure_pa"] for room in rooms if room.get("pressure_pa") is not None
    ]
    device_counts = {
        device_type: sum(1 for device in devices if device["type"] == device_type)
        for device_type in DEVICE_TYPES
    }
    unassigned_devices = sum(
        1 for device in devices if device.get("room_id") not in room_ids
    )
    overlap_conflicts = room_overlap_conflicts(rooms)
    if rooms:
        min_x = min(room["x_m"] for room in rooms)
        min_y = min(room["y_m"] for room in rooms)
        max_x = max(room["x_m"] + room["length_m"] for room in rooms)
        max_y = max(room["y_m"] + room["width_m"] for room in rooms)
        extents_m = {"width": max_x - min_x, "height": max_y - min_y}
    else:
        extents_m = {"width": 0.0, "height": 0.0}

    return {
        "room_count": len(rooms),
        "device_count": len(devices),
        "footprint_m2": footprint_m2,
        "volume_m3": volume_m3,
        "pressure_min_pa": min(pressures) if pressures else None,
        "pressure_max_pa": max(pressures) if pressures else None,
        "device_counts": device_counts,
        "unassigned_device_count": unassigned_devices,
        "room_overlap_count": len(overlap_conflicts),
        "room_overlap_area_m2": sum(item["area_m2"] for item in overlap_conflicts),
        "extents_m": extents_m,
    }


def derive_layout_from_analysis(analysis: Any) -> dict:
    layout = empty_layout()
    if analysis is None or not isinstance(getattr(analysis, "input", None), dict):
        return layout

    payload = analysis.input
    kind = getattr(analysis, "kind", "")
    if kind == "room_verification":
        raw_rooms = [payload]
    elif kind == "project_verification":
        raw_rooms = payload.get("rooms", [])
    else:
        raw_rooms = []

    x_cursor = 0.0
    for index, raw in enumerate(raw_rooms):
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or f"Room {index + 1}")
        length = _positive(raw.get("length_m"), 4.0)
        width = _positive(raw.get("width_m"), 4.0)
        height = _positive(raw.get("height_m"), 3.0)
        room = {
            "id": _room_id(name),
            "name": name,
            "x_m": x_cursor,
            "y_m": 0.0,
            "length_m": length,
            "width_m": width,
            "height_m": height,
        }
        if raw.get("observed_pressure_pa") is not None:
            room["pressure_pa"] = _finite_number(raw.get("observed_pressure_pa"), 0.0)
        layout["rooms"].append(room)
        x_cursor += length + 1.0
    return layout


def ensure_project_layout(project: Any, analysis: Any = None) -> dict:
    metadata = getattr(project, "metadata", None)
    if not isinstance(metadata, dict):
        project.metadata = {}
        metadata = project.metadata

    raw = metadata.get(SPATIAL_METADATA_KEY)
    if isinstance(raw, dict):
        normalized = normalize_layout(raw)
        metadata[SPATIAL_METADATA_KEY] = normalized
        return normalized

    normalized = derive_layout_from_analysis(analysis)
    if not normalized["rooms"]:
        for candidate in getattr(project, "analyses", []):
            normalized = derive_layout_from_analysis(candidate)
            if normalized["rooms"]:
                break

    # Do not persist an empty auto-layout. This lets a later verification analysis
    # seed the workspace without overwriting a deliberately persisted empty layout.
    if normalized["rooms"]:
        metadata[SPATIAL_METADATA_KEY] = normalized
    return normalized


def sync_layout_to_analysis(layout: dict, analysis: Any) -> bool:
    if analysis is None or not isinstance(getattr(analysis, "input", None), dict):
        return False
    rooms = normalize_layout(layout)["rooms"]
    if not rooms:
        return False

    changed = False
    if getattr(analysis, "kind", "") == "room_verification":
        source = rooms[0]
        for key in ("name", "length_m", "width_m", "height_m"):
            value = source[key]
            if analysis.input.get(key) != value:
                analysis.input[key] = value
                changed = True
        if "observed_pressure_pa" in analysis.input and "pressure_pa" in source:
            if analysis.input.get("observed_pressure_pa") != source["pressure_pa"]:
                analysis.input["observed_pressure_pa"] = source["pressure_pa"]
                changed = True
        return changed

    if getattr(analysis, "kind", "") != "project_verification":
        return False
    raw_rooms = analysis.input.get("rooms")
    if not isinstance(raw_rooms, list):
        return False

    by_name = {str(room.get("name")): room for room in raw_rooms if isinstance(room, dict)}
    for source in rooms:
        target = by_name.get(source["name"])
        if target is None:
            continue
        for key in ("length_m", "width_m", "height_m"):
            if target.get(key) != source[key]:
                target[key] = source[key]
                changed = True
        if "observed_pressure_pa" in target and "pressure_pa" in source:
            if target.get("observed_pressure_pa") != source["pressure_pa"]:
                target["observed_pressure_pa"] = source["pressure_pa"]
                changed = True
    return changed


def _pressure_fill(pressure: Any, min_pressure: float | None, max_pressure: float | None) -> str:
    if pressure is None or min_pressure is None or max_pressure is None:
        return "#dfe7ef"
    if max_pressure <= min_pressure:
        ratio = 0.5
    else:
        ratio = (_finite_number(pressure, min_pressure) - min_pressure) / (max_pressure - min_pressure)
    ratio = max(0.0, min(1.0, ratio))
    # Low pressure: cool blue. High pressure: warm amber.
    r = int(90 + 145 * ratio)
    g = int(150 + 55 * (1.0 - abs(ratio - 0.5) * 2.0))
    b = int(225 - 135 * ratio)
    return f"#{r:02x}{g:02x}{b:02x}"


def spatial_layout_svg(
    value: Any,
    *,
    pixels_per_m: float = 80.0,
    padding_m: float = 0.5,
) -> str:
    """Render the canonical 2D spatial model as deterministic standalone SVG."""

    layout = normalize_layout(value)
    rooms = layout["rooms"]
    devices = layout["devices"]
    scale = max(10.0, _positive(pixels_per_m, 80.0))
    padding = max(0.0, _finite_number(padding_m, 0.5))

    xs: list[float] = []
    ys: list[float] = []
    for room in rooms:
        xs.extend((room["x_m"], room["x_m"] + room["length_m"]))
        ys.extend((room["y_m"], room["y_m"] + room["width_m"]))
    for device in devices:
        xs.append(device["x_m"])
        ys.append(device["y_m"])

    if xs and ys:
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
    else:
        min_x, min_y, max_x, max_y = 0.0, 0.0, 10.0, 8.0

    width_m = max(1.0, max_x - min_x + 2.0 * padding)
    height_m = max(1.0, max_y - min_y + 2.0 * padding)
    width_px = width_m * scale
    height_px = height_m * scale

    def sx(x_m: float) -> float:
        return (x_m - min_x + padding) * scale

    def sy(y_m: float) -> float:
        return (y_m - min_y + padding) * scale

    def num(value: float) -> str:
        return f"{value:.3f}".rstrip("0").rstrip(".")

    pressures = [
        room.get("pressure_pa")
        for room in rooms
        if room.get("pressure_pa") is not None
    ]
    pmin = min(pressures) if pressures else None
    pmax = max(pressures) if pressures else None
    symbols = {
        "door": "D",
        "supply": "S",
        "return": "R",
        "exhaust": "E",
        "ffu": "F",
        "equipment": "Q",
        "sensor": "●",
    }

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            '<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{num(width_px)}" height="{num(height_px)}" '
            f'viewBox="0 0 {num(width_px)} {num(height_px)}">'
        ),
        "  <title>CleanroomX 2D spatial plan</title>",
        '  <rect width="100%" height="100%" fill="#ffffff"/>',
        '  <g id="rooms">',
    ]

    for room in rooms:
        x = sx(room["x_m"])
        y = sy(room["y_m"])
        width = room["length_m"] * scale
        height = room["width_m"] * scale
        fill = _pressure_fill(room.get("pressure_pa"), pmin, pmax)
        room_id = escape(str(room["id"]), quote=True)
        room_name = escape(str(room["name"]))
        pressure_text = (
            ""
            if room.get("pressure_pa") is None
            else f" · {room['pressure_pa']:g} Pa"
        )
        label = escape(
            f"{room['length_m']:g} × {room['width_m']:g} m{pressure_text}"
        )
        cx = x + width / 2.0
        cy = y + height / 2.0
        lines.extend(
            [
                (
                    f'    <rect x="{num(x)}" y="{num(y)}" '
                    f'width="{num(width)}" height="{num(height)}" '
                    f'fill="{fill}" stroke="#34495e" stroke-width="2" '
                    f'data-room-id="{room_id}"/>'
                ),
                (
                    f'    <text x="{num(cx)}" y="{num(cy - 6)}" '
                    'text-anchor="middle" font-family="sans-serif" '
                    f'font-size="13" font-weight="700">{room_name}</text>'
                ),
                (
                    f'    <text x="{num(cx)}" y="{num(cy + 12)}" '
                    'text-anchor="middle" font-family="sans-serif" '
                    f'font-size="11">{label}</text>'
                ),
            ]
        )
    lines.append("  </g>")
    lines.append('  <g id="devices">')

    for device in devices:
        x = sx(device["x_m"])
        y = sy(device["y_m"])
        device_id = escape(str(device["id"]), quote=True)
        device_type = escape(str(device["type"]), quote=True)
        name = escape(str(device["name"]))
        symbol = escape(symbols.get(device["type"], "?"))
        title = escape(
            f"{device['name']} · {device['type']} · z={device['z_m']:g} m"
        )
        lines.extend(
            [
                (
                    f'    <g data-device-id="{device_id}" '
                    f'data-device-type="{device_type}">'
                ),
                (
                    f'      <circle cx="{num(x)}" cy="{num(y)}" r="7" '
                    'fill="#ffffff" stroke="#2c3e50" stroke-width="2"/>'
                ),
                (
                    f'      <text x="{num(x)}" y="{num(y + 4)}" '
                    'text-anchor="middle" font-family="sans-serif" '
                    f'font-size="10" font-weight="700">{symbol}</text>'
                ),
                f"      <title>{title}</title>",
                (
                    f'      <text x="{num(x + 10)}" y="{num(y - 10)}" '
                    'font-family="sans-serif" font-size="10">'
                    f"{name}</text>"
                ),
                "    </g>",
            ]
        )
    lines.extend(["  </g>", "</svg>", ""])
    return "\n".join(lines)


def spatial_layout_schedule_csv(value: Any) -> str:
    """Export a deterministic room/device engineering schedule as UTF-8 CSV."""

    layout = normalize_layout(value)
    rooms = layout["rooms"]
    devices = layout["devices"]
    room_names = {room["id"]: room["name"] for room in rooms}
    fieldnames = [
        "record_type",
        "id",
        "name",
        "device_type",
        "room_id",
        "room_name",
        "x_m",
        "y_m",
        "z_m",
        "length_m",
        "width_m",
        "height_m",
        "area_m2",
        "volume_m3",
        "pressure_pa",
    ]

    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=fieldnames,
        lineterminator="\n",
        extrasaction="ignore",
    )
    writer.writeheader()

    for room in rooms:
        writer.writerow(
            {
                "record_type": "room",
                "id": room["id"],
                "name": room["name"],
                "room_id": room["id"],
                "room_name": room["name"],
                "x_m": f'{room["x_m"]:g}',
                "y_m": f'{room["y_m"]:g}',
                "length_m": f'{room["length_m"]:g}',
                "width_m": f'{room["width_m"]:g}',
                "height_m": f'{room["height_m"]:g}',
                "area_m2": f'{room["length_m"] * room["width_m"]:g}',
                "volume_m3": (
                    f'{room["length_m"] * room["width_m"] * room["height_m"]:g}'
                ),
                "pressure_pa": (
                    ""
                    if room.get("pressure_pa") is None
                    else f'{room["pressure_pa"]:g}'
                ),
            }
        )

    for device in devices:
        room_id = device.get("room_id")
        writer.writerow(
            {
                "record_type": "device",
                "id": device["id"],
                "name": device["name"],
                "device_type": device["type"],
                "room_id": "" if room_id is None else room_id,
                "room_name": room_names.get(room_id, ""),
                "x_m": f'{device["x_m"]:g}',
                "y_m": f'{device["y_m"]:g}',
                "z_m": f'{device["z_m"]:g}',
            }
        )

    return stream.getvalue()


def spatial_overlap_report_csv(value: Any) -> str:
    """Export deterministic room-overlap QA evidence as UTF-8 CSV."""

    layout = normalize_layout(value)
    rooms = layout["rooms"]
    rooms_by_id = {room["id"]: room for room in rooms}
    fieldnames = [
        "conflict_index",
        "room_a_id",
        "room_a_name",
        "room_b_id",
        "room_b_name",
        "overlap_x_m",
        "overlap_y_m",
        "overlap_length_m",
        "overlap_width_m",
        "overlap_area_m2",
        "room_a_area_m2",
        "room_b_area_m2",
        "room_a_overlap_pct",
        "room_b_overlap_pct",
    ]

    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=fieldnames,
        lineterminator="\n",
        extrasaction="ignore",
    )
    writer.writeheader()

    for index, conflict in enumerate(room_overlap_conflicts(rooms), start=1):
        room_a = rooms_by_id.get(conflict["room_a_id"])
        room_b = rooms_by_id.get(conflict["room_b_id"])
        if room_a is None or room_b is None:
            continue
        room_a_area = room_a["length_m"] * room_a["width_m"]
        room_b_area = room_b["length_m"] * room_b["width_m"]
        overlap_area = conflict["area_m2"]
        writer.writerow(
            {
                "conflict_index": index,
                "room_a_id": room_a["id"],
                "room_a_name": room_a["name"],
                "room_b_id": room_b["id"],
                "room_b_name": room_b["name"],
                "overlap_x_m": f'{conflict["x_m"]:g}',
                "overlap_y_m": f'{conflict["y_m"]:g}',
                "overlap_length_m": f'{conflict["length_m"]:g}',
                "overlap_width_m": f'{conflict["width_m"]:g}',
                "overlap_area_m2": f"{overlap_area:g}",
                "room_a_area_m2": f"{room_a_area:g}",
                "room_b_area_m2": f"{room_b_area:g}",
                "room_a_overlap_pct": f"{100.0 * overlap_area / room_a_area:.6g}",
                "room_b_overlap_pct": f"{100.0 * overlap_area / room_b_area:.6g}",
            }
        )

    return stream.getvalue()


def resize_room(
    room: dict,
    handle: str,
    target_x_m: float,
    target_y_m: float,
    *,
    grid_m: float | None = None,
    min_size_m: float = 0.25,
) -> bool:
    """Resize a room from one edge/corner while preserving the opposite edge."""
    if handle not in RESIZE_HANDLES:
        return False

    x0 = _finite_number(room.get("x_m"), 0.0)
    y0 = _finite_number(room.get("y_m"), 0.0)
    x1 = x0 + _positive(room.get("length_m"), 4.0)
    y1 = y0 + _positive(room.get("width_m"), 4.0)
    original = (x0, y0, x1, y1)

    grid = _positive(grid_m, 0.0) if grid_m is not None else 0.0
    min_size = max(0.01, _positive(min_size_m, 0.25), grid)
    tx = _finite_number(target_x_m, x0)
    ty = _finite_number(target_y_m, y0)
    if grid > 0:
        tx = round(tx / grid) * grid
        ty = round(ty / grid) * grid

    if "w" in handle:
        x0 = min(tx, x1 - min_size)
    if "e" in handle:
        x1 = max(tx, x0 + min_size)
    if "n" in handle:
        y0 = min(ty, y1 - min_size)
    if "s" in handle:
        y1 = max(ty, y0 + min_size)

    room["x_m"] = x0
    room["y_m"] = y0
    room["length_m"] = x1 - x0
    room["width_m"] = y1 - y0
    return (x0, y0, x1, y1) != original


def snap_room_translation(
    room: dict,
    rooms: list[dict],
    target_x_m: float,
    target_y_m: float,
    *,
    tolerance_m: float = 0.15,
) -> tuple[float, float, list[dict]]:
    """Snap a moving room to nearby room edges/centers and return guide metadata."""
    target_x = _finite_number(target_x_m, _finite_number(room.get("x_m"), 0.0))
    target_y = _finite_number(target_y_m, _finite_number(room.get("y_m"), 0.0))
    length = _positive(room.get("length_m"), 4.0)
    width = _positive(room.get("width_m"), 4.0)
    tolerance = max(0.0, _finite_number(tolerance_m, 0.15))
    moving_id = str(room.get("id") or "")

    reference_x: list[tuple[str, float, str]] = []
    reference_y: list[tuple[str, float, str]] = []
    for other in rooms:
        if not isinstance(other, dict):
            continue
        other_id = str(other.get("id") or "")
        if other is room or (moving_id and other_id == moving_id):
            continue
        ox = _finite_number(other.get("x_m"), 0.0)
        oy = _finite_number(other.get("y_m"), 0.0)
        ol = _positive(other.get("length_m"), 4.0)
        ow = _positive(other.get("width_m"), 4.0)
        reference_x.extend(
            (
                ("left", ox, other_id),
                ("center", ox + ol / 2.0, other_id),
                ("right", ox + ol, other_id),
            )
        )
        reference_y.extend(
            (
                ("top", oy, other_id),
                ("center", oy + ow / 2.0, other_id),
                ("bottom", oy + ow, other_id),
            )
        )

    def best_snap(
        moving: tuple[tuple[str, float], ...],
        references: list[tuple[str, float, str]],
        axis: str,
    ) -> tuple[float, dict | None]:
        best: tuple[tuple, float, dict] | None = None
        for moving_anchor, moving_value in moving:
            for reference_anchor, reference_value, reference_room_id in references:
                delta = reference_value - moving_value
                distance = abs(delta)
                if distance > tolerance + 1e-12:
                    continue
                key = (round(distance, 12),)
                guide = {
                    "axis": axis,
                    "value_m": reference_value,
                    "reference_room_id": reference_room_id,
                    "moving_anchor": moving_anchor,
                    "reference_anchor": reference_anchor,
                }
                if best is None or key < best[0]:
                    best = (key, delta, guide)
        if best is None:
            return 0.0, None
        return best[1], best[2]

    dx, guide_x = best_snap(
        (
            ("left", target_x),
            ("center", target_x + length / 2.0),
            ("right", target_x + length),
        ),
        reference_x,
        "x",
    )
    dy, guide_y = best_snap(
        (
            ("top", target_y),
            ("center", target_y + width / 2.0),
            ("bottom", target_y + width),
        ),
        reference_y,
        "y",
    )
    guides = [guide for guide in (guide_x, guide_y) if guide is not None]
    return target_x + dx, target_y + dy, guides


def room_clearance_dimensions(room: dict, rooms: list[dict]) -> list[dict]:
    """Return nearest orthogonal room-to-room clearances on each side.

    Only neighbors whose perpendicular spans overlap are considered. Touching
    rooms are reported as a 0 m clearance, while diagonal rooms are ignored.
    The result order is deterministic: left, right, top, bottom.
    """

    x0 = _finite_number(room.get("x_m"), 0.0)
    y0 = _finite_number(room.get("y_m"), 0.0)
    x1 = x0 + _positive(room.get("length_m"), 0.0)
    y1 = y0 + _positive(room.get("width_m"), 0.0)
    room_id = room.get("id")
    epsilon = 1e-9
    best: dict[str, tuple[tuple[float, str], dict]] = {}

    def consider(side: str, gap: float, other: dict, start: tuple[float, float], end: tuple[float, float]) -> None:
        reference_id = str(other.get("id") or "")
        candidate = {
            "side": side,
            "gap_m": max(0.0, float(gap)),
            "reference_room_id": reference_id,
            "start_x_m": start[0],
            "start_y_m": start[1],
            "end_x_m": end[0],
            "end_y_m": end[1],
        }
        key = (candidate["gap_m"], reference_id)
        current = best.get(side)
        if current is None or key < current[0]:
            best[side] = (key, candidate)

    for other in rooms:
        if not isinstance(other, dict):
            continue
        if other is room or (
            room_id is not None and other.get("id") == room_id
        ):
            continue

        ox0 = _finite_number(other.get("x_m"), 0.0)
        oy0 = _finite_number(other.get("y_m"), 0.0)
        ox1 = ox0 + _positive(other.get("length_m"), 0.0)
        oy1 = oy0 + _positive(other.get("width_m"), 0.0)

        overlap_y0 = max(y0, oy0)
        overlap_y1 = min(y1, oy1)
        if overlap_y1 - overlap_y0 > epsilon:
            measure_y = (overlap_y0 + overlap_y1) / 2.0
            if ox1 <= x0 + epsilon:
                consider("left", x0 - ox1, other, (ox1, measure_y), (x0, measure_y))
            if ox0 >= x1 - epsilon:
                consider("right", ox0 - x1, other, (x1, measure_y), (ox0, measure_y))

        overlap_x0 = max(x0, ox0)
        overlap_x1 = min(x1, ox1)
        if overlap_x1 - overlap_x0 > epsilon:
            measure_x = (overlap_x0 + overlap_x1) / 2.0
            if oy1 <= y0 + epsilon:
                consider("top", y0 - oy1, other, (measure_x, oy1), (measure_x, y0))
            if oy0 >= y1 - epsilon:
                consider("bottom", oy0 - y1, other, (measure_x, y1), (measure_x, oy0))

    return [
        best[side][1]
        for side in ("left", "right", "top", "bottom")
        if side in best
    ]


class SpatialEditHistory:
    """Bounded undo/redo history for normalized spatial-layout snapshots."""

    def __init__(self, limit: int = SPATIAL_HISTORY_LIMIT):
        self.limit = max(1, int(limit))
        self._undo: list[dict] = []
        self._redo: list[dict] = []

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()

    def record(self, before: Any, after: Any) -> bool:
        before_layout = normalize_layout(before)
        after_layout = normalize_layout(after)
        if before_layout == after_layout:
            return False
        self._undo.append(copy.deepcopy(before_layout))
        if len(self._undo) > self.limit:
            del self._undo[: len(self._undo) - self.limit]
        self._redo.clear()
        return True

    def undo(self, current: Any) -> dict | None:
        if not self._undo:
            return None
        current_layout = normalize_layout(current)
        previous = self._undo.pop()
        self._redo.append(copy.deepcopy(current_layout))
        return copy.deepcopy(previous)

    def redo(self, current: Any) -> dict | None:
        if not self._redo:
            return None
        current_layout = normalize_layout(current)
        next_layout = self._redo.pop()
        self._undo.append(copy.deepcopy(current_layout))
        if len(self._undo) > self.limit:
            del self._undo[: len(self._undo) - self.limit]
        return copy.deepcopy(next_layout)


@dataclass
class _Hit:
    kind: str
    item_id: str


class SpatialDesignWorkspace(ttk.Frame):
    """Synchronized 2D/3D cleanroom design workspace backed by project metadata."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        project_getter: Callable[[], Any],
        analysis_getter: Callable[[], Any],
        on_change: Callable[[], None],
        on_sync_requested: Callable[[], None],
        status_setter: Callable[[str], None],
    ):
        super().__init__(master)
        self._project_getter = project_getter
        self._analysis_getter = analysis_getter
        self._on_change = on_change
        self._on_sync_requested = on_sync_requested
        self._status_setter = status_setter

        self.layout = empty_layout()
        self.selected: _Hit | None = None
        self._drag_anchor: tuple[float, float] | None = None
        self._pan_anchor: tuple[int, int] | None = None
        self._pan_origin: tuple[float, float] | None = None
        self._show_grid = tk.BooleanVar(value=True)
        self._snap_to_grid = tk.BooleanVar(value=True)
        self._coord_var = tk.StringVar(value="x 0.00 m   y 0.00 m")
        self._selection_var = tk.StringVar(value="No selection")
        self._summary_var = tk.StringVar(value="0 rooms • 0 devices")
        self._view_2d_var = tk.StringVar(value="2D • 100%")
        self._view_3d_var = tk.StringVar(value="3D • 35° / 28°")
        self._property_vars: dict[str, tk.StringVar] = {}
        self._history = SpatialEditHistory()
        self._drag_before: dict | None = None
        self._drag_changed = False
        self._resize_handle: str | None = None
        self._smart_align = tk.BooleanVar(value=True)
        self._alignment_guides: list[dict] = []
        self._show_clearances = tk.BooleanVar(value=True)
        self._show_conflicts = tk.BooleanVar(value=True)
        self._conflict_cursor = -1

        self._build()
        self.refresh()

    def _build(self) -> None:
        toolbar = ttk.Frame(self, padding=(6, 6, 6, 3))
        toolbar.pack(fill="x")

        ttk.Button(toolbar, text="+ Room", command=self.add_room).pack(side="left", padx=2)
        for device_type, label in (
            ("door", "+ Door"),
            ("ffu", "+ FFU"),
            ("supply", "+ Supply"),
            ("return", "+ Return"),
            ("exhaust", "+ Exhaust"),
            ("equipment", "+ Equipment"),
            ("sensor", "+ Sensor"),
        ):
            ttk.Button(
                toolbar,
                text=label,
                command=lambda t=device_type: self.add_device(t),
            ).pack(side="left", padx=2)
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=6)
        self._undo_button = ttk.Button(
            toolbar, text="Undo", command=self.undo_edit, state="disabled"
        )
        self._undo_button.pack(side="left", padx=2)
        self._redo_button = ttk.Button(
            toolbar, text="Redo", command=self.redo_edit, state="disabled"
        )
        self._redo_button.pack(side="left", padx=2)
        ttk.Button(toolbar, text="Duplicate", command=self.duplicate_selected).pack(
            side="left", padx=2
        )
        ttk.Button(toolbar, text="Delete", command=self.delete_selected).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Fit", command=self.fit_views).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Export SVG", command=self.export_svg).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Export CSV", command=self.export_schedule_csv).pack(side="left", padx=2)
        ttk.Button(
            toolbar,
            text="Export conflicts",
            command=self.export_overlap_report_csv,
        ).pack(side="left", padx=2)
        ttk.Checkbutton(toolbar, text="Grid", variable=self._show_grid, command=self.redraw).pack(
            side="left", padx=(6, 2)
        )
        ttk.Checkbutton(toolbar, text="Snap", variable=self._snap_to_grid).pack(
            side="left", padx=2
        )
        ttk.Checkbutton(toolbar, text="Align", variable=self._smart_align).pack(
            side="left", padx=2
        )
        ttk.Checkbutton(
            toolbar,
            text="Gaps",
            variable=self._show_clearances,
            command=self.redraw,
        ).pack(side="left", padx=2)
        ttk.Checkbutton(
            toolbar,
            text="Conflicts",
            variable=self._show_conflicts,
            command=self.redraw,
        ).pack(side="left", padx=2)
        ttk.Button(
            toolbar,
            text="Next conflict",
            command=self.select_next_overlap_conflict,
        ).pack(side="left", padx=2)
        ttk.Button(
            toolbar,
            text="Resolve overlap",
            command=self.resolve_selected_overlap,
        ).pack(side="left", padx=2)
        ttk.Button(
            toolbar,
            text="Resolve all",
            command=self.resolve_all_overlaps,
        ).pack(side="left", padx=2)
        ttk.Button(
            toolbar,
            text="Sync dimensions to active analysis",
            command=self._on_sync_requested,
        ).pack(side="right", padx=2)

        scene_bar = ttk.Frame(self, padding=(8, 2, 8, 5))
        scene_bar.pack(fill="x")
        ttk.Label(
            scene_bar,
            textvariable=self._summary_var,
            font=("TkDefaultFont", 9, "bold"),
        ).pack(side="left")
        ttk.Label(
            scene_bar,
            text="2D: drag to move • smart align • live gaps/conflicts • wheel to zoom • middle/right drag to pan    "
                 "3D: click to select • wheel to zoom",
        ).pack(side="right")

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=6, pady=(3, 6))

        two_d = ttk.Frame(body)
        body.add(two_d, weight=4)
        header2 = ttk.Frame(two_d)
        header2.pack(fill="x")
        ttk.Label(header2, text="2D PLAN", font=("TkDefaultFont", 10, "bold")).pack(
            side="left", padx=4, pady=(2, 4)
        )
        ttk.Label(header2, textvariable=self._view_2d_var).pack(
            side="right", padx=4, pady=(2, 4)
        )
        self.canvas_2d = tk.Canvas(two_d, background="#f7f9fb", highlightthickness=1)
        self.canvas_2d.pack(fill="both", expand=True)
        ttk.Label(two_d, textvariable=self._coord_var, anchor="w").pack(fill="x", padx=4, pady=2)

        right = ttk.Panedwindow(body, orient="vertical")
        body.add(right, weight=4)

        three_d = ttk.Frame(right)
        right.add(three_d, weight=3)
        header3 = ttk.Frame(three_d)
        header3.pack(fill="x")
        ttk.Label(header3, text="3D PERSPECTIVE", font=("TkDefaultFont", 10, "bold")).pack(
            side="left", padx=4, pady=(2, 4)
        )
        ttk.Label(header3, textvariable=self._view_3d_var).pack(
            side="left", padx=(8, 4), pady=(2, 4)
        )
        for label, delta in (("↺", -15), ("↻", 15)):
            ttk.Button(header3, text=label, width=3, command=lambda d=delta: self.rotate_3d(d)).pack(
                side="right", padx=2
            )
        ttk.Button(header3, text="↓", width=3, command=lambda: self.tilt_3d(-5)).pack(side="right", padx=2)
        ttk.Button(header3, text="↑", width=3, command=lambda: self.tilt_3d(5)).pack(side="right", padx=2)
        ttk.Button(header3, text="Reset", command=self.reset_3d).pack(side="right", padx=2)
        self.canvas_3d = tk.Canvas(three_d, background="#111820", highlightthickness=1)
        self.canvas_3d.pack(fill="both", expand=True)

        inspector = ttk.Frame(right, padding=6)
        right.add(inspector, weight=2)
        ttk.Label(inspector, text="Properties", font=("TkDefaultFont", 10, "bold")).grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 6)
        )
        ttk.Label(inspector, textvariable=self._selection_var).grid(
            row=1, column=0, columnspan=4, sticky="w", pady=(0, 6)
        )
        fields = (
            ("name", "Name"),
            ("x_m", "X (m)"),
            ("y_m", "Y (m)"),
            ("length_m", "Length (m)"),
            ("width_m", "Width (m)"),
            ("height_m", "Height (m)"),
            ("pressure_pa", "Pressure (Pa)"),
        )
        for index, (key, label) in enumerate(fields):
            row = 2 + index // 2
            column = (index % 2) * 2
            ttk.Label(inspector, text=label).grid(row=row, column=column, sticky="w", padx=(0, 4), pady=2)
            var = tk.StringVar()
            self._property_vars[key] = var
            ttk.Entry(inspector, textvariable=var, width=18).grid(
                row=row, column=column + 1, sticky="ew", padx=(0, 8), pady=2
            )
        button_row = 2 + (len(fields) + 1) // 2
        ttk.Button(inspector, text="Apply", command=self.apply_properties).grid(
            row=button_row, column=3, sticky="e", pady=(8, 0)
        )
        inspector.columnconfigure(1, weight=1)
        inspector.columnconfigure(3, weight=1)

        self.canvas_2d.bind("<Configure>", lambda event: self.redraw())
        self.canvas_3d.bind("<Configure>", lambda event: self._draw_3d())
        self.canvas_2d.bind("<Motion>", self._on_motion)
        self.canvas_2d.bind("<Button-1>", self._on_left_down)
        self.canvas_2d.bind("<B1-Motion>", self._on_left_drag)
        self.canvas_2d.bind("<ButtonRelease-1>", self._on_left_up)
        self.canvas_2d.bind("<Button-2>", self._on_pan_down)
        self.canvas_2d.bind("<B2-Motion>", self._on_pan_drag)
        self.canvas_2d.bind("<Button-3>", self._on_pan_down)
        self.canvas_2d.bind("<B3-Motion>", self._on_pan_drag)
        self.canvas_2d.bind("<MouseWheel>", self._on_wheel)
        self.canvas_2d.bind("<Button-4>", lambda event: self._zoom_at(1.1, event.x, event.y))
        self.canvas_2d.bind("<Button-5>", lambda event: self._zoom_at(1 / 1.1, event.x, event.y))
        self.canvas_2d.bind("<Delete>", lambda event: self.delete_selected())
        self.canvas_2d.bind("<Key-f>", lambda event: self.fit_views())
        self.canvas_3d.bind("<MouseWheel>", self._on_wheel_3d)
        self.canvas_3d.bind("<Button-4>", lambda event: self._zoom_3d(1.1))
        self.canvas_3d.bind("<Button-5>", lambda event: self._zoom_3d(1 / 1.1))
        self.canvas_3d.bind("<Button-1>", self._on_3d_click)
        self.canvas_3d.bind("<Button-2>", self._on_pan_3d_down)
        self.canvas_3d.bind("<B2-Motion>", self._on_pan_3d_drag)
        self.canvas_3d.bind("<Button-3>", self._on_pan_3d_down)
        self.canvas_3d.bind("<B3-Motion>", self._on_pan_3d_drag)
        self.canvas_3d.bind("<Delete>", lambda event: self.delete_selected())
        self.canvas_3d.bind("<Key-f>", lambda event: self.fit_views())
        for canvas in (self.canvas_2d, self.canvas_3d):
            canvas.bind("<Control-z>", lambda event: self.undo_edit())
            canvas.bind("<Control-y>", lambda event: self.redo_edit())
            canvas.bind("<Control-d>", lambda event: self.duplicate_selected())
            canvas.bind("<Left>", lambda event: self.nudge_selected(-1, 0))
            canvas.bind("<Right>", lambda event: self.nudge_selected(1, 0))
            canvas.bind("<Up>", lambda event: self.nudge_selected(0, -1))
            canvas.bind("<Down>", lambda event: self.nudge_selected(0, 1))

    def refresh(self) -> None:
        project = self._project_getter()
        analysis = self._analysis_getter()
        self.layout = ensure_project_layout(project, analysis)
        self._alignment_guides = []
        self._history.clear()
        self._update_history_controls()
        if self.selected and not self._selected_object():
            self.selected = None
        self._load_property_panel()
        self.redraw()

    def _snapshot_layout(self) -> dict:
        return copy.deepcopy(normalize_layout(self.layout))

    def _update_history_controls(self) -> None:
        if hasattr(self, "_undo_button"):
            self._undo_button.configure(state="normal" if self._history.can_undo else "disabled")
        if hasattr(self, "_redo_button"):
            self._redo_button.configure(state="normal" if self._history.can_redo else "disabled")

    def _commit_layout(self, message: str) -> None:
        project = self._project_getter()
        project.metadata[SPATIAL_METADATA_KEY] = normalize_layout(self.layout)
        self._conflict_cursor = -1
        self.layout = project.metadata[SPATIAL_METADATA_KEY]
        if self.selected and not self._selected_object():
            self.selected = None
        self._load_property_panel()
        self._update_history_controls()
        self._on_change()
        self._status_setter(message)
        self.redraw()

    def _persist(self, message: str, *, history_before: dict | None = None) -> bool:
        current = normalize_layout(self.layout)
        if history_before is not None and not self._history.record(history_before, current):
            self.layout = current
            self._update_history_controls()
            self.redraw()
            return False
        self.layout = current
        self._commit_layout(message)
        return True

    def undo_edit(self) -> None:
        previous = self._history.undo(self.layout)
        if previous is None:
            return
        self.layout = previous
        self._commit_layout("Undid spatial edit")

    def redo_edit(self) -> None:
        next_layout = self._history.redo(self.layout)
        if next_layout is None:
            return
        self.layout = next_layout
        self._commit_layout("Redid spatial edit")

    def export_svg(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export 2D plan as SVG",
            defaultextension=".svg",
            initialfile="cleanroomx-plan.svg",
            filetypes=(("SVG vector drawing", "*.svg"), ("All files", "*.*")),
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(spatial_layout_svg(self.layout))
        except OSError as exc:
            messagebox.showerror(
                "Export SVG",
                f"Could not export the 2D plan:\n{exc}",
                parent=self,
            )
            return
        self._status_setter(f"Exported 2D plan SVG: {path}")

    def export_schedule_csv(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export spatial engineering schedule as CSV",
            defaultextension=".csv",
            initialfile="cleanroomx-spatial-schedule.csv",
            filetypes=(("CSV schedule", "*.csv"), ("All files", "*.*")),
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(spatial_layout_schedule_csv(self.layout))
        except OSError as exc:
            messagebox.showerror(
                "Export CSV",
                f"Could not export the spatial schedule:\n{exc}",
                parent=self,
            )
            return
        self._status_setter(f"Exported spatial schedule CSV: {path}")

    def export_overlap_report_csv(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export room-overlap QA report as CSV",
            defaultextension=".csv",
            initialfile="cleanroomx-overlap-conflicts.csv",
            filetypes=(("CSV QA report", "*.csv"), ("All files", "*.*")),
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(spatial_overlap_report_csv(self.layout))
        except OSError as exc:
            messagebox.showerror(
                "Export overlap report",
                f"Could not export the room-overlap QA report:\n{exc}",
                parent=self,
            )
            return
        conflict_count = len(room_overlap_conflicts(self.layout["rooms"]))
        self._status_setter(
            f"Exported {conflict_count} room-overlap conflict(s) to CSV: {path}"
        )

    def _selected_object(self) -> dict | None:
        if self.selected is None:
            return None
        collection = self.layout["rooms"] if self.selected.kind == "room" else self.layout["devices"]
        return next((item for item in collection if item["id"] == self.selected.item_id), None)

    def _translate_selected(self, dx: float, dy: float) -> bool:
        item = self._selected_object()
        if item is None or (dx == 0 and dy == 0):
            return False
        item["x_m"] += dx
        item["y_m"] += dy
        if self.selected and self.selected.kind == "room":
            for device in self.layout["devices"]:
                if device.get("room_id") == item["id"]:
                    device["x_m"] += dx
                    device["y_m"] += dy
        return True

    def _load_property_panel(self) -> None:
        item = self._selected_object()
        if item is None:
            self._selection_var.set("No selection")
            for var in self._property_vars.values():
                var.set("")
            return
        prefix = "Room" if self.selected and self.selected.kind == "room" else item.get("type", "Device").title()
        self._selection_var.set(f"{prefix}: {item.get('name', '')}")
        for key, var in self._property_vars.items():
            value = item.get(key, "")
            var.set("" if value is None else str(value))

    def apply_properties(self) -> None:
        item = self._selected_object()
        if item is None:
            return
        before = self._snapshot_layout()
        name = self._property_vars["name"].get().strip()
        if name:
            item["name"] = name
        for key in ("x_m", "y_m"):
            text = self._property_vars[key].get().strip()
            if text:
                item[key] = _finite_number(text, item.get(key, 0.0))
        if self.selected and self.selected.kind == "room":
            for key in ("length_m", "width_m", "height_m"):
                text = self._property_vars[key].get().strip()
                if text:
                    item[key] = _positive(text, item[key])
            pressure = self._property_vars["pressure_pa"].get().strip()
            if pressure:
                item["pressure_pa"] = _finite_number(pressure, item.get("pressure_pa", 0.0))
            elif "pressure_pa" in item:
                item.pop("pressure_pa", None)
        self._load_property_panel()
        self._persist("Spatial properties updated", history_before=before)

    def add_room(self) -> None:
        before = self._snapshot_layout()
        x = max(
            (room["x_m"] + room["length_m"] for room in self.layout["rooms"]),
            default=0.0,
        )
        index = len(self.layout["rooms"]) + 1
        room = {
            "id": f"room-{uuid.uuid4().hex[:8]}",
            "name": f"Room {index}",
            "x_m": x + (1.0 if self.layout["rooms"] else 0.0),
            "y_m": 0.0,
            "length_m": 4.0,
            "width_m": 4.0,
            "height_m": 3.0,
        }
        self.layout["rooms"].append(room)
        self.selected = _Hit("room", room["id"])
        self._load_property_panel()
        self._persist(f"Added {room['name']}", history_before=before)

    def add_device(self, device_type: str) -> None:
        before = self._snapshot_layout()
        device_type = device_type if device_type in DEVICE_TYPES else "equipment"
        room = self._selected_object() if self.selected and self.selected.kind == "room" else None
        if room is None and self.layout["rooms"]:
            room = self.layout["rooms"][0]
        if room:
            x = room["x_m"] + room["length_m"] / 2.0
            y = room["y_m"] + room["width_m"] / 2.0
            z = room["height_m"] if device_type in {"ffu", "supply", "return", "exhaust", "sensor"} else 0.0
            room_id = room["id"]
        else:
            x = y = z = 0.0
            room_id = None
        device = {
            "id": f"device-{uuid.uuid4().hex[:8]}",
            "type": device_type,
            "name": device_type.upper(),
            "room_id": room_id,
            "x_m": x,
            "y_m": y,
            "z_m": z,
        }
        self.layout["devices"].append(device)
        self.selected = _Hit("device", device["id"])
        self._load_property_panel()
        self._persist(f"Added {device_type}", history_before=before)

    def delete_selected(self) -> None:
        if self.selected is None:
            return
        before = self._snapshot_layout()
        collection_name = "rooms" if self.selected.kind == "room" else "devices"
        item_id = self.selected.item_id
        self.layout[collection_name] = [item for item in self.layout[collection_name] if item["id"] != item_id]
        if self.selected.kind == "room":
            self.layout["devices"] = [
                item for item in self.layout["devices"] if item.get("room_id") != item_id
            ]
        self.selected = None
        self._load_property_panel()
        self._persist("Deleted spatial item", history_before=before)

    def duplicate_selected(self) -> None:
        item = self._selected_object()
        if item is None or self.selected is None:
            return
        before = self._snapshot_layout()
        duplicate = copy.deepcopy(item)
        duplicate["id"] = (
            f"room-{uuid.uuid4().hex[:8]}"
            if self.selected.kind == "room"
            else f"device-{uuid.uuid4().hex[:8]}"
        )
        duplicate["name"] = f"{item.get('name', 'Item')} Copy"
        offset = max(0.1, self.layout["grid_m"])
        duplicate["x_m"] += offset
        duplicate["y_m"] += offset
        if self.selected.kind == "room":
            self.layout["rooms"].append(duplicate)
            self.selected = _Hit("room", duplicate["id"])
        else:
            self.layout["devices"].append(duplicate)
            self.selected = _Hit("device", duplicate["id"])
            self._reassign_selected_device_room()
        self._load_property_panel()
        self._persist("Duplicated spatial item", history_before=before)

    def nudge_selected(self, dx_steps: int, dy_steps: int) -> None:
        if self.selected is None:
            return
        before = self._snapshot_layout()
        step = self.layout["grid_m"] if self._snap_to_grid.get() else 0.1
        if not self._translate_selected(dx_steps * step, dy_steps * step):
            return
        self._reassign_selected_device_room()
        self._load_property_panel()
        self._persist("Nudged spatial item", history_before=before)

    def select_next_overlap_conflict(self) -> None:
        conflict = next_room_overlap_conflict(
            self.layout["rooms"], self._conflict_cursor
        )
        if conflict is None:
            self._conflict_cursor = -1
            self._status_setter("No room overlap conflicts to review")
            return

        self._conflict_cursor = conflict["index"]
        target_room_id = conflict["room_b_id"] or conflict["room_a_id"]
        if target_room_id:
            self.selected = _Hit("room", target_room_id)
        self._show_conflicts.set(True)
        self._load_property_panel()
        self.redraw()

        target_name = (
            conflict["room_b_name"]
            if target_room_id == conflict["room_b_id"]
            else conflict["room_a_name"]
        )
        self._status_setter(
            f"Conflict {conflict['index'] + 1}/{conflict['count']}: "
            f"{conflict['room_a_name']} ↔ {conflict['room_b_name']} · "
            f"{conflict['area_m2']:.2f} m² overlap; selected {target_name}"
        )

    def resolve_selected_overlap(self) -> None:
        if self.selected is None or self.selected.kind != "room":
            self._status_setter("Select a room to resolve overlap conflicts")
            return
        room = self._selected_object()
        if room is None:
            return
        target_x, target_y = nearest_nonoverlap_room_position(
            room, self.layout["rooms"]
        )
        dx = target_x - room["x_m"]
        dy = target_y - room["y_m"]
        if abs(dx) <= 1e-9 and abs(dy) <= 1e-9:
            self._status_setter("Selected room has no overlap conflicts")
            return
        before = self._snapshot_layout()
        if not self._translate_selected(dx, dy):
            return
        self._alignment_guides = []
        self._load_property_panel()
        self._persist("Resolved selected room overlap", history_before=before)

    def resolve_all_overlaps(self) -> None:
        moves = resolve_room_overlaps(self.layout["rooms"])
        if not moves:
            self._status_setter("No room overlap conflicts to resolve")
            return

        before = self._snapshot_layout()
        rooms_by_id = {
            str(room.get("id") or ""): room for room in self.layout["rooms"]
        }
        for move in moves:
            room = rooms_by_id.get(move["room_id"])
            if room is None:
                continue
            room["x_m"] = move["x_m"]
            room["y_m"] = move["y_m"]
            for device in self.layout["devices"]:
                if device.get("room_id") == room.get("id"):
                    device["x_m"] += move["dx_m"]
                    device["y_m"] += move["dy_m"]

        self._alignment_guides = []
        self._load_property_panel()
        self._persist(
            f"Resolved overlaps in {len(moves)} room(s)",
            history_before=before,
        )

    def _bounds(self) -> tuple[float, float, float, float]:
        rooms = self.layout["rooms"]
        if not rooms:
            return (0.0, 0.0, 10.0, 8.0)
        min_x = min(room["x_m"] for room in rooms)
        min_y = min(room["y_m"] for room in rooms)
        max_x = max(room["x_m"] + room["length_m"] for room in rooms)
        max_y = max(room["y_m"] + room["width_m"] for room in rooms)
        return min_x, min_y, max_x, max_y

    def _scale_2d(self) -> float:
        return 55.0 * self.layout["view"]["zoom_2d"]

    def _world_to_canvas(self, x: float, y: float) -> tuple[float, float]:
        scale = self._scale_2d()
        return (
            self.canvas_2d.winfo_width() / 2 + self.layout["view"]["pan_x"] + x * scale,
            self.canvas_2d.winfo_height() / 2 + self.layout["view"]["pan_y"] + y * scale,
        )

    def _canvas_to_world(self, x: float, y: float) -> tuple[float, float]:
        scale = self._scale_2d()
        return (
            (x - self.canvas_2d.winfo_width() / 2 - self.layout["view"]["pan_x"]) / scale,
            (y - self.canvas_2d.winfo_height() / 2 - self.layout["view"]["pan_y"]) / scale,
        )

    def fit_views(self) -> None:
        min_x, min_y, max_x, max_y = self._bounds()
        width_m = max(1.0, max_x - min_x)
        height_m = max(1.0, max_y - min_y)
        cw = max(200, self.canvas_2d.winfo_width())
        ch = max(200, self.canvas_2d.winfo_height())
        self.layout["view"]["zoom_2d"] = max(0.2, min(5.0, 0.78 * min(cw / (55 * width_m), ch / (55 * height_m))))
        scale = self._scale_2d()
        cx = (min_x + max_x) / 2
        cy = (min_y + max_y) / 2
        self.layout["view"]["pan_x"] = -cx * scale
        self.layout["view"]["pan_y"] = -cy * scale
        self.layout["view"]["zoom_3d"] = 1.0
        self._persist("Fit spatial views")

    def _update_scene_status(self) -> None:
        summary = spatial_layout_summary(self.layout)
        pressure_text = ""
        if summary["pressure_min_pa"] is not None:
            pressure_text = (
                f" • pressure {summary['pressure_min_pa']:g}–"
                f"{summary['pressure_max_pa']:g} Pa"
            )
        unassigned_text = (
            f" • {summary['unassigned_device_count']} unassigned"
            if summary["unassigned_device_count"]
            else ""
        )
        overlap_text = (
            f" • {summary['room_overlap_count']} overlap"
            f"{'s' if summary['room_overlap_count'] != 1 else ''}"
            if summary["room_overlap_count"]
            else ""
        )
        self._summary_var.set(
            f"{summary['room_count']} rooms • {summary['device_count']} devices"
            f" • {summary['footprint_m2']:.1f} m² footprint"
            f" • {summary['volume_m3']:.1f} m³ volume"
            f"{pressure_text}{unassigned_text}{overlap_text}"
        )
        self._view_2d_var.set(
            f"2D • {self.layout['view']['zoom_2d'] * 100:.0f}%"
        )
        self._view_3d_var.set(
            "3D • "
            f"{self.layout['view']['azimuth_deg']:.0f}° az / "
            f"{self.layout['view']['elevation_deg']:.0f}° el"
        )

    def redraw(self) -> None:
        self._update_scene_status()
        self._draw_2d()
        self._draw_3d()

    def _draw_2d(self) -> None:
        canvas = self.canvas_2d
        canvas.delete("all")
        w = max(1, canvas.winfo_width())
        h = max(1, canvas.winfo_height())
        if self._show_grid.get():
            grid = max(0.1, self.layout["grid_m"])
            scale = self._scale_2d()
            if grid * scale >= 8:
                x0, y0 = self._canvas_to_world(0, 0)
                x1, y1 = self._canvas_to_world(w, h)
                start_x = math.floor(min(x0, x1) / grid) * grid
                end_x = math.ceil(max(x0, x1) / grid) * grid
                start_y = math.floor(min(y0, y1) / grid) * grid
                end_y = math.ceil(max(y0, y1) / grid) * grid
                x = start_x
                while x <= end_x + 1e-9:
                    cx, _ = self._world_to_canvas(x, 0)
                    canvas.create_line(cx, 0, cx, h, fill="#e7ecf1", tags=("grid",))
                    x += grid
                y = start_y
                while y <= end_y + 1e-9:
                    _, cy = self._world_to_canvas(0, y)
                    canvas.create_line(0, cy, w, cy, fill="#e7ecf1", tags=("grid",))
                    y += grid

        for guide in self._alignment_guides:
            axis = guide.get("axis")
            value = guide.get("value_m")
            if axis == "x":
                cx, _ = self._world_to_canvas(_finite_number(value, 0.0), 0.0)
                canvas.create_line(
                    cx, 0, cx, h,
                    fill="#0f766e", width=2, dash=(5, 3), tags=("alignment-guide",)
                )
            elif axis == "y":
                _, cy = self._world_to_canvas(0.0, _finite_number(value, 0.0))
                canvas.create_line(
                    0, cy, w, cy,
                    fill="#0f766e", width=2, dash=(5, 3), tags=("alignment-guide",)
                )

        pressures = [room.get("pressure_pa") for room in self.layout["rooms"] if room.get("pressure_pa") is not None]
        pmin = min(pressures) if pressures else None
        pmax = max(pressures) if pressures else None

        if pmin is not None:
            canvas.create_text(
                12,
                12,
                anchor="nw",
                text=f"Pressure map  {pmin:g} → {pmax:g} Pa",
                fill="#40566d",
                font=("TkDefaultFont", 9, "bold"),
            )

        for room in self.layout["rooms"]:
            x0, y0 = self._world_to_canvas(room["x_m"], room["y_m"])
            x1, y1 = self._world_to_canvas(room["x_m"] + room["length_m"], room["y_m"] + room["width_m"])
            selected = self.selected == _Hit("room", room["id"])
            outline = "#1d4ed8" if selected else "#34495e"
            fill = _pressure_fill(room.get("pressure_pa"), pmin, pmax)
            canvas.create_rectangle(
                x0, y0, x1, y1,
                fill=fill, outline=outline, width=3 if selected else 2,
                tags=(f"room:{room['id']}", "room"),
            )
            pressure_text = "" if room.get("pressure_pa") is None else f"\n{room['pressure_pa']:g} Pa"
            canvas.create_text(
                (x0 + x1) / 2,
                (y0 + y1) / 2,
                text=f"{room['name']}\n{room['length_m']:g} × {room['width_m']:g} m{pressure_text}",
                justify="center",
                tags=(f"room:{room['id']}", "room"),
            )
            if selected:
                handle_points = {
                    "nw": (x0, y0),
                    "n": ((x0 + x1) / 2, y0),
                    "ne": (x1, y0),
                    "e": (x1, (y0 + y1) / 2),
                    "se": (x1, y1),
                    "s": ((x0 + x1) / 2, y1),
                    "sw": (x0, y1),
                    "w": (x0, (y0 + y1) / 2),
                }
                for handle, (hx, hy) in handle_points.items():
                    radius = 5
                    canvas.create_rectangle(
                        hx - radius,
                        hy - radius,
                        hx + radius,
                        hy + radius,
                        fill="#ffffff",
                        outline="#1d4ed8",
                        width=2,
                        tags=(f"resize:{handle}", f"room:{room['id']}", "resize"),
                    )

        if self._show_conflicts.get():
            self._draw_room_overlap_conflicts()

        if (
            self._show_clearances.get()
            and self.selected is not None
            and self.selected.kind == "room"
        ):
            selected_room = self._selected_object()
            if selected_room is not None:
                self._draw_room_clearances(selected_room)

        symbols = {
            "door": "D",
            "supply": "S",
            "return": "R",
            "exhaust": "E",
            "ffu": "F",
            "equipment": "Q",
            "sensor": "●",
        }
        for device in self.layout["devices"]:
            x, y = self._world_to_canvas(device["x_m"], device["y_m"])
            selected = self.selected == _Hit("device", device["id"])
            radius = 9 if selected else 7
            canvas.create_oval(
                x - radius, y - radius, x + radius, y + radius,
                fill="#ffffff", outline="#c0392b" if selected else "#2c3e50",
                width=3 if selected else 2,
                tags=(f"device:{device['id']}", "device"),
            )
            canvas.create_text(
                x, y, text=symbols.get(device["type"], "?"),
                tags=(f"device:{device['id']}", "device"),
            )

        if not self.layout["rooms"] and not self.layout["devices"]:
            canvas.create_text(
                w / 2,
                h / 2,
                text="No spatial layout yet\nUse + Room or open a verification project with room geometry.",
                justify="center",
                fill="#667788",
            )

    def _draw_room_overlap_conflicts(self) -> None:
        canvas = self.canvas_2d
        for conflict in room_overlap_conflicts(self.layout["rooms"]):
            x0, y0 = self._world_to_canvas(conflict["x_m"], conflict["y_m"])
            x1, y1 = self._world_to_canvas(
                conflict["x_m"] + conflict["length_m"],
                conflict["y_m"] + conflict["width_m"],
            )
            tag = (
                "room-overlap",
                f"overlap:{conflict['room_a_id']}:{conflict['room_b_id']}",
            )
            canvas.create_rectangle(
                x0,
                y0,
                x1,
                y1,
                outline="#b91c1c",
                width=3,
                dash=(6, 3),
                tags=tag,
            )
            canvas.create_line(x0, y0, x1, y1, fill="#b91c1c", width=2, tags=tag)
            canvas.create_line(x0, y1, x1, y0, fill="#b91c1c", width=2, tags=tag)
            if abs(x1 - x0) >= 40 and abs(y1 - y0) >= 24:
                canvas.create_text(
                    (x0 + x1) / 2.0,
                    (y0 + y1) / 2.0,
                    text=f"OVERLAP\n{conflict['area_m2']:.3g} m²",
                    fill="#991b1b",
                    font=("TkDefaultFont", 8, "bold"),
                    justify="center",
                    tags=tag,
                )

    def _draw_room_clearances(self, room: dict) -> None:
        canvas = self.canvas_2d
        for dimension in room_clearance_dimensions(room, self.layout["rooms"]):
            x0, y0 = self._world_to_canvas(
                dimension["start_x_m"], dimension["start_y_m"]
            )
            x1, y1 = self._world_to_canvas(
                dimension["end_x_m"], dimension["end_y_m"]
            )
            side = dimension["side"]
            gap_m = dimension["gap_m"]
            horizontal = side in {"left", "right"}
            line_length_px = abs(x1 - x0) + abs(y1 - y0)

            if line_length_px >= 2:
                canvas.create_line(
                    x0,
                    y0,
                    x1,
                    y1,
                    fill="#6d28d9",
                    width=2,
                    arrow=tk.BOTH,
                    arrowshape=(6, 7, 3),
                    tags=("clearance",),
                )

            if horizontal:
                for x in (x0, x1):
                    canvas.create_line(
                        x,
                        y0 - 5,
                        x,
                        y0 + 5,
                        fill="#6d28d9",
                        width=2,
                        tags=("clearance",),
                    )
                label_x = (x0 + x1) / 2.0
                label_y = y0 - 10
            else:
                for y in (y0, y1):
                    canvas.create_line(
                        x0 - 5,
                        y,
                        x0 + 5,
                        y,
                        fill="#6d28d9",
                        width=2,
                        tags=("clearance",),
                    )
                label_x = x0 + 10
                label_y = (y0 + y1) / 2.0

            canvas.create_text(
                label_x,
                label_y,
                text=f"{gap_m:.3g} m",
                fill="#6d28d9",
                font=("TkDefaultFont", 8, "bold"),
                tags=("clearance",),
            )

    def _project_3d(self, x: float, y: float, z: float) -> tuple[float, float]:
        az = math.radians(self.layout["view"]["azimuth_deg"])
        el = math.radians(self.layout["view"]["elevation_deg"])
        xr = x * math.cos(az) - y * math.sin(az)
        yr = x * math.sin(az) + y * math.cos(az)
        sy = yr * math.sin(el) - z * math.cos(el)
        scale = 34.0 * self.layout["view"]["zoom_3d"]
        return (
            self.canvas_3d.winfo_width() / 2 + self.layout["view"]["pan_3d_x"] + xr * scale,
            self.canvas_3d.winfo_height() * 0.66 + self.layout["view"]["pan_3d_y"] + sy * scale,
        )

    def _draw_3d(self) -> None:
        canvas = self.canvas_3d
        canvas.delete("all")
        if not self.layout["rooms"]:
            canvas.create_text(
                max(1, canvas.winfo_width()) / 2,
                max(1, canvas.winfo_height()) / 2,
                text="3D geometry appears here",
                fill="#9fb2c5",
            )
            return

        min_x, min_y, max_x, max_y = self._bounds()
        cx = (min_x + max_x) / 2
        cy = (min_y + max_y) / 2
        pressures = [room.get("pressure_pa") for room in self.layout["rooms"] if room.get("pressure_pa") is not None]
        pmin = min(pressures) if pressures else None
        pmax = max(pressures) if pressures else None

        # Floor extent and axes keep the perspective view spatially readable.
        floor = [
            self._project_3d(min_x - cx, min_y - cy, 0),
            self._project_3d(max_x - cx, min_y - cy, 0),
            self._project_3d(max_x - cx, max_y - cy, 0),
            self._project_3d(min_x - cx, max_y - cy, 0),
        ]
        canvas.create_polygon(
            *sum(floor, ()),
            fill="#17222d",
            outline="#31465a",
            width=1,
        )
        axis_origin = self._project_3d(min_x - cx, min_y - cy, 0)
        axis_x = self._project_3d(min_x - cx + 1.5, min_y - cy, 0)
        axis_y = self._project_3d(min_x - cx, min_y - cy + 1.5, 0)
        canvas.create_line(*axis_origin, *axis_x, fill="#7dd3fc", width=2, arrow=tk.LAST)
        canvas.create_line(*axis_origin, *axis_y, fill="#fbbf24", width=2, arrow=tk.LAST)
        canvas.create_text(*axis_x, text=" X", fill="#7dd3fc", anchor="w")
        canvas.create_text(*axis_y, text=" Y", fill="#fbbf24", anchor="w")
        if pmin is not None:
            canvas.create_text(
                12,
                12,
                anchor="nw",
                text=f"Pressure  {pmin:g} → {pmax:g} Pa",
                fill="#d8e5f1",
                font=("TkDefaultFont", 9, "bold"),
            )

        # Draw farther rooms first to improve visual depth.
        az = math.radians(self.layout["view"]["azimuth_deg"])
        ordered = sorted(
            self.layout["rooms"],
            key=lambda room: (room["x_m"] - cx) * math.sin(az) + (room["y_m"] - cy) * math.cos(az),
        )
        for room in ordered:
            x0 = room["x_m"] - cx
            y0 = room["y_m"] - cy
            x1 = x0 + room["length_m"]
            y1 = y0 + room["width_m"]
            z = room["height_m"]
            base = [
                self._project_3d(x0, y0, 0),
                self._project_3d(x1, y0, 0),
                self._project_3d(x1, y1, 0),
                self._project_3d(x0, y1, 0),
            ]
            top = [
                self._project_3d(x0, y0, z),
                self._project_3d(x1, y0, z),
                self._project_3d(x1, y1, z),
                self._project_3d(x0, y1, z),
            ]
            fill = _pressure_fill(room.get("pressure_pa"), pmin, pmax)
            selected = self.selected == _Hit("room", room["id"])
            outline = "#7dd3fc" if selected else "#c8d5e3"
            tag = f"room:{room['id']}"
            canvas.create_polygon(*sum(top, ()), fill=fill, outline=outline, width=2, tags=(tag, "room3d"))
            canvas.create_polygon(
                *sum((base[1], base[2], top[2], top[1]), ()),
                fill="#6c7f92", outline=outline, tags=(tag, "room3d")
            )
            canvas.create_polygon(
                *sum((base[2], base[3], top[3], top[2]), ()),
                fill="#53687c", outline=outline, tags=(tag, "room3d")
            )
            canvas.create_text(
                *self._project_3d((x0 + x1) / 2, (y0 + y1) / 2, z + 0.2),
                text=room["name"],
                fill="#f0f6fc",
                tags=(tag, "room3d"),
            )

        for device in self.layout["devices"]:
            x, y = self._project_3d(device["x_m"] - cx, device["y_m"] - cy, device["z_m"])
            tag = f"device:{device['id']}"
            selected = self.selected == _Hit("device", device["id"])
            radius = 5 if selected else 4
            canvas.create_oval(
                x - radius, y - radius, x + radius, y + radius,
                fill="#fbbf24", outline="#ffffff" if selected else "#d6a20f",
                width=2, tags=(tag, "device3d"),
            )

    def _parse_hit(self, tags: tuple[str, ...]) -> _Hit | None:
        for tag in tags:
            if tag.startswith("room:"):
                return _Hit("room", tag.split(":", 1)[1])
            if tag.startswith("device:"):
                return _Hit("device", tag.split(":", 1)[1])
        return None

    def _on_left_down(self, event: tk.Event) -> None:
        self.canvas_2d.focus_set()
        current = self.canvas_2d.find_withtag("current")
        hit = None
        self._resize_handle = None
        self._alignment_guides = []
        if current:
            tags = self.canvas_2d.gettags(current[0])
            self._resize_handle = next(
                (tag.split(":", 1)[1] for tag in tags if tag.startswith("resize:")),
                None,
            )
            hit = self._parse_hit(tags)
        self.selected = hit
        self._drag_anchor = self._canvas_to_world(event.x, event.y) if hit else None
        self._drag_before = self._snapshot_layout() if hit else None
        self._drag_changed = False
        self._load_property_panel()
        self.redraw()

    def _on_left_drag(self, event: tk.Event) -> None:
        item = self._selected_object()
        if item is None or self._drag_anchor is None:
            return
        world = self._canvas_to_world(event.x, event.y)
        self._alignment_guides = []
        if self._resize_handle and self.selected and self.selected.kind == "room":
            grid = self.layout["grid_m"] if self._snap_to_grid.get() else None
            if resize_room(
                item,
                self._resize_handle,
                world[0],
                world[1],
                grid_m=grid,
            ):
                self._drag_changed = True
            self._load_property_panel()
            self.redraw()
            return
        dx = world[0] - self._drag_anchor[0]
        dy = world[1] - self._drag_anchor[1]
        old_x = item["x_m"]
        old_y = item["y_m"]
        if self._snap_to_grid.get():
            grid = self.layout["grid_m"]
            target_x = round((old_x + dx) / grid) * grid
            target_y = round((old_y + dy) / grid) * grid
        else:
            target_x = old_x + dx
            target_y = old_y + dy
        if (
            self.selected
            and self.selected.kind == "room"
            and self._smart_align.get()
        ):
            tolerance_m = max(
                0.02,
                SMART_ALIGN_TOLERANCE_PX / max(1.0, self._scale_2d()),
            )
            target_x, target_y, self._alignment_guides = snap_room_translation(
                item,
                self.layout["rooms"],
                target_x,
                target_y,
                tolerance_m=tolerance_m,
            )
        actual_dx = target_x - old_x
        actual_dy = target_y - old_y
        if self._translate_selected(actual_dx, actual_dy):
            self._drag_changed = True
            self._drag_anchor = world
        elif not self._snap_to_grid.get():
            self._drag_anchor = world
        self._load_property_panel()
        self.redraw()

    def _room_at(self, x: float, y: float) -> dict | None:
        for room in reversed(self.layout["rooms"]):
            if (
                room["x_m"] <= x <= room["x_m"] + room["length_m"]
                and room["y_m"] <= y <= room["y_m"] + room["width_m"]
            ):
                return room
        return None

    def _reassign_selected_device_room(self) -> None:
        if self.selected is None or self.selected.kind != "device":
            return
        device = self._selected_object()
        if device is None:
            return
        room = self._room_at(device["x_m"], device["y_m"])
        device["room_id"] = None if room is None else room["id"]
        if room is not None and device["type"] in {
            "ffu", "supply", "return", "exhaust", "sensor"
        }:
            device["z_m"] = room["height_m"]

    def _on_left_up(self, event: tk.Event) -> None:
        had_guides = bool(self._alignment_guides)
        drag_changed = self._drag_changed
        self._alignment_guides = []
        if (
            self._drag_anchor is not None
            and self.selected is not None
            and drag_changed
        ):
            if self._resize_handle:
                message = "Spatial room resized"
            else:
                self._reassign_selected_device_room()
                message = "Spatial item moved"
            self._load_property_panel()
            self._persist(message, history_before=self._drag_before)
        self._drag_anchor = None
        self._drag_before = None
        self._drag_changed = False
        self._resize_handle = None
        if had_guides and not drag_changed:
            self.redraw()

    def _on_motion(self, event: tk.Event) -> None:
        x, y = self._canvas_to_world(event.x, event.y)
        self._coord_var.set(f"x {x:.2f} m   y {y:.2f} m")

    def _on_pan_down(self, event: tk.Event) -> None:
        self._pan_anchor = (event.x, event.y)
        self._pan_origin = (
            self.layout["view"]["pan_x"],
            self.layout["view"]["pan_y"],
        )

    def _on_pan_drag(self, event: tk.Event) -> None:
        if self._pan_anchor is None or self._pan_origin is None:
            return
        self.layout["view"]["pan_x"] = self._pan_origin[0] + event.x - self._pan_anchor[0]
        self.layout["view"]["pan_y"] = self._pan_origin[1] + event.y - self._pan_anchor[1]
        self.redraw()

    def _on_wheel(self, event: tk.Event) -> None:
        self._zoom_at(1.1 if event.delta > 0 else 1 / 1.1, event.x, event.y)

    def _zoom_at(self, factor: float, x: float, y: float) -> None:
        before = self._canvas_to_world(x, y)
        self.layout["view"]["zoom_2d"] = max(0.2, min(8.0, self.layout["view"]["zoom_2d"] * factor))
        after = self._world_to_canvas(*before)
        self.layout["view"]["pan_x"] += x - after[0]
        self.layout["view"]["pan_y"] += y - after[1]
        self.redraw()

    def _on_wheel_3d(self, event: tk.Event) -> None:
        self._zoom_3d(1.1 if event.delta > 0 else 1 / 1.1)

    def _zoom_3d(self, factor: float) -> None:
        self.layout["view"]["zoom_3d"] = max(0.2, min(8.0, self.layout["view"]["zoom_3d"] * factor))
        self._draw_3d()

    def rotate_3d(self, delta: float) -> None:
        self.layout["view"]["azimuth_deg"] = (self.layout["view"]["azimuth_deg"] + delta) % 360
        self._update_scene_status()
        self._draw_3d()

    def tilt_3d(self, delta: float) -> None:
        self.layout["view"]["elevation_deg"] = max(
            5.0, min(75.0, self.layout["view"]["elevation_deg"] + delta)
        )
        self._update_scene_status()
        self._draw_3d()

    def reset_3d(self) -> None:
        self.layout["view"]["azimuth_deg"] = 35.0
        self.layout["view"]["elevation_deg"] = 28.0
        self.layout["view"]["zoom_3d"] = 1.0
        self.layout["view"]["pan_3d_x"] = 0.0
        self.layout["view"]["pan_3d_y"] = 0.0
        self._update_scene_status()
        self._draw_3d()

    def _on_pan_3d_down(self, event: tk.Event) -> None:
        self._pan_anchor = (event.x, event.y)
        self._pan_origin = (
            self.layout["view"]["pan_3d_x"],
            self.layout["view"]["pan_3d_y"],
        )

    def _on_pan_3d_drag(self, event: tk.Event) -> None:
        if self._pan_anchor is None or self._pan_origin is None:
            return
        self.layout["view"]["pan_3d_x"] = self._pan_origin[0] + event.x - self._pan_anchor[0]
        self.layout["view"]["pan_3d_y"] = self._pan_origin[1] + event.y - self._pan_anchor[1]
        self._draw_3d()

    def _on_3d_click(self, event: tk.Event) -> None:
        self.canvas_3d.focus_set()
        current = self.canvas_3d.find_withtag("current")
        if not current:
            return
        hit = self._parse_hit(self.canvas_3d.gettags(current[0]))
        if hit is None:
            return
        self.selected = hit
        self._load_property_panel()
        self.redraw()
