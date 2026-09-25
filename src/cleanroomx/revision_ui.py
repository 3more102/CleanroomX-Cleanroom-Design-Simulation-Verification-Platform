from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import ttk

from .project import ProjectRevisionScan


class ProjectRevisionCenter(tk.Toplevel):
    """Read-only browser for verified explicit-save revision artifacts."""

    def __init__(self, parent: tk.Misc, scan: ProjectRevisionScan):
        super().__init__(parent)
        self.title("Saved project revisions")
        self.geometry("920x500")
        self.minsize(720, 380)
        self.transient(parent)
        self.grab_set()
        self.result: Path | None = None
        self._revisions = {str(item.path): item for item in scan.revisions}

        header = ttk.Frame(self, padding=(12, 12, 12, 6))
        header.pack(fill="x")
        ttk.Label(
            header,
            text="Saved project revisions",
            font=("TkDefaultFont", 13, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            header,
            text=(
                "Each entry is the exact prior project state preserved before a "
                "successful guarded overwrite. Restore always writes a separate copy; "
                "the current project is never replaced by this dialog."
            ),
            wraplength=880,
        ).pack(anchor="w", pady=(4, 0))

        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=12, pady=8)
        self.tree = ttk.Treeview(
            frame,
            columns=("time", "size", "sha", "version"),
            show="tree headings",
            selectmode="browse",
        )
        self.tree.heading("#0", text="Project")
        self.tree.heading("time", text="Saved revision timestamp (UTC)")
        self.tree.heading("size", text="Bytes")
        self.tree.heading("sha", text="SHA-256")
        self.tree.heading("version", text="CleanroomX")
        self.tree.column("#0", width=190, stretch=False)
        self.tree.column("time", width=220, stretch=False)
        self.tree.column("size", width=90, anchor="e", stretch=False)
        self.tree.column("sha", width=150, stretch=False)
        self.tree.column("version", width=100, stretch=False)

        yscroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")

        for revision in scan.revisions:
            self.tree.insert(
                "",
                "end",
                iid=str(revision.path),
                text=revision.project_name,
                values=(
                    revision.created_at_utc,
                    str(revision.source_size),
                    revision.source_sha256[:16] + "…",
                    revision.application_version,
                ),
            )

        message = (
            f"{len(scan.issues)} unreadable/corrupted revision artifact(s) were "
            "preserved and excluded from restore."
            if scan.issues
            else "All listed revision artifacts passed schema, SHA-256, and project validation."
        )
        ttk.Label(
            self,
            text=message,
            wraplength=880,
            padding=(12, 0, 12, 6),
        ).pack(fill="x")

        buttons = ttk.Frame(self, padding=(12, 4, 12, 12))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        self.restore_button = ttk.Button(
            buttons,
            text="Restore as Copy…",
            command=self._accept,
        )
        self.restore_button.pack(side="right", padx=(0, 6))

        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children[0])
            self.tree.focus(children[0])
        else:
            self.restore_button.configure(state="disabled")
        self.tree.bind("<Double-1>", lambda _event: self._accept())

    def _accept(self) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        path = selection[0]
        if path not in self._revisions:
            return
        self.result = Path(path)
        self.destroy()
