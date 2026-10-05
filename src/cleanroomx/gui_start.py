from __future__ import annotations

from collections.abc import Callable
import tkinter as tk
from tkinter import ttk


class StartCenter(ttk.Frame):
    """Industrial zero-state surface; project actions remain in the app layer."""

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
        super().__init__(master, padding=(18, 16))
        self._on_open_recent = on_open_recent
        self._recent_paths: dict[str, str] = {}

        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(
            header,
            text="CLEANROOMX",
            style="CX.Brand.TLabel",
        ).pack(side="left")
        ttk.Label(
            header,
            text="INDUSTRIAL ENGINEERING WORKSTATION",
            style="CX.Muted.TLabel",
        ).pack(side="left", padx=(12, 0))
        ttk.Label(
            header,
            text="WORKSTATION READY",
            style="CX.Status.Success.TLabel",
        ).pack(side="right")

        launch = ttk.Frame(
            self,
            style="CX.Card.TFrame",
            padding=(12, 10),
        )
        launch.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        launch.columnconfigure(4, weight=1)
        ttk.Label(
            launch,
            text="PROJECT",
            style="CX.CardTitle.TLabel",
        ).grid(row=0, column=0, sticky="w", padx=(0, 10))
        ttk.Button(
            launch,
            text="New Project",
            style="CX.Primary.TButton",
            command=on_new,
        ).grid(row=0, column=1, sticky="w", padx=(0, 5))
        ttk.Button(
            launch,
            text="Open Project",
            style="CX.Primary.TButton",
            command=on_open,
        ).grid(row=0, column=2, sticky="w", padx=(0, 5))
        ttk.Button(
            launch,
            text="Import IFC…",
            style="CX.Compact.TButton",
            command=on_import_ifc,
        ).grid(row=0, column=3, sticky="w", padx=(0, 5))
        ttk.Label(
            launch,
            text=(
                "Project-native design, analysis, deterministic verification, "
                "ProofGraph traceability, and evidence handoff."
            ),
            style="CX.CardBody.TLabel",
            justify="right",
            wraplength=430,
        ).grid(row=0, column=4, sticky="e", padx=(14, 0))

        flow = ttk.Frame(
            self,
            style="CX.Card.TFrame",
            padding=(12, 9),
        )
        flow.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(
            flow,
            text="ENGINEERING FLOW",
            style="CX.CardTitle.TLabel",
        ).pack(side="left", padx=(0, 10))
        for label, domain in (
            ("01  Design", "Geometry"),
            ("02  Inputs", "HVAC"),
            ("03  Simulate", "Simulation"),
            ("04  Verify", "Verification"),
            ("05  Evidence", "Evidence"),
        ):
            ttk.Label(
                flow,
                text=label,
                style=f"CX.Domain.{domain}.TLabel",
            ).pack(side="left", padx=(0, 5))
        ttk.Label(
            flow,
            text="Requirement → Model → Solver → Verification → Evidence → Report",
            style="CX.CardTitle.TLabel",
        ).pack(side="right")

        body = ttk.Panedwindow(self, orient="horizontal")
        body.grid(row=3, column=0, sticky="nsew")

        recent_host = ttk.Frame(body, style="CX.Card.TFrame", padding=(10, 9))
        demo_host = ttk.Frame(body, style="CX.Card.TFrame", padding=(10, 9))
        body.add(recent_host, weight=4)
        body.add(demo_host, weight=2)

        recent_header = ttk.Frame(recent_host, style="CX.Card.TFrame")
        recent_header.pack(fill="x", pady=(0, 7))
        ttk.Label(
            recent_header,
            text="RECENT PROJECTS",
            style="CX.CardTitle.TLabel",
        ).pack(side="left")
        self.recent_hint = ttk.Label(
            recent_header,
            text="No recent projects in this session.",
            style="CX.CardTitle.TLabel",
        )
        self.recent_hint.pack(side="right")

        recent_table = ttk.Frame(recent_host, style="CX.Card.TFrame")
        recent_table.pack(fill="both", expand=True)
        recent_table.rowconfigure(0, weight=1)
        recent_table.columnconfigure(0, weight=1)
        self.recent_tree = ttk.Treeview(
            recent_table,
            columns=("path", "modified"),
            show="tree headings",
            height=8,
            selectmode="browse",
        )
        self.recent_tree.heading("#0", text="Project")
        self.recent_tree.heading("path", text="Location")
        self.recent_tree.heading("modified", text="Modified")
        self.recent_tree.column("#0", width=185, minwidth=120)
        self.recent_tree.column("path", width=330, minwidth=180)
        self.recent_tree.column("modified", width=130, minwidth=100, stretch=False)
        scroll = ttk.Scrollbar(
            recent_table,
            orient="vertical",
            command=self.recent_tree.yview,
        )
        self.recent_tree.configure(yscrollcommand=scroll.set)
        self.recent_tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.recent_tree.bind("<Double-1>", self._open_selected_recent)
        self.recent_tree.bind("<Return>", self._open_selected_recent)
        ttk.Button(
            recent_host,
            text="Open Selected",
            style="CX.Compact.TButton",
            command=self._open_selected_recent,
        ).pack(anchor="e", pady=(7, 0))

        ttk.Label(
            demo_host,
            text="REFERENCE WORKSPACE",
            style="CX.CardTitle.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            demo_host,
            text="Bundled CleanroomX Demo",
            style="CX.CardValue.TLabel",
        ).pack(anchor="w", pady=(7, 2))
        ttk.Label(
            demo_host,
            text=(
                "Explore linked 2D/3D design, engineering overlays, project "
                "diagnostics, verification currency, ProofGraph, and retained evidence."
            ),
            style="CX.CardBody.TLabel",
            justify="left",
            wraplength=300,
        ).pack(anchor="w", pady=(0, 10))
        ttk.Button(
            demo_host,
            text="Open Demo Project",
            style="CX.Primary.TButton",
            command=on_open_demo,
        ).pack(fill="x")
        ttk.Separator(demo_host, orient="horizontal").pack(fill="x", pady=12)
        ttk.Label(
            demo_host,
            text="WORKSPACE CAPABILITIES",
            style="CX.CardTitle.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            demo_host,
            text=(
                "• 2D / 3D / Split engineering views\n"
                "• IFC spatial import and re-import review\n"
                "• Airflow / ACH / pressure overlays\n"
                "• DRC-style diagnostics and navigation\n"
                "• Verification and evidence traceability"
            ),
            style="CX.CardBody.TLabel",
            justify="left",
        ).pack(anchor="w", pady=(6, 0))

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
