from __future__ import annotations

from typing import Any, Callable

import tkinter as tk
from tkinter import ttk

from .gui_theme import normalize_theme_name, theme_palette


class EngineeringDashboardPanel(ttk.Frame):
    """Project-health overview backed only by canonical CleanroomX diagnostics."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        navigate_callback: Callable[[dict[str, Any]], None],
        show_problems_callback: Callable[[], None],
        verify_callback: Callable[[], Any],
        open_design_callback: Callable[[], None],
    ) -> None:
        super().__init__(master, style="CX.Panel.TFrame", padding=(10, 8))
        self._navigate_callback = navigate_callback
        self._show_problems_callback = show_problems_callback
        self._verify_callback = verify_callback
        self._open_design_callback = open_design_callback
        self._issues_by_iid: dict[str, dict[str, Any]] = {}
        self._theme_name = "dark"

        self.project_var = tk.StringVar(value="Unsaved project")
        self.health_var = tk.StringVar(value="NOT EVALUATED")
        self.scope_var = tk.StringVar(
            value="Canonical project diagnostics have not been evaluated."
        )
        self.diagnostics_var = tk.StringVar(value="—")
        self.verification_var = tk.StringVar(value="—")
        self.spatial_var = tk.StringVar(value="—")
        self.evidence_var = tk.StringVar(value="—")
        self.activity_var = tk.StringVar(value="No analysis run in this session")
        self.verification_percent_var = tk.StringVar(value="0% current")
        self.empty_var = tk.StringVar(
            value="Run or refresh project diagnostics to populate engineering health."
        )

        self._build()

    def _build(self) -> None:
        header = ttk.Frame(self, style="CX.PanelHeader.TFrame")
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(header, text="▎", style="CX.PanelAccent.TLabel").pack(
            side="left", padx=(0, 4)
        )
        ttk.Label(
            header,
            text="ENGINEERING DASHBOARD",
            style="CX.PanelHeader.TLabel",
        ).pack(side="left")
        ttk.Label(
            header,
            text="Canonical health / traceability overview",
            style="CX.CardHelper.TLabel",
        ).pack(side="left", padx=(10, 0))

        identity = ttk.Frame(self, style="CX.Card.TFrame", padding=(10, 8))
        identity.pack(fill="x", pady=(0, 8))
        left = ttk.Frame(identity, style="CX.Card.TFrame")
        left.pack(side="left", fill="x", expand=True)
        ttk.Label(left, text="ACTIVE PROJECT", style="CX.CardSection.TLabel").pack(
            anchor="w"
        )
        ttk.Label(
            left,
            textvariable=self.project_var,
            style="CX.CardValue.TLabel",
        ).pack(anchor="w", pady=(2, 1))
        ttk.Label(
            left,
            textvariable=self.scope_var,
            style="CX.CardHelper.TLabel",
        ).pack(anchor="w")

        health = ttk.Frame(identity, style="CX.Card.TFrame")
        health.pack(side="right", padx=(12, 0))
        ttk.Label(health, text="DIAGNOSTIC HEALTH", style="CX.CardSection.TLabel").pack(
            anchor="e"
        )
        self.health_badge = ttk.Label(
            health,
            textvariable=self.health_var,
            style="CX.InfoBadge.TLabel",
        )
        self.health_badge.pack(anchor="e", pady=(3, 0))

        metrics = ttk.Frame(self, style="CX.Panel.TFrame")
        metrics.pack(fill="x", pady=(0, 7))
        metric_specs = (
            ("DIAGNOSTICS", self.diagnostics_var),
            ("VERIFICATION CURRENCY", self.verification_var),
            ("SPATIAL MODEL", self.spatial_var),
            ("EVIDENCE", self.evidence_var),
        )
        for column, (title, variable) in enumerate(metric_specs):
            card = ttk.Frame(metrics, style="CX.Card.TFrame", padding=(9, 7))
            card.grid(
                row=0,
                column=column,
                sticky="nsew",
                padx=(0 if column == 0 else 3, 0 if column == len(metric_specs) - 1 else 3),
            )
            ttk.Label(card, text=title, style="CX.CardSection.TLabel").pack(anchor="w")
            ttk.Label(
                card,
                textvariable=variable,
                style="CX.CardValue.TLabel",
                justify="left",
            ).pack(anchor="w", pady=(4, 0))
            metrics.columnconfigure(column, weight=1)

        currency = ttk.Frame(
            self,
            style="CX.SubtlePanel.TFrame",
            padding=(10, 7),
        )
        currency.pack(fill="x", pady=(0, 7))
        ttk.Label(
            currency,
            text="VERIFICATION CURRENCY",
            style="CX.Section.TLabel",
        ).pack(side="left", padx=(0, 10))
        self.verification_progress = ttk.Progressbar(
            currency,
            mode="determinate",
            maximum=100,
            value=0,
            style="CX.Readiness.Horizontal.TProgressbar",
        )
        self.verification_progress.pack(side="left", fill="x", expand=True)
        ttk.Label(
            currency,
            textvariable=self.verification_percent_var,
            style="CX.StatusPrimary.TLabel",
            width=13,
            anchor="e",
        ).pack(side="right", padx=(10, 0))

        actionbar = ttk.Frame(self, style="CX.Toolbar.TFrame")
        actionbar.pack(fill="x", pady=(0, 6))
        ttk.Label(
            actionbar,
            text="QUICK ACTIONS",
            style="CX.ToolbarGroup.TLabel",
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            actionbar,
            text="Open Design",
            style="CX.Compact.TButton",
            command=self._open_design_callback,
        ).pack(side="left", padx=2)
        ttk.Button(
            actionbar,
            text="Problems",
            style="CX.Compact.TButton",
            command=self._show_problems_callback,
        ).pack(side="left", padx=2)
        ttk.Button(
            actionbar,
            text="Verify Project",
            style="CX.Secondary.TButton",
            command=self._verify_callback,
        ).pack(side="left", padx=2)
        ttk.Label(
            actionbar,
            textvariable=self.activity_var,
            style="CX.ToolbarLabel.TLabel",
        ).pack(side="right", padx=(12, 0))

        body = ttk.Panedwindow(self, orient="vertical")
        body.pack(fill="both", expand=True)

        issues_host = ttk.Frame(body, style="CX.Panel.TFrame")
        body.add(issues_host, weight=4)
        details_host = ttk.Frame(body, style="CX.Panel.TFrame")
        body.add(details_host, weight=1)

        issues_header = ttk.Frame(issues_host, style="CX.Panel.TFrame")
        issues_header.pack(fill="x", pady=(0, 4))
        ttk.Label(
            issues_header,
            text="HIGHEST-PRIORITY ENGINEERING ISSUES",
            style="CX.Section.TLabel",
        ).pack(side="left")
        ttk.Label(
            issues_header,
            textvariable=self.empty_var,
            style="CX.Helper.TLabel",
        ).pack(side="right")

        columns = ("severity", "code", "description", "object", "domain")
        self.issue_tree = ttk.Treeview(
            issues_host,
            columns=columns,
            show="headings",
            selectmode="browse",
            height=8,
        )
        headings = {
            "severity": "Severity",
            "code": "Code",
            "description": "Description",
            "object": "Object",
            "domain": "Domain",
        }
        widths = {
            "severity": 90,
            "code": 210,
            "description": 560,
            "object": 170,
            "domain": 130,
        }
        for column in columns:
            self.issue_tree.heading(column, text=headings[column])
            self.issue_tree.column(
                column,
                width=widths[column],
                minwidth=70,
                stretch=column == "description",
            )

        yscroll = ttk.Scrollbar(
            issues_host,
            orient="vertical",
            command=self.issue_tree.yview,
        )
        xscroll = ttk.Scrollbar(
            issues_host,
            orient="horizontal",
            command=self.issue_tree.xview,
        )
        self.issue_tree.configure(
            yscrollcommand=yscroll.set,
            xscrollcommand=xscroll.set,
        )
        xscroll.pack(side="bottom", fill="x")
        yscroll.pack(side="right", fill="y")
        self.issue_tree.pack(side="left", fill="both", expand=True)
        self.issue_tree.bind("<<TreeviewSelect>>", self._show_detail)
        self.issue_tree.bind("<Double-1>", self._locate_selected)
        self.issue_tree.bind("<Return>", self._locate_selected)

        detail_toolbar = ttk.Frame(details_host, style="CX.Panel.TFrame")
        detail_toolbar.pack(fill="x", pady=(4, 2))
        ttk.Label(
            detail_toolbar,
            text="ISSUE DETAIL",
            style="CX.Section.TLabel",
        ).pack(side="left")
        self.locate_button = ttk.Button(
            detail_toolbar,
            text="Locate",
            style="CX.Compact.TButton",
            command=self._locate_selected,
            state="disabled",
        )
        self.locate_button.pack(side="right")

        self.detail_var = tk.StringVar(
            value="Select an issue to inspect its engineering context and suggested recovery."
        )
        ttk.Label(
            details_host,
            textvariable=self.detail_var,
            justify="left",
            anchor="nw",
            wraplength=980,
        ).pack(fill="both", expand=True, padx=2, pady=(2, 4))

    @staticmethod
    def _count(value: Any) -> int:
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _object_text(issue: dict[str, Any]) -> str:
        element = issue.get("element")
        if not isinstance(element, dict):
            return "project"
        return str(
            element.get("name")
            or element.get("id")
            or element.get("type")
            or "project"
        )

    @staticmethod
    def _severity_label(value: Any) -> str:
        severity = str(value or "info").strip().casefold()
        return {
            "error": "✕ ERROR",
            "warning": "⚠ WARNING",
            "info": "ⓘ INFO",
        }.get(severity, severity.upper())

    def refresh(
        self,
        diagnostics: dict[str, Any] | None,
        *,
        last_run_title: str | None = None,
        last_run_status: str | None = None,
    ) -> None:
        for iid in self.issue_tree.get_children():
            self.issue_tree.delete(iid)
        self._issues_by_iid.clear()
        self.locate_button.configure(state="disabled")
        self.detail_var.set(
            "Select an issue to inspect its engineering context and suggested recovery."
        )

        if not isinstance(diagnostics, dict):
            self.project_var.set("Project diagnostics unavailable")
            self.health_var.set("UNAVAILABLE")
            self.health_badge.configure(style="CX.ErrorBadge.TLabel")
            self.scope_var.set("Canonical project diagnostics could not be evaluated.")
            self.diagnostics_var.set("Unavailable")
            self.verification_var.set("Unavailable")
            self.verification_progress.configure(value=0)
            self.verification_percent_var.set("unavailable")
            self.spatial_var.set("Unavailable")
            self.evidence_var.set("Unavailable")
            self.empty_var.set("Diagnostics unavailable")
            return

        project = diagnostics.get("project", {})
        summary = diagnostics.get("summary", {})
        currency = diagnostics.get("verification_currency", {})
        currency_summary = (
            currency.get("summary", {}) if isinstance(currency, dict) else {}
        )

        self.project_var.set(str(project.get("name") or "Untitled project"))
        status = str(summary.get("status") or "unknown").strip().lower()
        errors = self._count(summary.get("error_count"))
        warnings = self._count(summary.get("warning_count"))
        info = self._count(summary.get("info_count"))
        issue_count = self._count(summary.get("issue_count"))

        if status == "error" or errors:
            self.health_var.set("ERRORS PRESENT")
            self.health_badge.configure(style="CX.ErrorBadge.TLabel")
        elif status == "warning" or warnings:
            self.health_var.set("ATTENTION")
            self.health_badge.configure(style="CX.WarningBadge.TLabel")
        elif status == "pass":
            self.health_var.set("PASS")
            self.health_badge.configure(style="CX.SuccessBadge.TLabel")
        else:
            self.health_var.set(status.upper() or "UNKNOWN")
            self.health_badge.configure(style="CX.InfoBadge.TLabel")

        self.scope_var.set(
            "Software/design diagnostics only — not certification, CFD validation, or commissioning acceptance."
        )
        self.diagnostics_var.set(
            f"{errors} errors · {warnings} warnings\n{info} information"
        )

        configured = self._count(currency_summary.get("configured_analysis_count"))
        current = self._count(currency_summary.get("current_count"))
        stale = self._count(currency_summary.get("stale_count"))
        not_verified = self._count(currency_summary.get("not_verified_count"))
        self.verification_var.set(
            f"{current}/{configured} current\n{stale} stale · {not_verified} not verified"
        )
        percent = int(round((current / configured) * 100)) if configured else 0
        self.verification_progress.configure(value=percent)
        self.verification_percent_var.set(
            f"{percent}% current" if configured else "not checked"
        )

        rooms = self._count(project.get("spatial_room_count"))
        devices = self._count(project.get("spatial_device_count"))
        analyses = self._count(project.get("analysis_count"))
        self.spatial_var.set(
            f"{rooms} rooms · {devices} devices\n{analyses} analyses"
        )

        evidence = self._count(project.get("verification_run_count"))
        self.evidence_var.set(
            f"{evidence} persisted verification\nrecord{'s' if evidence != 1 else ''}"
        )

        if last_run_title:
            state = str(last_run_status or "unknown").upper()
            self.activity_var.set(f"Last run: {last_run_title} · {state}")
        else:
            self.activity_var.set("No analysis run in this session")

        issues = [
            item
            for item in diagnostics.get("issues", [])
            if isinstance(item, dict)
        ]
        severity_rank = {"error": 0, "warning": 1, "info": 2}
        issues.sort(
            key=lambda item: (
                severity_rank.get(
                    str(item.get("severity", "info")).casefold(),
                    3,
                ),
                self._count(item.get("sequence")),
            )
        )
        for index, issue in enumerate(issues[:12], start=1):
            iid = f"dashboard-issue:{index}"
            severity = str(issue.get("severity", "info")).casefold()
            self.issue_tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    self._severity_label(severity),
                    issue.get("rule", ""),
                    issue.get("message", ""),
                    self._object_text(issue),
                    issue.get("category", ""),
                ),
                tags=(severity,),
            )
            self._issues_by_iid[iid] = issue

        if issue_count == 0:
            self.empty_var.set("No diagnostic errors or warnings")
        elif len(issues) > 12:
            self.empty_var.set(f"Showing 12 of {issue_count} diagnostics")
        else:
            self.empty_var.set(f"{issue_count} diagnostic item(s)")

    def selected_issue(self) -> dict[str, Any] | None:
        selection = self.issue_tree.selection()
        if not selection:
            return None
        return self._issues_by_iid.get(selection[0])

    def _show_detail(self, _event=None) -> None:
        issue = self.selected_issue()
        if issue is None:
            self.locate_button.configure(state="disabled")
            self.detail_var.set(
                "Select an issue to inspect its engineering context and suggested recovery."
            )
            return
        self.locate_button.configure(state="normal")
        message = str(issue.get("message") or "")
        action = str(issue.get("suggested_action") or "")
        self.detail_var.set(
            f"{self._severity_label(issue.get('severity'))} · {issue.get('rule', '')}\n"
            f"{message}\nSuggested recovery: {action}"
        )

    def _locate_selected(self, _event=None):
        issue = self.selected_issue()
        if issue is None:
            return "break"
        self._navigate_callback(issue)
        return "break"

    def apply_theme(self, value: Any) -> None:
        self._theme_name = normalize_theme_name(value)
        palette = theme_palette(self._theme_name)
        self.issue_tree.tag_configure(
            "error",
            foreground=palette["error"],
            font=("TkDefaultFont", 9, "bold"),
        )
        self.issue_tree.tag_configure("warning", foreground=palette["warning"])
        self.issue_tree.tag_configure("info", foreground=palette["info"])
