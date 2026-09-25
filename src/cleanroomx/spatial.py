from __future__ import annotations

from dataclasses import dataclass
import copy
import math
import uuid
from typing import Any, Callable

import tkinter as tk
from tkinter import messagebox, ttk


SPATIAL_METADATA_KEY = "spatial_layout"
SPATIAL_LAYOUT_VERSION = 1
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
    used_device_ids: set[str] = set()
    raw_devices = source.get("devices", [])
    if isinstance(raw_devices, list):
        for raw in raw_devices:
            if not isinstance(raw, dict):
                continue
            device_type = str(raw.get("type") or "equipment").lower()
            if device_type not in DEVICE_TYPES:
                device_type = "equipment"
            device_id = str(raw.get("id") or f"device-{uuid.uuid4().hex[:8]}").strip()
            if not device_id:
                device_id = f"device-{uuid.uuid4().hex[:8]}"
            if device_id in used_device_ids:
                base_id = device_id
                suffix = 2
                while f"{base_id}-{suffix}" in used_device_ids:
                    suffix += 1
                device_id = f"{base_id}-{suffix}"
            used_device_ids.add(device_id)
            raw_room_id = raw.get("room_id")
            room_id = None if raw_room_id is None else str(raw_room_id).strip() or None
            devices.append(
                {
                    "id": device_id,
                    "type": device_type,
                    "name": str(raw.get("name") or device_type.upper()),
                    "room_id": room_id,
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
        target_name = str(analysis.input.get("name") or "").strip()
        matching_rooms = [room for room in rooms if room["name"] == target_name]
        if len(matching_rooms) == 1:
            source = matching_rooms[0]
        elif len(rooms) == 1:
            source = rooms[0]
        else:
            return False
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


def room_contains_point(
    room: dict,
    x_m: float,
    y_m: float,
    *,
    tolerance: float = 1e-9,
) -> bool:
    """Return whether a plan point lies inside a room footprint, including its boundary."""

    x0 = _finite_number(room.get("x_m"), 0.0)
    y0 = _finite_number(room.get("y_m"), 0.0)
    x1 = x0 + _positive(room.get("length_m"), 4.0)
    y1 = y0 + _positive(room.get("width_m"), 4.0)
    x = _finite_number(x_m, 0.0)
    y = _finite_number(y_m, 0.0)
    return (
        x0 - tolerance <= x <= x1 + tolerance
        and y0 - tolerance <= y <= y1 + tolerance
    )


def find_room_for_point(
    layout: dict,
    x_m: float,
    y_m: float,
    *,
    preferred_room_id: str | None = None,
) -> str | None:
    """Resolve a point to a deterministic containing room.

    If overlapping rooms exist, keep the preferred current room when it still
    contains the point. Otherwise choose the smallest containing room, then ID.
    """

    rooms = layout.get("rooms", []) if isinstance(layout, dict) else []
    candidates = [
        room
        for room in rooms
        if isinstance(room, dict) and room_contains_point(room, x_m, y_m)
    ]
    if not candidates:
        return None
    if preferred_room_id is not None:
        for room in candidates:
            if room.get("id") == preferred_room_id:
                return str(preferred_room_id)
    chosen = min(
        candidates,
        key=lambda room: (
            _positive(room.get("length_m"), 4.0)
            * _positive(room.get("width_m"), 4.0),
            str(room.get("id") or ""),
        ),
    )
    room_id = chosen.get("id")
    return str(room_id) if room_id is not None else None


def reassociate_device(layout: dict, device: dict) -> str | None:
    """Update a device's room association from its current plan position."""

    room_id = find_room_for_point(
        layout,
        _finite_number(device.get("x_m"), 0.0),
        _finite_number(device.get("y_m"), 0.0),
        preferred_room_id=device.get("room_id"),
    )
    device["room_id"] = room_id
    return room_id


def repair_device_assignments(layout: dict) -> int:
    """Repair device-to-room associations from current plan positions.

    This changes only device room_id metadata. Room geometry, device
    coordinates, solver inputs, and engineering acceptance logic are untouched.
    """

    if not isinstance(layout, dict):
        return 0
    changed = 0
    for device in layout.get("devices", []):
        if not isinstance(device, dict):
            continue
        previous = device.get("room_id")
        resolved = find_room_for_point(
            layout,
            _finite_number(device.get("x_m"), 0.0),
            _finite_number(device.get("y_m"), 0.0),
            preferred_room_id=previous,
        )
        if resolved != previous:
            device["room_id"] = resolved
            changed += 1
    return changed


def spatial_issues(layout: dict) -> list[dict[str, Any]]:
    """Return deterministic, non-blocking spatial design warnings."""

    normalized = normalize_layout(layout)
    rooms = normalized["rooms"]
    devices = normalized["devices"]
    issues: list[dict[str, Any]] = []

    for index, left in enumerate(rooms):
        lx0 = left["x_m"]
        ly0 = left["y_m"]
        lx1 = lx0 + left["length_m"]
        ly1 = ly0 + left["width_m"]
        for right in rooms[index + 1 :]:
            rx0 = right["x_m"]
            ry0 = right["y_m"]
            rx1 = rx0 + right["length_m"]
            ry1 = ry0 + right["width_m"]
            overlap_x = min(lx1, rx1) - max(lx0, rx0)
            overlap_y = min(ly1, ry1) - max(ly0, ry0)
            if overlap_x > 1e-9 and overlap_y > 1e-9:
                issues.append(
                    {
                        "code": "ROOM_OVERLAP",
                        "room_ids": [left["id"], right["id"]],
                        "message": (
                            f"Rooms {left['name']!r} and {right['name']!r} overlap "
                            f"by {overlap_x:.2f} × {overlap_y:.2f} m."
                        ),
                    }
                )

    by_id = {room["id"]: room for room in rooms}
    for device in devices:
        assigned_id = device.get("room_id")
        containing_id = find_room_for_point(
            normalized,
            device["x_m"],
            device["y_m"],
            preferred_room_id=assigned_id,
        )
        if assigned_id is None:
            issues.append(
                {
                    "code": "DEVICE_UNASSIGNED",
                    "device_id": device["id"],
                    "message": (
                        f"Device {device['name']!r} is not assigned to a room."
                        if containing_id is None
                        else (
                            f"Device {device['name']!r} lies inside room "
                            f"{by_id[containing_id]['name']!r} but is not assigned to it."
                        )
                    ),
                }
            )
            continue
        assigned_room = by_id.get(str(assigned_id))
        if assigned_room is None:
            issues.append(
                {
                    "code": "DEVICE_UNKNOWN_ROOM",
                    "device_id": device["id"],
                    "message": (
                        f"Device {device['name']!r} references missing room "
                        f"{assigned_id!r}."
                    ),
                }
            )
            continue
        if not room_contains_point(
            assigned_room,
            device["x_m"],
            device["y_m"],
        ):
            destination = by_id.get(containing_id) if containing_id else None
            issues.append(
                {
                    "code": "DEVICE_ROOM_MISMATCH" if destination else "DEVICE_OUTSIDE_ROOM",
                    "device_id": device["id"],
                    "room_ids": [assigned_room["id"]],
                    "message": (
                        f"Device {device['name']!r} is assigned to "
                        f"{assigned_room['name']!r} but lies inside "
                        f"{destination['name']!r}."
                        if destination
                        else (
                            f"Device {device['name']!r} lies outside its assigned room "
                            f"{assigned_room['name']!r}."
                        )
                    ),
                }
            )
            continue

        z_m = _finite_number(device.get("z_m"), 0.0)
        if z_m < -1e-9:
            issues.append(
                {
                    "code": "DEVICE_BELOW_FLOOR",
                    "device_id": device["id"],
                    "room_ids": [assigned_room["id"]],
                    "message": (
                        f"Device {device['name']!r} is at z={z_m:g} m, below the floor "
                        f"of room {assigned_room['name']!r}."
                    ),
                }
            )
        elif z_m > assigned_room["height_m"] + 1e-9:
            issues.append(
                {
                    "code": "DEVICE_ABOVE_CEILING",
                    "device_id": device["id"],
                    "room_ids": [assigned_room["id"]],
                    "message": (
                        f"Device {device['name']!r} is at z={z_m:g} m, above the "
                        f"{assigned_room['height_m']:g} m ceiling of room "
                        f"{assigned_room['name']!r}."
                    ),
                }
            )
    return issues


def spatial_sync_blockers(layout: dict, analysis: Any) -> list[str]:
    """Return geometry-sync conditions that require explicit operator correction."""

    if analysis is None or not isinstance(getattr(analysis, "input", None), dict):
        return ["No compatible active analysis is available for spatial synchronization."]

    kind = getattr(analysis, "kind", "")
    if kind not in {"room_verification", "project_verification"}:
        return []

    rooms = normalize_layout(layout)["rooms"]
    if not rooms:
        return ["The spatial layout has no rooms to synchronize."]

    names: dict[str, int] = {}
    for room in rooms:
        names[room["name"]] = names.get(room["name"], 0) + 1
    duplicate_layout_names = sorted(name for name, count in names.items() if count > 1)
    blockers: list[str] = []
    if duplicate_layout_names:
        blockers.append(
            "Spatial room names must be unique before synchronization: "
            + ", ".join(repr(name) for name in duplicate_layout_names)
            + "."
        )

    if kind == "room_verification":
        target_name = str(analysis.input.get("name") or "").strip()
        matches = [room for room in rooms if room["name"] == target_name]
        if len(rooms) > 1 and len(matches) != 1:
            blockers.append(
                "The active single-room analysis cannot be mapped unambiguously. "
                f"Rename exactly one spatial room to {target_name!r}, or reduce the layout "
                "to a single room before synchronizing."
            )
        return blockers

    raw_rooms = analysis.input.get("rooms")
    if not isinstance(raw_rooms, list):
        return blockers
    analysis_names = [
        str(room.get("name") or "").strip()
        for room in raw_rooms
        if isinstance(room, dict)
    ]
    duplicate_analysis_names = sorted(
        name for name in set(analysis_names) if name and analysis_names.count(name) > 1
    )
    if duplicate_analysis_names:
        blockers.append(
            "Analysis room names must be unique before spatial synchronization: "
            + ", ".join(repr(name) for name in duplicate_analysis_names)
            + "."
        )
    return blockers


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
        self._pan_anchor: tuple[int, int] | None = None
        self._pan_origin: tuple[float, float] | None = None
        self._show_grid = tk.BooleanVar(value=True)
        self._coord_var = tk.StringVar(value="x 0.00 m   y 0.00 m")
        self._selection_var = tk.StringVar(value="No selection")
        self._issues_var = tk.StringVar(value="Spatial checks: OK")
        self._issue_cursor = -1
        self._property_vars: dict[str, tk.StringVar] = {}

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
        ttk.Button(toolbar, text="Delete", command=self.delete_selected).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Fit", command=self.fit_views).pack(side="left", padx=2)
        ttk.Checkbutton(toolbar, text="Grid", variable=self._show_grid, command=self.redraw).pack(
            side="left", padx=6
        )
        ttk.Button(
            toolbar,
            text="Sync dimensions to active analysis",
            command=self._on_sync_requested,
        ).pack(side="right", padx=2)
        ttk.Button(toolbar, text="Issues", command=self.show_issues).pack(side="right", padx=2)
        ttk.Button(toolbar, text="Next Issue", command=self.show_next_issue).pack(side="right", padx=2)
        ttk.Button(toolbar, text="Fix Devices", command=self.fix_device_assignments).pack(side="right", padx=2)
        ttk.Label(toolbar, textvariable=self._issues_var).pack(side="right", padx=(8, 2))

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=6, pady=(3, 6))

        two_d = ttk.Frame(body)
        body.add(two_d, weight=4)
        ttk.Label(two_d, text="2D Layout", font=("TkDefaultFont", 10, "bold")).pack(
            anchor="w", padx=4, pady=(2, 4)
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
        ttk.Label(header3, text="3D View", font=("TkDefaultFont", 10, "bold")).pack(
            side="left", padx=4, pady=(2, 4)
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
        self.canvas_3d.bind("<MouseWheel>", self._on_wheel_3d)
        self.canvas_3d.bind("<Button-4>", lambda event: self._zoom_3d(1.1))
        self.canvas_3d.bind("<Button-5>", lambda event: self._zoom_3d(1 / 1.1))
        self.canvas_3d.bind("<Button-1>", self._on_3d_click)
        self.canvas_3d.bind("<Button-2>", self._on_pan_3d_down)
        self.canvas_3d.bind("<B2-Motion>", self._on_pan_3d_drag)
        self.canvas_3d.bind("<Button-3>", self._on_pan_3d_down)
        self.canvas_3d.bind("<B3-Motion>", self._on_pan_3d_drag)

    def refresh(self) -> None:
        project = self._project_getter()
        analysis = self._analysis_getter()
        self.layout = ensure_project_layout(project, analysis)
        if self.selected and not self._selected_object():
            self.selected = None
        self._load_property_panel()
        self.redraw()

    def _persist(self, message: str) -> None:
        project = self._project_getter()
        project.metadata[SPATIAL_METADATA_KEY] = normalize_layout(self.layout)
        self.layout = project.metadata[SPATIAL_METADATA_KEY]
        self._on_change()
        self._status_setter(message)
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
            for var in self._property_vars.values():
                var.set("")
            return
        prefix = "Room" if self.selected and self.selected.kind == "room" else item.get("type", "Device").title()
        self._selection_var.set(f"{prefix}: {item.get('name', '')}")
        for key, var in self._property_vars.items():
            value = item.get(key, "")
            var.set("" if value is None else str(value))

    def _current_issues(self) -> list[dict[str, Any]]:
        return spatial_issues(self.layout)

    def _update_issues_summary(self) -> None:
        issues = self._current_issues()
        if issues:
            self._issues_var.set(
                f"Spatial checks: {len(issues)} issue{'s' if len(issues) != 1 else ''}"
            )
        else:
            self._issues_var.set("Spatial checks: OK")

    def show_issues(self) -> None:
        issues = self._current_issues()
        if not issues:
            messagebox.showinfo(
                "Spatial checks",
                "No room-overlap or device-placement issues were detected.",
                parent=self,
            )
            return
        lines = [f"{index}. {issue['message']}" for index, issue in enumerate(issues, start=1)]
        messagebox.showwarning(
            "Spatial checks",
            "\n".join(lines),
            parent=self,
        )

    def _select_issue_target(self, issue: dict[str, Any]) -> bool:
        device_id = issue.get("device_id")
        if device_id is not None:
            self.selected = _Hit("device", str(device_id))
        else:
            room_ids = issue.get("room_ids", [])
            if not room_ids:
                return False
            self.selected = _Hit("room", str(room_ids[0]))
        if self._selected_object() is None:
            self.selected = None
            return False
        item = self._selected_object()
        assert item is not None
        if self.selected.kind == "room":
            target_x = item["x_m"] + item["length_m"] / 2.0
            target_y = item["y_m"] + item["width_m"] / 2.0
        else:
            target_x = item["x_m"]
            target_y = item["y_m"]
        scale = self._scale_2d()
        self.layout["view"]["pan_x"] = -target_x * scale
        self.layout["view"]["pan_y"] = -target_y * scale
        self._load_property_panel()
        self.redraw()
        return True

    def show_next_issue(self) -> None:
        issues = self._current_issues()
        if not issues:
            self._issue_cursor = -1
            self._status_setter("Spatial checks: no issues")
            return
        self._issue_cursor = (self._issue_cursor + 1) % len(issues)
        issue = issues[self._issue_cursor]
        selected = self._select_issue_target(issue)
        prefix = f"Issue {self._issue_cursor + 1}/{len(issues)}"
        self._status_setter(
            f"{prefix}: {issue['message']}"
            if selected
            else f"{prefix}: {issue['message']} (target unavailable)"
        )

    def fix_device_assignments(self) -> None:
        changed = repair_device_assignments(self.layout)
        self._issue_cursor = -1
        if changed:
            self._load_property_panel()
            self._persist(
                f"Repaired {changed} device room association"
                f"{'s' if changed != 1 else ''}"
            )
        else:
            self.redraw()
            self._status_setter("Device room associations already consistent")

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
            reassociate_device(self.layout, item)
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

    def redraw(self) -> None:
        self._update_issues_summary()
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
        issues = self._current_issues()
        problem_rooms = {
            room_id
            for issue in issues
            for room_id in issue.get("room_ids", [])
        }
        problem_devices = {
            issue["device_id"]
            for issue in issues
            if issue.get("device_id") is not None
        }

        for room in self.layout["rooms"]:
            x0, y0 = self._world_to_canvas(room["x_m"], room["y_m"])
            x1, y1 = self._world_to_canvas(room["x_m"] + room["length_m"], room["y_m"] + room["width_m"])
            selected = self.selected == _Hit("room", room["id"])
            has_issue = room["id"] in problem_rooms
            outline = "#dc2626" if has_issue else ("#1d4ed8" if selected else "#34495e")
            fill = _pressure_fill(room.get("pressure_pa"), pmin, pmax)
            canvas.create_rectangle(
                x0, y0, x1, y1,
                fill=fill, outline=outline, width=4 if has_issue else (3 if selected else 2),
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
            has_issue = device["id"] in problem_devices
            radius = 9 if selected else 7
            canvas.create_oval(
                x - radius, y - radius, x + radius, y + radius,
                fill="#fee2e2" if has_issue else "#ffffff",
                outline="#dc2626" if has_issue else ("#c0392b" if selected else "#2c3e50"),
                width=3 if selected or has_issue else 2,
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
        issues = self._current_issues()
        problem_rooms = {
            room_id
            for issue in issues
            for room_id in issue.get("room_ids", [])
        }
        problem_devices = {
            issue["device_id"]
            for issue in issues
            if issue.get("device_id") is not None
        }

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
            has_issue = room["id"] in problem_rooms
            outline = "#ef4444" if has_issue else ("#7dd3fc" if selected else "#c8d5e3")
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
            has_issue = device["id"] in problem_devices
            radius = 5 if selected else 4
            canvas.create_oval(
                x - radius, y - radius, x + radius, y + radius,
                fill="#fecaca" if has_issue else "#fbbf24",
                outline="#ef4444" if has_issue else ("#ffffff" if selected else "#d6a20f"),
                width=3 if has_issue else 2, tags=(tag, "device3d"),
            )

    def _parse_hit(self, tags: tuple[str, ...]) -> _Hit | None:
        for tag in tags:
            if tag.startswith("room:"):
                return _Hit("room", tag.split(":", 1)[1])
            if tag.startswith("device:"):
                return _Hit("device", tag.split(":", 1)[1])
        return None

    def _on_left_down(self, event: tk.Event) -> None:
        current = self.canvas_2d.find_withtag("current")
        hit = None
        if current:
            hit = self._parse_hit(self.canvas_2d.gettags(current[0]))
        self.selected = hit
        self._drag_anchor = self._canvas_to_world(event.x, event.y) if hit else None
        self._load_property_panel()
        self.redraw()

    def _on_left_drag(self, event: tk.Event) -> None:
        item = self._selected_object()
        if item is None or self._drag_anchor is None:
            return
        world = self._canvas_to_world(event.x, event.y)
        dx = world[0] - self._drag_anchor[0]
        dy = world[1] - self._drag_anchor[1]
        grid = self.layout["grid_m"]
        old_x = item["x_m"]
        old_y = item["y_m"]
        item["x_m"] = round((item["x_m"] + dx) / grid) * grid
        item["y_m"] = round((item["y_m"] + dy) / grid) * grid
        if self.selected and self.selected.kind == "room":
            moved_x = item["x_m"] - old_x
            moved_y = item["y_m"] - old_y
            if moved_x or moved_y:
                for device in self.layout["devices"]:
                    if device.get("room_id") == item["id"]:
                        device["x_m"] += moved_x
                        device["y_m"] += moved_y
        self._drag_anchor = world
        self._load_property_panel()
        self.redraw()

    def _on_left_up(self, event: tk.Event) -> None:
        if self._drag_anchor is not None and self.selected is not None:
            item = self._selected_object()
            if item is not None and self.selected.kind == "device":
                reassociate_device(self.layout, item)
                self._load_property_panel()
            self._persist("Spatial item moved")
        self._drag_anchor = None

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
        self._draw_3d()

    def tilt_3d(self, delta: float) -> None:
        self.layout["view"]["elevation_deg"] = max(
            5.0, min(75.0, self.layout["view"]["elevation_deg"] + delta)
        )
        self._draw_3d()

    def reset_3d(self) -> None:
        self.layout["view"]["azimuth_deg"] = 35.0
        self.layout["view"]["elevation_deg"] = 28.0
        self.layout["view"]["zoom_3d"] = 1.0
        self.layout["view"]["pan_3d_x"] = 0.0
        self.layout["view"]["pan_3d_y"] = 0.0
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
        current = self.canvas_3d.find_withtag("current")
        if not current:
            return
        hit = self._parse_hit(self.canvas_3d.gettags(current[0]))
        if hit is None:
            return
        self.selected = hit
        self._load_property_panel()
        self.redraw()
