"""Model-backed Design Studio overview widgets.

These widgets present layout measurements only. They do not infer CFD results or
modify engineering inputs. Selection callbacks are delegated to SpatialDesignWorkspace.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable


class StudioSummaryCards(ttk.Frame):
    """Four live geometry/device indicators with no demo-specific constants."""

    def __init__(self, master: tk.Misc):
        super().__init__(master, padding=(4, 3))
        self.values: dict[str, tk.StringVar] = {}
        for column, (key, label) in enumerate((
            ("rooms", "ROOMS"),
            ("area", "FLOOR AREA"),
            ("volume", "GEOMETRIC VOLUME"),
            ("devices", "PLACED DEVICES / OPENINGS"),
        )):
            card = ttk.LabelFrame(self, text=label, padding=(8, 4))
            card.grid(row=0, column=column, sticky="nsew", padx=3)
            self.columnconfigure(column, weight=1, uniform="studio-kpi")
            var = tk.StringVar(value="—")
            self.values[key] = var
            ttk.Label(
                card, textvariable=var, font=("TkDefaultFont", 12, "bold")
            ).pack(anchor="w", pady=2)

    def update_metrics(self, metrics: dict) -> None:
        self.values["rooms"].set(str(metrics["room_count"]))
        self.values["area"].set(f"{metrics['total_floor_area_m2']:.1f} m²")
        self.values["volume"].set(f"{metrics['total_volume_m3']:.1f} m³")
        # All placed spatial devices, including doors, windows and openings.
        self.values["devices"].set(str(sum(metrics["device_counts"].values())))


class RoomNavigator(ttk.LabelFrame):
    """Miniature floor plan and room list; selection is shared with 2D/3D."""

    def __init__(self, master: tk.Misc, *, on_select: Callable[[str], None]):
        super().__init__(master, text="ROOM NAVIGATOR", padding=(5, 4))
        self._on_select = on_select
        self._rooms: list[dict] = []
        self._selected_id: str | None = None
        self._snapshot: tuple = ()
        self._syncing = False
        self._palette: dict[str, str] = {
            "canvas_2d": "#1b222a",
            "surface_alt": "#293847",
            "accent": "#26c6da",
            "text": "#e6edf3",
            "accent_text": "#101923",
            "border": "#394451",
        }
        self.map_canvas = tk.Canvas(
            self, width=230, height=124, background=self._palette["canvas_2d"],
            highlightthickness=1, highlightbackground=self._palette["border"],
        )
        self.map_canvas.pack(side="left", fill="both", expand=True, padx=(0, 6))
        self.map_canvas.bind("<Configure>", lambda _event: self._draw_map())
        self.map_canvas.bind("<Button-1>", self._on_map_click)
        self.tree = ttk.Treeview(
            self, columns=("area",), show="tree headings", selectmode="browse",
            height=4,
        )
        self.tree.heading("#0", text="Room")
        self.tree.heading("area", text="m²")
        self.tree.column("#0", minwidth=90, width=132, stretch=True)
        self.tree.column("area", minwidth=40, width=52, stretch=False, anchor="e")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

    def apply_palette(self, palette: dict[str, str]) -> None:
        self._palette = dict(palette)
        self.map_canvas.configure(
            background=palette["canvas_2d"],
            highlightbackground=palette["border"],
        )
        self._draw_map()

    def refresh(self, rooms: list[dict], selected_id: str | None) -> None:
        snapshot = tuple(
            (room["id"], room["name"], room["x_m"], room["y_m"],
             room["length_m"], room["width_m"]) for room in rooms
        )
        self._rooms = rooms
        self._selected_id = selected_id
        self._syncing = True
        try:
            if snapshot != self._snapshot:
                self.tree.delete(*self.tree.get_children())
                for room in rooms:
                    self.tree.insert(
                        "", "end", iid=room["id"], text=room["name"],
                        values=(f"{room['length_m'] * room['width_m']:.1f}",),
                    )
                self._snapshot = snapshot
            current = tuple(self.tree.selection())
            desired = (selected_id,) if selected_id and self.tree.exists(selected_id) else ()
            if current != desired:
                self.tree.selection_set(desired)
        finally:
            self._syncing = False
        self._draw_map()

    def _on_tree_select(self, _event: tk.Event) -> None:
        if self._syncing:
            return
        selection = self.tree.selection()
        if selection:
            self._on_select(selection[0])

    def _on_map_click(self, _event: tk.Event) -> None:
        current = self.map_canvas.find_withtag("current")
        if not current:
            return
        for tag in self.map_canvas.gettags(current[0]):
            if tag.startswith("room:"):
                self._on_select(tag[5:])
                return

    def _draw_map(self) -> None:
        canvas = self.map_canvas
        canvas.delete("all")
        if not self._rooms:
            canvas.create_text(
                max(canvas.winfo_width(), 180) / 2,
                max(canvas.winfo_height(), 100) / 2,
                text="No rooms", fill=self._palette["text"],
            )
            return
        left = min(room["x_m"] for room in self._rooms)
        top = min(room["y_m"] for room in self._rooms)
        right = max(room["x_m"] + room["length_m"] for room in self._rooms)
        bottom = max(room["y_m"] + room["width_m"] for room in self._rooms)
        width = max(180, canvas.winfo_width())
        height = max(100, canvas.winfo_height())
        scale = min(
            (width - 24) / max(right - left, 1e-6),
            (height - 24) / max(bottom - top, 1e-6),
        )
        offset_x = (width - (right - left) * scale) / 2
        offset_y = (height - (bottom - top) * scale) / 2
        for room in self._rooms:
            x0 = offset_x + (room["x_m"] - left) * scale
            y0 = offset_y + (room["y_m"] - top) * scale
            x1 = x0 + room["length_m"] * scale
            y1 = y0 + room["width_m"] * scale
            active = room["id"] == self._selected_id
            tag = f"room:{room['id']}"
            canvas.create_rectangle(
                x0, y0, x1, y1, width=2 if active else 1,
                outline=self._palette["accent"] if active else self._palette["border"],
                fill=self._palette["accent"] if active else self._palette["surface_alt"],
                tags=(tag,),
            )
            if x1 - x0 >= 40 and y1 - y0 >= 18:
                canvas.create_text(
                    (x0 + x1) / 2, (y0 + y1) / 2,
                    text=room["name"],
                    fill=self._palette["accent_text"] if active else self._palette["text"],
                    width=max(20, x1 - x0 - 6), tags=(tag,),
                )


class SelectedRoomPanel(ttk.LabelFrame):
    """Geometry and configured pressure only; never labels a setpoint as CFD."""

    def __init__(self, master: tk.Misc):
        super().__init__(master, text="SELECTED ROOM", padding=(8, 5))
        self.name = tk.StringVar(value="No room selected")
        self.geometry = tk.StringVar(value="")
        self.details = tk.StringVar(value="")
        self.pressure = tk.StringVar(value="")
        for var in (self.name, self.geometry, self.details, self.pressure):
            ttk.Label(self, textvariable=var, wraplength=280).pack(anchor="w")

    def update_room(self, room: dict | None, device_count: int = 0) -> None:
        if room is None:
            self.name.set("No room selected")
            self.geometry.set("")
            self.details.set("")
            self.pressure.set("")
            return
        self.name.set(str(room["name"]))
        length, width, height = (
            room["length_m"], room["width_m"], room["height_m"]
        )
        self.geometry.set(
            f"{length:g} × {width:g} × {height:g} m · "
            f"{length * width:g} m² · {length * width * height:g} m³"
        )
        classification = room.get("classification") or "Not classified"
        self.details.set(f"{classification} · {device_count} devices / openings")
        pressure = room.get("pressure_pa")
        self.pressure.set(
            "Configured pressure: not set" if pressure is None
            else f"Configured pressure setpoint: {pressure:g} Pa (not CFD)"
        )


class PlacedDevicesPanel(ttk.LabelFrame):
    """Counts all model device types, with explicit opening inclusion."""

    def __init__(self, master: tk.Misc):
        super().__init__(master, text="PLACED DEVICES", padding=(8, 5))
        self.scope = tk.StringVar(value="All rooms")
        self.counts = tk.StringVar(value="FFU 0 · Supply 0 · Return/Exhaust 0 · Other 0")
        ttk.Label(self, textvariable=self.scope).pack(anchor="w")
        ttk.Label(self, textvariable=self.counts, wraplength=280).pack(anchor="w")

    def update_devices(self, devices: list[dict], room: dict | None) -> None:
        self.scope.set(f"In {room['name']}" if room else "All rooms")
        subset = (
            [device for device in devices if device.get("room_id") == room["id"]]
            if room else devices
        )
        counts = {key: 0 for key in ("ffu", "supply", "return", "exhaust")}
        for device in subset:
            if device["type"] in counts:
                counts[device["type"]] += 1
        other = len(subset) - sum(counts.values())
        self.counts.set(
            f"FFU {counts['ffu']} · Supply {counts['supply']} · "
            f"Return/Exhaust {counts['return'] + counts['exhaust']} · Other {other}"
        )
