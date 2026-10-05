from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import tkinter as tk
from tkinter import ttk

from .project_diagnostics import analyze_project_diagnostics
from .verification_currency import assess_project_verification_currency
from .verification_run_history import verification_run_history_records


class ProjectDiagnosticsPanel(ttk.Frame):
    """IDE-style view over the canonical CleanroomX project diagnostics service."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        project_getter: Callable[[], Any],
        base_dir_getter: Callable[[], str | Path | None],
        navigate_callback: Callable[[dict[str, Any]], None],
        export_callback: Callable[[dict[str, Any]], None] | None = None,
        status_setter: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(master)
        self._project_getter = project_getter
        self._base_dir_getter = base_dir_getter
        self._navigate_callback = navigate_callback
        self._export_callback = export_callback
        self._status_setter = status_setter or (lambda _message: None)
        self._issues_by_iid: dict[str, dict[str, Any]] = {}
        self.last_result: dict[str, Any] | None = None

        self.search_var = tk.StringVar()
        self.severity_var = tk.StringVar(value="All")
        self.summary_var = tk.StringVar(value="Project diagnostics not evaluated")
        self._build()

        self.search_var.trace_add("write", lambda *_: self._populate())
        self.severity_var.trace_add("write", lambda *_: self._populate())

    def _build(self) -> None:
        toolbar = ttk.Frame(self, style="CX.Toolbar.TFrame", padding=(8, 6))
        toolbar.pack(fill="x")

        ttk.Label(toolbar, text="PROBLEMS", style="CX.Warning.TLabel").pack(
            side="left", padx=(0, 8)
        )
        ttk.Label(toolbar, text="Search").pack(side="left")
        ttk.Entry(toolbar, textvariable=self.search_var, width=28).pack(
            side="left", padx=(4, 8)
        )
        ttk.Label(toolbar, text="Severity").pack(side="left")
        severity = ttk.Combobox(
            toolbar,
            textvariable=self.severity_var,
            values=("All", "Error", "Warning", "Info"),
            state="readonly",
            width=10,
        )
        severity.pack(side="left", padx=(4, 8))
        ttk.Button(
            toolbar,
            text="Refresh",
            command=self.refresh,
            style="CX.Compact.TButton",
        ).pack(side="left", padx=2)
        ttk.Button(
            toolbar,
            text="Copy",
            command=self.copy_selected,
            style="CX.Compact.TButton",
        ).pack(side="left", padx=2)
        self.locate_button = ttk.Button(
            toolbar,
            text="Locate",
            command=self._navigate_selected,
            state="disabled",
            style="CX.Primary.TButton",
        )
        self.locate_button.pack(side="left", padx=2)
        self.export_button = ttk.Button(
            toolbar,
            text="Export…",
            command=self._export,
            state="normal" if self._export_callback is not None else "disabled",
            style="CX.Info.TButton",
        )
        self.export_button.pack(side="left", padx=2)

        ttk.Label(
            toolbar,
            textvariable=self.summary_var,
            anchor="e",
        ).pack(side="right", fill="x", expand=True, padx=(12, 0))

        body = ttk.Panedwindow(self, orient="vertical")
        body.pack(fill="both", expand=True)

        table_frame = ttk.Frame(body)
        detail_frame = ttk.Frame(body)
        body.add(table_frame, weight=4)
        body.add(detail_frame, weight=1)

        columns = ("severity", "code", "description", "object", "level", "source")
        self.tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
            height=7,
        )
        headings = {
            "severity": "Severity",
            "code": "Code",
            "description": "Description",
            "object": "Object",
            "level": "Level",
            "source": "Source",
        }
        widths = {
            "severity": 90,
            "code": 220,
            "description": 520,
            "object": 180,
            "level": 120,
            "source": 150,
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(
                column,
                width=widths[column],
                minwidth=70,
                stretch=column == "description",
            )

        yscroll = ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=self.tree.yview,
        )
        xscroll = ttk.Scrollbar(
            table_frame,
            orient="horizontal",
            command=self.tree.xview,
        )
        self.tree.configure(
            yscrollcommand=yscroll.set,
            xscrollcommand=xscroll.set,
        )
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        self.tree.tag_configure(
            "error",
            foreground="#EF4444",
            font=("TkDefaultFont", 9, "bold"),
        )
        self.tree.tag_configure(
            "warning",
            foreground="#F59E0B",
            font=("TkDefaultFont", 9, "bold"),
        )
        self.tree.tag_configure("info", foreground="#38BDF8")
        self.tree.bind("<<TreeviewSelect>>", self._show_selected_detail)
        self.tree.bind("<Double-1>", self._navigate_selected)
        self.tree.bind("<Return>", self._navigate_selected)

        self.detail = tk.Text(
            detail_frame,
            wrap="word",
            height=4,
            state="disabled",
            borderwidth=0,
        )
        detail_scroll = ttk.Scrollbar(
            detail_frame,
            orient="vertical",
            command=self.detail.yview,
        )
        self.detail.configure(yscrollcommand=detail_scroll.set)
        self.detail.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=4)
        detail_scroll.pack(side="right", fill="y", pady=4)

    @staticmethod
    def _element_text(issue: dict[str, Any]) -> str:
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
    def _level_text(issue: dict[str, Any]) -> str:
        details = issue.get("details")
        if not isinstance(details, dict):
            return ""
        for key in ("level", "level_name", "floor", "floor_name"):
            value = details.get(key)
            if value not in (None, ""):
                return str(value)
        return ""

    def _filtered_issues(self) -> list[dict[str, Any]]:
        if not isinstance(self.last_result, dict):
            return []
        issues = self.last_result.get("issues")
        if not isinstance(issues, list):
            return []

        severity = self.severity_var.get().strip().casefold()
        query = self.search_var.get().strip().casefold()
        visible: list[dict[str, Any]] = []
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            issue_severity = str(issue.get("severity", "")).casefold()
            if severity and severity != "all" and issue_severity != severity:
                continue
            if query:
                haystack = " ".join(
                    (
                        str(issue.get("rule", "")),
                        str(issue.get("category", "")),
                        str(issue.get("message", "")),
                        str(issue.get("suggested_action", "")),
                        self._element_text(issue),
                        json.dumps(
                            issue.get("details", {}),
                            sort_keys=True,
                            ensure_ascii=False,
                            allow_nan=False,
                        ),
                    )
                ).casefold()
                if query not in haystack:
                    continue
            visible.append(issue)
        return visible

    def _populate(self) -> None:
        selection = self.tree.selection()
        selected_sequence = None
        if selection:
            selected = self._issues_by_iid.get(selection[0])
            if selected is not None:
                selected_sequence = selected.get("sequence")

        for item in self.tree.get_children():
            self.tree.delete(item)
        self._issues_by_iid.clear()

        for index, issue in enumerate(self._filtered_issues(), start=1):
            sequence = issue.get("sequence", index)
            iid = f"issue:{sequence}"
            if self.tree.exists(iid):
                iid = f"{iid}:{index}"
            severity = str(issue.get("severity", "info")).lower()
            self.tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    severity.upper(),
                    issue.get("rule", ""),
                    issue.get("message", ""),
                    self._element_text(issue),
                    self._level_text(issue),
                    issue.get("category", ""),
                ),
                tags=(severity,),
            )
            self._issues_by_iid[iid] = issue

        if selected_sequence is not None:
            for iid, issue in self._issues_by_iid.items():
                if issue.get("sequence") == selected_sequence:
                    self.tree.selection_set(iid)
                    self.tree.focus(iid)
                    self.tree.see(iid)
                    break
        self._show_selected_detail()

    def refresh(self) -> dict[str, Any] | None:
        try:
            result = analyze_project_diagnostics(
                self._project_getter(),
                base_dir=self._base_dir_getter(),
            )
        except Exception as exc:
            self.last_result = None
            self.summary_var.set(f"Diagnostics unavailable: {exc}")
            self._status_setter("Project diagnostics failed")
            self._populate()
            return None

        self.last_result = result
        summary = result.get("summary", {})
        self.summary_var.set(
            "{status} · {errors} error(s) · {warnings} warning(s) · {info} info".format(
                status=str(summary.get("status", "unknown")).upper(),
                errors=summary.get("error_count", 0),
                warnings=summary.get("warning_count", 0),
                info=summary.get("info_count", 0),
            )
        )
        self._populate()
        return result

    def selected_issue(self) -> dict[str, Any] | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return self._issues_by_iid.get(selection[0])

    def _show_selected_detail(self, event=None) -> None:
        issue = self.selected_issue()
        self.locate_button.configure(state="normal" if issue is not None else "disabled")
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        if issue is not None:
            lines = [
                f"{str(issue.get('severity', 'info')).upper()} · {issue.get('rule', '')}",
                str(issue.get("message", "")),
                "",
                "Suggested action:",
                str(issue.get("suggested_action", "")),
            ]
            details = issue.get("details")
            if isinstance(details, dict) and details:
                lines.extend(
                    (
                        "",
                        "Details:",
                        json.dumps(
                            details,
                            indent=2,
                            sort_keys=True,
                            ensure_ascii=False,
                            allow_nan=False,
                        ),
                    )
                )
            self.detail.insert("1.0", "\n".join(lines))
        elif self.last_result is None:
            self.detail.insert(
                "1.0",
                "Diagnostics have not been evaluated. Refresh to run the canonical project diagnostics.",
            )
        elif not self._filtered_issues():
            summary = self.last_result.get("summary", {}) if isinstance(self.last_result, dict) else {}
            total = int(summary.get("issue_count", 0) or 0)
            if total:
                self.detail.insert(
                    "1.0",
                    "No diagnostics match the current search/severity filter.",
                )
            else:
                self.detail.insert(
                    "1.0",
                    "No violations detected by the currently enabled project diagnostics.",
                )
        self.detail.configure(state="disabled")

    def _navigate_selected(self, event=None):
        issue = self.selected_issue()
        if issue is None:
            return "break"
        self._navigate_callback(issue)
        return "break"

    def copy_selected(self) -> None:
        issue = self.selected_issue()
        if issue is None:
            self._status_setter("Select a diagnostic to copy")
            return
        payload = json.dumps(
            issue,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        self.clipboard_clear()
        self.clipboard_append(payload)
        self._status_setter("Diagnostic copied to clipboard")

    def _export(self) -> None:
        if self._export_callback is None:
            return
        result = self.last_result or self.refresh()
        if result is not None:
            self._export_callback(result)



class EngineeringDashboard(ttk.Frame):
    """Read-only project-health dashboard over canonical CleanroomX services.

    The dashboard summarizes existing diagnostics, verification currency, retained
    verification evidence and spatial counts. It intentionally does not introduce
    new acceptance criteria or solver semantics.
    """

    def __init__(
        self,
        master: tk.Misc,
        *,
        project_getter: Callable[[], Any],
        base_dir_getter: Callable[[], str | Path | None],
        spatial_summary_getter: Callable[[], dict[str, int]] | None = None,
        navigate_issue_callback: Callable[[dict[str, Any]], None] | None = None,
        open_design_callback: Callable[[], None] | None = None,
        open_problems_callback: Callable[[], None] | None = None,
        open_proofgraph_callback: Callable[[], None] | None = None,
        verify_callback: Callable[[], None] | None = None,
        status_setter: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(master)
        self._project_getter = project_getter
        self._base_dir_getter = base_dir_getter
        self._spatial_summary_getter = spatial_summary_getter
        self._navigate_issue_callback = navigate_issue_callback
        self._status_setter = status_setter or (lambda _message: None)
        self._issues_by_iid: dict[str, dict[str, Any]] = {}

        self.project_var = tk.StringVar(value="PROJECT HEALTH")
        self.subtitle_var = tk.StringVar(
            value="Canonical diagnostics, verification currency and retained evidence"
        )
        self.model_kpi_var = tk.StringVar(value="—")
        self.model_detail_var = tk.StringVar(value="Model not evaluated")
        self.verify_kpi_var = tk.StringVar(value="—")
        self.verify_detail_var = tk.StringVar(value="Verification not evaluated")
        self.issues_kpi_var = tk.StringVar(value="—")
        self.issues_detail_var = tk.StringVar(value="Diagnostics not evaluated")
        self.evidence_kpi_var = tk.StringVar(value="—")
        self.evidence_detail_var = tk.StringVar(value="Evidence not evaluated")
        self.readiness_var = tk.StringVar(value="Verification currency: —")
        self.readiness_value = tk.DoubleVar(value=0.0)
        self._build(
            open_design_callback=open_design_callback,
            open_problems_callback=open_problems_callback,
            open_proofgraph_callback=open_proofgraph_callback,
            verify_callback=verify_callback,
        )

    def _build(
        self,
        *,
        open_design_callback: Callable[[], None] | None,
        open_problems_callback: Callable[[], None] | None,
        open_proofgraph_callback: Callable[[], None] | None,
        verify_callback: Callable[[], None] | None,
    ) -> None:
        header = ttk.Frame(self, style="CX.PanelHeader.TFrame", padding=(12, 8))
        header.pack(fill="x", padx=8, pady=(8, 5))
        ttk.Label(header, textvariable=self.project_var, style="CX.PanelHeader.TLabel").pack(
            side="left"
        )
        ttk.Label(header, textvariable=self.subtitle_var, style="CX.PanelHint.TLabel").pack(
            side="left", padx=(12, 0)
        )
        ttk.Button(
            header,
            text="Refresh",
            command=self.refresh,
            style="CX.Compact.TButton",
        ).pack(side="right")

        metrics = ttk.Frame(self)
        metrics.pack(fill="x", padx=8, pady=(0, 6))
        for column in range(4):
            metrics.columnconfigure(column, weight=1, uniform="dashboard-card")

        cards = (
            ("MODEL", self.model_kpi_var, self.model_detail_var, "CX.Domain.Geometry.TLabel"),
            (
                "VERIFICATION",
                self.verify_kpi_var,
                self.verify_detail_var,
                "CX.Domain.Evidence.TLabel",
            ),
            ("ISSUES", self.issues_kpi_var, self.issues_detail_var, "CX.Domain.Warning.TLabel"),
            (
                "EVIDENCE",
                self.evidence_kpi_var,
                self.evidence_detail_var,
                "CX.Domain.Pressure.TLabel",
            ),
        )
        for column, (title, kpi, detail, title_style) in enumerate(cards):
            card = ttk.Frame(metrics, style="CX.Card.TFrame")
            card.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 3, 0))
            ttk.Label(card, text=title, style=title_style).pack(anchor="w")
            ttk.Label(card, textvariable=kpi, style="CX.Kpi.TLabel").pack(anchor="w", pady=(4, 1))
            ttk.Label(
                card,
                textvariable=detail,
                style="CX.CardBody.TLabel",
                wraplength=210,
                justify="left",
            ).pack(anchor="w")

        currency = ttk.Frame(self, style="CX.Card.TFrame")
        currency.pack(fill="x", padx=8, pady=(0, 6))
        ttk.Label(
            currency,
            textvariable=self.readiness_var,
            style="CX.CardTitle.TLabel",
        ).pack(anchor="w")
        self.readiness_bar = ttk.Progressbar(
            currency,
            variable=self.readiness_value,
            maximum=100.0,
            style="CX.Engineering.Horizontal.TProgressbar",
        )
        self.readiness_bar.pack(fill="x", pady=(5, 0))

        actions = ttk.Frame(self, style="CX.Toolbar.TFrame")
        actions.pack(fill="x", padx=8, pady=(0, 6))
        for label, callback, style in (
            ("Open Design", open_design_callback, "CX.Info.TButton"),
            ("Problems", open_problems_callback, "CX.Warning.TButton"),
            ("ProofGraph", open_proofgraph_callback, "CX.Violet.TButton"),
            ("Save & Verify", verify_callback, "CX.Success.TButton"),
        ):
            button = ttk.Button(
                actions,
                text=label,
                command=callback if callback is not None else lambda: None,
                style=style,
                state="normal" if callback is not None else "disabled",
            )
            button.pack(side="left", padx=(0, 4))

        issues_host = ttk.Frame(self, style="CX.Panel.TFrame")
        issues_host.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        issues_header = ttk.Frame(issues_host, style="CX.PanelHeader.TFrame")
        issues_header.pack(fill="x")
        ttk.Label(
            issues_header,
            text="CRITICAL ENGINEERING ISSUES",
            style="CX.PanelHeader.TLabel",
        ).pack(side="left")
        ttk.Label(
            issues_header,
            text="Double-click an issue to locate the affected object",
            style="CX.PanelHint.TLabel",
        ).pack(side="right")

        columns = ("severity", "code", "object", "description")
        self.issue_tree = ttk.Treeview(
            issues_host,
            columns=columns,
            show="headings",
            height=8,
            style="CX.Table.Treeview",
            selectmode="browse",
        )
        for column, title, width, stretch in (
            ("severity", "Severity", 85, False),
            ("code", "Code", 175, False),
            ("object", "Object", 150, False),
            ("description", "Description", 540, True),
        ):
            self.issue_tree.heading(column, text=title)
            self.issue_tree.column(column, width=width, minwidth=70, stretch=stretch)
        self.issue_tree.tag_configure("error", foreground="#EF4444", font=("TkDefaultFont", 9, "bold"))
        self.issue_tree.tag_configure("warning", foreground="#F59E0B")
        self.issue_tree.tag_configure("info", foreground="#38BDF8")
        scroll = ttk.Scrollbar(issues_host, orient="vertical", command=self.issue_tree.yview)
        self.issue_tree.configure(yscrollcommand=scroll.set)
        self.issue_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.issue_tree.bind("<Double-1>", self._navigate_selected)
        self.issue_tree.bind("<Return>", self._navigate_selected)

    @staticmethod
    def _issue_object(issue: dict[str, Any]) -> str:
        element = issue.get("element")
        if not isinstance(element, dict):
            return "project"
        return str(element.get("name") or element.get("id") or element.get("type") or "project")

    def refresh(
        self,
        *,
        diagnostics: dict[str, Any] | None = None,
        currency: dict[str, Any] | None = None,
        records: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        project = self._project_getter()
        project_name = str(getattr(project, "name", "") or "Untitled project")
        analyses = list(getattr(project, "analyses", ()) or ())
        self.project_var.set(f"PROJECT HEALTH · {project_name}")

        spatial: dict[str, int] = {}
        if self._spatial_summary_getter is not None:
            try:
                spatial = dict(self._spatial_summary_getter() or {})
            except Exception:
                spatial = {}
        rooms = int(spatial.get("rooms", 0) or 0)
        devices = int(spatial.get("devices", 0) or 0)
        self.model_kpi_var.set(f"{rooms} rooms")
        self.model_detail_var.set(f"{devices} devices · {len(analyses)} configured analyses")

        if diagnostics is None:
            try:
                diagnostics = analyze_project_diagnostics(
                    project,
                    base_dir=self._base_dir_getter(),
                )
            except Exception as exc:
                diagnostics = {"summary": {}, "issues": []}
                self.issues_kpi_var.set("Unavailable")
                self.issues_detail_var.set(str(exc))
        diag_summary = diagnostics.get("summary", {}) if isinstance(diagnostics, dict) else {}
        errors = int(diag_summary.get("error_count", 0) or 0)
        warnings = int(diag_summary.get("warning_count", 0) or 0)
        info = int(diag_summary.get("info_count", 0) or 0)
        self.issues_kpi_var.set(str(errors + warnings))
        self.issues_detail_var.set(f"{errors} error · {warnings} warning · {info} info")

        if currency is None:
            try:
                currency = assess_project_verification_currency(
                    project,
                    base_dir=self._base_dir_getter(),
                )
            except Exception:
                currency = {"summary": {}, "analyses": []}
        verify_summary = currency.get("summary", {}) if isinstance(currency, dict) else {}
        configured = int(verify_summary.get("configured_analysis_count", 0) or 0)
        current = int(verify_summary.get("current_count", 0) or 0)
        stale = int(verify_summary.get("stale_count", 0) or 0)
        not_verified = int(verify_summary.get("not_verified_count", 0) or 0)
        percent = (100.0 * current / configured) if configured else 0.0
        self.readiness_value.set(percent)
        self.readiness_var.set(
            f"Verification currency: {current}/{configured} current ({percent:.0f}%)"
            if configured
            else "Verification currency: no configured analyses"
        )
        self.verify_kpi_var.set(f"{current}/{configured}" if configured else "—")
        self.verify_detail_var.set(f"{stale} stale · {not_verified} not verified")

        if records is None:
            try:
                records = verification_run_history_records(getattr(project, "metadata", {}))
            except Exception:
                records = []
        records = list(records or [])
        self.evidence_kpi_var.set(str(len(records)))
        if records:
            latest = records[-1]
            verification = latest.get("verification", {}) if isinstance(latest, dict) else {}
            status = str(verification.get("status", "unknown")).upper()
            self.evidence_detail_var.set(f"Retained verification runs · latest {status}")
        else:
            self.evidence_detail_var.set("No persisted project-verification evidence")

        self._populate_issues(diagnostics)
        return {
            "diagnostics": diagnostics,
            "currency": currency,
            "records": records,
            "verification_currency_percent": percent,
        }

    def _populate_issues(self, diagnostics: dict[str, Any] | None) -> None:
        for iid in self.issue_tree.get_children():
            self.issue_tree.delete(iid)
        self._issues_by_iid.clear()
        issues = diagnostics.get("issues", []) if isinstance(diagnostics, dict) else []
        normalized = [item for item in issues if isinstance(item, dict)]
        rank = {"error": 0, "warning": 1, "info": 2}
        normalized.sort(
            key=lambda item: (
                rank.get(str(item.get("severity", "info")).casefold(), 3),
                int(item.get("sequence", 0) or 0),
            )
        )
        for index, issue in enumerate(normalized[:10], start=1):
            iid = f"dashboard-issue:{index}"
            severity = str(issue.get("severity", "info")).casefold()
            self.issue_tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    severity.upper(),
                    issue.get("rule", ""),
                    self._issue_object(issue),
                    issue.get("message", ""),
                ),
                tags=(severity,),
            )
            self._issues_by_iid[iid] = issue
        if not normalized:
            self.issue_tree.insert(
                "",
                "end",
                iid="dashboard-empty",
                values=("PASS", "—", "Project", "No current diagnostics issues detected."),
            )

    def selected_issue(self) -> dict[str, Any] | None:
        selection = self.issue_tree.selection()
        return self._issues_by_iid.get(selection[0]) if selection else None

    def _navigate_selected(self, _event=None):
        issue = self.selected_issue()
        if issue is None:
            return "break"
        if self._navigate_issue_callback is not None:
            self._navigate_issue_callback(issue)
        else:
            self._status_setter("No diagnostic navigation target configured")
        return "break"
