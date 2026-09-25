from __future__ import annotations

import json
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from .autosave import (
    RecoveryCandidate,
    RecoveryFormatError,
    RecoveryScan,
    discard_recovery_artifact,
    load_recovery_artifact,
    prepare_recovery_restore,
)


_SOURCE_LABELS = {
    "unsaved": "Unsaved project",
    "source_unchanged": "Source unchanged",
    "source_changed": "Source changed",
    "source_newer": "Source is newer",
    "source_missing": "Source missing",
}


def recovery_relation_label(candidate: RecoveryCandidate) -> str:
    return _SOURCE_LABELS.get(candidate.source_relation, candidate.source_relation)


class RecoveryInspectDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, candidate: RecoveryCandidate):
        super().__init__(parent)
        self.title("Inspect Recovery Snapshot")
        self.transient(parent)
        self.geometry("900x620")
        self.minsize(680, 420)

        summary = ttk.Frame(self, padding=12)
        summary.pack(fill="x")
        rows = (
            ("Project", candidate.project_name),
            ("Recovered at", candidate.saved_at_utc),
            ("Project identity", candidate.project_identity),
            ("Source status", recovery_relation_label(candidate)),
            (
                "Source path",
                str(candidate.source_path) if candidate.source_path is not None else "Unsaved",
            ),
            ("Recovery artifact", str(candidate.path)),
        )
        for row, (label, value) in enumerate(rows):
            ttk.Label(summary, text=f"{label}:").grid(
                row=row, column=0, sticky="nw", padx=(0, 8), pady=2
            )
            ttk.Label(summary, text=value, wraplength=720).grid(
                row=row, column=1, sticky="nw", pady=2
            )
        summary.columnconfigure(1, weight=1)

        frame = ttk.Frame(self, padding=(12, 0, 12, 8))
        frame.pack(fill="both", expand=True)
        text = tk.Text(frame, wrap="none", state="normal")
        yscroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        xscroll = ttk.Scrollbar(frame, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        try:
            payload = load_recovery_artifact(candidate.path)
            body = json.dumps(
                payload,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            )
        except (OSError, RecoveryFormatError, TypeError, ValueError) as exc:
            body = f"Recovery artifact could not be read.\n\n{exc}"
        text.insert("1.0", body)
        text.configure(state="disabled")

        buttons = ttk.Frame(self, padding=(12, 0, 12, 12))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="right")


