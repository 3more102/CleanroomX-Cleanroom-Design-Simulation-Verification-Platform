from __future__ import annotations

from collections.abc import Callable
import tkinter as tk
from tkinter import ttk


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
    ):
        super().__init__(master, padding=(30, 24))
        self._on_open_recent = on_open_recent
        self._recent_paths: dict[str, str] = {}

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(3, weight=1)

        brand = ttk.Frame(self, style="CX.Hero.TFrame")
        brand.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(4, 20))
        ttk.Label(
            brand,
            text="ENGINEERING WORKSTATION",
            style="CX.InfoBadge.TLabel",
        ).pack(anchor="w", pady=(0, 8))
        ttk.Label(
            brand,
            text="CleanroomX",
            style="CX.HeroBrand.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            brand,
            text="Engineering Design • Simulation • Verification",
            style="CX.HeroTitle.TLabel",
        ).pack(anchor="w", pady=(4, 0))
        ttk.Label(
            brand,
            text=(
                "Project-native cleanroom engineering with linked 2D/3D design, "
                "analysis, deterministic verification, IFC semantics, diagnostics, "
                "ProofGraph, and evidence traceability."
            ),
            style="CX.HeroMuted.TLabel",
            wraplength=960,
            justify="left",
        ).pack(anchor="w", pady=(8, 0))

        actions = ttk.LabelFrame(
            self,
            text="PROJECT CONTROL",
            padding=18,
            style="CX.Card.TLabelframe",
        )
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
            style="CX.Secondary.TButton",
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

        capabilities = ttk.LabelFrame(
            self,
            text="ENGINEERING SYSTEMS",
            padding=18,
            style="CX.Card.TLabelframe",
        )
        capabilities.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        capability_rows = (
            ("●", "2D / 3D / Split engineering views", "CX.InfoCard.TLabel"),
            ("●", "Project Navigator + contextual properties", "CX.InfoCard.TLabel"),
            ("●", "Analysis + verification overlays", "CX.SuccessCard.TLabel"),
            ("●", "IDE-style deterministic diagnostics", "CX.WarningCard.TLabel"),
            ("●", "ProofGraph + evidence traceability", "CX.InfoCard.TLabel"),
            ("●", "IFC semantic import / re-import review", "CX.SuccessCard.TLabel"),
        )
        for marker, text, marker_style in capability_rows:
            row = ttk.Frame(capabilities, style="CX.Card.TFrame")
            row.pack(fill="x", anchor="w", pady=2)
            ttk.Label(row, text=marker, style=marker_style).pack(side="left")
            ttk.Label(
                row,
                text=text,
                style="CX.Card.TLabel",
            ).pack(side="left", padx=(7, 0))

        recent = ttk.LabelFrame(
            self,
            text="RECENT PROJECTS",
            padding=12,
            style="CX.Card.TLabelframe",
        )
        recent.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="nsew",
            pady=(18, 0),
        )
        recent.columnconfigure(0, weight=1)
        recent.rowconfigure(0, weight=1)
        self.recent_tree = ttk.Treeview(
            recent,
            columns=("path", "modified"),
            show="tree headings",
            height=6,
            selectmode="browse",
            style="CX.Card.Treeview",
        )
        self.recent_tree.heading("#0", text="Project")
        self.recent_tree.heading("path", text="Path")
        self.recent_tree.heading("modified", text="Modified")
        self.recent_tree.column("#0", width=220, minwidth=140)
        self.recent_tree.column("path", width=520, minwidth=240)
        self.recent_tree.column("modified", width=150, minwidth=110, stretch=False)
        scroll = ttk.Scrollbar(recent, orient="vertical", command=self.recent_tree.yview)
        self.recent_tree.configure(yscrollcommand=scroll.set)
        self.recent_tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.recent_tree.bind("<Double-1>", self._open_selected_recent)
        self.recent_tree.bind("<Return>", self._open_selected_recent)
        footer = ttk.Frame(recent, style="CX.Card.TFrame")
        footer.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(9, 0))
        self.recent_hint = ttk.Label(
            footer,
            text="No recent projects in this session.",
            style="CX.CardMuted.TLabel",
        )
        self.recent_hint.pack(side="left")
        ttk.Button(
            footer,
            text="Open Selected",
            style="CX.Compact.TButton",
            command=self._open_selected_recent,
        ).pack(side="right")

        examples = ttk.LabelFrame(
            self,
            text="DEMO & VALIDATION",
            padding=14,
            style="CX.Card.TLabelframe",
        )
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
            style="CX.CardTitle.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            examples,
            text=(
                "Open the packaged demo project to explore the project browser, "
                "2D/3D workspace, analyses, diagnostics, verification, and evidence."
            ),
            style="CX.CardMuted.TLabel",
            wraplength=760,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Button(
            examples,
            text="Launch Demo Workspace",
            style="CX.Secondary.TButton",
            command=on_open_demo,
        ).grid(row=0, column=1, rowspan=2, sticky="e", padx=(18, 0))
        examples.columnconfigure(0, weight=1)

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
                "No recent projects in this session."
                if count == 0
                else f"{count} recent project{'s' if count != 1 else ''}."
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
