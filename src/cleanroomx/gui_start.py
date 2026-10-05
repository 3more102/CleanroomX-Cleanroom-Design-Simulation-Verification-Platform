from __future__ import annotations

from collections.abc import Callable
import tkinter as tk
from tkinter import ttk


class StartCenter(ttk.Frame):
    """Industrial zero-state surface; project mutations stay in the app layer."""

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
        super().__init__(master, padding=(22, 18))
        self._on_open_recent = on_open_recent
        self._on_forget_recent = on_forget_recent
        self._recent_paths: dict[str, str] = {}
        self._recent_records: list[dict[str, str]] = []
        self.recent_search_var = tk.StringVar()
        self.recent_count_var = tk.StringVar(value="0 of 0 recent projects")

        self.columnconfigure(0, weight=3)
        self.columnconfigure(1, weight=2)
        self.rowconfigure(3, weight=1)

        header = ttk.Frame(self, style="CX.PanelHeader.TFrame", padding=(14, 11))
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header,
            text="CLEANROOMX",
            style="CX.PanelHeader.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="ENGINEERING WORKSTATION",
            style="CX.Status.Info.TLabel",
        ).grid(row=0, column=1, sticky="e")
        ttk.Label(
            header,
            text="Design · Simulation · Verification · Traceability",
            style="CX.PanelHeader.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(
            header,
            text="Ctrl+Shift+P  Commands",
            style="CX.PanelHeader.TLabel",
        ).grid(row=1, column=1, sticky="e", pady=(4, 0))

        operations = ttk.Frame(self, style="CX.Panel.TFrame", padding=(14, 12))
        operations.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        operations.columnconfigure(0, weight=1)
        operations.columnconfigure(1, weight=1)
        ttk.Label(
            operations,
            text="PROJECT OPERATIONS",
            style="CX.PanelSection.TLabel",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Button(
            operations,
            text="New Project",
            style="CX.Primary.TButton",
            command=on_new,
        ).grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=3)
        ttk.Button(
            operations,
            text="Open Project",
            style="CX.Primary.TButton",
            command=on_open,
        ).grid(row=1, column=1, sticky="ew", padx=(4, 0), pady=3)
        ttk.Button(
            operations,
            text="Import IFC",
            style="CX.Compact.TButton",
            command=on_import_ifc,
        ).grid(row=2, column=0, sticky="ew", padx=(0, 4), pady=3)
        ttk.Button(
            operations,
            text="Open Example Project",
            style="CX.Compact.TButton",
            command=on_open_demo,
        ).grid(row=2, column=1, sticky="ew", padx=(4, 0), pady=3)
        ttk.Label(
            operations,
            text=(
                "Start with project-native geometry or import IFC semantics, then keep "
                "design, analysis, diagnostics, verification, and evidence linked."
            ),
            style="CX.PanelMuted.TLabel",
            wraplength=650,
            justify="left",
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))

        workflow = ttk.Frame(self, style="CX.SubtlePanel.TFrame", padding=(14, 12))
        workflow.grid(row=1, column=1, sticky="nsew", padx=(6, 0))
        workflow.columnconfigure(0, weight=1)
        ttk.Label(
            workflow,
            text="ENGINEERING FLOW",
            style="CX.SurfaceSection.TLabel",
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))
        stages = (
            ("01  DESIGN", "2D / 3D cleanroom geometry, rooms, devices, IFC context"),
            ("02  ANALYZE", "Airflow, ACH, pressure and configured engineering solvers"),
            ("03  VERIFY", "Diagnostics, rule checks and verification currency"),
            ("04  TRACE", "ProofGraph, evidence provenance and engineering dossier"),
        )
        for row, (title, detail) in enumerate(stages, start=1):
            stage = ttk.Frame(workflow, style="CX.Card.TFrame", padding=(8, 6))
            stage.grid(row=row, column=0, sticky="ew", pady=2)
            stage.columnconfigure(1, weight=1)
            ttk.Label(stage, text=title, style="CX.PanelSecondary.TLabel").grid(
                row=0, column=0, sticky="nw", padx=(0, 8)
            )
            ttk.Label(
                stage,
                text=detail,
                style="CX.PanelMuted.TLabel",
                wraplength=420,
                justify="left",
            ).grid(row=0, column=1, sticky="w")

        recent = ttk.Frame(self, style="CX.Panel.TFrame", padding=(12, 10))
        recent.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="nsew",
            pady=(12, 0),
        )
        recent.columnconfigure(0, weight=1)
        recent.rowconfigure(3, weight=1)
        recent_header = ttk.Frame(recent, style="CX.PanelHeader.TFrame")
        recent_header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ttk.Label(
            recent_header,
            text="RECENT PROJECTS",
            style="CX.PanelHeader.TLabel",
        ).pack(side="left")
        self.recent_hint = ttk.Label(
            recent_header,
            text="No recent projects in this session.",
            style="CX.PanelHeader.TLabel",
        )
        self.recent_hint.pack(side="right")

        ttk.Label(
            recent,
            text="Double-click a project to return to active engineering work.",
            style="CX.PanelMuted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(0, 5))
        ttk.Button(
            recent,
            text="Open Selected",
            style="CX.Compact.TButton",
            command=self._open_selected_recent,
        ).grid(row=1, column=1, sticky="e", pady=(0, 5))

        filter_row = ttk.Frame(recent)
        filter_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ttk.Label(filter_row, text="Search").pack(side="left")
        self.recent_search_entry = ttk.Entry(
            filter_row,
            textvariable=self.recent_search_var,
            width=34,
        )
        self.recent_search_entry.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(4, 8),
        )
        ttk.Button(
            filter_row,
            text="Clear",
            style="CX.Compact.TButton",
            command=lambda: self.recent_search_var.set(""),
        ).pack(side="left")
        ttk.Label(
            filter_row,
            textvariable=self.recent_count_var,
            style="CX.Muted.TLabel",
        ).pack(side="right", padx=(12, 0))

        self.recent_tree = ttk.Treeview(
            recent,
            columns=("path", "modified"),
            show="tree headings",
            height=6,
            selectmode="browse",
        )
        self.recent_tree.heading("#0", text="Project")
        self.recent_tree.heading("path", text="Location")
        self.recent_tree.heading("modified", text="Modified")
        self.recent_tree.column("#0", width=230, minwidth=140)
        self.recent_tree.column("path", width=560, minwidth=260)
        self.recent_tree.column("modified", width=150, minwidth=110, stretch=False)
        scroll = ttk.Scrollbar(recent, orient="vertical", command=self.recent_tree.yview)
        self.recent_tree.configure(yscrollcommand=scroll.set)
        self.recent_tree.grid(row=3, column=0, sticky="nsew")
        scroll.grid(row=3, column=1, sticky="ns")
        self.recent_tree.bind("<Double-1>", self._open_selected_recent)
        self.recent_tree.bind("<Return>", self._open_selected_recent)
        self.recent_tree.bind("<Delete>", self._forget_selected_recent)
        self.recent_tree.bind("<Button-3>", self._show_recent_context_menu)

        recent_actions = ttk.Frame(recent)
        recent_actions.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.remove_recent_button = ttk.Button(
            recent_actions,
            text="Remove from Recent",
            style="CX.Compact.TButton",
            command=self._forget_selected_recent,
            state="normal" if self._on_forget_recent is not None else "disabled",
        )
        self.remove_recent_button.pack(side="right")

        self.recent_search_var.trace_add(
            "write",
            lambda *_: self._populate_recent(),
        )

        example = ttk.Frame(self, style="CX.SubtlePanel.TFrame", padding=(12, 9))
        example.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="new",
            pady=(12, 0),
        )
        example.columnconfigure(0, weight=1)
        ttk.Label(
            example,
            text="BUNDLED ENGINEERING DEMO",
            style="CX.SurfaceSection.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            example,
            text=(
                "Explore the navigator, spatial workspace, analysis overlays, "
                "diagnostics, verification, ProofGraph, and evidence traceability."
            ),
            style="CX.SurfaceMuted.TLabel",
            wraplength=820,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))
        ttk.Button(
            example,
            text="Open Demo",
            style="CX.Primary.TButton",
            command=on_open_demo,
        ).grid(row=0, column=1, rowspan=2, sticky="e", padx=(18, 0))

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

        total = len(self._recent_records)
        self.recent_count_var.set(
            f"{len(visible)} of {total} recent projects"
        )
        self.recent_hint.configure(
            text=(
                "No recent projects in this session."
                if total == 0
                else (
                    "No recent projects match the search."
                    if not visible
                    else f"{total} recent project{'s' if total != 1 else ''}"
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
