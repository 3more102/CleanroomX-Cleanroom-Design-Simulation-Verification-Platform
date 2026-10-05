"""IFC import review presentation helpers for the desktop workstation.

This module is deliberately presentation-only.  It summarizes already-validated
IFC semantics and the spatial preview produced by :mod:`cleanroomx.bim_ifc`.
It never parses IFC, changes engineering values, or decides whether an import is
valid.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any
import tkinter as tk
from tkinter import ttk


def _items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def ifc_import_review_snapshot(
    semantics: Mapping[str, Any],
    provenance: Mapping[str, str],
    preview: Mapping[str, Any],
    *,
    existing_layout: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic, read-only operator summary for first IFC import."""

    records = _items(semantics.get("records"))
    rooms = _items(preview.get("rooms"))
    devices = _items(preview.get("devices"))
    existing_rooms = _items((existing_layout or {}).get("rooms"))
    existing_devices = _items((existing_layout or {}).get("devices"))

    ifc_class_counts = Counter(
        str(item.get("ifc_class", "")).strip()
        for item in records
        if str(item.get("ifc_class", "")).strip()
    )
    device_type_counts = Counter(
        str(item.get("type", "")).strip()
        for item in devices
        if str(item.get("type", "")).strip()
    )
    dimension_source_counts = Counter(
        str(item.get("dimension_source", "")).strip()
        for item in records
        if item.get("ifc_class") == "IfcSpace"
        and str(item.get("dimension_source", "")).strip()
    )
    storey_ids = {
        str(item.get("storey_global_id", "")).strip()
        for item in records
        if item.get("ifc_class") == "IfcSpace"
        and str(item.get("storey_global_id", "")).strip()
    }

    orphan_devices = sum(1 for item in devices if not item.get("room_id"))
    classified_rooms = sum(1 for item in rooms if item.get("classification"))
    analysis_linked_rooms = sum(1 for item in rooms if item.get("analysis_room_name"))
    geometry_fallback_spaces = dimension_source_counts.get(
        "ifcopenshell_geometry", 0
    )

    warnings: list[str] = []
    if existing_rooms or existing_devices:
        warnings.append(
            "The current unlinked spatial layout will be replaced if this IFC "
            "baseline is imported."
        )
    if geometry_fallback_spaces:
        warnings.append(
            f"{geometry_fallback_spaces} space(s) use the conservative "
            "IfcOpenShell geometry fallback instead of explicit IFC dimensions."
        )
    if orphan_devices:
        warnings.append(
            f"{orphan_devices} device(s) are not associated with an imported "
            "IfcSpace and will remain unassigned."
        )
    if len(storey_ids) > 1:
        warnings.append(
            f"Imported spaces span {len(storey_ids)} IFC storeys. Room elevations "
            "are preserved individually in the CleanroomX spatial model."
        )
    if not rooms:
        warnings.append("No IfcSpace records produced importable CleanroomX rooms.")

    floor = preview.get("floor")
    if not isinstance(floor, Mapping):
        floor = {}

    return {
        "source_name": str(provenance.get("source_name", "")),
        "source_sha256": str(provenance.get("source_sha256", "")),
        "semantic_sha256": str(semantics.get("semantic_sha256", "")),
        "record_count": len(records),
        "room_count": len(rooms),
        "device_count": len(devices),
        "storey_count": len(storey_ids),
        "orphan_device_count": orphan_devices,
        "classified_room_count": classified_rooms,
        "analysis_linked_room_count": analysis_linked_rooms,
        "existing_room_count": len(existing_rooms),
        "existing_device_count": len(existing_devices),
        "will_replace_existing_layout": bool(existing_rooms or existing_devices),
        "floor_name": str(floor.get("name", "")),
        "floor_elevation_m": floor.get("elevation_m"),
        "ifc_class_counts": dict(sorted(ifc_class_counts.items())),
        "device_type_counts": dict(sorted(device_type_counts.items())),
        "dimension_source_counts": dict(sorted(dimension_source_counts.items())),
        "warnings": warnings,
    }


