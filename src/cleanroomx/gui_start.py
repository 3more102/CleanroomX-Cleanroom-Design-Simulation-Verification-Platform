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
        super().__init__(master, padding=(34, 28))
        self._on_open_recent = on_open_recent
        self._recent_paths: dict[str, str] = {}

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(4, weight=1)

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

        self.health_project_var = tk.StringVar(value="Unsaved project")
        self.health_rooms_var = tk.StringVar(value="0")
        self.health_analyses_var = tk.StringVar(value="0")
        self.health_devices_var = tk.StringVar(value="0")
        self.health_problems_var = tk.StringVar(value="—")
        self.health_verify_var = tk.StringVar(value="VERIFY —")
        self.health_evidence_var = tk.StringVar(value="EVIDENCE 0")

        health = ttk.Frame(self, style="CX.Panel.TFrame", padding=(14, 11))
        health.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 16))
        ttk.Label(health, text="PROJECT HEALTH", style="CX.PanelTitle.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 18)
        )
        ttk.Label(
            health,
            textvariable=self.health_project_var,
            style="CX.Panel.TLabel",
        ).grid(row=1, column=0, sticky="w", padx=(0, 18), pady=(2, 0))

        metric_specs = (
            ("ROOMS", self.health_rooms_var),
            ("ANALYSES", self.health_analyses_var),
            ("DEVICES", self.health_devices_var),
        )
        for column, (label, variable) in enumerate(metric_specs, start=1):
            ttk.Label(
                health,
                textvariable=variable,
                style="CX.Metric.TLabel",
                anchor="center",
            ).grid(row=0, column=column, sticky="ew", padx=8)
            ttk.Label(
                health,
                text=label,
                style="CX.Panel.TLabel",
                anchor="center",
            ).grid(row=1, column=column, sticky="ew", padx=8)
            health.columnconfigure(column, weight=1)

        self.health_problems_label = ttk.Label(
            health,
            textvariable=self.health_problems_var,
            style="CX.MutedBadge.TLabel",
        )
        self.health_problems_label.grid(row=0, column=4, rowspan=2, padx=6)
        self.health_verify_label = ttk.Label(
            health,
            textvariable=self.health_verify_var,
            style="CX.MutedBadge.TLabel",
        )
        self.health_verify_label.grid(row=0, column=5, rowspan=2, padx=6)
        self.health_evidence_label = ttk.Label(
            health,
            textvariable=self.health_evidence_var,
            style="CX.MutedBadge.TLabel",
        )
        self.health_evidence_label.grid(row=0, column=6, rowspan=2, padx=6)
        health.columnconfigure(0, weight=2)

        actions = ttk.LabelFrame(self, text="Start", padding=18)
        actions.grid(row=2, column=0, sticky="nsew", padx=(0, 10))
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
        capabilities.grid(row=2, column=1, sticky="nsew", padx=(10, 0))
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
            row=4,
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
        footer = ttk.Frame(recent)
        footer.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.recent_hint = ttk.Label(footer, text="No recent projects in this session.")
        self.recent_hint.pack(side="left")
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

    def set_project_health(self, snapshot: dict[str, object]) -> None:
        """Update the start dashboard from already-computed project state."""
        from .gui_theme import status_style_name

        self.health_project_var.set(
            str(snapshot.get("project_name") or "Unsaved project")
        )
        self.health_rooms_var.set(str(snapshot.get("room_count", 0)))
        self.health_analyses_var.set(str(snapshot.get("analysis_count", 0)))
        self.health_devices_var.set(str(snapshot.get("device_count", 0)))

        errors = int(snapshot.get("error_count", 0) or 0)
        warnings = int(snapshot.get("warning_count", 0) or 0)
        problems = errors + warnings
        self.health_problems_var.set(f"PROBLEMS {problems}")
        self.health_problems_label.configure(
            style=status_style_name(
                "FAIL" if errors else ("WARNING" if warnings else "PASS")
            )
        )

        verify_text = str(snapshot.get("verification") or "VERIFY —")
        self.health_verify_var.set(verify_text)
        verify_status = "VERIFIED" if "/" in verify_text else "NOT CHECKED"
        self.health_verify_label.configure(style=status_style_name(verify_status))

        evidence_text = str(snapshot.get("evidence") or "EVIDENCE 0")
        self.health_evidence_var.set(evidence_text)
        evidence_count = 0
        try:
            evidence_count = int(evidence_text.rsplit(" ", 1)[-1])
        except (TypeError, ValueError):
            evidence_count = 0
        self.health_evidence_label.configure(
            style=status_style_name("VERIFIED" if evidence_count else "NOT CHECKED")
        )

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
