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
        "extents_m": extents_m,
    }


def spatial_measurement(
    start: tuple[float, float],
    end: tuple[float, float],
) -> dict[str, float]:
    """Return deterministic CAD measurement deltas and Euclidean distance in metres."""
    x0 = _finite_number(start[0], 0.0)
    y0 = _finite_number(start[1], 0.0)
    x1 = _finite_number(end[0], 0.0)
    y1 = _finite_number(end[1], 0.0)
    dx = x1 - x0
    dy = y1 - y0
    distance = math.hypot(dx, dy)
    angle = math.degrees(math.atan2(dy, dx)) if distance > 0 else 0.0
    return {
        "dx_m": dx,
        "dy_m": dy,
        "distance_m": distance,
        "angle_deg": angle,
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
        self._measure_enabled = tk.BooleanVar(value=False)
        self._measure_start: tuple[float, float] | None = None
        self._measure_end: tuple[float, float] | None = None
        self._measure_hover: tuple[float, float] | None = None

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
        ttk.Checkbutton(
            toolbar,
            text="Measure",
            variable=self._measure_enabled,
            command=self._toggle_measure,
        ).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Fit", command=self.fit_views).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Export SVG", command=self.export_svg).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Export CSV", command=self.export_schedule_csv).pack(side="left", padx=2)
        ttk.Checkbutton(toolbar, text="Grid", variable=self._show_grid, command=self.redraw).pack(
            side="left", padx=(6, 2)
        )
        ttk.Checkbutton(toolbar, text="Snap", variable=self._snap_to_grid).pack(
            side="left", padx=2
        )
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
            text="2D: drag to move • M measure • Esc clear • wheel to zoom • middle/right drag to pan    "
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
        self.canvas_2d.bind("<Key-m>", lambda event: self._toggle_measure_from_key())
        self.canvas_2d.bind("<Escape>", lambda event: self.clear_measurement())
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
        self._history.clear()
        self._measure_start = None
        self._measure_end = None
        self._measure_hover = None
        self._update_history_controls()
        if self.selected and not self._selected_object():
            self.selected = None
        self._load_property_panel()
        self.redraw()

    def _snapshot_layout(self) -> dict:
        return copy.deepcopy(normalize_layout(self.layout))

    def _toggle_measure_from_key(self) -> None:
        self._measure_enabled.set(not self._measure_enabled.get())
        self._toggle_measure()

    def _toggle_measure(self) -> None:
        self._measure_start = None
        self._measure_end = None
        self._measure_hover = None
        if self._measure_enabled.get():
            self._status_setter("Measure mode: click two points in the 2D plan")
        else:
            self._status_setter("Measure mode off")
        self._draw_2d()

    def clear_measurement(self) -> None:
        self._measure_start = None
        self._measure_end = None
        self._measure_hover = None
        self._status_setter(
            "Measurement cleared" if self._measure_enabled.get() else "Ready"
        )
        self._draw_2d()

    def _measurement_point(self, x: float, y: float) -> tuple[float, float]:
        if not self._snap_to_grid.get():
            return (x, y)
        grid = max(0.1, self.layout["grid_m"])
        return (round(x / grid) * grid, round(y / grid) * grid)

    def _update_history_controls(self) -> None:
        if hasattr(self, "_undo_button"):
            self._undo_button.configure(state="normal" if self._history.can_undo else "disabled")
        if hasattr(self, "_redo_button"):
            self._redo_button.configure(state="normal" if self._history.can_redo else "disabled")

    def _commit_layout(self, message: str) -> None:
        project = self._project_getter()
        project.metadata[SPATIAL_METADATA_KEY] = normalize_layout(self.layout)
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
        self._summary_var.set(
            f"{summary['room_count']} rooms • {summary['device_count']} devices"
            f" • {summary['footprint_m2']:.1f} m² footprint"
            f" • {summary['volume_m3']:.1f} m³ volume"
            f"{pressure_text}{unassigned_text}"
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

        measure_end = self._measure_end or self._measure_hover
        if self._measure_start is not None and measure_end is not None:
            start_px = self._world_to_canvas(*self._measure_start)
            end_px = self._world_to_canvas(*measure_end)
            summary = spatial_measurement(self._measure_start, measure_end)
            preview = self._measure_end is None
            canvas.create_line(
                *start_px,
                *end_px,
                fill="#7c3aed",
                width=2,
                dash=(5, 3) if preview else (),
                arrow=tk.BOTH,
                tags=("measurement",),
            )
            for px, py in (start_px, end_px):
                canvas.create_oval(
                    px - 4,
                    py - 4,
                    px + 4,
                    py + 4,
                    fill="#ffffff",
                    outline="#7c3aed",
                    width=2,
                    tags=("measurement",),
                )
            mx = (start_px[0] + end_px[0]) / 2.0
            my = (start_px[1] + end_px[1]) / 2.0
            canvas.create_text(
                mx,
                my - 12,
                text=(
                    f"{summary['distance_m']:.3f} m   "
                    f"ΔX {summary['dx_m']:+.3f}   ΔY {summary['dy_m']:+.3f}"
                ),
                fill="#5b21b6",
                font=("TkDefaultFont", 9, "bold"),
                tags=("measurement",),
            )

        if not self.layout["rooms"] and not self.layout["devices"]:
            canvas.create_text(
                w / 2,
                h / 2,
                text="No spatial layout yet\nUse + Room or open a verification project with room geometry.",
                justify="center",
                fill="#667788",
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
        if self._measure_enabled.get():
            world = self._canvas_to_world(event.x, event.y)
            point = self._measurement_point(*world)
            if self._measure_start is None or self._measure_end is not None:
                self._measure_start = point
                self._measure_end = None
                self._measure_hover = point
                self._status_setter(
                    f"Measure start: x {point[0]:.3f} m, y {point[1]:.3f} m"
                )
            else:
                self._measure_end = point
                self._measure_hover = point
                summary = spatial_measurement(self._measure_start, self._measure_end)
                self._status_setter(
                    "Measured "
                    f"{summary['distance_m']:.3f} m "
                    f"(ΔX {summary['dx_m']:+.3f} m, "
                    f"ΔY {summary['dy_m']:+.3f} m, "
                    f"{summary['angle_deg']:+.1f}°)"
                )
            self._draw_2d()
            return
        current = self.canvas_2d.find_withtag("current")
        hit = None
        if current:
            hit = self._parse_hit(self.canvas_2d.gettags(current[0]))
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
        if (
            self._drag_anchor is not None
            and self.selected is not None
            and self._drag_changed
        ):
            self._reassign_selected_device_room()
            self._load_property_panel()
            self._persist("Spatial item moved", history_before=self._drag_before)
        self._drag_anchor = None
        self._drag_before = None
        self._drag_changed = False

    def _on_motion(self, event: tk.Event) -> None:
        x, y = self._canvas_to_world(event.x, event.y)
        self._coord_var.set(f"x {x:.2f} m   y {y:.2f} m")
        if (
            self._measure_enabled.get()
            and self._measure_start is not None
            and self._measure_end is None
        ):
            self._measure_hover = self._measurement_point(x, y)
            self._draw_2d()

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