class IfcImportReviewDialog(tk.Toplevel):
    """Operator review gate for a validated first-time IFC baseline import."""

    def __init__(self, parent: tk.Misc, snapshot: Mapping[str, Any]) -> None:
        super().__init__(parent)
        self.accepted = False
        self.snapshot = dict(snapshot)
        self.title("Review IFC Import")
        self.geometry("1040x720")
        self.minsize(840, 560)
        self.transient(parent)
        self.grab_set()

        heading = ttk.Frame(self, padding=(12, 10, 12, 4))
        heading.pack(fill="x")
        ttk.Label(
            heading,
            text="IFC BASELINE REVIEW",
            style="CX.Section.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            heading,
            text=(
                "Review extracted model identity and import consequences before "
                "CleanroomX changes the project spatial model."
            ),
            wraplength=980,
        ).pack(anchor="w", pady=(3, 0))

        identity = ttk.LabelFrame(self, text="Source and integrity", padding=10)
        identity.pack(fill="x", padx=12, pady=(4, 8))
        self._identity_row(identity, 0, "Source", self.snapshot.get("source_name"))
        self._identity_row(
            identity, 1, "Source SHA-256", self.snapshot.get("source_sha256")
        )
        self._identity_row(
            identity, 2, "Semantic SHA-256", self.snapshot.get("semantic_sha256")
        )
        identity.columnconfigure(1, weight=1)

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        summary_host = ttk.Frame(body)
        breakdown_host = ttk.Frame(body)
        body.add(summary_host, weight=3)
        body.add(breakdown_host, weight=2)

        self.summary_tree = ttk.Treeview(
            summary_host,
            columns=("value",),
            show="tree headings",
            selectmode="browse",
        )
        self.summary_tree.heading("#0", text="Import metric")
        self.summary_tree.heading("value", text="Value")
        self.summary_tree.column("#0", width=280)
        self.summary_tree.column("value", width=180, anchor="e")
        summary_scroll = ttk.Scrollbar(
            summary_host, orient="vertical", command=self.summary_tree.yview
        )
        self.summary_tree.configure(yscrollcommand=summary_scroll.set)
        self.summary_tree.pack(side="left", fill="both", expand=True)
        summary_scroll.pack(side="right", fill="y")
        self._populate_summary()

        ttk.Label(
            breakdown_host,
            text="ENTITY BREAKDOWN",
            style="CX.Section.TLabel",
        ).pack(anchor="w", padx=6, pady=(2, 4))
        self.breakdown_tree = ttk.Treeview(
            breakdown_host,
            columns=("count",),
            show="tree headings",
            selectmode="browse",
        )
        self.breakdown_tree.heading("#0", text="IFC / CleanroomX type")
        self.breakdown_tree.heading("count", text="Count")
        self.breakdown_tree.column("#0", width=250)
        self.breakdown_tree.column("count", width=90, anchor="e")
        breakdown_scroll = ttk.Scrollbar(
            breakdown_host, orient="vertical", command=self.breakdown_tree.yview
        )
        self.breakdown_tree.configure(yscrollcommand=breakdown_scroll.set)
        self.breakdown_tree.pack(side="left", fill="both", expand=True, padx=(6, 0))
        breakdown_scroll.pack(side="right", fill="y")
        self._populate_breakdown()

        warnings = ttk.LabelFrame(self, text="Import notes", padding=8)
        warnings.pack(fill="x", padx=12, pady=(0, 8))
        notes = self.snapshot.get("warnings")
        if isinstance(notes, list) and notes:
            warning_text = "\n".join(f"• {item}" for item in notes)
        else:
            warning_text = "No import warnings were derived from the validated preview."
        ttk.Label(warnings, text=warning_text, wraplength=980, justify="left").pack(
            anchor="w"
        )

        actions = ttk.Frame(self, padding=(12, 0, 12, 12))
        actions.pack(fill="x")
        ttk.Button(actions, text="Cancel", command=self._cancel).pack(side="right")
        self.import_button = ttk.Button(
            actions,
            text="Import IFC Baseline",
            command=self._accept,
        )
        self.import_button.pack(side="right", padx=(0, 8))

        self.bind("<Escape>", lambda _event: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.import_button.focus_set()

    @staticmethod
    def _identity_row(parent: ttk.Frame, row: int, label: str, value: Any) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12))
        ttk.Label(parent, text=str(value or "—")).grid(
            row=row, column=1, sticky="ew"
        )

    def _populate_summary(self) -> None:
        floor_elevation = self.snapshot.get("floor_elevation_m")
        floor_text = self.snapshot.get("floor_name") or "—"
        if isinstance(floor_elevation, (int, float)):
            floor_text = f"{floor_text} · {float(floor_elevation):g} m"
        rows = (
            ("Canonical semantic records", self.snapshot.get("record_count", 0)),
            ("Importable rooms", self.snapshot.get("room_count", 0)),
            ("Importable devices", self.snapshot.get("device_count", 0)),
            ("IFC storeys represented", self.snapshot.get("storey_count", 0)),
            ("Unassigned devices", self.snapshot.get("orphan_device_count", 0)),
            ("Rooms with classification", self.snapshot.get("classified_room_count", 0)),
            (
                "Rooms mapped to analysis names",
                self.snapshot.get("analysis_linked_room_count", 0),
            ),
            ("Spatial floor", floor_text),
            (
                "Existing rooms replaced",
                self.snapshot.get("existing_room_count", 0),
            ),
            (
                "Existing devices replaced",
                self.snapshot.get("existing_device_count", 0),
            ),
        )
        for index, (label, value) in enumerate(rows):
            self.summary_tree.insert(
                "",
                "end",
                iid=f"summary:{index}",
                text=label,
                values=(value,),
            )

    def _populate_breakdown(self) -> None:
        groups = (
            ("IFC classes", self.snapshot.get("ifc_class_counts")),
            ("CleanroomX device types", self.snapshot.get("device_type_counts")),
            ("IfcSpace dimension source", self.snapshot.get("dimension_source_counts")),
        )
        for group_index, (label, values) in enumerate(groups):
            parent = f"group:{group_index}"
            self.breakdown_tree.insert("", "end", iid=parent, text=label, open=True)
            if isinstance(values, Mapping) and values:
                for item_index, (name, count) in enumerate(values.items()):
                    self.breakdown_tree.insert(
                        parent,
                        "end",
                        iid=f"{parent}:{item_index}",
                        text=str(name),
                        values=(count,),
                    )
            else:
                self.breakdown_tree.insert(
                    parent,
                    "end",
                    iid=f"{parent}:empty",
                    text="None",
                    values=(0,),
                )

    def _accept(self) -> None:
        self.accepted = True
        self.destroy()

    def _cancel(self) -> None:
        self.accepted = False
        self.destroy()


def show_ifc_import_review(
    parent: tk.Misc,
    snapshot: Mapping[str, Any],
) -> bool:
    """Display the IFC review gate and return whether the operator accepted it."""

    dialog = IfcImportReviewDialog(parent, snapshot)
    wait_window = getattr(parent, "wait_window", None)
    if callable(wait_window):
        wait_window(dialog)
    return bool(dialog.accepted)
