from __future__ import annotations

import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk

from .gui_windowing import fit_window_to_display
from .project_revisions import ProjectRevisionScan


class ProjectRevisionCenter(tk.Toplevel):
    """Read-only browser for verified explicit-save revision artifacts."""

    def __init__(self, parent: tk.Misc, scan: ProjectRevisionScan):
        super().__init__(parent)
        self.title("Saved project revisions")
        fit_window_to_display(
            self,
            preferred_width=1020,
            preferred_height=600,
            minimum_width=760,
            minimum_height=430,
        )
        self.transient(parent)
        self.grab_set()
        self.result: Path | None = None
        self._revisions = {str(item.path): item for item in scan.revisions}
        self._issues = tuple(scan.issues)
        self.search_var = tk.StringVar()
        self.version_var = tk.StringVar(value="All")
        self.count_var = tk.StringVar()

        header = ttk.Frame(self, padding=(12, 12, 12, 6))
        header.pack(fill="x")
        ttk.Label(
            header,
            text="Saved project revisions",
            style="CX.Section.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            header,
            text=(
                "Each entry is the exact prior project state preserved before a "
                "successful guarded overwrite. Restore always writes a separate copy; "
                "the current project is never replaced by this dialog."
            ),
            wraplength=980,
        ).pack(anchor="w", pady=(4, 0))

        filters = ttk.Frame(self)
        filters.pack(fill="x", padx=12, pady=(2, 6))
        ttk.Label(filters, text="Search").pack(side="left")
        self.search_entry = ttk.Entry(
            filters,
            textvariable=self.search_var,
            width=32,
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(4, 8))

        versions = sorted(
            {
                str(item.application_version).strip()
                for item in scan.revisions
                if str(item.application_version).strip()
            },
            key=str.casefold,
        )
        ttk.Label(filters, text="CleanroomX").pack(side="left")
        self.version_combo = ttk.Combobox(
            filters,
            textvariable=self.version_var,
            values=("All", *versions),
            state="readonly",
            width=14,
        )
        self.version_combo.pack(side="left", padx=(4, 8))
        ttk.Button(
            filters,
            text="Clear",
            command=self._clear_filters,
        ).pack(side="left")
        ttk.Button(
            filters,
            text="Previous",
            command=lambda: self._select_relative(-1),
        ).pack(side="left", padx=(10, 2))
        ttk.Button(
            filters,
            text="Next",
            command=lambda: self._select_relative(1),
        ).pack(side="left", padx=2)
        ttk.Button(
            filters,
            text="Copy metadata",
            command=self._copy_selected,
        ).pack(side="left", padx=2)
        ttk.Label(filters, textvariable=self.count_var).pack(side="right", padx=(12, 0))

        body = ttk.Panedwindow(self, orient="vertical")
        body.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        table_frame = ttk.Frame(body)
        detail_frame = ttk.Frame(body)
        body.add(table_frame, weight=3)
        body.add(detail_frame, weight=2)

        self.tree = ttk.Treeview(
            table_frame,
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
        self.tree.column("sha", width=170, stretch=False)
        self.tree.column("version", width=100, stretch=False)

        yscroll = ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=self.tree.yview,
        )
        xscroll = ttk.Scrollbar(
            table_frame,
            orient="horizontal",
            command=self.tree.xview,
        )
        self.tree.configure(
            yscrollcommand=yscroll.set,
            xscrollcommand=xscroll.set,
        )
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        self.detail = tk.Text(
            detail_frame,
            wrap="none",
            state="disabled",
            borderwidth=0,
            height=7,
        )
        detail_scroll_y = ttk.Scrollbar(
            detail_frame,
            orient="vertical",
            command=self.detail.yview,
        )
        detail_scroll_x = ttk.Scrollbar(
            detail_frame,
            orient="horizontal",
            command=self.detail.xview,
        )
        self.detail.configure(
            yscrollcommand=detail_scroll_y.set,
            xscrollcommand=detail_scroll_x.set,
        )
        self.detail.grid(row=0, column=0, sticky="nsew")
        detail_scroll_y.grid(row=0, column=1, sticky="ns")
        detail_scroll_x.grid(row=1, column=0, sticky="ew")
        detail_frame.rowconfigure(0, weight=1)
        detail_frame.columnconfigure(0, weight=1)

        if scan.issues:
            issue_preview = "; ".join(
                f"{issue.path.name}: {issue.error}"
                for issue in scan.issues[:3]
            )
            message = (
                f"{len(scan.issues)} unreadable/corrupted revision artifact(s) were "
                f"preserved and excluded from restore. {issue_preview}"
            )
        else:
            message = (
                "All listed revision artifacts passed schema, SHA-256, "
                "and project validation."
            )
        ttk.Label(
            self,
            text=message,
            wraplength=980,
            padding=(12, 0, 12, 6),
        ).pack(fill="x")

        buttons = ttk.Frame(self, padding=(12, 4, 12, 12))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        self.restore_button = ttk.Button(
            buttons,
            text="Restore as Copy…",
            command=self._accept,
            style="CX.Primary.TButton",
        )
        self.restore_button.pack(side="right", padx=(0, 6))

        self.search_var.trace_add("write", lambda *_: self._populate())
        self.version_var.trace_add("write", lambda *_: self._populate())
        self.tree.bind("<<TreeviewSelect>>", self._show_selected)
        self.tree.bind("<Double-1>", lambda _event: self._accept())
        self.tree.bind("<Return>", lambda _event: self._accept())
        self.tree.bind("<F4>", lambda _event: self._select_relative(1))
        self.tree.bind("<Shift-F4>", lambda _event: self._select_relative(-1))
        self.tree.bind("<Control-c>", lambda _event: self._copy_selected())
        self.bind("<Control-f>", lambda _event: self.search_entry.focus_set())
        self.bind("<Escape>", lambda _event: self.destroy())

        self._populate()

    @staticmethod
    def _metadata_payload(revision) -> dict[str, object]:
        return {
            "project_name": revision.project_name,
            "created_at_utc": revision.created_at_utc,
            "source_size": revision.source_size,
            "source_sha256": revision.source_sha256,
            "application_version": revision.application_version,
            "artifact_size": revision.artifact_size,
            "artifact_sha256": revision.artifact_sha256,
            "artifact_path": str(revision.path),
        }

    def _filtered_revisions(self):
        query = self.search_var.get().strip().casefold()
        version = self.version_var.get().strip().casefold()
        visible = []
        for revision in self._revisions.values():
            if (
                version
                and version != "all"
                and str(revision.application_version).casefold() != version
            ):
                continue
            if query:
                haystack = " ".join(
                    (
                        revision.project_name,
                        revision.created_at_utc,
                        str(revision.path),
                        revision.source_sha256,
                        revision.artifact_sha256,
                        str(revision.application_version),
                    )
                ).casefold()
                if query not in haystack:
                    continue
            visible.append(revision)
        visible.sort(
            key=lambda item: (item.created_at_utc, item.path.name),
            reverse=True,
        )
        return visible

    def _populate(self) -> None:
        selection = self.tree.selection()
        selected_path = selection[0] if selection else None
        for iid in self.tree.get_children():
            self.tree.delete(iid)

        visible = self._filtered_revisions()
        for revision in visible:
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

        self.count_var.set(
            f"{len(visible)} of {len(self._revisions)} verified revisions"
        )
        children = self.tree.get_children()
        target = (
            selected_path
            if selected_path is not None and self.tree.exists(selected_path)
            else children[0]
            if children
            else None
        )
        if target is not None:
            self.tree.selection_set(target)
            self.tree.focus(target)
            self.tree.see(target)
        self.restore_button.configure(state="normal" if children else "disabled")
        self._show_selected()

    def _selected_revision(self):
        selection = self.tree.selection()
        if not selection:
            return None
        return self._revisions.get(selection[0])

    def _show_selected(self, _event=None) -> None:
        revision = self._selected_revision()
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        if revision is not None:
            self.detail.insert(
                "1.0",
                json.dumps(
                    self._metadata_payload(revision),
                    indent=2,
                    sort_keys=True,
                    ensure_ascii=False,
                ),
            )
        elif self._revisions and not self._filtered_revisions():
            self.detail.insert(
                "1.0",
                "No verified saved revision matches the active filters.",
            )
        else:
            self.detail.insert(
                "1.0",
                "No verified saved revisions are available.",
            )
        self.detail.configure(state="disabled")

    def _clear_filters(self) -> None:
        self.search_var.set("")
        self.version_var.set("All")
        self.search_entry.focus_set()

    def _select_relative(self, step: int):
        children = list(self.tree.get_children())
        if not children:
            return "break"
        selection = self.tree.selection()
        if selection and selection[0] in children:
            index = children.index(selection[0])
            target = children[(index + step) % len(children)]
        else:
            target = children[0 if step >= 0 else -1]
        self.tree.selection_set(target)
        self.tree.focus(target)
        self.tree.see(target)
        self._show_selected()
        return "break"

    def _copy_selected(self) -> None:
        revision = self._selected_revision()
        if revision is None:
            return
        self.clipboard_clear()
        self.clipboard_append(
            json.dumps(
                self._metadata_payload(revision),
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
        )

    def _accept(self) -> None:
        revision = self._selected_revision()
        if revision is None:
            return
        self.result = revision.path
        self.destroy()
