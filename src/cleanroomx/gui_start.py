from __future__ import annotations

from collections.abc import Callable
import tkinter as tk
from tkinter import ttk


class StartCenter(ttk.Frame):
    """Dense project-control surface for opening or creating engineering work."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_new: Callable[[], None],
        on_open: Callable[[], None],
        on_import_ifc: Callable[[], None],
        on_open_demo: Callable[[], None],
        on_open_recent: Callable[[str], None],
    ):
        super().__init__(master, padding=(18, 15))
        self._on_open_recent = on_open_recent
        self._recent_paths: dict[str, str] = {}

        self.columnconfigure(0, weight=3)
        self.columnconfigure(1, weight=2)
        self.rowconfigure(2, weight=1)

        header = ttk.Frame(self, style="CX.Surface.TFrame", padding=(12, 9))
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header,
            text="START / PROJECT CONTROL",
            style="CX.Section.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="CleanroomX Engineering Workstation",
            style="CX.ViewTitle.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        ttk.Label(
            header,
            text=(
                "Open a project, import IFC semantics, or start a validated "
                "cleanroom engineering workflow."
            ),
            style="CX.Secondary.TLabel",
        ).grid(row=2, column=0, sticky="w", pady=(2, 0))
        ttk.Label(
            header,
            text="MODEL → SOLVER → VERIFICATION → PROOFGRAPH → EVIDENCE",
            style="CX.Status.Verified.TLabel",
        ).grid(row=0, column=1, rowspan=2, sticky="e", padx=(12, 0))

        actions = ttk.Frame(self, style="CX.Raised.TFrame", padding=(12, 10))
        actions.grid(row=1, column=0, sticky="nsew", padx=(0, 4), pady=(0, 8))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        ttk.Label(actions, text="PROJECT", style="CX.Section.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 5)
        )
        ttk.Button(
            actions,
            text="New Project",
            style="CX.Primary.TButton",
            command=on_new,
        ).grid(row=1, column=0, sticky="ew", padx=(0, 3), pady=2)
        ttk.Button(
            actions,
            text="Open Project…",
            style="CX.Primary.TButton",
            command=on_open,
        ).grid(row=1, column=1, sticky="ew", padx=(3, 0), pady=2)
        ttk.Button(
            actions,
            text="Import IFC Spatial Layout…",
            style="CX.Compact.TButton",
            command=on_import_ifc,
        ).grid(row=2, column=0, sticky="ew", padx=(0, 3), pady=2)
        ttk.Button(
            actions,
            text="Open Engineering Demo",
            style="CX.Compact.TButton",
            command=on_open_demo,
        ).grid(row=2, column=1, sticky="ew", padx=(3, 0), pady=2)

        capabilities = ttk.Frame(
            self,
            style="CX.Raised.TFrame",
            padding=(12, 10),
        )
        capabilities.grid(row=1, column=1, sticky="nsew", padx=(4, 0), pady=(0, 8))
        ttk.Label(
            capabilities,
            text="WORKSTATION CAPABILITIES",
            style="CX.Section.TLabel",
        ).pack(anchor="w", pady=(0, 5))
        for label, detail in (
            ("DESIGN", "Linked 2D / 3D cleanroom layout and engineering overlays"),
            ("ANALYSIS", "HVAC, airflow, pressure, uncertainty, and solver workflows"),
            ("VERIFY", "Deterministic diagnostics and project requirements checks"),
            ("TRACE", "ProofGraph, provenance, evidence, and report handoff"),
        ):
            row = ttk.Frame(capabilities)
            row.pack(fill="x", pady=2)
            ttk.Label(
                row,
                text=label,
                style="CX.Status.Running.TLabel",
                width=9,
                anchor="center",
            ).pack(side="left", padx=(0, 7))
            ttk.Label(
                row,
                text=detail,
                style="CX.Secondary.TLabel",
                wraplength=380,
                justify="left",
            ).pack(side="left", fill="x", expand=True)

        recent = ttk.Frame(self, style="CX.Panel.TFrame", padding=(10, 8))
        recent.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="nsew",
            pady=(0, 8),
        )
        recent.columnconfigure(0, weight=1)
        recent.rowconfigure(1, weight=1)

        recent_header = ttk.Frame(recent, style="CX.PanelHeader.TFrame")
        recent_header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        ttk.Label(
            recent_header,
            text="RECENT PROJECTS",
            style="CX.PanelHeader.TLabel",
        ).pack(side="left")
        self.recent_hint = ttk.Label(
            recent_header,
            text="No recent projects.",
            style="CX.Muted.TLabel",
        )
        self.recent_hint.pack(side="right", padx=5)

        self.recent_tree = ttk.Treeview(
            recent,
            columns=("path", "modified"),
            show="tree headings",
            height=7,
            selectmode="browse",
        )
        self.recent_tree.heading("#0", text="Project")
        self.recent_tree.heading("path", text="Location")
        self.recent_tree.heading("modified", text="Modified")
        self.recent_tree.column("#0", width=220, minwidth=140)
        self.recent_tree.column("path", width=600, minwidth=260)
        self.recent_tree.column("modified", width=160, minwidth=110, stretch=False)
        scroll = ttk.Scrollbar(recent, orient="vertical", command=self.recent_tree.yview)
        self.recent_tree.configure(yscrollcommand=scroll.set)
        self.recent_tree.grid(row=1, column=0, sticky="nsew")
        scroll.grid(row=1, column=1, sticky="ns")
        self.recent_tree.bind("<Double-1>", self._open_selected_recent)
        self.recent_tree.bind("<Return>", self._open_selected_recent)

        footer = ttk.Frame(self, style="CX.Toolbar.TFrame", padding=(8, 5))
        footer.grid(row=3, column=0, columnspan=2, sticky="ew")
        ttk.Label(
            footer,
            text="Recent project: double-click or press Enter to open",
            style="CX.Toolbar.TLabel",
        ).pack(side="left")
        ttk.Button(
            footer,
            text="Open Selected",
            style="CX.Compact.TButton",
            command=self._open_selected_recent,
        ).pack(side="right")
        ttk.Button(
            footer,
            text="Open Demo",
            style="CX.Compact.TButton",
            command=on_open_demo,
        ).pack(side="right", padx=(0, 4))

    def set_recent_projects(self, records: list[dict[str, str]]) -> None:
        for item in self.recent_tree.get_children():
            self.recent_tree.delete(item)
        self._recent_paths.clear()
        for index, record in enumerate(records):
            path = str(record.get("path") or "").strip()
            if not path:
                continue
            iid = f"recent-{index}"
            self._recent_paths[iid] = path
            self.recent_tree.insert(
                "",
                "end",
                iid=iid,
                text=str(record.get("name") or path),
                values=(path, str(record.get("modified") or "—")),
            )
        count = len(self._recent_paths)
        self.recent_hint.configure(
            text=(
                "No recent projects."
                if count == 0
                else f"{count} recent project{'s' if count != 1 else ''}"
            )
        )

    def _open_selected_recent(self, _event=None):
        selection = self.recent_tree.selection()
        if not selection:
            return "break"
        path = self._recent_paths.get(selection[0])
        if path:
            self._on_open_recent(path)
        return "break"
