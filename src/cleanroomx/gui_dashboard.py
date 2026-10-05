from __future__ import annotations

from typing import Any, Callable

import tkinter as tk
from tkinter import ttk


class ProjectDashboard(ttk.Frame):
    """Read-only engineering health dashboard driven by canonical app projections."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_design: Callable[[], None],
        on_problems: Callable[[], None],
        on_verify: Callable[[], None],
        on_proofgraph: Callable[[], None],
    ) -> None:
        super().__init__(master, padding=(14, 12))
        self._on_design = on_design
        self._on_problems = on_problems
        self._on_verify = on_verify
        self._on_proofgraph = on_proofgraph

        self.project_var = tk.StringVar(value="Unsaved project")
        self.location_var = tk.StringVar(value="Unsaved")
        self.state_var = tk.StringVar(value="PROJECT READY")
        self.summary_var = tk.StringVar(value="Engineering status not evaluated")
        self.rooms_var = tk.StringVar(value="0")
        self.devices_var = tk.StringVar(value="0")
        self.analyses_var = tk.StringVar(value="0")
        self.evidence_var = tk.StringVar(value="0")
        self.verification_var = tk.StringVar(value="0 / 0 current")
        self.diagnostics_var = tk.StringVar(value="Not evaluated")
        self.last_run_var = tk.StringVar(value="No analysis run in this session")
        self._health_rows: list[str] = []
        self._build()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        header = ttk.Frame(self, style="CX.Surface.TFrame", padding=(12, 9))
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header,
            text="ENGINEERING DASHBOARD",
            style="CX.Section.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            textvariable=self.project_var,
            style="CX.ViewTitle.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        ttk.Label(
            header,
            textvariable=self.location_var,
            style="CX.Muted.TLabel",
        ).grid(row=2, column=0, sticky="w", pady=(1, 0))
        self.state_badge = ttk.Label(
            header,
            textvariable=self.state_var,
            style="CX.Status.Unknown.TLabel",
        )
        self.state_badge.grid(row=0, column=1, rowspan=2, sticky="e", padx=(12, 0))
        ttk.Label(
            header,
            textvariable=self.summary_var,
            style="CX.Secondary.TLabel",
        ).grid(row=2, column=1, sticky="e", padx=(12, 0))

        metrics = ttk.Frame(self)
        metrics.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        for index in range(4):
            metrics.columnconfigure(index, weight=1)

        self._metric(
            metrics, 0, "ROOMS", self.rooms_var, "Defined spatial rooms"
        )
        self._metric(
            metrics, 1, "DEVICES", self.devices_var, "Openings / HVAC / equipment"
        )
        self._metric(
            metrics, 2, "ANALYSES", self.analyses_var, "Configured engineering analyses"
        )
        self._metric(
            metrics, 3, "EVIDENCE", self.evidence_var, "Persisted verification records"
        )

        actionbar = ttk.Frame(self, style="CX.Toolbar.TFrame", padding=(8, 5))
        actionbar.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(
            actionbar,
            text="QUICK ENGINEERING ACTIONS",
            style="CX.Toolbar.TLabel",
        ).pack(side="left", padx=(0, 8))
        ttk.Button(
            actionbar,
            text="Design",
            style="CX.Compact.TButton",
            command=self._on_design,
        ).pack(side="left", padx=2)
        ttk.Button(
            actionbar,
            text="Problems",
            style="CX.Compact.TButton",
            command=self._on_problems,
        ).pack(side="left", padx=2)
        ttk.Button(
            actionbar,
            text="Save & Verify",
            style="CX.Primary.TButton",
            command=self._on_verify,
        ).pack(side="left", padx=2)
        ttk.Button(
            actionbar,
            text="ProofGraph",
            style="CX.Compact.TButton",
            command=self._on_proofgraph,
        ).pack(side="left", padx=2)

        body = ttk.Panedwindow(self, orient="horizontal")
        body.grid(row=3, column=0, sticky="nsew")

        health = ttk.Frame(body, padding=(0, 0, 6, 0))
        activity = ttk.Frame(body, padding=(6, 0, 0, 0))
        body.add(health, weight=3)
        body.add(activity, weight=2)

        health_header = ttk.Frame(health, style="CX.PanelHeader.TFrame")
        health_header.pack(fill="x")
        ttk.Label(
            health_header,
            text="PROJECT HEALTH",
            style="CX.PanelHeader.TLabel",
        ).pack(side="left")
        self.health_tree = ttk.Treeview(
            health,
            columns=("status", "value", "detail"),
            show="headings",
            height=11,
            selectmode="browse",
        )
        for column, heading, width, stretch in (
            ("status", "Status", 90, False),
            ("value", "Engineering value", 160, False),
            ("detail", "Details", 420, True),
        ):
            self.health_tree.heading(column, text=heading)
            self.health_tree.column(
                column,
                width=width,
                minwidth=70,
                stretch=stretch,
            )
        self.health_tree.pack(fill="both", expand=True, pady=(5, 0))

        activity_header = ttk.Frame(activity, style="CX.PanelHeader.TFrame")
        activity_header.pack(fill="x")
        ttk.Label(
            activity_header,
            text="SESSION / TRACEABILITY",
            style="CX.PanelHeader.TLabel",
        ).pack(side="left")
        self.activity_text = tk.Text(
            activity,
            wrap="word",
            height=12,
            state="disabled",
            borderwidth=0,
            padx=8,
            pady=8,
        )
        self.activity_text.pack(fill="both", expand=True, pady=(5, 0))

    @staticmethod
    def _metric(
        master: ttk.Frame,
        column: int,
        title: str,
        variable: tk.StringVar,
        subtitle: str,
    ) -> None:
        card = ttk.Frame(master, style="CX.Raised.TFrame", padding=(10, 8))
        card.grid(
            row=0,
            column=column,
            sticky="nsew",
            padx=(0 if column == 0 else 3, 0 if column == 3 else 3),
        )
        ttk.Label(card, text=title, style="CX.Section.TLabel").pack(anchor="w")
        ttk.Label(card, textvariable=variable, style="CX.Metric.TLabel").pack(
            anchor="w", pady=(2, 0)
        )
        ttk.Label(
            card,
            text=subtitle,
            style="CX.Muted.TLabel",
        ).pack(anchor="w", pady=(1, 0))

    def set_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Render a pre-computed read-only project health snapshot."""
        self.project_var.set(str(snapshot.get("project_name") or "Untitled project"))
        self.location_var.set(str(snapshot.get("location") or "Unsaved project"))
        self.rooms_var.set(str(snapshot.get("room_count", 0)))
        self.devices_var.set(str(snapshot.get("device_count", 0)))
        self.analyses_var.set(str(snapshot.get("analysis_count", 0)))
        self.evidence_var.set(str(snapshot.get("evidence_count", 0)))

        error_count = int(snapshot.get("error_count", 0) or 0)
        warning_count = int(snapshot.get("warning_count", 0) or 0)
        diagnostic_status = str(snapshot.get("diagnostic_status") or "unknown").upper()
        self.diagnostics_var.set(
            f"{diagnostic_status} · {error_count} errors · {warning_count} warnings"
        )

        configured = int(snapshot.get("verification_configured", 0) or 0)
        current = int(snapshot.get("verification_current", 0) or 0)
        stale = int(snapshot.get("verification_stale", 0) or 0)
        not_verified = int(snapshot.get("verification_not_verified", 0) or 0)
        self.verification_var.set(f"{current} / {configured} current")

        dirty = bool(snapshot.get("dirty", False))
        running = bool(snapshot.get("running", False))
        if running:
            state = "RUNNING"
            style = "CX.Status.Running.TLabel"
        elif error_count:
            state = "ACTION REQUIRED"
            style = "CX.Status.Fail.TLabel"
        elif warning_count or stale or not_verified:
            state = "REVIEW"
            style = "CX.Status.Warning.TLabel"
        elif dirty:
            state = "UNSAVED"
            style = "CX.Status.Stale.TLabel"
        else:
            state = "READY"
            style = "CX.Status.Pass.TLabel"
        self.state_var.set(state)
        self.state_badge.configure(style=style)
        self.summary_var.set(
            f"Diagnostics {diagnostic_status} · Verification {current}/{configured}"
        )

        rows = (
            (
                "Diagnostics",
                "FAIL" if error_count else "WARNING" if warning_count else "PASS",
                self.diagnostics_var.get(),
                "Canonical project/model health diagnostics",
            ),
            (
                "Verification currency",
                "WARNING" if stale or not_verified else "PASS" if configured else "UNKNOWN",
                self.verification_var.get(),
                f"Stale {stale} · Not verified {not_verified}",
            ),
            (
                "Evidence",
                "VERIFIED" if int(snapshot.get("evidence_count", 0) or 0) else "UNKNOWN",
                f"{int(snapshot.get('evidence_count', 0) or 0)} record(s)",
                "Persisted verification evidence / ProofGraph source",
            ),
            (
                "Model",
                "PASS" if int(snapshot.get("room_count", 0) or 0) else "UNKNOWN",
                f"{int(snapshot.get('room_count', 0) or 0)} rooms · "
                f"{int(snapshot.get('device_count', 0) or 0)} devices",
                "Project spatial design metadata",
            ),
        )
        for item in self.health_tree.get_children():
            self.health_tree.delete(item)
        for index, row in enumerate(rows):
            status = row[1].lower()
            self.health_tree.insert(
                "",
                "end",
                iid=f"health:{index}",
                values=(row[1], row[2], row[3]),
                tags=(status,),
            )

        last_run = str(snapshot.get("last_run") or "No analysis run in this session")
        self.last_run_var.set(last_run)
        lines = [
            "LAST ANALYSIS",
            last_run,
            "",
            "TRACEABILITY",
            f"Persisted evidence records: {int(snapshot.get('evidence_count', 0) or 0)}",
            f"Configured analyses: {int(snapshot.get('analysis_count', 0) or 0)}",
            f"Current verification records: {current}",
            "",
            "PROJECT STATE",
            "Unsaved changes" if dirty else "Saved / baseline unchanged",
        ]
        self.activity_text.configure(state="normal")
        self.activity_text.delete("1.0", "end")
        self.activity_text.insert("1.0", "\n".join(lines))
        self.activity_text.configure(state="disabled")

    def apply_theme(self, palette: dict[str, str]) -> None:
        self.activity_text.configure(
            background=palette["field"],
            foreground=palette["field_text"],
            insertbackground=palette["text"],
            selectbackground=palette["selection"],
            selectforeground=palette["selection_text"],
            highlightbackground=palette["border"],
        )
        self.health_tree.tag_configure(
            "pass", foreground=palette["success"]
        )
        self.health_tree.tag_configure(
            "verified", foreground=palette["verified"]
        )
        self.health_tree.tag_configure(
            "warning", foreground=palette["warning"]
        )
        self.health_tree.tag_configure(
            "fail", foreground=palette["error"]
        )
        self.health_tree.tag_configure(
            "unknown", foreground=palette["muted"]
        )
