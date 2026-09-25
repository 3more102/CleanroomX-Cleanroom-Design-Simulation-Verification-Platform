from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from .saved_revisions import (
    SavedRevisionCandidate,
    SavedRevisionScan,
    discard_saved_revision_artifact,
)


def saved_revision_safety_message(candidate: SavedRevisionCandidate) -> str:
    return (
        "Restoring opens this saved version as a separate unsaved copy. "
        "The current project file is not overwritten; use Save Project As to preserve "
        "the restored copy separately."
    )


class SavedVersionsCenter(tk.Toplevel):
    """Chooser for explicit saved project revisions."""

    def __init__(self, parent: tk.Misc, scan: SavedRevisionScan):
        super().__init__(parent)
        self.title("Saved CleanroomX versions")
        self.geometry("930x470")
        self.minsize(760, 380)
        self.transient(parent)
        self.grab_set()
        self.result: Path | None = None
        self._candidates = {str(item.path): item for item in scan.candidates}

        header = ttk.Frame(self, padding=(12, 12, 12, 6))
        header.pack(fill="x")
        ttk.Label(
            header,
            text="Saved project versions",
            font=("TkDefaultFont", 13, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            header,
            text=(
                "CleanroomX preserves the previous valid project before an explicit "
                "overwrite. Restoring a version always opens an unsaved copy."
            ),
            wraplength=870,
        ).pack(anchor="w", pady=(4, 0))

        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=12, pady=8)
        self.tree = ttk.Treeview(
            frame,
            columns=("time", "version", "size", "digest"),
            show="tree headings",
            selectmode="browse",
        )
        self.tree.heading("#0", text="Project")
        self.tree.heading("time", text="Archived at (UTC)")
        self.tree.heading("version", text="CleanroomX")
        self.tree.heading("size", text="Bytes")
        self.tree.heading("digest", text="SHA-256")
        self.tree.column("#0", width=210, stretch=True)
        self.tree.column("time", width=205, stretch=False)
        self.tree.column("version", width=100, stretch=False)
        self.tree.column("size", width=90, stretch=False)
        self.tree.column("digest", width=135, stretch=False)
        yscroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")

        for candidate in scan.candidates:
            self.tree.insert(
                "",
                "end",
                iid=str(candidate.path),
                text=candidate.project_name,
                values=(
                    candidate.archived_at_utc,
                    candidate.application_version,
                    str(candidate.source_size_bytes),
                    candidate.source_sha256[:16] + "…",
                ),
            )

        self.message_var = tk.StringVar()
        ttk.Label(
            self,
            textvariable=self.message_var,
            wraplength=880,
            anchor="w",
            padding=(12, 0, 12, 0),
        ).pack(fill="x")

        if scan.issues:
            issue_lines = "; ".join(
                f"{issue.path.name}: {issue.error}" for issue in scan.issues[:3]
            )
            suffix = (
                f" (+{len(scan.issues) - 3} more)" if len(scan.issues) > 3 else ""
            )
            ttk.Label(
                self,
                text=(
                    f"{len(scan.issues)} saved-version artifact(s) could not be read "
                    f"and were preserved: {issue_lines}{suffix}"
                ),
                wraplength=880,
                padding=(12, 6, 12, 0),
            ).pack(fill="x")

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=12, pady=12)
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="right")
        self.restore_button = ttk.Button(
            buttons,
            text="Restore as Unsaved Copy",
            command=self._restore,
        )
        self.restore_button.pack(side="right", padx=(0, 6))
        self.discard_button = ttk.Button(
            buttons,
            text="Delete Saved Version",
            command=self._discard,
        )
        self.discard_button.pack(side="left")

        self.tree.bind("<<TreeviewSelect>>", lambda event: self._selection_changed())
        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children[0])
            self.tree.focus(children[0])
        self._selection_changed()

    def _selected_candidate(self) -> SavedRevisionCandidate | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return self._candidates.get(selection[0])

    def _selection_changed(self) -> None:
        candidate = self._selected_candidate()
        state = "normal" if candidate is not None else "disabled"
        self.restore_button.configure(state=state)
        self.discard_button.configure(state=state)
        self.message_var.set(
            saved_revision_safety_message(candidate) if candidate is not None else ""
        )

    def _restore(self) -> None:
        candidate = self._selected_candidate()
        if candidate is None:
            return
        self.result = candidate.path
        self.destroy()

    def _discard(self) -> None:
        candidate = self._selected_candidate()
        if candidate is None:
            return
        if not messagebox.askyesno(
            "Delete saved version",
            (
                f"Delete this saved version of {candidate.project_name!r}?\n\n"
                "This removes only the selected historical version. "
                "The current project file is not changed."
            ),
            parent=self,
        ):
            return
        try:
            discard_saved_revision_artifact(
                candidate.path,
                revision_dir=candidate.path.parent,
            )
        except (OSError, ValueError) as exc:
            messagebox.showerror("Delete failed", str(exc), parent=self)
            return
        key = str(candidate.path)
        self._candidates.pop(key, None)
        if self.tree.exists(key):
            self.tree.delete(key)
        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children[0])
            self.tree.focus(children[0])
            self.message_var.set("Selected saved version deleted.")
        else:
            self.message_var.set("No saved versions remain.")
        self._selection_changed()
