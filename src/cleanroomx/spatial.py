from __future__ import annotations

from dataclasses import dataclass
import copy
import math
import uuid
from typing import Any, Callable

import tkinter as tk
from tkinter import ttk


SPATIAL_METADATA_KEY = "spatial_layout"
SPATIAL_LAYOUT_VERSION = 1
DEVICE_TYPES = ("door", "supply", "return", "exhaust", "ffu", "equipment", "sensor")
DEVICE_COLORS = {
    "door": "#94a3b8",
    "supply": "#38bdf8",
    "return": "#818cf8",
    "exhaust": "#f97316",
    "ffu": "#22c55e",
    "equipment": "#f59e0b",
    "sensor": "#e879f9",
}


def _finite_number(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _positive(value: Any, default: float) -> float:
    number = _finite_number(value, default)
    return number if number > 0 else default


def _nice_ruler_step(scale_px_per_m: float, target_px: float = 72.0) -> float:
    """Return a stable CAD-style metric ruler interval for the current 2D scale."""
    scale = max(_positive(scale_px_per_m, 1.0), 1e-9)
    target_m = max(target_px / scale, 1e-9)
    exponent = math.floor(math.log10(target_m))
    base = 10.0 ** exponent
    fraction = target_m / base
    if fraction <= 1.0:
        multiplier = 1.0
    elif fraction <= 2.0:
        multiplier = 2.0
    elif fraction <= 5.0:
        multiplier = 5.0
    else:
        multiplier = 10.0
    return multiplier * base


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


def _shared_wall_midpoint(
    room_a: dict,
    room_b: dict,
    *,
    tolerance_m: float = 0.05,
) -> tuple[float, float] | None:
    """Return the midpoint of a shared wall, allowing a small drafting tolerance."""
    ax0 = room_a["x_m"]
    ay0 = room_a["y_m"]
    ax1 = ax0 + room_a["length_m"]
    ay1 = ay0 + room_a["width_m"]
    bx0 = room_b["x_m"]
    by0 = room_b["y_m"]
    bx1 = bx0 + room_b["length_m"]
    by1 = by0 + room_b["width_m"]

    y0 = max(ay0, by0)
    y1 = min(ay1, by1)
    if y1 - y0 > tolerance_m:
        if abs(ax1 - bx0) <= tolerance_m:
            return ((ax1 + bx0) / 2.0, (y0 + y1) / 2.0)
        if abs(bx1 - ax0) <= tolerance_m:
            return ((bx1 + ax0) / 2.0, (y0 + y1) / 2.0)

    x0 = max(ax0, bx0)
    x1 = min(ax1, bx1)
    if x1 - x0 > tolerance_m:
        if abs(ay1 - by0) <= tolerance_m:
            return ((x0 + x1) / 2.0, (ay1 + by0) / 2.0)
        if abs(by1 - ay0) <= tolerance_m:
            return ((x0 + x1) / 2.0, (by1 + ay0) / 2.0)
    return None


def pressure_cascade_links(
    layout: dict,
    *,
    tolerance_m: float = 0.05,
) -> list[dict]:
    """Build deterministic high-to-low pressure links for geometrically adjacent rooms."""
    rooms = normalize_layout(layout)["rooms"]
    links: list[dict] = []
    for index, room_a in enumerate(rooms):
        pressure_a = room_a.get("pressure_pa")
        if pressure_a is None:
            continue
        for room_b in rooms[index + 1 :]:
            pressure_b = room_b.get("pressure_pa")
            if pressure_b is None:
                continue
            boundary = _shared_wall_midpoint(room_a, room_b, tolerance_m=tolerance_m)
            if boundary is None:
                continue
            delta = pressure_a - pressure_b
            if abs(delta) <= 1e-9:
                continue
            higher, lower = (room_a, room_b) if delta > 0 else (room_b, room_a)
            links.append(
                {
                    "higher_room_id": higher["id"],
                    "higher_room_name": higher["name"],
                    "lower_room_id": lower["id"],
                    "lower_room_name": lower["name"],
                    "delta_pa": abs(delta),
                    "start": (
                        higher["x_m"] + higher["length_m"] / 2.0,
                        higher["y_m"] + higher["width_m"] / 2.0,
                    ),
                    "end": (
                        lower["x_m"] + lower["length_m"] / 2.0,
                        lower["y_m"] + lower["width_m"] / 2.0,
                    ),
                    "boundary": boundary,
                }
            )
    return links


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
        self._resize_handle: str | None = None
        self._resize_start: dict | None = None
        self._pan_anchor: tuple[int, int] | None = None
        self._pan_origin: tuple[float, float] | None = None
        self._show_grid = tk.BooleanVar(value=True)
        self._snap_to_grid = tk.BooleanVar(value=True)
        self._show_labels = tk.BooleanVar(value=True)
        self._show_dimensions = tk.BooleanVar(value=True)
        self._show_rulers = tk.BooleanVar(value=True)
        self._show_crosshair = tk.BooleanVar(value=True)
        self._show_pressure = tk.BooleanVar(value=True)
        self._show_cascade = tk.BooleanVar(value=True)
        self._show_devices = tk.BooleanVar(value=True)
        self._coord_var = tk.StringVar(value="x 0.00 m   y 0.00 m")
        self._cursor_world: tuple[float, float] | None = None
        self._summary_var = tk.StringVar(value="0 rooms · 0 devices")
        self._selection_var = tk.StringVar(value="No selection")
        self._view_mode_var = tk.StringVar(value="split")
        self._grid_var = tk.StringVar(value="0.5")
        self._mode_buttons: dict[str, ttk.Button] = {}
        self._property_vars: dict[str, tk.StringVar] = {}
        self._property_entries: dict[str, ttk.Entry] = {}
        self._device_type_var = tk.StringVar()
        self._device_room_var = tk.StringVar()
        self._device_type_box: ttk.Combobox | None = None
        self._device_room_box: ttk.Combobox | None = None
        self._room_label_to_id: dict[str, str | None] = {}
        self._model_tree: ttk.Treeview | None = None
        self._tree_selection_guard = False
        self._undo_stack: list[dict] = []
        self._redo_stack: list[dict] = []
        self._history_limit = 50
        self._persisted_layout_snapshot: dict | None = None
        self._undo_button: ttk.Button | None = None
        self._redo_button: ttk.Button | None = None
        self._orbit_anchor: tuple[int, int] | None = None
        self._orbit_origin: tuple[float, float] | None = None

        self._build()
        self.refresh()

    def _build(self) -> None:
        objectbar = ttk.Frame(self, padding=(6, 6, 6, 2))
        objectbar.pack(fill="x")
        ttk.Label(objectbar, text="OBJECTS").pack(side="left", padx=(0, 6))
        ttk.Button(objectbar, text="+ Room", command=self.add_room).pack(side="left", padx=2)
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
                objectbar,
                text=label,
                command=lambda t=device_type: self.add_device(t),
            ).pack(side="left", padx=2)
        ttk.Separator(objectbar, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Button(objectbar, text="Center Selected", command=self.center_selected).pack(side="left", padx=2)
        ttk.Button(objectbar, text="Duplicate", command=self.duplicate_selected).pack(side="left", padx=2)
        ttk.Button(objectbar, text="Delete", command=self.delete_selected).pack(side="left", padx=2)
        ttk.Separator(objectbar, orient="vertical").pack(side="left", fill="y", padx=6)
        self._undo_button = ttk.Button(objectbar, text="Undo", command=self.undo)
        self._undo_button.pack(side="left", padx=2)
        self._redo_button = ttk.Button(objectbar, text="Redo", command=self.redo)
        self._redo_button.pack(side="left", padx=2)

        displaybar = ttk.Frame(self, padding=(6, 0, 6, 3))
        displaybar.pack(fill="x")
        ttk.Label(displaybar, text="VIEW / LAYERS").pack(side="left", padx=(0, 6))
        ttk.Button(displaybar, text="Fit", command=self.fit_views).pack(side="left", padx=2)
        ttk.Button(displaybar, text="Reset 3D", command=self.reset_3d).pack(side="left", padx=2)
        ttk.Checkbutton(displaybar, text="Grid", variable=self._show_grid, command=self.redraw).pack(
            side="left", padx=(6, 2)
        )
        ttk.Checkbutton(displaybar, text="Labels", variable=self._show_labels, command=self.redraw).pack(
            side="left", padx=2
        )
        ttk.Checkbutton(
            displaybar,
            text="Dimensions",
            variable=self._show_dimensions,
            command=self.redraw,
        ).pack(side="left", padx=2)
        ttk.Checkbutton(displaybar, text="Rulers", variable=self._show_rulers, command=self.redraw).pack(
            side="left", padx=2
        )
        ttk.Checkbutton(
            displaybar,
            text="Crosshair",
            variable=self._show_crosshair,
            command=self.redraw,
        ).pack(side="left", padx=2)
        ttk.Checkbutton(displaybar, text="Pressure", variable=self._show_pressure, command=self.redraw).pack(
            side="left", padx=2
        )
        ttk.Checkbutton(
            displaybar,
            text="ΔP Links",
            variable=self._show_cascade,
            command=self.redraw,
        ).pack(side="left", padx=2)
        ttk.Checkbutton(displaybar, text="Devices", variable=self._show_devices, command=self.redraw).pack(
            side="left", padx=(2, 6)
        )
        ttk.Label(
            displaybar,
            text="Wheel zoom · drag pan · Shift+drag 3D orbit · arrows nudge · F center",
        ).pack(side="left", padx=(8, 2))
        ttk.Button(
            displaybar,
            text="Sync geometry to analysis",
            command=self._on_sync_requested,
        ).pack(side="right", padx=2)

        viewbar = ttk.Frame(self, padding=(6, 0, 6, 4))
        viewbar.pack(fill="x")
        ttk.Label(viewbar, text="Workspace").pack(side="left", padx=(0, 5))
        for mode, label in (("2d", "2D"), ("split", "Split"), ("3d", "3D")):
            button = ttk.Button(
                viewbar,
                text=label,
                width=7,
                command=lambda m=mode: self.set_view_mode(m),
            )
            button.pack(side="left", padx=2)
            self._mode_buttons[mode] = button
        ttk.Separator(viewbar, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Label(viewbar, text="2D zoom").pack(side="left", padx=(0, 4))
        ttk.Button(viewbar, text="−", width=3, command=lambda: self.zoom_2d(1 / 1.15)).pack(
            side="left", padx=1
        )
        ttk.Button(viewbar, text="+", width=3, command=lambda: self.zoom_2d(1.15)).pack(
            side="left", padx=1
        )
        ttk.Label(viewbar, text="3D zoom").pack(side="left", padx=(10, 4))
        ttk.Button(viewbar, text="−", width=3, command=lambda: self._zoom_3d(1 / 1.15)).pack(
            side="left", padx=1
        )
        ttk.Button(viewbar, text="+", width=3, command=lambda: self._zoom_3d(1.15)).pack(
            side="left", padx=1
        )
        ttk.Separator(viewbar, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Label(viewbar, text="Snap grid").pack(side="left", padx=(0, 4))
        grid_box = ttk.Combobox(
            viewbar,
            textvariable=self._grid_var,
            values=("0.10", "0.25", "0.50", "1.00", "2.00"),
            state="readonly",
            width=6,
        )
        grid_box.pack(side="left")
        grid_box.bind("<<ComboboxSelected>>", lambda event: self.set_grid_spacing())
        ttk.Label(viewbar, text="m").pack(side="left", padx=(3, 4))
        ttk.Checkbutton(viewbar, text="Snap", variable=self._snap_to_grid).pack(
            side="left", padx=(0, 8)
        )
        ttk.Label(
            viewbar,
            text="Ctrl+Z/Y undo/redo · arrows nudge · Shift+arrows ×5 · Ctrl+D duplicate",
        ).pack(side="right")

        body = ttk.Panedwindow(self, orient="horizontal")
        self._body = body
        body.pack(fill="both", expand=True, padx=6, pady=(3, 6))

        two_d = ttk.Frame(body)
        self._two_d = two_d
        body.add(two_d, weight=4)
        ttk.Label(two_d, text="2D FLOOR PLAN", font=("TkDefaultFont", 10, "bold")).pack(
            anchor="w", padx=4, pady=(2, 4)
        )
        self.canvas_2d = tk.Canvas(two_d, background="#f7f9fb", highlightthickness=1)
        self.canvas_2d.pack(fill="both", expand=True)
        footer2d = ttk.Frame(two_d)
        footer2d.pack(fill="x", padx=4, pady=2)
        ttk.Label(footer2d, textvariable=self._coord_var, anchor="w").pack(side="left")
        ttk.Label(footer2d, textvariable=self._summary_var, anchor="e").pack(side="right")

        right = ttk.Panedwindow(body, orient="vertical")
        self._right = right
        body.add(right, weight=4)

        three_d = ttk.Frame(right)
        right.add(three_d, weight=3)
        header3 = ttk.Frame(three_d)
        header3.pack(fill="x")
        ttk.Label(header3, text="3D DIGITAL TWIN", font=("TkDefaultFont", 10, "bold")).pack(
            side="left", padx=4, pady=(2, 4)
        )
        for label, delta in (("↺", -15), ("↻", 15)):
            ttk.Button(header3, text=label, width=3, command=lambda d=delta: self.rotate_3d(d)).pack(
                side="right", padx=2
            )
        ttk.Button(header3, text="↓", width=3, command=lambda: self.tilt_3d(-5)).pack(side="right", padx=2)
        ttk.Button(header3, text="↑", width=3, command=lambda: self.tilt_3d(5)).pack(side="right", padx=2)
        ttk.Button(header3, text="Reset", command=self.reset_3d).pack(side="right", padx=2)
        ttk.Button(header3, text="Front", command=lambda: self.set_3d_preset("front")).pack(side="right", padx=2)
        ttk.Button(header3, text="Top", command=lambda: self.set_3d_preset("top")).pack(side="right", padx=2)
        ttk.Button(header3, text="ISO", command=lambda: self.set_3d_preset("iso")).pack(side="right", padx=2)
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
            ("z_m", "Z (m)"),
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
            entry = ttk.Entry(inspector, textvariable=var, width=18)
            self._property_entries[key] = entry
            entry.grid(
                row=row, column=column + 1, sticky="ew", padx=(0, 8), pady=2
            )
        device_row = 2 + (len(fields) + 1) // 2
        ttk.Label(inspector, text="Device type").grid(
            row=device_row, column=0, sticky="w", padx=(0, 4), pady=2
        )
        self._device_type_box = ttk.Combobox(
            inspector,
            textvariable=self._device_type_var,
            values=DEVICE_TYPES,
            state="disabled",
            width=16,
        )
        self._device_type_box.grid(row=device_row, column=1, sticky="ew", padx=(0, 8), pady=2)
        ttk.Label(inspector, text="Assigned room").grid(
            row=device_row, column=2, sticky="w", padx=(0, 4), pady=2
        )
        self._device_room_box = ttk.Combobox(
            inspector,
            textvariable=self._device_room_var,
            state="disabled",
            width=18,
        )
        self._device_room_box.grid(row=device_row, column=3, sticky="ew", padx=(0, 8), pady=2)

        button_row = device_row + 1
        ttk.Button(inspector, text="Center selected", command=self.center_selected).grid(
            row=button_row, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )
        ttk.Button(inspector, text="Apply", command=self.apply_properties).grid(
            row=button_row, column=3, sticky="e", pady=(8, 0)
        )

        browser_row = button_row + 1
        ttk.Separator(inspector, orient="horizontal").grid(
            row=browser_row, column=0, columnspan=4, sticky="ew", pady=(10, 6)
        )
        ttk.Label(inspector, text="Model Browser", font=("TkDefaultFont", 10, "bold")).grid(
            row=browser_row + 1, column=0, columnspan=4, sticky="w", pady=(0, 4)
        )
        self._model_tree = ttk.Treeview(
            inspector,
            columns=("kind", "details"),
            show="tree headings",
            height=6,
            selectmode="browse",
        )
        self._model_tree.heading("#0", text="Object")
        self._model_tree.heading("kind", text="Kind")
        self._model_tree.heading("details", text="Geometry / placement")
        self._model_tree.column("#0", width=180, minwidth=120, stretch=True)
        self._model_tree.column("kind", width=90, minwidth=70, stretch=False)
        self._model_tree.column("details", width=190, minwidth=120, stretch=True)
        self._model_tree.grid(
            row=browser_row + 2,
            column=0,
            columnspan=4,
            sticky="nsew",
            pady=(0, 2),
        )
        self._model_tree.bind("<<TreeviewSelect>>", self._on_tree_selected)
        self._model_tree.bind("<Double-1>", lambda event: self.center_selected())

        inspector.columnconfigure(1, weight=1)
        inspector.columnconfigure(3, weight=1)
        inspector.rowconfigure(browser_row + 2, weight=1)

        self.canvas_2d.bind("<Configure>", lambda event: self.redraw())
        self.canvas_3d.bind("<Configure>", lambda event: self._draw_3d())
        self.canvas_2d.bind("<Motion>", self._on_motion)
        self.canvas_2d.bind("<Leave>", self._on_leave_2d)
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
        self.canvas_3d.bind("<MouseWheel>", self._on_wheel_3d)
        self.canvas_3d.bind("<Button-4>", lambda event: self._zoom_3d(1.1))
        self.canvas_3d.bind("<Button-5>", lambda event: self._zoom_3d(1 / 1.1))
        self.canvas_3d.bind("<Button-1>", self._on_3d_click)
        self.canvas_3d.bind("<Shift-Button-1>", self._on_orbit_down)
        self.canvas_3d.bind("<Shift-B1-Motion>", self._on_orbit_drag)
        self.canvas_3d.bind("<Button-2>", self._on_pan_3d_down)
        self.canvas_3d.bind("<B2-Motion>", self._on_pan_3d_drag)
        self.canvas_3d.bind("<Button-3>", self._on_pan_3d_down)
        self.canvas_3d.bind("<B3-Motion>", self._on_pan_3d_drag)

        for canvas in (self.canvas_2d, self.canvas_3d):
            canvas.bind("<Delete>", lambda event: self.delete_selected())
            canvas.bind("<Key-f>", lambda event: self.center_selected())
            canvas.bind("<Key-F>", lambda event: self.center_selected())
            canvas.bind("<Home>", lambda event: self.fit_views())
            canvas.bind("<Control-d>", lambda event: self.duplicate_selected())
            canvas.bind("<Control-D>", lambda event: self.duplicate_selected())
            canvas.bind("<Control-z>", lambda event: self.undo())
            canvas.bind("<Control-Z>", lambda event: self.undo())
            canvas.bind("<Control-y>", lambda event: self.redo())
            canvas.bind("<Control-Y>", lambda event: self.redo())
            canvas.bind("<Left>", lambda event: self.nudge_selected(-1, 0))
            canvas.bind("<Right>", lambda event: self.nudge_selected(1, 0))
            canvas.bind("<Up>", lambda event: self.nudge_selected(0, -1))
            canvas.bind("<Down>", lambda event: self.nudge_selected(0, 1))
            canvas.bind("<Shift-Left>", lambda event: self.nudge_selected(-5, 0))
            canvas.bind("<Shift-Right>", lambda event: self.nudge_selected(5, 0))
            canvas.bind("<Shift-Up>", lambda event: self.nudge_selected(0, -5))
            canvas.bind("<Shift-Down>", lambda event: self.nudge_selected(0, 5))
        self.bind_all("<Escape>", lambda event: self.clear_selection())
        self._update_view_mode_buttons()

    def _update_view_mode_buttons(self) -> None:
        active = self._view_mode_var.get()
        for mode, button in self._mode_buttons.items():
            button.configure(style="Accent.TButton" if mode == active else "TButton")

    def set_view_mode(self, mode: str, *, announce: bool = True) -> None:
        if mode not in {"2d", "split", "3d"}:
            return
        self._view_mode_var.set(mode)
        for pane in (self._two_d, self._right):
            try:
                self._body.forget(pane)
            except tk.TclError:
                pass
        if mode in {"2d", "split"}:
            self._body.add(self._two_d, weight=7 if mode == "2d" else 4)
        if mode in {"3d", "split"}:
            self._body.add(self._right, weight=7 if mode == "3d" else 4)
        self._update_view_mode_buttons()
        self.after_idle(self.redraw)
        if announce:
            label = {"2d": "2D floor plan", "split": "2D + 3D split", "3d": "3D digital twin"}[mode]
            self._status_setter(f"Spatial workspace: {label}")

    def set_grid_spacing(self) -> None:
        try:
            spacing = float(self._grid_var.get())
        except ValueError:
            return
        if not math.isfinite(spacing) or spacing <= 0:
            return
        self.layout["grid_m"] = spacing
        self._persist(f"Snap grid set to {spacing:g} m")

    def refresh(self) -> None:
        project = self._project_getter()
        analysis = self._analysis_getter()
        self.layout = ensure_project_layout(project, analysis)
        self._grid_var.set(f"{self.layout['grid_m']:g}")
        if self.selected and not self._selected_object():
            self.selected = None
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._persisted_layout_snapshot = copy.deepcopy(normalize_layout(self.layout))
        self._update_summary()
        self._load_property_panel()
        self._update_history_controls()
        self.redraw()

    def _persist(self, message: str) -> None:
        project = self._project_getter()
        normalized = normalize_layout(self.layout)
        previous = self._persisted_layout_snapshot
        if previous is not None and normalized != previous:
            self._undo_stack.append(copy.deepcopy(previous))
            if len(self._undo_stack) > self._history_limit:
                del self._undo_stack[0 : len(self._undo_stack) - self._history_limit]
            self._redo_stack.clear()
        project.metadata[SPATIAL_METADATA_KEY] = normalized
        self.layout = project.metadata[SPATIAL_METADATA_KEY]
        self._persisted_layout_snapshot = copy.deepcopy(self.layout)
        self._on_change()
        self._update_summary()
        self._update_history_controls()
        self._status_setter(message)
        self.redraw()

    def _update_history_controls(self) -> None:
        if self._undo_button is not None:
            self._undo_button.configure(state="normal" if self._undo_stack else "disabled")
        if self._redo_button is not None:
            self._redo_button.configure(state="normal" if self._redo_stack else "disabled")

    def _restore_history_layout(self, layout: dict, message: str) -> None:
        project = self._project_getter()
        project.metadata[SPATIAL_METADATA_KEY] = normalize_layout(layout)
        self.layout = project.metadata[SPATIAL_METADATA_KEY]
        self._persisted_layout_snapshot = copy.deepcopy(self.layout)
        self._grid_var.set(f"{self.layout['grid_m']:g}")
        if self.selected and not self._selected_object():
            self.selected = None
        self._on_change()
        self._update_summary()
        self._load_property_panel()
        self._update_history_controls()
        self._status_setter(message)
        self.redraw()

    def undo(self) -> None:
        if not self._undo_stack:
            self._status_setter("Nothing to undo")
            return
        current = copy.deepcopy(
            self._persisted_layout_snapshot
            if self._persisted_layout_snapshot is not None
            else normalize_layout(self.layout)
        )
        target = self._undo_stack.pop()
        self._redo_stack.append(current)
        self._restore_history_layout(target, "Undid spatial edit")

    def redo(self) -> None:
        if not self._redo_stack:
            self._status_setter("Nothing to redo")
            return
        current = copy.deepcopy(
            self._persisted_layout_snapshot
            if self._persisted_layout_snapshot is not None
            else normalize_layout(self.layout)
        )
        target = self._redo_stack.pop()
        self._undo_stack.append(current)
        if len(self._undo_stack) > self._history_limit:
            del self._undo_stack[0 : len(self._undo_stack) - self._history_limit]
        self._restore_history_layout(target, "Redid spatial edit")

    def _update_summary(self) -> None:
        rooms = self.layout["rooms"]
        room_count = len(rooms)
        device_count = len(self.layout["devices"])
        total_area = sum(room["length_m"] * room["width_m"] for room in rooms)
        total_volume = sum(
            room["length_m"] * room["width_m"] * room["height_m"] for room in rooms
        )
        self._summary_var.set(
            f"{room_count} room{'s' if room_count != 1 else ''} · "
            f"{device_count} device{'s' if device_count != 1 else ''} · "
            f"{total_area:.1f} m² · {total_volume:.1f} m³"
        )
        self._update_model_tree()

    def _update_model_tree(self) -> None:
        tree = self._model_tree
        if tree is None:
            return
        self._tree_selection_guard = True
        try:
            children = tree.get_children()
            if children:
                tree.delete(*children)
            rooms_parent = tree.insert(
                "", "end", iid="group:rooms", text=f"Rooms ({len(self.layout['rooms'])})", open=True
            )
            for room in self.layout["rooms"]:
                pressure = room.get("pressure_pa")
                details = (
                    f"{room['length_m']:.2f}×{room['width_m']:.2f}×{room['height_m']:.2f} m"
                )
                if pressure is not None:
                    details += f" · {pressure:g} Pa"
                tree.insert(
                    rooms_parent,
                    "end",
                    iid=f"room:{room['id']}",
                    text=room["name"],
                    values=("Room", details),
                )
            devices_parent = tree.insert(
                "", "end", iid="group:devices", text=f"Devices ({len(self.layout['devices'])})", open=True
            )
            room_names = {room["id"]: room["name"] for room in self.layout["rooms"]}
            for device in self.layout["devices"]:
                room_name = room_names.get(device.get("room_id"), "Unassigned")
                details = f"{room_name} · z {device.get('z_m', 0.0):.2f} m"
                tree.insert(
                    devices_parent,
                    "end",
                    iid=f"device:{device['id']}",
                    text=device["name"],
                    values=(device.get("type", "device").title(), details),
                )
            self._sync_tree_selection()
        finally:
            self._tree_selection_guard = False

    def _sync_tree_selection(self) -> None:
        tree = self._model_tree
        if tree is None:
            return
        current = tree.selection()
        if self.selected is None:
            if current:
                tree.selection_remove(*current)
            return
        iid = f"{self.selected.kind}:{self.selected.item_id}"
        if not tree.exists(iid):
            return
        self._tree_selection_guard = True
        try:
            tree.selection_set(iid)
            tree.see(iid)
        finally:
            self._tree_selection_guard = False

    def _on_tree_selected(self, event=None) -> None:
        if self._tree_selection_guard or self._model_tree is None:
            return
        selection = self._model_tree.selection()
        if not selection:
            return
        iid = selection[0]
        if iid.startswith("room:"):
            self.selected = _Hit("room", iid.split(":", 1)[1])
        elif iid.startswith("device:"):
            self.selected = _Hit("device", iid.split(":", 1)[1])
        else:
            return
        self._load_property_panel()
        self.redraw()

    def clear_selection(self) -> None:
        self.selected = None
        self._resize_handle = None
        self._resize_start = None
        self._drag_anchor = None
        self._load_property_panel()
        self.redraw()

    def _selected_object(self) -> dict | None:
        if self.selected is None:
            return None
        collection = self.layout["rooms"] if self.selected.kind == "room" else self.layout["devices"]
        return next((item for item in collection if item["id"] == self.selected.item_id), None)

    def _load_property_panel(self) -> None:
        item = self._selected_object()
        if item is None:
            self._selection_var.set("No selection")
            for key, var in self._property_vars.items():
                var.set("")
                entry = self._property_entries.get(key)
                if entry is not None:
                    entry.configure(state="disabled")
            self._device_type_var.set("")
            self._device_room_var.set("")
            if self._device_type_box is not None:
                self._device_type_box.configure(state="disabled")
            if self._device_room_box is not None:
                self._device_room_box.configure(state="disabled", values=())
            self._sync_tree_selection()
            return

        is_room = bool(self.selected and self.selected.kind == "room")
        prefix = "Room" if is_room else item.get("type", "Device").title()
        self._selection_var.set(f"{prefix}: {item.get('name', '')}")
        room_only = {"length_m", "width_m", "height_m", "pressure_pa"}
        device_only = {"z_m"}
        for key, var in self._property_vars.items():
            value = item.get(key, "")
            var.set("" if value is None else str(value))
            entry = self._property_entries.get(key)
            if entry is None:
                continue
            allowed = key not in room_only | device_only
            if is_room and key in room_only:
                allowed = True
            if not is_room and key in device_only:
                allowed = True
            entry.configure(state="normal" if allowed else "disabled")

        labels: list[str] = ["Unassigned"]
        self._room_label_to_id = {"Unassigned": None}
        for room in self.layout["rooms"]:
            label = f"{room['name']} · {room['id'][-6:]}"
            labels.append(label)
            self._room_label_to_id[label] = room["id"]

        if is_room:
            self._device_type_var.set("")
            self._device_room_var.set("")
            if self._device_type_box is not None:
                self._device_type_box.configure(state="disabled")
            if self._device_room_box is not None:
                self._device_room_box.configure(state="disabled", values=labels)
        else:
            self._device_type_var.set(item.get("type", "equipment"))
            selected_room = "Unassigned"
            room_id = item.get("room_id")
            for label, mapped_id in self._room_label_to_id.items():
                if mapped_id == room_id:
                    selected_room = label
                    break
            self._device_room_var.set(selected_room)
            if self._device_type_box is not None:
                self._device_type_box.configure(state="readonly")
            if self._device_room_box is not None:
                self._device_room_box.configure(state="readonly", values=labels)
        self._sync_tree_selection()

    def apply_properties(self) -> None:
        item = self._selected_object()
        if item is None:
            return
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
        elif self.selected and self.selected.kind == "device":
            z_text = self._property_vars["z_m"].get().strip()
            if z_text:
                item["z_m"] = _finite_number(z_text, item.get("z_m", 0.0))
            device_type = self._device_type_var.get().strip().lower()
            if device_type in DEVICE_TYPES:
                item["type"] = device_type
            room_label = self._device_room_var.get().strip()
            if room_label in self._room_label_to_id:
                item["room_id"] = self._room_label_to_id[room_label]
        self._load_property_panel()
        self._persist("Spatial properties updated")

    def add_room(self) -> None:
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
        self._persist(f"Added {room['name']}")

    def add_device(self, device_type: str) -> None:
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
        self._persist(f"Added {device_type}")

    def duplicate_selected(self) -> None:
        item = self._selected_object()
        if item is None or self.selected is None:
            return
        grid = max(0.05, self.layout["grid_m"])
        clone = copy.deepcopy(item)
        clone["name"] = f"{item.get('name', self.selected.kind.title())} Copy"
        clone["x_m"] = item.get("x_m", 0.0) + grid
        clone["y_m"] = item.get("y_m", 0.0) + grid

        if self.selected.kind == "room":
            source_room_id = item["id"]
            clone["id"] = f"room-{uuid.uuid4().hex[:8]}"
            self.layout["rooms"].append(clone)
            copied_devices = 0
            for device in list(self.layout["devices"]):
                if device.get("room_id") != source_room_id:
                    continue
                device_clone = copy.deepcopy(device)
                device_clone["id"] = f"device-{uuid.uuid4().hex[:8]}"
                device_clone["name"] = f"{device.get('name', 'Device')} Copy"
                device_clone["room_id"] = clone["id"]
                device_clone["x_m"] = device.get("x_m", 0.0) + grid
                device_clone["y_m"] = device.get("y_m", 0.0) + grid
                self.layout["devices"].append(device_clone)
                copied_devices += 1
            self.selected = _Hit("room", clone["id"])
            suffix = (
                f" with {copied_devices} assigned device{'s' if copied_devices != 1 else ''}"
                if copied_devices
                else ""
            )
            message = f"Duplicated room{suffix}"
        else:
            clone["id"] = f"device-{uuid.uuid4().hex[:8]}"
            self.layout["devices"].append(clone)
            self.selected = _Hit("device", clone["id"])
            message = "Duplicated device"

        self._load_property_panel()
        self._persist(message)

    def _translate_room_devices(self, room_id: str, dx: float, dy: float) -> None:
        if abs(dx) < 1e-12 and abs(dy) < 1e-12:
            return
        for device in self.layout["devices"]:
            if device.get("room_id") == room_id:
                device["x_m"] = device.get("x_m", 0.0) + dx
                device["y_m"] = device.get("y_m", 0.0) + dy

    def nudge_selected(self, x_steps: int, y_steps: int) -> None:
        item = self._selected_object()
        if item is None or self.selected is None:
            return
        grid = max(0.05, self.layout["grid_m"])
        dx = x_steps * grid
        dy = y_steps * grid
        item["x_m"] = item.get("x_m", 0.0) + dx
        item["y_m"] = item.get("y_m", 0.0) + dy
        if self.selected.kind == "room":
            self._translate_room_devices(self.selected.item_id, dx, dy)
        self._load_property_panel()
        self._persist(
            f"Nudged {self.selected.kind} by {dx:+g} m, {dy:+g} m"
        )

    def delete_selected(self) -> None:
        if self.selected is None:
            return
        collection_name = "rooms" if self.selected.kind == "room" else "devices"
        item_id = self.selected.item_id
        self.layout[collection_name] = [item for item in self.layout[collection_name] if item["id"] != item_id]
        if self.selected.kind == "room":
            self.layout["devices"] = [
                item for item in self.layout["devices"] if item.get("room_id") != item_id
            ]
        self.selected = None
        self._load_property_panel()
        self._persist("Deleted spatial item")

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

    def center_selected(self) -> None:
        item = self._selected_object()
        if item is None:
            self._status_setter("Select a room or device to center")
            return

        if self.selected and self.selected.kind == "room":
            target_x = item["x_m"] + item["length_m"] / 2.0
            target_y = item["y_m"] + item["width_m"] / 2.0
            target_z = item["height_m"] / 2.0
        else:
            target_x = item["x_m"]
            target_y = item["y_m"]
            target_z = item.get("z_m", 0.0)

        scale = self._scale_2d()
        self.layout["view"]["pan_x"] = -target_x * scale
        self.layout["view"]["pan_y"] = -target_y * scale

        min_x, min_y, max_x, max_y = self._bounds()
        cx = (min_x + max_x) / 2.0
        cy = (min_y + max_y) / 2.0
        px, py = self._project_3d(target_x - cx, target_y - cy, target_z)
        self.layout["view"]["pan_3d_x"] += self.canvas_3d.winfo_width() / 2.0 - px
        self.layout["view"]["pan_3d_y"] += self.canvas_3d.winfo_height() / 2.0 - py
        self.redraw()
        self._status_setter(f"Centered {item.get('name', 'selection')} in 2D and 3D")

    def redraw(self) -> None:
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

        for room in self.layout["rooms"]:
            x0, y0 = self._world_to_canvas(room["x_m"], room["y_m"])
            x1, y1 = self._world_to_canvas(room["x_m"] + room["length_m"], room["y_m"] + room["width_m"])
            selected = self.selected == _Hit("room", room["id"])
            outline = "#1d4ed8" if selected else "#34495e"
            fill = (
                _pressure_fill(room.get("pressure_pa"), pmin, pmax)
                if self._show_pressure.get()
                else "#eef2f7"
            )
            canvas.create_rectangle(
                x0, y0, x1, y1,
                fill=fill, outline=outline, width=3 if selected else 2,
                tags=(f"room:{room['id']}", "room"),
            )
            if self._show_labels.get() or selected:
                pressure_text = (
                    ""
                    if room.get("pressure_pa") is None or not self._show_pressure.get()
                    else f"\n{room['pressure_pa']:g} Pa"
                )
                area_m2 = room["length_m"] * room["width_m"]
                selected_metrics = (
                    f"\n{area_m2:.1f} m² · H {room['height_m']:g} m"
                    if selected
                    else ""
                )
                canvas.create_text(
                    (x0 + x1) / 2,
                    (y0 + y1) / 2,
                    text=(
                        f"{room['name']}\n"
                        f"{room['length_m']:g} × {room['width_m']:g} m"
                        f"{selected_metrics}{pressure_text}"
                    ),
                    justify="center",
                    fill="#0f172a",
                    tags=(f"room:{room['id']}", "room"),
                )
            if self._show_dimensions.get():
                self._draw_room_dimensions(canvas, room, x0, y0, x1, y1, selected=selected)
            if selected:
                handle_size = 5
                for handle, hx, hy in (
                    ("nw", x0, y0),
                    ("ne", x1, y0),
                    ("se", x1, y1),
                    ("sw", x0, y1),
                ):
                    canvas.create_rectangle(
                        hx - handle_size,
                        hy - handle_size,
                        hx + handle_size,
                        hy + handle_size,
                        fill="#ffffff",
                        outline="#1d4ed8",
                        width=2,
                        tags=(f"resize:{room['id']}:{handle}", "resize"),
                    )

        if self._show_cascade.get():
            self._draw_pressure_cascade_2d(canvas)

        symbols = {
            "door": "D",
            "supply": "S",
            "return": "R",
            "exhaust": "E",
            "ffu": "F",
            "equipment": "Q",
            "sensor": "●",
        }
        if self._show_devices.get():
            for device in self.layout["devices"]:
                x, y = self._world_to_canvas(device["x_m"], device["y_m"])
                selected = self.selected == _Hit("device", device["id"])
                radius = 9 if selected else 7
                fill = DEVICE_COLORS.get(device["type"], "#cbd5e1")
                canvas.create_oval(
                    x - radius, y - radius, x + radius, y + radius,
                    fill=fill, outline="#0f172a" if selected else "#334155",
                    width=3 if selected else 2,
                    tags=(f"device:{device['id']}", "device"),
                )
                canvas.create_text(
                    x,
                    y,
                    text=symbols.get(device["type"], "?"),
                    fill="#0f172a",
                    font=("TkDefaultFont", 8, "bold"),
                    tags=(f"device:{device['id']}", "device"),
                )
                if selected or self._show_labels.get():
                    canvas.create_text(
                        x,
                        y - 18,
                        text=device.get("name", device["type"]),
                        fill="#1f2937",
                        font=("TkDefaultFont", 8, "bold" if selected else "normal"),
                        tags=(f"device:{device['id']}", "device"),
                    )

        if pressures and self._show_pressure.get():
            self._draw_pressure_legend(canvas, pmin, pmax, dark=False)
        if self.layout["devices"] and self._show_devices.get():
            self._draw_device_legend(canvas, dark=False)
        if self._show_rulers.get():
            self._draw_2d_rulers(canvas)
        self._draw_2d_hud(canvas)
        if self._show_crosshair.get() and self._cursor_world is not None:
            self._draw_cursor_overlay(canvas, *self._cursor_world)

        if not self.layout["rooms"] and not self.layout["devices"]:
            canvas.create_text(
                w / 2,
                h / 2,
                text="No spatial layout yet\nUse + Room or open a verification project with room geometry.",
                justify="center",
                fill="#667788",
            )

    def _draw_pressure_cascade_2d(self, canvas: tk.Canvas) -> None:
        """Overlay high-to-low pressure links only across shared room boundaries."""
        for link in pressure_cascade_links(self.layout):
            sx, sy = self._world_to_canvas(*link["start"])
            ex, ey = self._world_to_canvas(*link["end"])
            dx = ex - sx
            dy = ey - sy
            length = math.hypot(dx, dy)
            if length <= 1e-6:
                continue
            padding = min(28.0, length * 0.22)
            ux = dx / length
            uy = dy / length
            start = (sx + ux * padding, sy + uy * padding)
            end = (ex - ux * padding, ey - uy * padding)
            canvas.create_line(
                *start,
                *end,
                fill="#dc2626",
                width=2,
                arrow="last",
                arrowshape=(9, 11, 4),
                tags=("cascade",),
            )
            bx, by = self._world_to_canvas(*link["boundary"])
            canvas.create_text(
                bx,
                by - 11,
                text=f"ΔP {link['delta_pa']:g} Pa",
                fill="#991b1b",
                font=("TkDefaultFont", 7, "bold"),
                tags=("cascade",),
            )

    def _draw_room_dimensions(
        self,
        canvas: tk.Canvas,
        room: dict,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        *,
        selected: bool,
    ) -> None:
        """Draw compact CAD-style length/width annotations for a room."""
        line_fill = "#1d4ed8" if selected else "#64748b"
        text_fill = "#0f172a"
        inset = 12.0
        if abs(x1 - x0) >= 58:
            y = y0 + inset
            canvas.create_line(
                x0 + inset,
                y,
                x1 - inset,
                y,
                fill=line_fill,
                width=1,
                arrow="both",
                tags=(f"room:{room['id']}", "dimension"),
            )
            canvas.create_text(
                (x0 + x1) / 2,
                y + 9,
                text=f"{room['length_m']:g} m",
                fill=text_fill,
                font=("TkDefaultFont", 7, "bold" if selected else "normal"),
                tags=(f"room:{room['id']}", "dimension"),
            )
        if abs(y1 - y0) >= 58:
            x = x1 - inset
            canvas.create_line(
                x,
                y0 + inset,
                x,
                y1 - inset,
                fill=line_fill,
                width=1,
                arrow="both",
                tags=(f"room:{room['id']}", "dimension"),
            )
            canvas.create_text(
                x - 20,
                (y0 + y1) / 2,
                text=f"{room['width_m']:g} m",
                fill=text_fill,
                font=("TkDefaultFont", 7, "bold" if selected else "normal"),
                tags=(f"room:{room['id']}", "dimension"),
            )

    def _draw_2d_hud(self, canvas: tk.Canvas) -> None:
        """Draw compact CAD-style view state and a scale bar."""
        zoom = self.layout["view"]["zoom_2d"]
        grid = self.layout["grid_m"]
        snap = "SNAP" if self._snap_to_grid.get() else "FREE"
        canvas.create_rectangle(10, 10, 230, 36, fill="#ffffff", outline="#cbd5e1", tags=("hud",))
        canvas.create_text(
            18,
            23,
            anchor="w",
            text=f"2D  ·  {zoom * 100:.0f}%  ·  grid {grid:g} m  ·  {snap}",
            fill="#334155",
            font=("TkDefaultFont", 8, "bold"),
            tags=("hud",),
        )

        scale = self._scale_2d()
        target_px = 90.0
        raw_m = target_px / max(scale, 1e-9)
        candidates = (0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0)
        scale_m = min(candidates, key=lambda value: abs(value - raw_m))
        length_px = scale_m * scale
        x0 = 18.0
        y = max(24.0, canvas.winfo_height() - 22.0)
        canvas.create_line(x0, y, x0 + length_px, y, fill="#334155", width=3, tags=("hud",))
        canvas.create_line(x0, y - 4, x0, y + 4, fill="#334155", width=2, tags=("hud",))
        canvas.create_line(x0 + length_px, y - 4, x0 + length_px, y + 4, fill="#334155", width=2, tags=("hud",))
        canvas.create_text(
            x0 + length_px / 2,
            y - 9,
            text=f"{scale_m:g} m",
            fill="#334155",
            font=("TkDefaultFont", 8),
            tags=("hud",),
        )

    def _draw_2d_rulers(self, canvas: tk.Canvas) -> None:
        """Overlay compact top/left metric rulers that follow pan and zoom."""
        w = max(1, canvas.winfo_width())
        h = max(1, canvas.winfo_height())
        ruler = 22
        bg = "#ffffff"
        edge = "#cbd5e1"
        fg = "#475569"
        canvas.create_rectangle(0, 0, w, ruler, fill=bg, outline="", tags=("ruler",))
        canvas.create_rectangle(0, 0, ruler, h, fill=bg, outline="", tags=("ruler",))
        canvas.create_line(0, ruler, w, ruler, fill=edge, tags=("ruler",))
        canvas.create_line(ruler, 0, ruler, h, fill=edge, tags=("ruler",))

        scale = self._scale_2d()
        major = _nice_ruler_step(scale)
        minor = major / 5.0
        x0, y0 = self._canvas_to_world(0, 0)
        x1, y1 = self._canvas_to_world(w, h)

        start_x = math.floor(min(x0, x1) / minor) * minor
        end_x = math.ceil(max(x0, x1) / minor) * minor
        x = start_x
        guard = 0
        while x <= end_x + minor * 0.5 and guard < 500:
            cx, _ = self._world_to_canvas(x, 0)
            major_tick = math.isclose(x / major, round(x / major), abs_tol=1e-6)
            tick = 10 if major_tick else 5
            canvas.create_line(cx, ruler, cx, ruler - tick, fill=fg, tags=("ruler",))
            if major_tick and ruler + 2 <= cx <= w - 2:
                canvas.create_text(
                    cx + 2,
                    2,
                    anchor="nw",
                    text=f"{x:g}",
                    fill=fg,
                    font=("TkDefaultFont", 7),
                    tags=("ruler",),
                )
            x += minor
            guard += 1

        start_y = math.floor(min(y0, y1) / minor) * minor
        end_y = math.ceil(max(y0, y1) / minor) * minor
        y = start_y
        guard = 0
        while y <= end_y + minor * 0.5 and guard < 500:
            _, cy = self._world_to_canvas(0, y)
            major_tick = math.isclose(y / major, round(y / major), abs_tol=1e-6)
            tick = 10 if major_tick else 5
            canvas.create_line(ruler, cy, ruler - tick, cy, fill=fg, tags=("ruler",))
            if major_tick and ruler + 2 <= cy <= h - 2:
                canvas.create_text(
                    2,
                    cy + 2,
                    anchor="nw",
                    text=f"{y:g}",
                    fill=fg,
                    font=("TkDefaultFont", 7),
                    tags=("ruler",),
                )
            y += minor
            guard += 1

        canvas.create_rectangle(0, 0, ruler, ruler, fill="#f8fafc", outline=edge, tags=("ruler",))
        canvas.create_text(
            ruler / 2,
            ruler / 2,
            text="m",
            fill=fg,
            font=("TkDefaultFont", 7, "bold"),
            tags=("ruler",),
        )

    def _draw_cursor_overlay(self, canvas: tk.Canvas, x_m: float, y_m: float) -> None:
        """Draw a CAD crosshair without mutating the spatial model."""
        canvas.delete("cursor")
        x, y = self._world_to_canvas(x_m, y_m)
        w = max(1, canvas.winfo_width())
        h = max(1, canvas.winfo_height())
        if not (0 <= x <= w and 0 <= y <= h):
            return
        fill = "#64748b"
        canvas.create_line(x, 0, x, h, fill=fill, dash=(3, 4), tags=("cursor",))
        canvas.create_line(0, y, w, y, fill=fill, dash=(3, 4), tags=("cursor",))
        label = f"{x_m:.2f}, {y_m:.2f} m"
        tx = min(max(x + 10, 28), max(28, w - 112))
        ty = min(max(y + 10, 28), max(28, h - 26))
        canvas.create_rectangle(
            tx - 4,
            ty - 2,
            tx + 104,
            ty + 16,
            fill="#ffffff",
            outline="#cbd5e1",
            tags=("cursor",),
        )
        canvas.create_text(
            tx,
            ty,
            anchor="nw",
            text=label,
            fill="#334155",
            font=("TkDefaultFont", 7, "bold"),
            tags=("cursor",),
        )

    def _draw_device_legend(self, canvas: tk.Canvas, *, dark: bool) -> None:
        present = [kind for kind in DEVICE_TYPES if any(d["type"] == kind for d in self.layout["devices"])]
        if not present:
            return
        fg = "#dbeafe" if dark else "#334155"
        bg = "#18232f" if dark else "#ffffff"
        outline = "#334b60" if dark else "#cbd5e1"
        x0 = 12
        y0 = 48
        width = 120
        row_h = 18
        height = 10 + row_h * len(present)
        canvas.create_rectangle(x0, y0, x0 + width, y0 + height, fill=bg, outline=outline, tags=("legend",))
        y = y0 + 9
        for kind in present:
            color = DEVICE_COLORS.get(kind, "#cbd5e1")
            canvas.create_oval(x0 + 8, y - 5, x0 + 18, y + 5, fill=color, outline=fg, tags=("legend",))
            canvas.create_text(
                x0 + 25,
                y,
                anchor="w",
                text=kind.upper(),
                fill=fg,
                font=("TkDefaultFont", 7, "bold"),
                tags=("legend",),
            )
            y += row_h

    def _draw_pressure_legend(
        self,
        canvas: tk.Canvas,
        min_pressure: float | None,
        max_pressure: float | None,
        *,
        dark: bool,
    ) -> None:
        if min_pressure is None or max_pressure is None:
            return
        width = 150
        height = 10
        margin = 14
        x1 = max(margin + width, canvas.winfo_width() - margin)
        x0 = x1 - width
        y1 = max(margin + 34, canvas.winfo_height() - margin)
        y0 = y1 - height
        steps = 30
        for index in range(steps):
            ratio = index / max(1, steps - 1)
            pressure = min_pressure + (max_pressure - min_pressure) * ratio
            fill = _pressure_fill(pressure, min_pressure, max_pressure)
            sx0 = x0 + width * index / steps
            sx1 = x0 + width * (index + 1) / steps
            canvas.create_rectangle(sx0, y0, sx1, y1, fill=fill, outline=fill, tags=("legend",))
        text_fill = "#dce8f4" if dark else "#334155"
        canvas.create_text(x0, y0 - 10, text="Pressure", anchor="w", fill=text_fill, font=("TkDefaultFont", 8, "bold"), tags=("legend",))
        canvas.create_text(x0, y1 + 10, text=f"{min_pressure:g} Pa", anchor="w", fill=text_fill, font=("TkDefaultFont", 8), tags=("legend",))
        canvas.create_text(x1, y1 + 10, text=f"{max_pressure:g} Pa", anchor="e", fill=text_fill, font=("TkDefaultFont", 8), tags=("legend",))

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

        margin = 0.75
        floor = [
            self._project_3d(min_x - cx - margin, min_y - cy - margin, 0),
            self._project_3d(max_x - cx + margin, min_y - cy - margin, 0),
            self._project_3d(max_x - cx + margin, max_y - cy + margin, 0),
            self._project_3d(min_x - cx - margin, max_y - cy + margin, 0),
        ]
        canvas.create_polygon(*sum(floor, ()), fill="#17212b", outline="#344b5f", width=1, tags=("floor",))

        origin = self._project_3d(min_x - cx - margin, min_y - cy - margin, 0)
        axis_x = self._project_3d(min_x - cx + 0.8, min_y - cy - margin, 0)
        axis_y = self._project_3d(min_x - cx - margin, min_y - cy + 0.8, 0)
        axis_z = self._project_3d(min_x - cx - margin, min_y - cy - margin, 0.8)
        canvas.create_line(*origin, *axis_x, fill="#fb7185", width=2, arrow="last")
        canvas.create_line(*origin, *axis_y, fill="#4ade80", width=2, arrow="last")
        canvas.create_line(*origin, *axis_z, fill="#60a5fa", width=2, arrow="last")

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
            fill = (
                _pressure_fill(room.get("pressure_pa"), pmin, pmax)
                if self._show_pressure.get()
                else "#8fa3b8"
            )
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
            if self._show_labels.get() or selected:
                canvas.create_text(
                    *self._project_3d((x0 + x1) / 2, (y0 + y1) / 2, z + 0.2),
                    text=room["name"],
                    fill="#f0f6fc",
                    font=("TkDefaultFont", 8, "bold" if selected else "normal"),
                    tags=(tag, "room3d"),
                )

        if self._show_cascade.get():
            self._draw_pressure_cascade_3d(canvas, cx, cy)

        if self._show_devices.get():
            for device in self.layout["devices"]:
                x, y = self._project_3d(
                    device["x_m"] - cx,
                    device["y_m"] - cy,
                    device["z_m"],
                )
                tag = f"device:{device['id']}"
                selected = self.selected == _Hit("device", device["id"])
                radius = 6 if selected else 4
                fill = DEVICE_COLORS.get(device["type"], "#fbbf24")
                canvas.create_oval(
                    x - radius, y - radius, x + radius, y + radius,
                    fill=fill,
                    outline="#ffffff" if selected else "#dbeafe",
                    width=2,
                    tags=(tag, "device3d"),
                )
                if selected or self._show_labels.get():
                    canvas.create_text(
                        x,
                        y - 14,
                        text=device.get("name", device["type"]),
                        fill="#f8fafc",
                        font=("TkDefaultFont", 8, "bold" if selected else "normal"),
                        tags=(tag, "device3d"),
                    )

        canvas.create_text(*axis_x, text="  X", anchor="w", fill="#fb7185", font=("TkDefaultFont", 8, "bold"))
        canvas.create_text(*axis_y, text="  Y", anchor="w", fill="#4ade80", font=("TkDefaultFont", 8, "bold"))
        canvas.create_text(*axis_z, text="  Z", anchor="w", fill="#60a5fa", font=("TkDefaultFont", 8, "bold"))

        if pressures and self._show_pressure.get():
            self._draw_pressure_legend(canvas, pmin, pmax, dark=True)
        if self.layout["devices"] and self._show_devices.get():
            self._draw_device_legend(canvas, dark=True)
        self._draw_3d_hud(canvas)

    def _draw_pressure_cascade_3d(self, canvas: tk.Canvas, cx: float, cy: float) -> None:
        """Project pressure-cascade links into the digital-twin view."""
        rooms_by_id = {room["id"]: room for room in self.layout["rooms"]}
        for link in pressure_cascade_links(self.layout):
            higher = rooms_by_id.get(link["higher_room_id"])
            lower = rooms_by_id.get(link["lower_room_id"])
            if higher is None or lower is None:
                continue
            z = max(0.2, min(higher["height_m"], lower["height_m"]) * 0.55)
            sx, sy = self._project_3d(link["start"][0] - cx, link["start"][1] - cy, z)
            ex, ey = self._project_3d(link["end"][0] - cx, link["end"][1] - cy, z)
            canvas.create_line(
                sx,
                sy,
                ex,
                ey,
                fill="#fb7185",
                width=3,
                arrow="last",
                arrowshape=(10, 12, 5),
                tags=("cascade3d",),
            )
            bx, by = self._project_3d(
                link["boundary"][0] - cx,
                link["boundary"][1] - cy,
                z + 0.12,
            )
            canvas.create_text(
                bx,
                by - 8,
                text=f"ΔP {link['delta_pa']:g} Pa",
                fill="#fecdd3",
                font=("TkDefaultFont", 7, "bold"),
                tags=("cascade3d",),
            )

    def _draw_3d_hud(self, canvas: tk.Canvas) -> None:
        az = self.layout["view"]["azimuth_deg"] % 360
        el = self.layout["view"]["elevation_deg"]
        zoom = self.layout["view"]["zoom_3d"]
        canvas.create_rectangle(10, 10, 220, 36, fill="#18232f", outline="#334b60", tags=("hud",))
        canvas.create_text(
            18,
            23,
            anchor="w",
            text=f"3D  ·  az {az:.0f}°  ·  el {el:.0f}°  ·  {zoom * 100:.0f}%",
            fill="#dbeafe",
            font=("TkDefaultFont", 8, "bold"),
            tags=("hud",),
        )

    def _parse_hit(self, tags: tuple[str, ...]) -> _Hit | None:
        for tag in tags:
            if tag.startswith("room:"):
                return _Hit("room", tag.split(":", 1)[1])
            if tag.startswith("device:"):
                return _Hit("device", tag.split(":", 1)[1])
        return None

    def _parse_resize_handle(self, tags: tuple[str, ...]) -> tuple[str, str] | None:
        for tag in tags:
            if tag.startswith("resize:"):
                _, room_id, handle = tag.split(":", 2)
                return room_id, handle
        return None

    def _on_left_down(self, event: tk.Event) -> None:
        self.canvas_2d.focus_set()
        current = self.canvas_2d.find_withtag("current")
        hit = None
        resize = None
        if current:
            tags = self.canvas_2d.gettags(current[0])
            resize = self._parse_resize_handle(tags)
            hit = self._parse_hit(tags)
        if resize is not None:
            room_id, handle = resize
            self.selected = _Hit("room", room_id)
            room = self._selected_object()
            self._resize_handle = handle
            self._resize_start = copy.deepcopy(room) if room is not None else None
            self._drag_anchor = None
        else:
            self.selected = hit
            self._resize_handle = None
            self._resize_start = None
            self._drag_anchor = self._canvas_to_world(event.x, event.y) if hit else None
        self._load_property_panel()
        self.redraw()

    def _on_left_drag(self, event: tk.Event) -> None:
        item = self._selected_object()
        if item is None:
            return
        world = self._canvas_to_world(event.x, event.y)
        grid = max(0.05, self.layout["grid_m"])

        if self._resize_handle and self._resize_start and self.selected and self.selected.kind == "room":
            start = self._resize_start
            x0 = start["x_m"]
            y0 = start["y_m"]
            x1 = x0 + start["length_m"]
            y1 = y0 + start["width_m"]
            if self._snap_to_grid.get():
                px = round(world[0] / grid) * grid
                py = round(world[1] / grid) * grid
                min_size = grid
            else:
                px, py = world
                min_size = 0.05
            if "w" in self._resize_handle:
                nx0 = min(px, x1 - min_size)
                item["x_m"] = nx0
                item["length_m"] = x1 - nx0
            if "e" in self._resize_handle:
                nx1 = max(px, x0 + min_size)
                item["x_m"] = x0
                item["length_m"] = nx1 - x0
            if "n" in self._resize_handle:
                ny0 = min(py, y1 - min_size)
                item["y_m"] = ny0
                item["width_m"] = y1 - ny0
            if "s" in self._resize_handle:
                ny1 = max(py, y0 + min_size)
                item["y_m"] = y0
                item["width_m"] = ny1 - y0
            self._load_property_panel()
            self.redraw()
            return

        if self._drag_anchor is None:
            return
        dx = world[0] - self._drag_anchor[0]
        dy = world[1] - self._drag_anchor[1]
        old_x = item["x_m"]
        old_y = item["y_m"]
        next_x = old_x + dx
        next_y = old_y + dy
        if self._snap_to_grid.get():
            next_x = round(next_x / grid) * grid
            next_y = round(next_y / grid) * grid
        item["x_m"] = next_x
        item["y_m"] = next_y
        if self.selected and self.selected.kind == "room":
            self._translate_room_devices(
                self.selected.item_id,
                item["x_m"] - old_x,
                item["y_m"] - old_y,
            )
        self._drag_anchor = world
        self._load_property_panel()
        self.redraw()

    def _on_left_up(self, event: tk.Event) -> None:
        if self._resize_handle is not None and self.selected is not None:
            self._persist("Room resized")
        elif self._drag_anchor is not None and self.selected is not None:
            self._persist("Spatial item moved")
        self._drag_anchor = None
        self._resize_handle = None
        self._resize_start = None

    def _on_motion(self, event: tk.Event) -> None:
        x, y = self._canvas_to_world(event.x, event.y)
        self._cursor_world = (x, y)
        self._coord_var.set(f"x {x:.2f} m   y {y:.2f} m")
        if self._show_crosshair.get():
            self._draw_cursor_overlay(self.canvas_2d, x, y)
        else:
            self.canvas_2d.delete("cursor")

    def _on_leave_2d(self, event: tk.Event) -> None:
        self._cursor_world = None
        self.canvas_2d.delete("cursor")

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

    def zoom_2d(self, factor: float) -> None:
        self._zoom_at(
            factor,
            max(1, self.canvas_2d.winfo_width()) / 2,
            max(1, self.canvas_2d.winfo_height()) / 2,
        )

    def _on_wheel_3d(self, event: tk.Event) -> None:
        self._zoom_3d(1.1 if event.delta > 0 else 1 / 1.1)

    def _zoom_3d(self, factor: float) -> None:
        self.layout["view"]["zoom_3d"] = max(0.2, min(8.0, self.layout["view"]["zoom_3d"] * factor))
        self._draw_3d()

    def rotate_3d(self, delta: float) -> None:
        self.layout["view"]["azimuth_deg"] = (self.layout["view"]["azimuth_deg"] + delta) % 360
        self._draw_3d()

    def tilt_3d(self, delta: float) -> None:
        self.layout["view"]["elevation_deg"] = max(
            5.0, min(75.0, self.layout["view"]["elevation_deg"] + delta)
        )
        self._draw_3d()

    def set_3d_preset(self, preset: str) -> None:
        presets = {
            "iso": (35.0, 28.0),
            "top": (0.0, 75.0),
            "front": (0.0, 5.0),
        }
        if preset not in presets:
            return
        azimuth, elevation = presets[preset]
        self.layout["view"]["azimuth_deg"] = azimuth
        self.layout["view"]["elevation_deg"] = elevation
        self.layout["view"]["pan_3d_x"] = 0.0
        self.layout["view"]["pan_3d_y"] = 0.0
        self._status_setter(f"3D view preset: {preset.upper()}")
        self._draw_3d()

    def reset_3d(self) -> None:
        self.layout["view"]["azimuth_deg"] = 35.0
        self.layout["view"]["elevation_deg"] = 28.0
        self.layout["view"]["zoom_3d"] = 1.0
        self.layout["view"]["pan_3d_x"] = 0.0
        self.layout["view"]["pan_3d_y"] = 0.0
        self._draw_3d()

    def _on_orbit_down(self, event: tk.Event) -> None:
        self.canvas_3d.focus_set()
        self._orbit_anchor = (event.x, event.y)
        self._orbit_origin = (
            self.layout["view"]["azimuth_deg"],
            self.layout["view"]["elevation_deg"],
        )

    def _on_orbit_drag(self, event: tk.Event) -> None:
        if self._orbit_anchor is None or self._orbit_origin is None:
            return
        dx = event.x - self._orbit_anchor[0]
        dy = event.y - self._orbit_anchor[1]
        self.layout["view"]["azimuth_deg"] = (self._orbit_origin[0] + dx * 0.45) % 360.0
        self.layout["view"]["elevation_deg"] = max(
            5.0, min(75.0, self._orbit_origin[1] - dy * 0.30)
        )
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
