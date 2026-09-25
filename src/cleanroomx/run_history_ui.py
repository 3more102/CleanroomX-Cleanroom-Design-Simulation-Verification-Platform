from __future__ import annotations

import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .project import atomic_write_text
from .run_history import (
    RunHistoryEntry,
    RunHistoryScan,
    load_run_history_artifact,
)


def _add_readonly_text_tab(notebook: ttk.Notebook, title: str, value: str) -> None:
    frame = ttk.Frame(notebook)
    notebook.add(frame, text=title)
    text = tk.Text(frame, wrap="none")
    yscroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
    xscroll = ttk.Scrollbar(frame, orient="horizontal", command=text.xview)
    text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
    text.grid(row=0, column=0, sticky="nsew")
    yscroll.grid(row=0, column=1, sticky="ns")
    xscroll.grid(row=1, column=0, sticky="ew")
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    text.insert("1.0", value)
    text.configure(state="disabled")


class RunHistoryInspectDialog(tk.Toplevel):
    """Read-only inspection of one retained run.

    Historical evidence is intentionally kept outside the application's current-run
    cache, so inspecting an older result can never make it eligible for current-result
    export or presentation as fresh evidence.
    """

    def __init__(self, parent: tk.Misc, entry: RunHistoryEntry):
        archive = load_run_history_artifact(entry.path)
        super().__init__(parent)
        self.title("Inspect analysis run")
        self.geometry("980x720")
        self.minsize(760, 520)
        self.transient(parent)
        self.grab_set()

        header = ttk.Frame(self, padding=(12, 12, 12, 6))
        header.pack(fill="x")
        ttk.Label(
            header,
            text=f"{archive.project_name} — {archive.analysis_name}",
            font=("TkDefaultFont", 12, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            header,
            text=(
                "Retained historical evidence. This view does not replace or validate "
                "the current analysis result."
            ),
            wraplength=930,
        ).pack(anchor="w", pady=(4, 0))

        provenance = archive.run.diagnostics["application_execution_provenance"]
        details = ttk.LabelFrame(self, text="Run identity", padding=10)
        details.pack(fill="x", padx=12, pady=(0, 10))
        rows = (
            ("Recorded at", archive.saved_at_utc),
            ("Analysis kind", archive.run.kind),
            ("Run status", archive.run.status),
            ("Analysis id", archive.analysis_id),
            ("Input SHA-256", provenance["input_sha256"]),
            ("CleanroomX version", archive.application_version),
            (
                "Project source",
                str(archive.source_path) if archive.source_path is not None else "Unsaved project",
            ),
            ("History id", archive.history_id),
        )
        for row, (label, value) in enumerate(rows):
            ttk.Label(details, text=label + ":", font=("TkDefaultFont", 9, "bold")).grid(
                row=row, column=0, sticky="nw", padx=(0, 8), pady=2
            )
            ttk.Label(details, text=value, wraplength=720).grid(
                row=row, column=1, sticky="nw", pady=2
            )
        details.columnconfigure(1, weight=1)

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        _add_readonly_text_tab(
            notebook,
            "Results",
            json.dumps(
                archive.run.result,
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
            ),
        )
        _add_readonly_text_tab(notebook, "Report", archive.run.markdown)
        _add_readonly_text_tab(
            notebook,
            "Diagnostics",
            json.dumps(
                archive.run.diagnostics,
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
            ),
        )

        ttk.Button(self, text="Close", command=self.destroy).pack(
            side="right", padx=12, pady=(0, 12)
        )


class RunHistoryCenter(tk.Toplevel):
    """Read-only browser for bounded local analysis-run evidence."""

    def __init__(self, parent: tk.Misc, scan: RunHistoryScan):
        super().__init__(parent)
        self.title("Analysis Run History")
        self.geometry("1080x560")
        self.minsize(820, 420)
        self.transient(parent)
        self.grab_set()
        self._entries = {str(item.path): item for item in scan.entries}

        header = ttk.Frame(self, padding=(12, 12, 12, 6))
        header.pack(fill="x")
        ttk.Label(
            header,
            text="Analysis Run History",
            font=("TkDefaultFont", 13, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            header,
            text=(
                "Completed runs accepted by the desktop are retained locally with "
                "integrity evidence. Opening a historical run is read-only and never "
                "changes current analysis state."
            ),
            wraplength=1020,
        ).pack(anchor="w", pady=(4, 0))

        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=12, pady=8)
        self.tree = ttk.Treeview(
            frame,
            columns=("time", "analysis", "kind", "status"),
            show="tree headings",
            selectmode="browse",
        )
        self.tree.heading("#0", text="Project")
        self.tree.heading("time", text="Recorded (UTC)")
        self.tree.heading("analysis", text="Analysis")
        self.tree.heading("kind", text="Kind")
        self.tree.heading("status", text="Status")
        self.tree.column("#0", width=220, stretch=True)
        self.tree.column("time", width=210, stretch=False)
        self.tree.column("analysis", width=220, stretch=True)
        self.tree.column("kind", width=210, stretch=True)
        self.tree.column("status", width=120, stretch=False)
        yscroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")

        for entry in scan.entries:
            self.tree.insert(
                "",
                "end",
                iid=str(entry.path),
                text=entry.project_name,
                values=(
                    entry.saved_at_utc,
                    entry.analysis_name,
                    entry.analysis_kind,
                    entry.run_status,
                ),
            )

        if scan.issues:
            preview = "; ".join(
                f"{issue.path.name}: {issue.error}" for issue in scan.issues[:3]
            )
            suffix = f" (+{len(scan.issues) - 3} more)" if len(scan.issues) > 3 else ""
            ttk.Label(
                self,
                text=(
                    f"{len(scan.issues)} run-history artifact(s) could not be verified "
                    f"and were preserved: {preview}{suffix}"
                ),
                wraplength=1040,
                padding=(12, 4, 12, 0),
            ).pack(fill="x")

        self.message_var = tk.StringVar(
            value=(
                "No retained runs were found."
                if not scan.entries
                else "Select a run to inspect or export its original run bundle."
            )
        )
        ttk.Label(
            self,
            textvariable=self.message_var,
            wraplength=1040,
            padding=(12, 4, 12, 0),
        ).pack(fill="x")

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=12, pady=12)
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="right")
        self.export_button = ttk.Button(
            buttons,
            text="Export Run Bundle…",
            command=self._export_selected,
        )
        self.export_button.pack(side="left")
        self.inspect_button = ttk.Button(
            buttons,
            text="Inspect…",
            command=self._inspect_selected,
        )
        self.inspect_button.pack(side="left", padx=(6, 0))

        self.tree.bind("<<TreeviewSelect>>", lambda event: self._selection_changed())
        self.tree.bind("<Double-1>", lambda event: self._inspect_selected())
        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children[0])
            self.tree.focus(children[0])
        self._selection_changed()

    def _selected_entry(self) -> RunHistoryEntry | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return self._entries.get(selection[0])

    def _selection_changed(self) -> None:
        entry = self._selected_entry()
        state = "normal" if entry is not None else "disabled"
        self.inspect_button.configure(state=state)
        self.export_button.configure(state=state)
        if entry is not None:
            self.message_var.set(
                f"Input SHA-256: {entry.input_sha256} — retained artifact is integrity checked."
            )

    def _inspect_selected(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        try:
            RunHistoryInspectDialog(self, entry)
        except (OSError, ValueError) as exc:
            messagebox.showerror(
                "Run history verification failed",
                (
                    f"{exc}\n\n"
                    "The artifact was not loaded as trusted historical evidence."
                ),
                parent=self,
            )

    def _export_selected(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        try:
            archive = load_run_history_artifact(entry.path)
        except (OSError, ValueError) as exc:
            messagebox.showerror(
                "Run history verification failed",
                str(exc),
                parent=self,
            )
            return

        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export historical run bundle",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
        )
        if not path:
            return
        try:
            text = json.dumps(
                archive.run.to_dict(),
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            ) + "\n"
            atomic_write_text(path, text)
        except Exception as exc:
            messagebox.showerror(
                "Run bundle export failed",
                str(exc),
                parent=self,
            )
            return
        self.message_var.set(f"Exported historical run bundle — {Path(path).name}")
