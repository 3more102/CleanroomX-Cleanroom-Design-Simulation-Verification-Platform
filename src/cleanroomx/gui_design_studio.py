"""Live Design Studio chrome around the canonical SpatialDesignWorkspace.

No independent spatial model or engineering calculations live in this module.
All values are derived from the active normalized project layout.
"""
from __future__ import annotations

import math
import tkinter as tk
from tkinter import simpledialog
from typing import Any

STUDIO_ROOM_COLORS = ("#ef8191", "#659cf5", "#31c5b4", "#b995ef", "#e9b66b")
_BG = "#0c1521"
_PANEL = "#12263b"
_BORDER = "#31506a"
_TEXT = "#e7f1fb"
_CYAN = "#39c4df"
_MUTED = "#a4b8ca"


def studio_shade(color: str, factor: float) -> str:
    """Deterministic opaque wall shading; Tk Canvas has no polygon alpha."""
    return "#" + "".join(
        f"{min(255, max(0, round(int(color[i:i+2], 16) * factor))):02x}"
        for i in (1, 3, 5)
    )


def studio_blend(color: str, background: str, opacity: float) -> str:
    """Approximate translucency without Tk's visibly stippled polygons.

    Each channel is composited in sRGB for a static, smooth view color.
    The underlying room model remains unchanged.
    """
    if not 0.0 <= opacity <= 1.0:
        raise ValueError("opacity must be between zero and one")
    if any(len(value) != 7 or not value.startswith("#") for value in (color, background)):
        raise ValueError("expected #RRGGBB colors")
    return "#" + "".join(
        f"{round(opacity * int(color[i:i+2], 16) + (1.0 - opacity) * int(background[i:i+2], 16)):02x}"
        for i in (1, 3, 5)
    )


def studio_snapshot(layout: dict, selected_room_id: str | None = None) -> dict[str, Any]:
    """Produce display-only figures from current model geometry and devices."""
    rooms = layout.get("rooms", ())
    devices = layout.get("devices", ())
    rows = []
    for index, room in enumerate(rooms):
        length = float(room["length_m"])
        width = float(room["width_m"])
        height = float(room["height_m"])
        rid = str(room["id"])
        owned = [item for item in devices if str(item.get("room_id")) == rid]
        counts = {"ffu": 0, "supply": 0, "return_exhaust": 0, "other": 0}
        for device in owned:
            kind = str(device.get("type", "")).lower()
            group = kind if kind in ("ffu", "supply") else (
                "return_exhaust" if kind in ("return", "exhaust") else "other"
            )
            counts[group] += 1
        rows.append({
            "id": rid,
            "name": str(room.get("name") or rid),
            "classification": str(room.get("classification") or "Not classified"),
            "length_m": length,
            "width_m": width,
            "height_m": height,
            "x_m": float(room.get("x_m", 0.0)),
            "y_m": float(room.get("y_m", 0.0)),
            "area_m2": length * width,
            "volume_m3": length * width * height,
            "pressure_pa": room.get("pressure_pa"),
            "devices": len(owned),
            "device_counts": counts,
            "color": STUDIO_ROOM_COLORS[index % len(STUDIO_ROOM_COLORS)],
        })
    selected = next((row for row in rows if row["id"] == selected_room_id), None)
    if selected is None and rows:
        selected = rows[0]
    return {
        "room_count": len(rows),
        "floor_area_m2": sum(row["area_m2"] for row in rows),
        "volume_m3": sum(row["volume_m3"] for row in rows),
        "placed_devices": len(devices),
        "rooms": rows,
        "selected_room": selected,
    }


def studio_nav_signature(rooms: list[dict], selected_id: str | None) -> tuple:
    """Track geometry as well as area so translated/resized rooms redraw the map."""
    return (
        tuple(
            (room["id"], room["name"], room["x_m"], room["y_m"],
             room["length_m"], room["width_m"])
            for room in rooms
        ),
        selected_id,
    )


