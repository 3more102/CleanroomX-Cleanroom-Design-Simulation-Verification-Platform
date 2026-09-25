from __future__ import annotations

import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .project import atomic_write_text
from .run_history import (
    RunHistoryEntry,
    RunHistoryScan,
    load_run_history_record,
)


class RunHistoryCenter(tk.Toplevel):
    """Read-only browser for integrity-verified historical analysis evidence."""

    def __init__(self, parent: tk.Misc, scan: RunHistoryScan):
        super().__init__(parent)
        self.title("Run History")
        self.geometry("1120x680")
        self.minsize(820, 520)
        self.transient(parent)
        self._scan = scan
        self._entries_by_iid: dict[str, RunHistoryEntry] = {}

        header = ttk.Frame(self, padding=(10, 10, 10, 4))
        header.pack(fill="x")
        ttk.Label(
            header,
            text="Durable analysis run history",
            font=("TkDefaultFont", 11, "bold"),
        ).pack(side="left")
        ttk.Label(
            header,
            text=(
                f"{len(scan.entries)} verified record(s)"
                + (f", {len(scan.issues)} issue(s)" if scan.issues else "")
            ),
        ).pack(side="right")

        panes = ttk.Panedwindow(self, orient="vertical")
        panes.pack(fill="both", expand=True, padx=10, pady=6)

        top = ttk.Frame(panes)
        panes.add(top, weight=2)
        columns = ("time", "analysis", "kind", "status", "project")
        self.tree = ttk.Treeview(
            top,
            columns=columns,
            show="headings",
            selectmode="browse",
            height=12,
        )
        headings = {
            "time": "Recorded (UTC)",
            "analysis": "Analysis",
            "kind": "Kind",
            "status": "Status",
            "project": "Project state",
        }
        widths = {
            "time": 190,
            "analysis": 220,
            "kind": 190,
            "status": 120,
            "project": 190,
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], stretch=True)
        scroll = ttk.Scrollbar(top, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        for index, entry in enumerate(scan.entries):
            iid = f"entry-{index}"
            project_state = entry.source_relation.replace("_", " ")
            if entry.project_dirty:
                project_state += " / unsaved edits"
            self._entries_by_iid[iid] = entry
            self.tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    entry.recorded_at_utc,
                    entry.analysis_name,
                    entry.analysis_kind,
                    entry.status,
                    project_state,
                ),
            )

        bottom = ttk.Notebook(panes)
        panes.add(bottom, weight=3)

        evidence_frame = ttk.Frame(bottom)
        bottom.add(evidence_frame, text="Evidence")
        self.detail_text = tk.Text(evidence_frame, wrap="none", state="disabled")
        yscroll = ttk.Scrollbar(
            evidence_frame, orient="vertical", command=self.detail_text.yview
        )
        xscroll = ttk.Scrollbar(
            evidence_frame, orient="horizontal", command=self.detail_text.xview
        )
        self.detail_text.configure(
            yscrollcommand=yscroll.set,
            xscrollcommand=xscroll.set,
        )
        self.detail_text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        evidence_frame.rowconfigure(0, weight=1)
        evidence_frame.columnconfigure(0, weight=1)

        issues_frame = ttk.Frame(bottom)
        bottom.add(issues_frame, text=f"Issues ({len(scan.issues)})")
        issues_text = tk.Text(issues_frame, wrap="word", state="normal")
        if scan.issues:
            for issue in scan.issues:
                issues_text.insert(
                    "end",
                    f"{issue.path.name}\n{issue.error}\n\n",
                )
        else:
            issues_text.insert("end", "No malformed or unreadable run-history artifacts.")
        issues_text.configure(state="disabled")
        issues_text.pack(fill="both", expand=True)

        buttons = ttk.Frame(self, padding=(10, 4, 10, 10))
        buttons.pack(fill="x")
        self.export_record_button = ttk.Button(
            buttons,
            text="Export Evidence Record...",
            command=self._export_record,
            state="disabled",
        )
        self.export_record_button.pack(side="left")
        self.export_bundle_button = ttk.Button(
            buttons,
            text="Export Run Bundle...",
            command=self._export_bundle,
            state="disabled",
        )
        self.export_bundle_button.pack(side="left", padx=(6, 0))
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="right")

        first = self.tree.get_children()
        if first:
            self.tree.selection_set(first[0])
            self.tree.focus(first[0])
            self._on_select()

    def _selected_entry(self) -> RunHistoryEntry | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return self._entries_by_iid.get(selection[0])

    def _selected_record(self) -> dict | None:
        entry = self._selected_entry()
        if entry is None:
            return None
        try:
            return load_run_history_record(entry.path)
        except (OSError, ValueError) as exc:
            messagebox.showerror(
                "Run history unavailable",
                (
                    f"The selected historical record could not be verified.\n\n{exc}\n\n"
                    "The artifact was preserved for inspection."
                ),
                parent=self,
            )
            return None

    def _set_detail(self, value: str) -> None:
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", value)
        self.detail_text.configure(state="disabled")

    def _on_select(self, event=None) -> None:
        record = self._selected_record()
        if record is None:
            self._set_detail("")
            self.export_record_button.configure(state="disabled")
            self.export_bundle_button.configure(state="disabled")
            return
        self._set_detail(
            json.dumps(
                record,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            )
        )
        self.export_record_button.configure(state="normal")
        self.export_bundle_button.configure(state="normal")

    def _write_export(self, content: str, *, label: str, defaultextension: str) -> None:
        path = filedialog.asksaveasfilename(
            parent=self,
            title=f"Export {label}",
            defaultextension=defaultextension,
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            atomic_write_text(Path(path), content)
        except Exception as exc:
            messagebox.showerror(
                f"{label} export failed",
                str(exc),
                parent=self,
            )
            return
        messagebox.showinfo(
            label,
            f"Exported {label.lower()} to {Path(path).name}.",
            parent=self,
        )

    def _export_record(self) -> None:
        record = self._selected_record()
        if record is None:
            return
        self._write_export(
            json.dumps(
                record,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            ) + "\n",
            label="Evidence Record",
            defaultextension=".json",
        )

    def _export_bundle(self) -> None:
        record = self._selected_record()
        if record is None:
            return
        self._write_export(
            json.dumps(
                record["run"],
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            ) + "\n",
            label="Run Bundle",
            defaultextension=".json",
        )
