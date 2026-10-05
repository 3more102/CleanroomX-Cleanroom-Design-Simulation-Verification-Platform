from __future__ import annotations

from typing import Any, Callable

import tkinter as tk
from tkinter import ttk

from .gui_theme import status_style_name, theme_palette


def _status_style(value: Any) -> str:
    return status_style_name(value)


def _count(summary: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = summary.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
    return 0


class EngineeringDashboard(ttk.Frame):
    """Dense, display-only engineering project health surface."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_issue: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        super().__init__(master, padding=(14, 12))
        self._snapshot: dict[str, Any] = {}
        self._on_issue = on_issue
        self._issues_by_iid: dict[str, dict[str, Any]] = {}

        self.project_var = tk.StringVar(value="Untitled project")
        self.location_var = tk.StringVar(value="Unsaved project")
        self.diagnostics_var = tk.StringVar(value="NOT CHECKED")
        self.diagnostics_detail_var = tk.StringVar(value="No diagnostics evaluated")
        self.verification_var = tk.StringVar(value="NOT CHECKED")
        self.verification_detail_var = tk.StringVar(value="0 / 0 current")
        self.model_var = tk.StringVar(value="0 rooms")
        self.model_detail_var = tk.StringVar(value="0.0 m² · 0.0 m³")
        self.analysis_var = tk.StringVar(value="0 configured")
        self.analysis_detail_var = tk.StringVar(value="No completed analysis run")
        self.evidence_var = tk.StringVar(value="0 records")
        self.evidence_detail_var = tk.StringVar(value="No persisted verification evidence")
        self.issue_summary_var = tk.StringVar(value="No project diagnostics evaluated")

        self.columnconfigure(0, weight=1)
        self.rowconfigure(4, weight=1)

        self._build_header()
        self._build_instruments()
        self._build_progress()
        self._build_issue_table()

    def _build_header(self) -> None:
        header = ttk.Frame(self, style="CX.PanelHeader.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header,
            text="ENGINEERING PROJECT HEALTH",
            style="CX.PanelHeader.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            textvariable=self.project_var,
            style="CX.PanelHeader.TLabel",
        ).grid(row=0, column=1, sticky="e", padx=(12, 0))
        ttk.Label(
            self,
            textvariable=self.location_var,
            style="CX.Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(0, 10))

    def _card(
        self,
        parent: tk.Misc,
        *,
        column: int,
        title: str,
        value_var: tk.StringVar,
        detail_var: tk.StringVar,
    ) -> tuple[ttk.Frame, ttk.Label]:
        card = ttk.Frame(parent, style="CX.Card.TFrame", padding=(12, 10))
        card.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 5, 5))
        card.columnconfigure(0, weight=1)
        ttk.Label(card, text=title, style="CX.PanelSection.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        value = ttk.Label(card, textvariable=value_var, style="CX.PanelTitle.TLabel")
        value.grid(row=1, column=0, sticky="w", pady=(6, 2))
        ttk.Label(
            card,
            textvariable=detail_var,
            style="CX.PanelMuted.TLabel",
            wraplength=250,
            justify="left",
        ).grid(row=2, column=0, sticky="w")
        return card, value

    def _build_instruments(self) -> None:
        instruments = ttk.Frame(self)
        instruments.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        for index in range(5):
            instruments.columnconfigure(index, weight=1)

        _, self.diagnostics_value = self._card(
            instruments,
            column=0,
            title="DIAGNOSTICS",
            value_var=self.diagnostics_var,
            detail_var=self.diagnostics_detail_var,
        )
        _, self.verification_value = self._card(
            instruments,
            column=1,
            title="VERIFICATION",
            value_var=self.verification_var,
            detail_var=self.verification_detail_var,
        )
        self._card(
            instruments,
            column=2,
            title="DESIGN MODEL",
            value_var=self.model_var,
            detail_var=self.model_detail_var,
        )
        self._card(
            instruments,
            column=3,
            title="ANALYSIS",
            value_var=self.analysis_var,
            detail_var=self.analysis_detail_var,
        )
        self._card(
            instruments,
            column=4,
            title="EVIDENCE",
            value_var=self.evidence_var,
            detail_var=self.evidence_detail_var,
        )

    def _build_progress(self) -> None:
        progress_host = ttk.Frame(self, style="CX.SubtlePanel.TFrame", padding=(10, 7))
        progress_host.grid(row=3, column=0, sticky="new", pady=(0, 10))
        progress_host.columnconfigure(1, weight=1)
        ttk.Label(
            progress_host,
            text="Verification currency",
            style="CX.SurfaceSection.TLabel",
        ).grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.verification_progress = ttk.Progressbar(
            progress_host,
            mode="determinate",
            maximum=100,
        )
        self.verification_progress.grid(row=0, column=1, sticky="ew")
        self.verification_percent_var = tk.StringVar(value="0%")
        ttk.Label(
            progress_host,
            textvariable=self.verification_percent_var,
            style="CX.SurfaceMuted.TLabel",
            width=6,
            anchor="e",
        ).grid(row=0, column=2, sticky="e", padx=(8, 0))

    def _build_issue_table(self) -> None:
        host = ttk.Frame(self)
        host.grid(row=4, column=0, sticky="nsew")
        host.rowconfigure(1, weight=1)
        host.columnconfigure(0, weight=1)

        heading = ttk.Frame(host, style="CX.PanelHeader.TFrame")
        heading.grid(row=0, column=0, sticky="ew")
        heading.columnconfigure(0, weight=1)
        ttk.Label(
            heading,
            text="HIGH-PRIORITY ENGINEERING ISSUES",
            style="CX.PanelHeader.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            heading,
            textvariable=self.issue_summary_var,
            style="CX.PanelHeader.TLabel",
        ).grid(row=0, column=1, sticky="e")

        columns = ("severity", "code", "object", "domain", "description")
        self.issue_tree = ttk.Treeview(
            host,
            columns=columns,
            show="headings",
            height=9,
            selectmode="browse",
        )
        specs = {
            "severity": ("Severity", 86, False),
            "code": ("Code", 180, False),
            "object": ("Object", 150, False),
            "domain": ("Domain", 120, False),
            "description": ("Description", 520, True),
        }
        for key in columns:
            title, width, stretch = specs[key]
            self.issue_tree.heading(key, text=title)
            self.issue_tree.column(key, width=width, minwidth=70, stretch=stretch)
        scroll = ttk.Scrollbar(host, orient="vertical", command=self.issue_tree.yview)
        self.issue_tree.configure(yscrollcommand=scroll.set)
        self.issue_tree.grid(row=1, column=0, sticky="nsew")
        scroll.grid(row=1, column=1, sticky="ns")
        self.issue_tree.bind("<Double-1>", self._open_selected_issue)
        self.issue_tree.bind("<Return>", self._open_selected_issue)

    def apply_theme(self, value: Any) -> None:
        """Keep dashboard severity cues legible in both workstation themes."""
        palette = theme_palette(value)
        self.issue_tree.tag_configure("critical", foreground=palette["error"])
        self.issue_tree.tag_configure("error", foreground=palette["error"])
        self.issue_tree.tag_configure("warning", foreground=palette["warning"])
        self.issue_tree.tag_configure("info", foreground=palette["info"])

    def selected_issue(self) -> dict[str, Any] | None:
        selection = self.issue_tree.selection()
        if not selection:
            return None
        return self._issues_by_iid.get(selection[0])

    def _open_selected_issue(self, _event=None):
        issue = self.selected_issue()
        if issue is None or self._on_issue is None:
            return None
        self._on_issue(issue)
        return "break"

    @staticmethod
    def _issue_object(issue: dict[str, Any]) -> str:
        element = issue.get("element")
        if not isinstance(element, dict):
            return "Project"
        return str(
            element.get("name")
            or element.get("id")
            or element.get("type")
            or "Project"
        )

    def refresh(self, snapshot: dict[str, Any] | None) -> None:
        self._snapshot = snapshot if isinstance(snapshot, dict) else {}
        project = self._snapshot.get("project", {})
        project = project if isinstance(project, dict) else {}
        diagnostics = self._snapshot.get("diagnostics", {})
        diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
        diagnostic_summary = diagnostics.get("summary", {})
        diagnostic_summary = diagnostic_summary if isinstance(diagnostic_summary, dict) else {}
        verification = self._snapshot.get("verification", {})
        verification = verification if isinstance(verification, dict) else {}
        model = self._snapshot.get("model", {})
        model = model if isinstance(model, dict) else {}
        evidence = self._snapshot.get("evidence", {})
        evidence = evidence if isinstance(evidence, dict) else {}

        self.project_var.set(str(project.get("name") or "Untitled project"))
        self.location_var.set(str(project.get("location") or "Unsaved project"))

        diagnostic_status = str(diagnostic_summary.get("status") or "not checked")
        issue_count = _count(diagnostic_summary, "issue_count", "total_count")
        error_count = _count(diagnostic_summary, "error_count")
        warning_count = _count(diagnostic_summary, "warning_count")
        self.diagnostics_var.set(diagnostic_status.upper().replace("_", " "))
        self.diagnostics_detail_var.set(
            f"{issue_count} issues · {error_count} errors · {warning_count} warnings"
        )
        self.diagnostics_value.configure(style=_status_style(diagnostic_status))

        configured = _count(verification, "configured_analysis_count")
        current = _count(verification, "current_count")
        stale = _count(verification, "stale_count")
        not_verified = _count(verification, "not_verified_count")
        if configured <= 0:
            verification_status = "not checked"
        elif current == configured and stale == 0 and not_verified == 0:
            verification_status = "current"
        elif stale > 0:
            verification_status = "stale"
        else:
            verification_status = "incomplete"
        self.verification_var.set(verification_status.upper().replace("_", " "))
        self.verification_detail_var.set(
            f"{current} / {configured} current · {stale} stale · {not_verified} not verified"
        )
        self.verification_value.configure(style=_status_style(verification_status))
        percent = int(round((current / configured) * 100)) if configured else 0
        self.verification_progress.configure(value=percent)
        self.verification_percent_var.set(f"{percent}%")

        rooms = int(model.get("room_count") or 0)
        area = float(model.get("total_floor_area_m2") or 0.0)
        volume = float(model.get("total_volume_m3") or 0.0)
        devices = int(model.get("device_count") or 0)
        self.model_var.set(f"{rooms} rooms · {devices} devices")
        self.model_detail_var.set(f"{area:,.1f} m² floor area · {volume:,.1f} m³ volume")

        analyses = int(self._snapshot.get("analysis_count") or 0)
        last_run = self._snapshot.get("last_run")
        self.analysis_var.set(f"{analyses} configured")
        if isinstance(last_run, dict):
            title = str(last_run.get("title") or "Analysis")
            status = str(last_run.get("status") or "unknown").upper()
            self.analysis_detail_var.set(f"Last run: {title} · {status}")
        else:
            self.analysis_detail_var.set("No completed analysis run")

        records = int(evidence.get("record_count") or 0)
        graphs = int(evidence.get("proofgraph_count") or 0)
        self.evidence_var.set(f"{records} records")
        self.evidence_detail_var.set(f"{graphs} ProofGraph artifact{'s' if graphs != 1 else ''} retained")

        issues = diagnostics.get("issues", [])
        issues = issues if isinstance(issues, list) else []
        severity_rank = {"critical": 0, "error": 1, "warning": 2, "info": 3}
        ordered = sorted(
            (issue for issue in issues if isinstance(issue, dict)),
            key=lambda issue: (
                severity_rank.get(str(issue.get("severity") or "info").lower(), 4),
                int(issue.get("sequence") or 0),
            ),
        )
        for iid in self.issue_tree.get_children():
            self.issue_tree.delete(iid)
        self._issues_by_iid.clear()
        for index, issue in enumerate(ordered[:12], start=1):
            severity_token = str(issue.get("severity") or "info").strip().lower()
            severity = severity_token.upper()
            iid = f"issue-{index}"
            self.issue_tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    severity,
                    str(issue.get("rule") or ""),
                    self._issue_object(issue),
                    str(issue.get("category") or ""),
                    str(issue.get("message") or ""),
                ),
                tags=(severity_token,),
            )
            self._issues_by_iid[iid] = issue
        self.issue_summary_var.set(
            "No unresolved issues"
            if not ordered
            else f"{len(ordered)} issue{'s' if len(ordered) != 1 else ''} · showing {min(len(ordered), 12)}"
        )
