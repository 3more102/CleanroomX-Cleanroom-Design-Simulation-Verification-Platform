from __future__ import annotations

import json
from pathlib import Path

import tkinter as tk
from tkinter import messagebox, ttk

from .run_history import RunHistoryRecord, RunHistoryScanItem, scan_run_history


class RunHistoryCenter(tk.Toplevel):
    """Read-only browser for immutable per-project analysis-run evidence."""

    def __init__(self, parent: tk.Misc, project_path: str | Path):
        super().__init__(parent)
        self.project_path = Path(project_path)
        self.title(f"Run History — {self.project_path.name}")
        self.geometry("1100x720")
        self.minsize(820, 520)
        self.transient(parent)
        self._items_by_iid: dict[str, RunHistoryScanItem] = {}
        self._summary_var = tk.StringVar(value="")
        self._build()
        self.refresh()

    def _build(self) -> None:
        outer = ttk.Frame(self, padding=10)
        outer.pack(fill="both", expand=True)

        ttk.Label(
            outer,
            text=(
                "Immutable analysis runs archived beside this saved project. "
                "Corrupt records remain visible and are never auto-deleted."
            ),
            wraplength=980,
            justify="left",
        ).pack(fill="x", pady=(0, 8))

        paned = ttk.Panedwindow(outer, orient="vertical")
        paned.pack(fill="both", expand=True)

        listing = ttk.Frame(paned)
        detail = ttk.Frame(paned)
        paned.add(listing, weight=2)
        paned.add(detail, weight=3)

        columns = ("completed", "analysis", "kind", "status", "project")
        self.tree = ttk.Treeview(
            listing,
            columns=columns,
            show="headings",
            selectmode="browse",
            height=10,
        )
        headings = {
            "completed": "Completed (UTC)",
            "analysis": "Analysis",
            "kind": "Workflow",
            "status": "Status",
            "project": "Project state",
        }
        widths = {
            "completed": 205,
            "analysis": 210,
            "kind": 180,
            "status": 130,
            "project": 120,
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], minwidth=80)
        scrollbar = ttk.Scrollbar(listing, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        ttk.Label(detail, textvariable=self._summary_var).pack(
            fill="x", pady=(8, 6)
        )
        self.notebook = ttk.Notebook(detail)
        self.notebook.pack(fill="both", expand=True)
        self._detail_widgets: dict[str, tk.Text] = {}
        for title in ("Metadata", "Input", "Result", "Diagnostics", "Report"):
            frame = ttk.Frame(self.notebook)
            self.notebook.add(frame, text=title)
            text = tk.Text(frame, wrap="none", state="disabled")
            scroll_y = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
            scroll_x = ttk.Scrollbar(frame, orient="horizontal", command=text.xview)
            text.configure(
                yscrollcommand=scroll_y.set,
                xscrollcommand=scroll_x.set,
            )
            text.grid(row=0, column=0, sticky="nsew")
            scroll_y.grid(row=0, column=1, sticky="ns")
            scroll_x.grid(row=1, column=0, sticky="ew")
            frame.rowconfigure(0, weight=1)
            frame.columnconfigure(0, weight=1)
            self._detail_widgets[title] = text

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Refresh", command=self.refresh).pack(side="left")
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="right")

    @staticmethod
    def _json_text(value) -> str:
        return json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )

    def _set_detail(self, title: str, value: str) -> None:
        widget = self._detail_widgets[title]
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def _clear_details(self) -> None:
        self._summary_var.set("")
        for title in self._detail_widgets:
            self._set_detail(title, "")

    @staticmethod
    def _metadata(record: RunHistoryRecord) -> dict:
        revision = record.project_revision
        return {
            "record_id": record.record_id,
            "completed_at_utc": record.completed_at_utc,
            "project_filename": record.project_filename,
            "project_revision": {
                "exists": revision.exists,
                "size_bytes": revision.size,
                "mtime_ns": revision.mtime_ns,
                "sha256": revision.sha256,
            },
            "project_dirty_at_run": record.project_dirty,
            "analysis": {
                "id": record.analysis_id,
                "name": record.analysis_name,
                "kind": record.analysis_kind,
            },
            "history_record_path": str(record.path) if record.path is not None else None,
        }

    def refresh(self) -> None:
        self._items_by_iid.clear()
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._clear_details()

        try:
            items = scan_run_history(self.project_path)
        except Exception as exc:
            messagebox.showerror(
                "Run history unavailable",
                str(exc),
                parent=self,
            )
            self._summary_var.set(f"Run history unavailable: {exc}")
            return

        for index, item in enumerate(items):
            iid = f"history-{index}"
            self._items_by_iid[iid] = item
            if item.record is None:
                values = (
                    "—",
                    item.path.name,
                    "—",
                    "CORRUPT",
                    "preserved",
                )
            else:
                record = item.record
                values = (
                    record.completed_at_utc,
                    record.analysis_name,
                    record.analysis_kind,
                    record.run.status,
                    "dirty" if record.project_dirty else "saved",
                )
            self.tree.insert("", "end", iid=iid, values=values)

        if not items:
            self._summary_var.set(
                "No archived runs yet. Successful runs are archived after a saved project is run."
            )
            return

        first = self.tree.get_children()[0]
        self.tree.selection_set(first)
        self.tree.focus(first)
        self._show_item(self._items_by_iid[first])

    def _on_select(self, _event=None) -> None:
        selection = self.tree.selection()
        if selection:
            item = self._items_by_iid.get(selection[0])
            if item is not None:
                self._show_item(item)

    def _show_item(self, item: RunHistoryScanItem) -> None:
        if item.record is None:
            self._summary_var.set(
                f"CORRUPT — {item.path.name}. Evidence preserved; automatic repair is disabled."
            )
            self._set_detail(
                "Metadata",
                self._json_text(
                    {
                        "path": str(item.path),
                        "status": "corrupt",
                        "error": item.error,
                    }
                ),
            )
            for title in ("Input", "Result", "Report"):
                self._set_detail(title, "")
            self._set_detail("Diagnostics", item.error or "Unknown history error")
            return

        record = item.record
        self._summary_var.set(
            f"{record.analysis_name} — {record.run.status} — "
            f"{record.completed_at_utc} — record {record.record_id[:16]}"
        )
        self._set_detail("Metadata", self._json_text(self._metadata(record)))
        self._set_detail("Input", self._json_text(record.input_snapshot))
        self._set_detail("Result", self._json_text(record.run.result))
        self._set_detail("Diagnostics", self._json_text(record.run.diagnostics))
        self._set_detail("Report", record.run.markdown)
