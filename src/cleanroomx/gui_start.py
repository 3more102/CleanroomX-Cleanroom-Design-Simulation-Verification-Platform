from __future__ import annotations

from collections.abc import Callable
import tkinter as tk
from tkinter import ttk

from .gui_table import TreeviewTableBehavior


class StartCenter(ttk.Frame):
    """Professional zero-state surface; all project actions stay in the app layer."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_new: Callable[[], None],
        on_open: Callable[[], None],
        on_import_ifc: Callable[[], None],
        on_open_demo: Callable[[], None],
        on_open_recent: Callable[[str], None],
        on_forget_recent: Callable[[str], None] | None = None,
    ):
        super().__init__(master, padding=(34, 28))
        self._on_open_recent = on_open_recent
        self._on_forget_recent = on_forget_recent
        self._recent_paths: dict[str, str] = {}
        self._recent_records: list[dict[str, str]] = []
        self.recent_search_var = tk.StringVar()
        self.recent_count_var = tk.StringVar(value="0 recent projects")

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(3, weight=1)

        brand = ttk.Frame(self)
        brand.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(4, 22))
        ttk.Label(brand, text="CleanroomX", style="CX.Brand.TLabel").pack(anchor="w")
        ttk.Label(
            brand,
            text="Engineering Design • Simulation • Verification",
            style="CX.ViewTitle.TLabel",
        ).pack(anchor="w", pady=(4, 0))
        ttk.Label(
            brand,
            text=(
                "Project-native cleanroom engineering with linked 2D/3D design, "
                "analysis, deterministic verification, IFC semantics, diagnostics, "
                "ProofGraph, and evidence traceability."
            ),
            wraplength=900,
            justify="left",
        ).pack(anchor="w", pady=(8, 0))

        actions = ttk.LabelFrame(self, text="Start", padding=18)
        actions.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        ttk.Button(
            actions,
            text="New Project",
            style="CX.Primary.TButton",
            command=on_new,
        ).grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        ttk.Button(
            actions,
            text="Open Project",
            style="CX.Primary.TButton",
            command=on_open,
        ).grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        ttk.Button(
            actions,
            text="Import IFC",
            command=on_import_ifc,
        ).grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        ttk.Button(
            actions,
            text="Open Example Project",
            command=on_open_demo,
        ).grid(row=1, column=1, sticky="ew", padx=5, pady=5)

        capabilities = ttk.LabelFrame(self, text="Engineering workspace", padding=18)
        capabilities.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        ttk.Label(
            capabilities,
            text=(
                "2D / 3D / Split engineering views\n"
                "Project Navigator + contextual properties\n"
                "Analysis + verification overlays\n"
                "IDE-style deterministic diagnostics\n"
                "ProofGraph + evidence traceability\n"
                "IFC semantic import / re-import review"
            ),
            justify="left",
        ).pack(anchor="w")

        recent = ttk.LabelFrame(self, text="Recent Projects", padding=12)
        recent.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="nsew",
            pady=(18, 0),
        )
        recent.columnconfigure(0, weight=1)
        recent.rowconfigure(1, weight=1)

        filter_row = ttk.Frame(recent)
        filter_row.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 7))
        ttk.Label(filter_row, text="Search").pack(side="left")
        self.recent_search_entry = ttk.Entry(
            filter_row,
            textvariable=self.recent_search_var,
            width=34,
        )
        self.recent_search_entry.pack(side="left", fill="x", expand=True, padx=(4, 8))
        ttk.Button(
            filter_row,
            text="Clear",
            command=lambda: self.recent_search_var.set(""),
        ).pack(side="left")
        ttk.Label(
            filter_row,
            textvariable=self.recent_count_var,
        ).pack(side="right", padx=(12, 0))

        self.recent_tree = ttk.Treeview(
            recent,
            columns=("path", "modified"),
            show="tree headings",
            height=6,
            selectmode="browse",
        )
        self.recent_tree.heading("#0", text="Project")
        self.recent_tree.heading("path", text="Path")
        self.recent_tree.heading("modified", text="Modified")
        self.recent_tree.column("#0", width=220, minwidth=140)
        self.recent_tree.column("path", width=520, minwidth=240)
        self.recent_tree.column("modified", width=150, minwidth=110, stretch=False)
        self.recent_table = TreeviewTableBehavior(
            self.recent_tree,
            sortable_columns=("#0", "path", "modified"),
            copy_columns=("#0", "path", "modified"),
        )
        self.recent_table.sort_column = "modified"
        self.recent_table.sort_descending = True
        scroll = ttk.Scrollbar(recent, orient="vertical", command=self.recent_tree.yview)
        self.recent_tree.configure(yscrollcommand=scroll.set)
        self.recent_tree.grid(row=1, column=0, sticky="nsew")
        scroll.grid(row=1, column=1, sticky="ns")
        self.recent_tree.bind("<Double-1>", self._open_selected_recent)
        self.recent_tree.bind("<Return>", self._open_selected_recent)
        self.recent_tree.bind("<Delete>", self._forget_selected_recent)
        self.recent_tree.bind("<Button-3>", self._show_recent_context_menu)

        footer = ttk.Frame(recent)
        footer.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.recent_hint = ttk.Label(footer, text="No recent projects in this session.")
        self.recent_hint.pack(side="left")
        self.remove_recent_button = ttk.Button(
            footer,
            text="Remove from Recent",
            command=self._forget_selected_recent,
            state="normal" if self._on_forget_recent is not None else "disabled",
        )
        self.remove_recent_button.pack(side="right", padx=(6, 0))
        ttk.Button(
            footer,
            text="Open Selected",
            command=self._open_selected_recent,
        ).pack(side="right")

        examples = ttk.LabelFrame(self, text="Example Projects", padding=12)
        examples.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="nsew",
            pady=(18, 0),
        )
        ttk.Label(
            examples,
            text="Bundled CleanroomX Demo",
            style="CX.Section.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            examples,
            text=(
                "Open the packaged demo project to explore the project browser, "
                "2D/3D workspace, analyses, diagnostics, verification, and evidence."
            ),
            wraplength=760,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Button(examples, text="Open Demo", command=on_open_demo).grid(
            row=0, column=1, rowspan=2, sticky="e", padx=(18, 0)
        )
        examples.columnconfigure(0, weight=1)

        self.recent_search_var.trace_add("write", lambda *_: self._populate_recent())

    def set_recent_projects(self, records: list[dict[str, str]]) -> None:
        self._recent_records = []
        for record in records:
            path = str(record.get("path") or "").strip()
            if not path:
                continue
            self._recent_records.append(
                {
                    "name": str(record.get("name") or path),
                    "path": path,
                    "modified": str(record.get("modified") or "—"),
                }
            )
        self._populate_recent()

    def _filtered_recent_records(self) -> list[dict[str, str]]:
        query = self.recent_search_var.get().strip().casefold()
        if not query:
            return list(self._recent_records)
        return [
            record
            for record in self._recent_records
            if query
            in " ".join(
                (
                    record["name"],
                    record["path"],
                    record["modified"],
                )
            ).casefold()
        ]

    def _populate_recent(self) -> None:
        selection = self.recent_tree.selection()
        selected_path = (
            self._recent_paths.get(selection[0])
            if selection
            else None
        )
        for item in self.recent_tree.get_children():
            self.recent_tree.delete(item)
        self._recent_paths.clear()

        visible = self._filtered_recent_records()
        for index, record in enumerate(visible):
            iid = f"recent-{index}"
            self._recent_paths[iid] = record["path"]
            self.recent_tree.insert(
                "",
                "end",
                iid=iid,
                text=record["name"],
                values=(record["path"], record["modified"]),
            )

        self.recent_table.reapply_sort()
        total = len(self._recent_records)
        self.recent_count_var.set(f"{len(visible)} of {total} recent projects")
        self.recent_hint.configure(
            text=(
                "No recent projects in this session."
                if total == 0
                else (
                    "No recent projects match the search."
                    if not visible
                    else f"{total} recent project{'s' if total != 1 else ''}."
                )
            )
        )

        target = None
        if selected_path is not None:
            for iid, path in self._recent_paths.items():
                if path == selected_path:
                    target = iid
                    break
        children = self.recent_tree.get_children()
        if target is None and children:
            target = children[0]
        if target is not None:
            self.recent_tree.selection_set(target)
            self.recent_tree.focus(target)
            self.recent_tree.see(target)

    def _open_selected_recent(self, _event=None):
        selection = self.recent_tree.selection()
        if not selection:
            return "break"
        path = self._recent_paths.get(selection[0])
        if path:
            self._on_open_recent(path)
        return "break"

    def _forget_selected_recent(self, _event=None):
        if self._on_forget_recent is None:
            return "break"
        selection = self.recent_tree.selection()
        if not selection:
            return "break"
        path = self._recent_paths.get(selection[0])
        if path:
            self._on_forget_recent(path)
        return "break"

    def _show_recent_context_menu(self, event: tk.Event):
        iid = self.recent_tree.identify_row(event.y)
        if iid:
            self.recent_tree.selection_set(iid)
            self.recent_tree.focus(iid)
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(
            label="Open Project",
            command=self._open_selected_recent,
        )
        menu.add_command(
            label="Remove from Recent",
            command=self._forget_selected_recent,
            state="normal" if self._on_forget_recent is not None else "disabled",
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"
