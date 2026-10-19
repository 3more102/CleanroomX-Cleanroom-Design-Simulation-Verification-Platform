"""Read-only equipment schedule for the real CleanroomX Design Studio.

The table and CSV export derive only from canonical project geometry. They
must never be described as solver-computed values or verification evidence.
"""

from __future__ import annotations

import csv
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING

from .studio_summary import device_layer_category

if TYPE_CHECKING:
    from .spatial import SpatialDesignWorkspace


CATEGORIES = {
    "all": "All equipment",
    "air": "Air devices",
    "opening": "Openings",
    "other": "Other equipment",
}
CSV_COLUMNS = (
    "Device ID", "Name", "Type", "Category", "Room", "Room ID",
    "X (m)", "Y (m)", "Z above floor (m)",
)


def equipment_schedule_rows(
    layout: dict, *, query: str = "", category: str = "all",
    room_id: str | None = None,
) -> list[dict]:
    """Return stable, searchable device facts without touching project state."""
    if category not in CATEGORIES:
        raise ValueError(f"Unsupported device category: {category}")
    rooms = {room["id"]: str(room.get("name") or room["id"])
             for room in layout.get("rooms", [])}
    needle = query.strip().casefold()
    rows = []
    for device in layout.get("devices", []):
        device_id = str(device["id"])
        assigned_room = device.get("room_id")
        actual_category = device_layer_category(device)
        if category != "all" and category != actual_category:
            continue
        if room_id is not None and assigned_room != room_id:
            continue
        room_name = rooms.get(assigned_room, "Unassigned")
        item = {
            "id": device_id,
            "name": str(device.get("name") or device_id),
            "type": str(device.get("type") or "Unspecified"),
            "category": actual_category,
            "room": room_name,
            "room_id": str(assigned_room or ""),
            "x_m": float(device["x_m"]),
            "y_m": float(device["y_m"]),
            "z_offset_m": float(device["z_m"]),
        }
        if needle and not any(needle in str(item[key]).casefold()
                              for key in ("id", "name", "type", "room", "room_id", "category")):
            continue
        rows.append(item)
    return sorted(rows, key=lambda item: (
        item["room"].casefold(), item["type"].casefold(),
        item["name"].casefold(), item["id"],
    ))


def _safe_csv_text(value: object) -> str:
    """Keep arbitrary imported names from becoming spreadsheet formulas."""
    text = str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


def export_equipment_schedule(path: str | Path, rows: list[dict]) -> None:
    """Export exactly the currently displayed, model-derived equipment rows."""
    with Path(path).open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        for item in rows:
            writer.writerow((
                _safe_csv_text(item["id"]), _safe_csv_text(item["name"]),
                _safe_csv_text(item["type"]), _safe_csv_text(item["category"]),
                _safe_csv_text(item["room"]), _safe_csv_text(item["room_id"]),
                item["x_m"], item["y_m"], item["z_offset_m"],
            ))