class DesignStudioPanels:
    """Integrated dashboard, navigator and selection surfaces for the real canvas."""

    def __init__(self, workspace, *, commandbar, modebar, viewbar, overlaybar):
        self.workspace = workspace
        self.enabled = True
        self._advanced_rows = (viewbar, overlaybar)
        self._extra_actions = []
        # Existing commands remain available in More tools. Hiding them is
        # a layout-only change; no editor or backend callbacks are replaced.
        for widget in modebar.winfo_children():
            if widget.winfo_class() == "TButton" and widget.cget("text") in (
                "Reset 2D", "Floor…", "Pull from analysis", "Push to analysis",
            ):
                widget.pack_forget()
        self.advanced_actions_bar = tk.Frame(workspace, bg=_BG)
        for title, command in (
            ("Reset 2D", workspace.reset_2d),
            ("Floor…", workspace.edit_floor),
            ("Pull from analysis", workspace._on_pull_requested),
            ("Push to analysis", workspace._on_sync_requested),
        ):
            tk.Button(
                self.advanced_actions_bar, text=title,
                command=command if command is not None else lambda: None,
                state="normal" if command is not None else "disabled",
                bg="#22415b", fg=_TEXT, relief="flat",
                activebackground="#315a76", padx=8, pady=4,
            ).pack(side="left", padx=(2, 4))

        for widget in commandbar.winfo_children():
            if isinstance(widget, (tk.Button,)):
                continue
            if widget.winfo_class() == "TSeparator" or (
                widget.winfo_class() == "TButton" and
                widget.cget("text") in ("Duplicate", "Delete", "Undo", "Redo")
            ):
                self._extra_actions.append(widget)
                widget.pack_forget()
        self._advanced_visible = False
        self._nav_signature = None
        self.nav_buttons = {}
        self.metric_vars = {
            key: tk.StringVar(value="0") for key in (
                "rooms", "area", "volume", "devices"
            )
        }
        metrics = tk.Frame(workspace, bg=_BG, highlightthickness=1,
                           highlightbackground=_BORDER)
        self.metrics_frame = metrics
        metrics.pack(before=workspace._body, fill="x", padx=8, pady=(3, 2))
        for index, (key, title) in enumerate((
            ("rooms", "ROOMS"),
            ("area", "FLOOR AREA · m²"),
            ("volume", "GEOMETRIC VOLUME · m³"),
            ("devices", "PLACED DEVICES"),
        )):
            card = tk.Frame(metrics, bg=_PANEL, padx=13, pady=5)
            card.grid(row=0, column=index, sticky="nsew", padx=1)
            metrics.grid_columnconfigure(index, weight=1)
            tk.Label(card, textvariable=self.metric_vars[key], bg=_PANEL,
                     fg=_TEXT, font=("Segoe UI", 17, "bold"),
                     anchor="w").pack(fill="x")
            tk.Label(card, text=title, bg=_PANEL, fg=_MUTED,
                     font=("Segoe UI", 8), anchor="w").pack(fill="x")

        self.nav = tk.Frame(workspace._three_d_frame, bg=_PANEL,
                            highlightbackground=_BORDER, highlightthickness=1,
                            padx=9, pady=8)
        tk.Label(self.nav, text="ROOM NAVIGATOR", bg=_PANEL,
                 fg=_CYAN, font=("Segoe UI", 9, "bold")).pack(
                     fill="x", anchor="w")
        self.mini_plan = tk.Canvas(self.nav, height=100, bg="#102133",
                                   highlightthickness=0, cursor="hand2")
        self.mini_plan.pack(fill="x", pady=(6, 1))
        self.nav_list = tk.Frame(self.nav, bg=_PANEL)
        self.nav_list.pack(fill="both", expand=True, pady=(8, 2))
        tk.Label(self.nav, text="Click a room to select", bg=_PANEL,
                 fg=_MUTED, font=("Segoe UI", 8)).pack(anchor="w", pady=(3, 0))

        self.sidebar = tk.Frame(workspace._three_d_frame, bg="#0d1c2b")
        self.details = tk.Frame(self.sidebar, bg=_PANEL,
                                highlightbackground=_CYAN, highlightthickness=2,
                                padx=10, pady=11)
        self.details.pack(fill="x", pady=(0, 18))
        tk.Label(self.details, text="SELECTED ROOM", bg=_PANEL, fg=_CYAN,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.room_name = tk.StringVar(value="No room")
        self.room_details = tk.StringVar(value="Add or select a room")
        self.room_pressure = tk.StringVar(value="")
        self.room_devices = tk.StringVar(value="")
        tk.Label(self.details, textvariable=self.room_name, bg=_PANEL, fg=_TEXT,
                 anchor="w", font=("Segoe UI", 10, "bold")).pack(fill="x", pady=(4, 3))
        tk.Label(self.details, textvariable=self.room_details, bg=_PANEL,
                 fg=_MUTED, anchor="w", justify="left", wraplength=295,
                 font=("Segoe UI", 9)).pack(fill="x", pady=(3, 8))
        tk.Label(self.details, textvariable=self.room_pressure,
                 bg=_PANEL, fg="#e7c17a", anchor="w", justify="left",
                 font=("Segoe UI", 9)).pack(fill="x", pady=(3, 0))
        self.device_panel = tk.Frame(
            self.sidebar, bg=_PANEL,
            highlightbackground=_BORDER, highlightthickness=1,
            padx=10, pady=9,
        )
        self.device_panel.pack(fill="x")
        tk.Label(self.device_panel, text="PLACED IN THIS ROOM", bg=_PANEL,
                 fg=_CYAN, font=("Segoe UI", 9, "bold")).pack(
                     anchor="w", pady=(0, 7))
        tk.Label(self.device_panel, textvariable=self.room_devices, bg=_PANEL,
                 fg=_TEXT, anchor="w", justify="left",
                 font=("Segoe UI", 9)).pack(fill="x")
        actions = tk.Frame(self.device_panel, bg=_PANEL)
        actions.pack(fill="x", pady=(10, 0))
        tk.Button(actions, text="Focus room", command=self.focus_room,
                  bg="#22415b", fg=_TEXT, relief="flat",
                  activebackground="#315a76").pack(side="left", expand=True, fill="x", padx=2)
        tk.Button(actions, text="Isolate room", command=self.isolate_room,
                  bg="#22415b", fg=_TEXT, relief="flat",
                  activebackground="#315a76").pack(side="left", expand=True, fill="x", padx=2)
        tk.Button(self.device_panel, text="Restore all rooms",
                  command=self.restore_all_rooms, bg="#22415b", fg=_TEXT,
                  relief="flat", activebackground="#315a76").pack(
                      fill="x", pady=(6, 0))

        self.camera = tk.Frame(workspace._three_d_frame, bg=_PANEL,
                               highlightbackground=_BORDER, highlightthickness=1)
        for title, action in (
            ("TOP", lambda: self._set_camera_preset("top")),
            ("FRONT", lambda: self._set_camera_preset("front")),
            ("ISO", lambda: self._set_camera_preset("iso")),
            ("FIT", workspace.fit_studio_3d),
        ):
            tk.Button(self.camera, text=title, command=action,
                      bg=_PANEL, fg=_CYAN, relief="flat",
                      activebackground="#25465e", activeforeground=_TEXT,
                      font=("Segoe UI", 8, "bold"), padx=9, pady=5).pack(side="left")

        # Match the reference: search belongs on the design command strip,
        # while Studio/View/Inspector actions belong on the second row.
        tk.Button(
            commandbar, text="Find room / device", command=self.find_item,
            bg="#22415b", fg=_TEXT, relief="flat",
            activebackground="#315a76",
        ).pack(side="right", padx=3)
        for title, action in (
            ("Balance", self.balance_view),
            ("Studio view", self.studio_view),
            ("Inspector", workspace.toggle_inspector),
        ):
            tk.Button(
                modebar, text=title, command=action, bg="#22415b",
                fg=_TEXT, relief="flat", activebackground="#315a76",
                padx=9, pady=5,
            ).pack(side="left", padx=3)
        tk.Button(
            modebar, text="More tools ▾", command=self.toggle_advanced,
            bg="#22415b", fg=_TEXT, relief="flat",
            activebackground="#315a76", padx=9, pady=5,
        ).pack(side="right", padx=3)

        self._compact_layout = None
        self.studio_view(request_focus=False)
        workspace.set_inspector_visible(False)
        for row in self._advanced_rows:
            row.pack_forget()
        self._place_overlays()
        workspace.canvas_3d.bind(
            "<Configure>", lambda _event: self._place_overlays(), add="+",
        )

    def _place_overlays(self):
        # Preserve both reference proportions on desktop and usable viewport
        # area on smaller engineering displays.
        compact = self.workspace.canvas_3d.winfo_width() < 1200
        self.nav.place(
            relx=0.01, rely=0.985, anchor="sw",
            width=230 if compact else 270,
        )
        self.sidebar.place(
            relx=0.985, y=52 if compact else 120, anchor="ne",
            width=250 if compact else 330,
        )
        self.camera.place(relx=0.52, rely=0.985, anchor="s")
        if not hasattr(self, "_axis_hint"):
            self._axis_hint = tk.Label(
                self.workspace._three_d_frame,
                text="Length X (m)\nWidth Y (m)\nHeight Z (m)",
                bg="#0d1117", fg=_MUTED, justify="right",
                font=("Segoe UI", 8, "bold"),
            )
        self._axis_hint.place(relx=0.987, rely=0.985, anchor="se")
        if compact != self._compact_layout:
            self._compact_layout = compact
            self._nav_signature = None
            self.workspace.after_idle(self.update)

    def studio_view(self, *, request_focus: bool = True):
        if request_focus:
            # Restore all rooms after Isolate Room without modifying geometry.
            self.workspace.show_all()
        self.workspace.set_workspace_mode("3d")
        callback = getattr(self.workspace, "_on_studio_requested", None)
        if request_focus and callback is not None:
            callback()
            # Refit only after the outer project/output panes have collapsed.
            self.workspace.after_idle(self.workspace.fit_studio_3d)
        else:
            self.workspace.fit_studio_3d()

    def _set_camera_preset(self, preset: str) -> None:
        self.workspace.set_3d_view_preset(preset)
        self.workspace.fit_studio_3d()

    def balance_view(self):
        """Restore a balanced isometric view of all visible project rooms."""
        self.workspace.show_all()
        self.workspace.set_workspace_mode("3d")
        self.workspace.set_3d_view_preset("iso")
        self.workspace.fit_studio_3d()

    def toggle_advanced(self):
        self._advanced_visible = not self._advanced_visible
        if self._advanced_visible:
            self.advanced_actions_bar.pack(
                before=self.metrics_frame, fill="x", padx=8, pady=(2, 4),
            )
        else:
            self.advanced_actions_bar.pack_forget()
        for widget in self._extra_actions:
            if self._advanced_visible:
                widget.pack(side="left", padx=2)
            else:
                widget.pack_forget()
        for row in self._advanced_rows:
            if self._advanced_visible:
                row.pack(before=self.metrics_frame, fill="x")
            else:
                row.pack_forget()

    def _select_room(self, room_id: str):
        isolated = self.workspace._isolated_item
        if isolated is not None and (
            isolated.kind != "room" or isolated.item_id != room_id
        ):
            # Selecting a different room should not leave it invisible because
            # an earlier isolation filter is still active.
            self.workspace.show_all()
        self.workspace.select_item("room", room_id, notify=True)

    def _draw_mini_plan(self, rooms, selected_id):
        canvas = self.mini_plan
        canvas.delete("all")
        if not rooms:
            return
        min_x = min(r["x_m"] for r in rooms)
        min_y = min(r["y_m"] for r in rooms)
        span_x = max(r["x_m"] + r["length_m"] for r in rooms) - min_x
        span_y = max(r["y_m"] + r["width_m"] for r in rooms) - min_y
        span_x = max(1.0, span_x)
        span_y = max(1.0, span_y)
        scale = min((192.0 if self._compact_layout else 230.0) / span_x, 78.0 / span_y)
        for index, room in enumerate(rooms, 1):
            x0 = 7 + (room["x_m"] - min_x) * scale
            y0 = 10 + (room["y_m"] - min_y) * scale
            x1 = x0 + room["length_m"] * scale
            y1 = y0 + room["width_m"] * scale
            tag = "floorplan:" + room["id"]
            canvas.create_rectangle(
                x0, y0, x1, y1, fill=room["color"],
                outline="#f0f8ff" if room["id"] == selected_id else "#3c6981",
                width=3 if room["id"] == selected_id else 1, tags=(tag,),
            )
            canvas.create_text((x0 + x1) / 2, (y0 + y1) / 2,
                               text=str(index), fill="#172235",
                               font=("Segoe UI", 10, "bold"), tags=(tag,))
            canvas.tag_bind(tag, "<Button-1>",
                            lambda _event, rid=room["id"]: self._select_room(rid))

    def focus_room(self):
        snapshot = studio_snapshot(self.workspace.layout, self._active_room_id())
        row = snapshot["selected_room"]
        if row is not None:
            if self.workspace._isolated_item is not None:
                self.workspace.show_all()
            self._select_room(row["id"])
            self.workspace.focus_room_3d(row["id"])

    def isolate_room(self):
        row = studio_snapshot(self.workspace.layout, self._active_room_id())["selected_room"]
        if row is not None:
            self._select_room(row["id"])
            self.workspace.isolate_selected()

    def restore_all_rooms(self):
        """Clear view-only isolation/hidden filters without changing the model."""
        self.workspace.show_all()
        self.workspace.fit_studio_3d()

    def _active_room_id(self):
        selection = self.workspace.selected
        if selection is None:
            return None
        if selection.kind == "room":
            return selection.item_id
        if selection.kind == "device":
            device = next((d for d in self.workspace.layout["devices"]
                           if str(d["id"]) == selection.item_id), None)
            if device:
                return str(device.get("room_id"))
        return None

    def find_item(self):
        text = simpledialog.askstring("Find room / device", "Name contains:",
                                      parent=self.workspace)
        if not text:
            return
        text = text.casefold().strip()
        for kind, collection in (("room", self.workspace.layout["rooms"]),
                                 ("device", self.workspace.layout["devices"])):
            for item in collection:
                if text in str(item.get("name", "")).casefold():
                    item_id = str(item["id"])
                    if not self.workspace._is_item_visible(kind, item_id):
                        self.workspace.show_all()
                    self.workspace.select_item(kind, item_id, notify=True)
                    return
        self.workspace._status_setter("No matching room or device")

    def update(self):
        if not self.enabled:
            return
        snapshot = studio_snapshot(self.workspace.layout, self._active_room_id())
        for key, value in (
            ("rooms", str(snapshot["room_count"])),
            ("area", f'{snapshot["floor_area_m2"]:.1f}'),
            ("volume", f'{snapshot["volume_m3"]:.1f}'),
            ("devices", str(snapshot["placed_devices"])),
        ):
            self.metric_vars[key].set(value)
        current = snapshot["selected_room"]
        selected_id = current["id"] if current else None
        signature = studio_nav_signature(snapshot["rooms"], selected_id)
        if signature != self._nav_signature:
            self._nav_signature = signature
            for child in self.nav_list.winfo_children():
                child.destroy()
            self.nav_buttons.clear()
            self._draw_mini_plan(snapshot["rooms"], selected_id)
            for index, room in enumerate(snapshot["rooms"], 1):
                chosen = room["id"] == selected_id
                color = room["color"]
                row = tk.Frame(self.nav_list, bg="#25445e" if chosen else _PANEL)
                row.pack(fill="x", pady=2)
                tk.Label(row, text=str(index), bg=color, fg="#101923",
                         width=3, font=("Segoe UI", 9, "bold")).pack(side="left", padx=3)
                btn = tk.Button(row, text=room["name"], anchor="w", relief="flat",
                                bg="#25445e" if chosen else _PANEL,
                                fg=_TEXT, activebackground="#315a76",
                                command=lambda rid=room["id"]: self._select_room(rid))
                btn.pack(side="left", fill="x", expand=True)
                self.nav_buttons[room["id"]] = btn
                tk.Label(row, text=f'{room["area_m2"]:.0f} m²',
                         bg="#25445e" if chosen else _PANEL, fg=_MUTED,
                         font=("Segoe UI", 8)).pack(side="right", padx=2)
        if current is None:
            self.room_name.set("No room selected")
            self.room_details.set("Add a room to start your design.")
            self.room_pressure.set("")
            self.room_devices.set("")
            return
        self.room_name.set(current["name"])
        pressure = current["pressure_pa"]
        pressure_text = (
            f'{float(pressure):+g} Pa'
            if isinstance(pressure, (int, float)) and math.isfinite(float(pressure))
            else "Not specified"
        )
        self.room_details.set(
            f'Project class: {current["classification"]}\n'
            f'L {current["length_m"]:g} W {current["width_m"]:g} '
            f'H {current["height_m"]:g} m\n'
            f'Floor area {current["area_m2"]:.1f} m² · '
            f'Volume {current["volume_m3"]:.1f} m³\n'
            f'Placed devices: {current["devices"]}'
        )
        self.room_pressure.set(f'Layout pressure (not CFD): {pressure_text}')
        counts = current["device_counts"]
        self.room_devices.set(
            f'{counts["ffu"]} FFU           {counts["supply"]} Supply\n'
            f'{counts["return_exhaust"]} Return / exhaust    '
            f'{counts["other"]} Other'
        )
