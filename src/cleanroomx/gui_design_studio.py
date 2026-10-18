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


class DesignStudioPanels:
    """Integrated dashboard, navigator and selection surfaces for the real canvas."""

    def __init__(self, workspace, *, commandbar, viewbar, overlaybar):
        self.workspace = workspace
        self.enabled = True
        self._advanced_rows = (viewbar, overlaybar)
        self._extra_actions = []
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
        self.nav_list = tk.Frame(self.nav, bg=_PANEL)
        self.nav_list.pack(fill="both", expand=True, pady=(8, 2))
        tk.Label(self.nav, text="Click a room to select", bg=_PANEL,
                 fg=_MUTED, font=("Segoe UI", 8)).pack(anchor="w", pady=(3, 0))

        self.details = tk.Frame(workspace._three_d_frame, bg=_PANEL,
                                highlightbackground=_CYAN, highlightthickness=2,
                                padx=10, pady=9)
        tk.Label(self.details, text="SELECTED ROOM", bg=_PANEL, fg=_CYAN,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.room_name = tk.StringVar(value="No room")
        self.room_details = tk.StringVar(value="Add or select a room")
        self.room_devices = tk.StringVar(value="")
        tk.Label(self.details, textvariable=self.room_name, bg=_PANEL, fg=_TEXT,
                 anchor="w", font=("Segoe UI", 10, "bold")).pack(fill="x", pady=(4, 3))
        tk.Label(self.details, textvariable=self.room_details, bg=_PANEL,
                 fg=_MUTED, anchor="w", justify="left", wraplength=215,
                 font=("Segoe UI", 9)).pack(fill="x")
        tk.Label(self.details, text="PLACED IN THIS ROOM", bg=_PANEL,
                 fg=_CYAN, font=("Segoe UI", 9, "bold")).pack(
                     anchor="w", pady=(10, 3))
        tk.Label(self.details, textvariable=self.room_devices, bg=_PANEL,
                 fg=_TEXT, anchor="w", justify="left",
                 font=("Segoe UI", 9)).pack(fill="x")
        actions = tk.Frame(self.details, bg=_PANEL)
        actions.pack(fill="x", pady=(10, 0))
        tk.Button(actions, text="Focus room", command=self.focus_room,
                  bg="#22415b", fg=_TEXT, relief="flat",
                  activebackground="#315a76").pack(side="left", expand=True, fill="x", padx=2)
        tk.Button(actions, text="Isolate room", command=self.isolate_room,
                  bg="#22415b", fg=_TEXT, relief="flat",
                  activebackground="#315a76").pack(side="left", expand=True, fill="x", padx=2)

        self.camera = tk.Frame(workspace._three_d_frame, bg=_PANEL,
                               highlightbackground=_BORDER, highlightthickness=1)
        for title, action in (
            ("TOP", lambda: workspace.set_3d_view_preset("top")),
            ("FRONT", lambda: workspace.set_3d_view_preset("front")),
            ("ISO", lambda: workspace.set_3d_view_preset("iso")),
            ("FIT", workspace.fit_3d),
        ):
            tk.Button(self.camera, text=title, command=action,
                      bg=_PANEL, fg=_CYAN, relief="flat",
                      activebackground="#25465e", activeforeground=_TEXT,
                      font=("Segoe UI", 8, "bold"), padx=9, pady=5).pack(side="left")

        tk.Button(commandbar, text="More tools ▾", command=self.toggle_advanced,
                  bg="#22415b", fg=_TEXT, relief="flat",
                  activebackground="#315a76").pack(side="right", padx=3)
        tk.Button(commandbar, text="Inspector", command=workspace.toggle_inspector,
                  bg="#22415b", fg=_TEXT, relief="flat",
                  activebackground="#315a76").pack(side="right", padx=3)
        tk.Button(commandbar, text="Studio view", command=self.studio_view,
                  bg="#22415b", fg=_TEXT, relief="flat",
                  activebackground="#315a76").pack(side="right", padx=3)
        tk.Button(commandbar, text="Find room / device", command=self.find_item,
                  bg="#22415b", fg=_TEXT, relief="flat",
                  activebackground="#315a76").pack(side="right", padx=3)

        self.studio_view()
        workspace.set_inspector_visible(False)
        for row in self._advanced_rows:
            row.pack_forget()
        self._place_overlays()

    def _place_overlays(self):
        self.nav.place(relx=0.015, rely=0.985, anchor="sw", width=230)
        self.details.place(relx=0.985, rely=0.015, anchor="ne", width=250)
        self.camera.place(relx=0.52, rely=0.985, anchor="s")

    def studio_view(self):
        self.workspace.set_workspace_mode("3d")
        self.workspace.fit_3d()

    def toggle_advanced(self):
        self._advanced_visible = not self._advanced_visible
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
        self.workspace.select_item("room", room_id, notify=True)

    def focus_room(self):
        snapshot = studio_snapshot(self.workspace.layout, self._active_room_id())
        row = snapshot["selected_room"]
        if row is not None:
            self._select_room(row["id"])
            self.workspace.fit_selected()
            self.workspace.fit_3d()

    def isolate_room(self):
        row = studio_snapshot(self.workspace.layout, self._active_room_id())["selected_room"]
        if row is not None:
            self._select_room(row["id"])
            self.workspace.isolate_selected()

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
                    self.workspace.select_item(kind, str(item["id"]), notify=True)
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
        signature = (
            tuple((r["id"], r["name"], r["area_m2"]) for r in snapshot["rooms"]),
            selected_id,
        )
        if signature != self._nav_signature:
            self._nav_signature = signature
            for child in self.nav_list.winfo_children():
                child.destroy()
            self.nav_buttons.clear()
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
            f'Placed devices: {current["devices"]}\n'
            f'Pressure: {pressure_text}'
        )
        counts = current["device_counts"]
        self.room_devices.set(
            f'{counts["ffu"]} FFU           {counts["supply"]} Supply\n'
            f'{counts["return_exhaust"]} Return / exhaust    '
            f'{counts["other"]} Other'
        )