class RecoveryDialog(tk.Toplevel):
    """Startup recovery chooser.

    Selecting Restore only returns the recovery artifact path. The application
    layer performs a validated restore into a protected working copy and never
    overwrites the source project as part of this dialog.
    """

    def __init__(
        self,
        parent: tk.Misc,
        scan: RecoveryScan,
        *,
        recovery_dir: str | Path,
    ):
        super().__init__(parent)
        self.title("Recover Unsaved CleanroomX Work")
        self.transient(parent)
        self.grab_set()
        self.geometry("1040x590")
        self.minsize(760, 470)

        self.result_path: Path | None = None
        self.recovery_dir = Path(recovery_dir)
        self._candidates: dict[str, RecoveryCandidate] = {}

        header = ttk.Frame(self, padding=(12, 12, 12, 6))
        header.pack(fill="x")
        ttk.Label(
            header,
            text="Recover unsaved work",
            font=("TkDefaultFont", 12, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            header,
            text=(
                "Recovery snapshots are separate from saved project files. "
                "Restoring opens a protected working copy; the source file is never "
                "overwritten automatically."
            ),
            wraplength=980,
        ).pack(anchor="w", pady=(4, 0))
        if scan.issues:
            ttk.Label(
                header,
                text=(
                    f"{len(scan.issues)} malformed or unreadable recovery artifact(s) "
                    "were skipped. They were not deleted."
                ),
            ).pack(anchor="w", pady=(4, 0))

        table_frame = ttk.Frame(self, padding=(12, 6))
        table_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            table_frame,
            columns=("project", "time", "source", "path"),
            show="headings",
            selectmode="browse",
            height=11,
        )
        self.tree.heading("project", text="Project")
        self.tree.heading("time", text="Recovery time (UTC)")
        self.tree.heading("source", text="Source comparison")
        self.tree.heading("path", text="Original project")
        self.tree.column("project", width=180, stretch=False)
        self.tree.column("time", width=210, stretch=False)
        self.tree.column("source", width=150, stretch=False)
        self.tree.column("path", width=420, stretch=True)
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        for index, candidate in enumerate(scan.candidates):
            iid = f"recovery-{index}"
            self._candidates[iid] = candidate
            self.tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    candidate.project_name,
                    candidate.saved_at_utc,
                    recovery_relation_label(candidate),
                    str(candidate.source_path) if candidate.source_path else "Unsaved",
                ),
            )

        details = ttk.LabelFrame(self, text="Selection details", padding=10)
        details.pack(fill="x", padx=12, pady=(0, 8))
        self.details_var = tk.StringVar(value="Select a recovery snapshot.")
        ttk.Label(
            details,
            textvariable=self.details_var,
            wraplength=980,
            justify="left",
        ).pack(anchor="w")

        buttons = ttk.Frame(self, padding=(12, 0, 12, 12))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Continue Without Restoring", command=self.destroy).pack(
            side="right"
        )
        ttk.Button(buttons, text="Restore Working Copy", command=self._restore).pack(
            side="right", padx=(0, 6)
        )
        ttk.Button(buttons, text="Inspect", command=self._inspect).pack(
            side="right", padx=(0, 6)
        )
        ttk.Button(buttons, text="Discard", command=self._discard).pack(
            side="left"
        )

        self.tree.bind("<<TreeviewSelect>>", self._selection_changed)
        self.tree.bind("<Double-1>", lambda event: self._inspect())
        first = self.tree.get_children()
        if first:
            self.tree.selection_set(first[0])
            self.tree.focus(first[0])
            self._selection_changed()

        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _selected_candidate(self) -> RecoveryCandidate | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return self._candidates.get(selection[0])

    def _selection_changed(self, event=None) -> None:
        candidate = self._selected_candidate()
        if candidate is None:
            self.details_var.set("Select a recovery snapshot.")
            return
        source_text = (
            str(candidate.source_path)
            if candidate.source_path is not None
            else "This work had not been saved to a project file."
        )
        warning = ""
        if candidate.source_relation == "source_newer":
            warning = (
                " The source project is newer than this recovery snapshot. "
                "Restoring will preserve that newer file and require Save As."
            )
        elif candidate.source_relation == "source_changed":
            warning = (
                " The source project differs from the version fingerprinted by autosave. "
                "Restoring will preserve both versions and require Save As."
            )
        elif candidate.source_relation == "source_missing":
            warning = (
                " The original project file is missing. The recovery can still be "
                "opened as a working copy and saved to a new path."
            )
        self.details_var.set(
            f"Identity: {candidate.project_identity}\n"
            f"Source: {source_text}\n"
            f"State: {recovery_relation_label(candidate)}.{warning}"
        )

    def _inspect(self) -> None:
        candidate = self._selected_candidate()
        if candidate is None:
            return
        dialog = RecoveryInspectDialog(self, candidate)
        self.wait_window(dialog)

    def _discard(self) -> None:
        selection = self.tree.selection()
        candidate = self._selected_candidate()
        if not selection or candidate is None:
            return
        if not messagebox.askyesno(
            "Discard recovery snapshot",
            (
                "Delete this recovery artifact?\n\n"
                "The original project file will not be modified."
            ),
            parent=self,
        ):
            return
        try:
            discard_recovery_artifact(
                candidate.path,
                recovery_dir=self.recovery_dir,
            )
        except (OSError, ValueError) as exc:
            messagebox.showerror(
                "Discard failed",
                str(exc),
                parent=self,
            )
            return

        iid = selection[0]
        self.tree.delete(iid)
        self._candidates.pop(iid, None)
        remaining = self.tree.get_children()
        if remaining:
            self.tree.selection_set(remaining[0])
            self.tree.focus(remaining[0])
            self._selection_changed()
        else:
            self.details_var.set("No recovery snapshots remain.")

    def _restore(self) -> None:
        candidate = self._selected_candidate()
        if candidate is None:
            return
        try:
            prepare_recovery_restore(candidate.path)
        except (OSError, RecoveryFormatError, TypeError, ValueError) as exc:
            messagebox.showerror(
                "Recovery snapshot is invalid",
                str(exc),
                parent=self,
            )
            return
        self.result_path = candidate.path
        self.destroy()
