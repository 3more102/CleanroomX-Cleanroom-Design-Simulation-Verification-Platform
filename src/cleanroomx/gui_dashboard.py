from __future__ import annotations

from typing import Any

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


def system_status_projection(snapshot: dict[str, Any] | None) -> tuple[tuple[str, str, str], ...]:
    """Project explicit project state into compact workstation status modules."""
    data = snapshot if isinstance(snapshot, dict) else {}
    diagnostics = data.get("diagnostics", {})
    diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
    summary = diagnostics.get("summary", {})
    summary = summary if isinstance(summary, dict) else {}
    verification = data.get("verification", {})
    verification = verification if isinstance(verification, dict) else {}
    model = data.get("model", {})
    model = model if isinstance(model, dict) else {}
    evidence = data.get("evidence", {})
    evidence = evidence if isinstance(evidence, dict) else {}

    rooms = int(model.get("room_count") or 0)
    configured = _count(verification, "configured_analysis_count")
    current = _count(verification, "current_count")
    stale = _count(verification, "stale_count")
    not_verified = _count(verification, "not_verified_count")
    records = int(evidence.get("record_count") or 0)
    graphs = int(evidence.get("proofgraph_count") or 0)
    analyses = int(data.get("analysis_count") or 0)
    last_run = data.get("last_run")

    if configured <= 0:
        verification_state, verification_detail = "not checked", "No configured analyses"
    elif current == configured and stale == 0 and not_verified == 0:
        verification_state, verification_detail = "current", f"{current}/{configured} current"
    elif stale > 0:
        verification_state, verification_detail = "stale", f"{stale} stale · {current}/{configured} current"
    else:
        verification_state, verification_detail = "incomplete", f"{not_verified} not verified · {current}/{configured} current"

    diagnostic_state = str(summary.get("status") or "not checked")
    issue_count = _count(summary, "issue_count", "total_count")
    if isinstance(last_run, dict):
        analysis_state = str(last_run.get("status") or "unknown")
        analysis_detail = str(last_run.get("title") or "Latest analysis")
    else:
        analysis_state = "available" if analyses else "not checked"
        analysis_detail = f"{analyses} configured · not run" if analyses else "No analysis configured"

    return (
        ("MODEL", "ready" if rooms else "not checked", f"{rooms} room{'s' if rooms != 1 else ''}"),
        ("DIAGNOSTICS", diagnostic_state, f"{issue_count} issue{'s' if issue_count != 1 else ''}"),
        ("VERIFICATION", verification_state, verification_detail),
        ("ANALYSIS", analysis_state, analysis_detail),
        ("EVIDENCE", "available" if records or graphs else "not checked", f"{records} record{'s' if records != 1 else ''} · {graphs} graph{'s' if graphs != 1 else ''}"),
    )


class EngineeringDashboard(ttk.Frame):
    """Dense, display-only engineering project health surface."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, padding=(14, 12))
        self._snapshot: dict[str, Any] = {}
        self._theme_name = "dark"
        self._palette = theme_palette(self._theme_name)
        self.system_status_vars: dict[str, tuple[tk.StringVar, tk.StringVar]] = {}
        self.system_status_labels: dict[str, ttk.Label] = {}

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
        self.rowconfigure(5, weight=1)

        self._build_header()
        self._build_instruments()
        self._build_progress()
        self._build_system_status()
        self._build_issue_table()
        self.apply_theme("dark")

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

    def _build_system_status(self) -> None:
        host = ttk.Frame(self, style="CX.SubtlePanel.TFrame", padding=(10, 7))
        host.grid(row=4, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(host, text="SYSTEM STATUS", style="CX.SurfaceSection.TLabel").pack(side="left", padx=(0, 10))
        for key in ("MODEL", "DIAGNOSTICS", "VERIFICATION", "ANALYSIS", "EVIDENCE"):
            state_var = tk.StringVar(value="NOT CHECKED")
            detail_var = tk.StringVar(value="")
            self.system_status_vars[key] = (state_var, detail_var)
            module = ttk.Frame(host, style="CX.Card.TFrame", padding=(6, 3))
            module.pack(side="left", padx=3)
            ttk.Label(module, text=key, style="CX.PanelSection.TLabel").pack(side="left", padx=(0, 5))
            label = ttk.Label(module, textvariable=state_var, style="CX.Status.Neutral.TLabel")
            label.pack(side="left")
            self.system_status_labels[key] = label

    def _build_issue_table(self) -> None:
        host = ttk.Frame(self)
        host.grid(row=5, column=0, sticky="nsew")
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

    def apply_theme(self, value: Any) -> None:
        self._theme_name = str(value or "dark")
        self._palette = theme_palette(self._theme_name)
        self.issue_tree.tag_configure("row_even", background=self._palette["tree"])
        self.issue_tree.tag_configure("row_odd", background=self._palette["surface_alt"])
        self.issue_tree.tag_configure("critical", foreground=self._palette["error"], font=("TkDefaultFont", 9, "bold"))
        self.issue_tree.tag_configure("error", foreground=self._palette["error"], font=("TkDefaultFont", 9, "bold"))
        self.issue_tree.tag_configure("warning", foreground=self._palette["warning"])
        self.issue_tree.tag_configure("info", foreground=self._palette["info"])

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

        for key, state, detail in system_status_projection(self._snapshot):
            state_var, detail_var = self.system_status_vars[key]
            state_var.set(state.upper().replace("_", " "))
            detail_var.set(detail)
            self.system_status_labels[key].configure(style=_status_style(state))

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
        for index, issue in enumerate(ordered[:12], start=1):
            severity = str(issue.get("severity") or "info").upper()
            severity_token = str(issue.get("severity") or "info").lower()
            row_tag = "row_even" if index % 2 == 0 else "row_odd"
            self.issue_tree.insert(
                "",
                "end",
                iid=f"issue-{index}",
                values=(
                    severity,
                    str(issue.get("rule") or ""),
                    self._issue_object(issue),
                    str(issue.get("category") or ""),
                    str(issue.get("message") or ""),
                ),
                tags=(row_tag, severity_token),
            )
        self.issue_summary_var.set(
            "No unresolved issues"
            if not ordered
            else f"{len(ordered)} issue{'s' if len(ordered) != 1 else ''} · showing {min(len(ordered), 12)}"
        )
