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
        super().__init__(master, padding=(34, 28), style="CX.StartCenter.TFrame")
        self._on_open_recent = on_open_recent
        self._recent_paths: dict[str, str] = {}

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(3, weight=1)

        brand = ttk.Frame(self, style="CX.Hero.TFrame")
        brand.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(4, 22))
        ttk.Label(
            brand,
            text="ENGINEERING WORKSTATION",
            style="CX.HeroEyebrow.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            brand,
            text="CleanroomX",
            style="CX.HeroTitle.TLabel",
        ).pack(anchor="w", pady=(3, 0))
        ttk.Label(
            brand,
            text="Design  •  Simulation  •  Verification  •  Evidence",
            style="CX.HeroSubtitle.TLabel",
        ).pack(anchor="w", pady=(4, 0))
        ttk.Separator(brand, orient="horizontal").pack(fill="x", pady=(12, 10))
        ttk.Label(
            brand,
            text=(
                "Project-native cleanroom engineering with linked 2D/3D design, "
                "analysis, deterministic verification, IFC semantics, diagnostics, "
                "ProofGraph, and evidence traceability."
            ),
            style="CX.HeroSubtitle.TLabel",
            wraplength=900,
            justify="left",
        ).pack(anchor="w")
        chips = ttk.Frame(brand, style="CX.Surface.TFrame")
        chips.pack(fill="x", pady=(12, 0))
        for label in ("IFC / BIM", "2D + 3D", "Diagnostics", "ProofGraph", "Traceability"):
            ttk.Label(
                chips,
                text=label.upper(),
                style="CX.AccentChip.TLabel",
            ).pack(side="left", padx=(0, 7))

        actions = ttk.LabelFrame(
            self,
            text="START / PROJECT",
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

        capabilities = ttk.LabelFrame(
            self,
            text="ENGINEERING WORKSPACE",
            padding=18,
            style="CX.Card.TLabelframe",
        )
        capabilities.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        capability_rows = (
            ("DESIGN", "2D / 3D / Split engineering views", "CX.Info.Panel.TLabel"),
            ("MODEL", "Project Navigator + contextual properties", "CX.Info.Panel.TLabel"),
            ("VERIFY", "Analysis + verification overlays", "CX.Success.Panel.TLabel"),
            ("DIAG", "IDE-style deterministic diagnostics", "CX.Warning.Panel.TLabel"),
            ("EVIDENCE", "ProofGraph + evidence traceability", "CX.Success.Panel.TLabel"),
            ("BIM", "IFC semantic import / re-import review", "CX.Info.Panel.TLabel"),
        )
        for code, description, style in capability_rows:
            row = ttk.Frame(capabilities, style="CX.Panel.TFrame")
            row.pack(fill="x", pady=2)
            ttk.Label(
                row,
                text=f"{code:<8}",
                style=style,
            ).pack(side="left")
            ttk.Label(
                row,
                text=description,
                style="CX.PanelText.TLabel",
            ).pack(side="left", padx=(8, 0))

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
        footer = ttk.Frame(recent, style="CX.Panel.TFrame")
        footer.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.recent_hint = ttk.Label(\n            footer,\n            text="No recent projects in this session.",\n            style="CX.PanelMuted.TLabel",\n        )
        self.recent_hint.pack(side="left")
        ttk.Button(
            footer,
            text="Open Selected",
            command=self._open_selected_recent,
        ).pack(side="right")

        examples = ttk.LabelFrame(
            self,
            text="EXAMPLE PROJECTS",
            padding=12,
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
            style="CX.PanelSection.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            examples,
            text=(
                "Open the packaged demo project to explore the project browser, "
                "2D/3D workspace, analyses, diagnostics, verification, and evidence."
            ),
            style="CX.PanelMuted.TLabel",
            wraplength=760,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Button(examples, text="Open Demo", command=on_open_demo).grid(
            row=0, column=1, rowspan=2, sticky="e", padx=(18, 0)
        )
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