class DeviceScheduleWindow(tk.Toplevel):
    """Search, filter, inspect and export actual placed model devices."""

    def __init__(self, workspace: SpatialDesignWorkspace) -> None:
        super().__init__(workspace)
        self.workspace = workspace
        self.title("CleanroomX | Device Schedule")
        self.geometry("1060x560")
        self.minsize(760, 370)
        self.transient(workspace.winfo_toplevel())
        self._query_var = tk.StringVar(master=self)
        self._category_var = tk.StringVar(master=self, value="all")
        self._room_var = tk.StringVar(master=self, value="All rooms")
        self._status_var = tk.StringVar(master=self, value="")
        self._room_labels: dict[str, str | None] = {"All rooms": None}
        self._row_ids: dict[str, str] = {}
        self._displayed_rows: list[dict] = []

        heading = ttk.Frame(self, padding=(16, 12))
        heading.pack(fill="x")
        ttk.Label(heading, text="DEVICE SCHEDULE",
                  font=("TkDefaultFont", 15, "bold")).pack(anchor="w")
        ttk.Label(
            heading,
            text="Design coordinates only · X/Y in the project plan · Z relative to the floor · No CFD claims",
        ).pack(anchor="w", pady=(2, 0))

        filters = ttk.Frame(self, padding=(16, 2))
        filters.pack(fill="x")
        ttk.Label(filters, text="Find").pack(side="left", padx=(0, 5))
        search = ttk.Entry(filters, textvariable=self._query_var, width=28)
        search.pack(side="left", padx=(0, 16))
        ttk.Label(filters, text="Category").pack(side="left", padx=(0, 5))
        self.category_box = ttk.Combobox(
            filters, state="readonly", textvariable=self._category_var,
            values=tuple(CATEGORIES), width=12,
        )
        self.category_box.pack(side="left", padx=(0, 16))
        ttk.Label(filters, text="Room").pack(side="left", padx=(0, 5))
        self.room_box = ttk.Combobox(
            filters, state="readonly", textvariable=self._room_var, width=24,
        )
        self.room_box.pack(side="left", fill="x", expand=True)

        table_frame = ttk.Frame(self, padding=(16, 12))
        table_frame.pack(fill="both", expand=True)
        columns = ("name", "type", "room", "x", "y", "z", "id")
        self.table = ttk.Treeview(
            table_frame, columns=columns, show="headings", selectmode="browse", height=14,
        )
        for col, title, width, anchor in (
            ("name", "Device", 210, "w"),
            ("type", "Type", 95, "w"),
            ("room", "Assigned room", 180, "w"),
            ("x", "X (m)", 80, "e"),
            ("y", "Y (m)", 80, "e"),
            ("z", "Z + floor (m)", 108, "e"),
            ("id", "Device ID", 165, "w"),
        ):
            self.table.heading(col, text=title)
            self.table.column(col, width=width, minwidth=55, anchor=anchor)
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.table.pack(side="left", fill="both", expand=True)

        footer = ttk.Frame(self, padding=(16, 2, 16, 12))
        footer.pack(fill="x")
        ttk.Label(footer, textvariable=self._status_var).pack(side="left")
        ttk.Button(footer, text="Close", command=self.destroy).pack(side="right", padx=3)
        ttk.Button(footer, text="Export visible CSV", command=self.export_current).pack(
            side="right", padx=3
        )
        ttk.Button(footer, text="Inspect", command=self.inspect_current).pack(
            side="right", padx=3
        )
        ttk.Button(footer, text="Focus in 3D", command=self.focus_current).pack(
            side="right", padx=3
        )
        ttk.Button(footer, text="Select", command=self.select_current).pack(
            side="right", padx=3
        )

        self._query_var.trace_add("write", lambda *_: self.refresh_rows())
        self.category_box.bind("<<ComboboxSelected>>", lambda _event: self.refresh_rows())
        self.room_box.bind("<<ComboboxSelected>>", lambda _event: self.refresh_rows())
        self.table.bind("<Double-1>", lambda _event: self.focus_current())
        self.table.bind("<Return>", lambda _event: self.focus_current())
        self.bind("<Escape>", lambda _event: self.destroy())
        self.bind("<Control-f>", lambda _event: search.focus_set())
        self.refresh_rows()
        search.focus_set()

    def refresh_rows(self) -> None:
        """Refresh source rows and selection when the underlying model changes."""
        if not self.winfo_exists():
            return
        selected_id = self.selected_device_id() or (
            self.workspace.selected.item_id
            if self.workspace.selected is not None and self.workspace.selected.kind == "device"
            else None
        )
        labels = {"All rooms": None}
        for room in self.workspace.layout["rooms"]:
            labels[f'{room["name"]} [{room["id"]}]'] = room["id"]
        self._room_labels = labels
        self.room_box.configure(values=tuple(labels))
        if self._room_var.get() not in labels:
            self._room_var.set("All rooms")
        category = self._category_var.get()
        if category not in CATEGORIES:
            self._category_var.set("all")
            category = "all"
        rows = equipment_schedule_rows(
            self.workspace.layout,
            query=self._query_var.get(),
            category=category,
            room_id=labels[self._room_var.get()],
        )
        self._displayed_rows = rows
        self.table.delete(*self.table.get_children(""))
        self._row_ids.clear()
        for i, item in enumerate(rows):
            iid = f"equipment-{i}"
            self._row_ids[iid] = item["id"]
            self.table.insert("", "end", iid=iid, values=(
                item["name"], item["type"], item["room"],
                f'{item["x_m"]:g}', f'{item["y_m"]:g}',
                f'{item["z_offset_m"]:+g}', item["id"],
            ))
            if item["id"] == selected_id:
                self.table.selection_set(iid)
                self.table.see(iid)
        total = len(self.workspace.layout["devices"])
        self._status_var.set(f"{len(rows)} of {total} placed devices · configured design values")

    def selected_device_id(self) -> str | None:
        selection = self.table.selection()
        return self._row_ids.get(selection[0]) if selection else None

    def select_current(self) -> bool:
        device_id = self.selected_device_id()
        if device_id is None:
            return False
        selected = bool(self.workspace.select_item("device", device_id, notify=True))
        if selected:
            self.workspace._status_setter(f"Selected schedule device: {device_id}")
        return selected

    def _reveal_current(self) -> bool:
        device_id = self.selected_device_id()
        if device_id is None:
            return False
        device = next((item for item in self.workspace.layout["devices"]
                       if item["id"] == device_id), None)
        if device is None:
            self.refresh_rows()
            return False
        category = device_layer_category(device)
        if not self.workspace._studio_device_layers[category].get():
            self.workspace._studio_device_layers[category].set(True)
            self.workspace._on_studio_device_layers_changed()
        return self.select_current()

    def focus_current(self) -> bool:
        if not self._reveal_current():
            return False
        fitted = bool(self.workspace.fit_selected())
        if fitted:
            self.destroy()
        return fitted

    def inspect_current(self) -> bool:
        if not self._reveal_current():
            return False
        self.destroy()
        self.workspace._focus_property("name")
        return True

    def export_current(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self, title="Export visible equipment schedule",
            defaultextension=".csv", filetypes=(("CSV files", "*.csv"),),
        )
        if not path:
            return
        try:
            export_equipment_schedule(path, self._displayed_rows)
        except OSError as exc:
            messagebox.showerror("Export failed", str(exc), parent=self)
            return
        self._status_var.set(f"Exported {len(self._displayed_rows)} design devices")
