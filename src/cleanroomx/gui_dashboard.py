from __future__ import annotations

from collections.abc import Callable
from typing import Any

import tkinter as tk
from tkinter import ttk

from .gui_theme import engineering_status_style


class ProjectDashboard(ttk.Frame):
    """Dense project-health dashboard derived only from canonical app state."""

    _SEVERITY_ORDER = {"critical": 0, "error": 0, "warning": 1, "info": 2}

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_issue: Callable[[dict[str, Any]], None] | None = None,
        on_open_design: Callable[[], None] | None = None,
        on_open_problems: Callable[[], None] | None = None,
        on_open_proofgraph: Callable[[], None] | None = None,
        on_verify: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master, padding=(12, 10))
        self._on_issue = on_issue
        self._issue_by_iid: dict[str, dict[str, Any]] = {}
        self._system_badges: dict[str, ttk.Label] = {}
        self._system_values: dict[str, tk.StringVar] = {}
        self._vars = {
            "project": tk.StringVar(value="Untitled"),
            "location": tk.StringVar(value="Unsaved project"),
            "diagnostics": tk.StringVar(value="NOT CHECKED"),
            "diagnostic_detail": tk.StringVar(value="No diagnostics evaluated"),
            "analyses": tk.StringVar(value="0 configured"),
            "verification": tk.StringVar(value="NOT CHECKED"),
            "verification_detail": tk.StringVar(value="No verification currency"),
            "verification_coverage": tk.StringVar(value="No verification targets configured"),
            "evidence": tk.StringVar(value="0 retained records"),
            "model": tk.StringVar(value="READY"),
            "run": tk.StringVar(value="IDLE"),
            "issues": tk.StringVar(value="Diagnostics have not been evaluated"),
        }

        header = ttk.Frame(self, style="CX.PanelHeader.TFrame")
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(
            header,
            text="PROJECT HEALTH / ENGINEERING READINESS",
            style="CX.PanelHeader.TLabel",
        ).pack(side="left")
        self.model_badge = ttk.Label(
            header,
            textvariable=self._vars["model"],
            style="CX.Badge.Unknown.TLabel",
        )
        self.model_badge.pack(side="right")

        identity = ttk.LabelFrame(
            self,
            text="ACTIVE PROJECT",
            padding=(10, 8),
            style="CX.Card.TLabelframe",
        )
        identity.pack(fill="x", pady=(0, 8))

        identity_text = ttk.Frame(identity, style="CX.Panel.TFrame")
        identity_text.pack(side="left", fill="x", expand=True)
        ttk.Label(
            identity_text,
            textvariable=self._vars["project"],
            style="CX.PanelTitle.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            identity_text,
            textvariable=self._vars["location"],
            style="CX.PanelMuted.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        actions = ttk.Frame(identity, style="CX.Panel.TFrame")
        actions.pack(side="right", padx=(10, 0))
        action_specs = (
            ("Design", on_open_design),
            ("Problems", on_open_problems),
            ("ProofGraph", on_open_proofgraph),
            ("Save & Verify", on_verify),
        )
        for label, callback in action_specs:
            ttk.Button(
                actions,
                text=label,
                style="CX.Compact.TButton",
                command=callback if callback is not None else lambda: None,
                state="normal" if callback is not None else "disabled",
            ).pack(side="left", padx=1)

        readiness = ttk.LabelFrame(
            self,
            text="VERIFICATION COVERAGE",
            padding=(10, 8),
            style="CX.Card.TLabelframe",
        )
        readiness.pack(fill="x", pady=(0, 8))
        coverage_header = ttk.Frame(readiness, style="CX.Panel.TFrame")
        coverage_header.pack(fill="x")
        self.verification_badge = ttk.Label(
            coverage_header,
            textvariable=self._vars["verification"],
            style="CX.Badge.Unknown.TLabel",
        )
        self.verification_badge.pack(side="left")
        ttk.Label(
            coverage_header,
            textvariable=self._vars["verification_detail"],
            style="CX.PanelMuted.TLabel",
        ).pack(side="right")
        self.verification_progress = ttk.Progressbar(
            readiness,
            orient="horizontal",
            mode="determinate",
            maximum=100,
            style="CX.Engineering.Horizontal.TProgressbar",
        )
        self.verification_progress.pack(fill="x", pady=(8, 4))
        ttk.Label(
            readiness,
            textvariable=self._vars["verification_coverage"],
            style="CX.PanelMuted.TLabel",
        ).pack(anchor="w")

        system = ttk.LabelFrame(
            self,
            text="SYSTEM STATUS",
            padding=(8, 7),
            style="CX.Card.TLabelframe",
        )
        system.pack(fill="x", pady=(0, 8))
        modules = (
            ("diagnostics", "DIAGNOSTICS / DRC"),
            ("verification", "VERIFICATION"),
            ("analyses", "ANALYSES"),
            ("evidence", "EVIDENCE"),
            ("run", "SOLVER"),
        )
        for index, (key, label) in enumerate(modules):
            cell = ttk.Frame(system, style="CX.Panel.TFrame", padding=(6, 4))
            cell.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 2, 0))
            system.columnconfigure(index, weight=1, uniform="system")
            ttk.Label(
                cell,
                text=label,
                style="CX.PanelSection.TLabel",
            ).pack(anchor="w")
            value = tk.StringVar(value="—")
            self._system_values[key] = value
            badge = ttk.Label(
                cell,
                textvariable=value,
                style="CX.Badge.Unknown.TLabel",
            )
            badge.pack(anchor="w", pady=(4, 0))
            self._system_badges[key] = badge

        issues = ttk.LabelFrame(
            self,
            text="CRITICAL ENGINEERING ISSUES",
            padding=(8, 7),
            style="CX.Card.TLabelframe",
        )
        issues.pack(fill="both", expand=True)
        issue_header = ttk.Frame(issues, style="CX.Panel.TFrame")
        issue_header.pack(fill="x", pady=(0, 5))
        ttk.Label(
            issue_header,
            textvariable=self._vars["issues"],
            style="CX.PanelMuted.TLabel",
        ).pack(side="left")
        if on_open_problems is not None:
            ttk.Button(
                issue_header,
                text="Open Problems",
                style="CX.Compact.TButton",
                command=on_open_problems,
            ).pack(side="right")

        columns = ("severity", "code", "object", "domain", "description")
        self.issue_tree = ttk.Treeview(
            issues,
            columns=columns,
            show="headings",
            selectmode="browse",
            height=7,
        )
        headings = {
            "severity": "Severity",
            "code": "Code",
            "object": "Object",
            "domain": "Domain",
            "description": "Description",
        }
        widths = {
            "severity": 86,
            "code": 150,
            "object": 145,
            "domain": 110,
            "description": 420,
        }
        for column in columns:
            self.issue_tree.heading(column, text=headings[column])
            self.issue_tree.column(
                column,
                width=widths[column],
                minwidth=70,
                stretch=column == "description",
            )
        issue_scroll = ttk.Scrollbar(
            issues,
            orient="vertical",
            command=self.issue_tree.yview,
        )
        self.issue_tree.configure(yscrollcommand=issue_scroll.set)
        self.issue_tree.pack(side="left", fill="both", expand=True)
        issue_scroll.pack(side="right", fill="y")
        self.issue_tree.bind("<Double-1>", self._open_selected_issue)
        self.issue_tree.bind("<Return>", self._open_selected_issue)
        self.issue_tree.tag_configure("error", font=("TkDefaultFont", 9, "bold"))
        self.issue_tree.tag_configure("critical", font=("TkDefaultFont", 9, "bold"))
        self.issue_tree.tag_configure("warning", font=("TkDefaultFont", 9, "bold"))

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

    def _populate_issues(self, issues: Any) -> None:
        for iid in self.issue_tree.get_children():
            self.issue_tree.delete(iid)
        self._issue_by_iid.clear()

        candidates = [issue for issue in issues or [] if isinstance(issue, dict)]
        def sequence_key(issue: dict[str, Any]) -> tuple[int, str]:
            raw = issue.get("sequence")
            try:
                return (0, f"{int(raw):012d}")
            except (TypeError, ValueError):
                return (1, str(raw or ""))

        candidates.sort(
            key=lambda issue: (
                self._SEVERITY_ORDER.get(
                    str(issue.get("severity") or "info").casefold(),
                    3,
                ),
                sequence_key(issue),
            )
        )
        important = [
            issue
            for issue in candidates
            if str(issue.get("severity") or "").casefold()
            in {"critical", "error", "warning"}
        ][:8]

        if not important:
            if candidates:
                self._vars["issues"].set("No unresolved error/warning diagnostics")
            else:
                self._vars["issues"].set("No diagnostic issues reported")
            return

        error_count = sum(
            str(issue.get("severity") or "").casefold() in {"critical", "error"}
            for issue in important
        )
        warning_count = sum(
            str(issue.get("severity") or "").casefold() == "warning"
            for issue in important
        )
        self._vars["issues"].set(
            f"{error_count} error(s) · {warning_count} warning(s) · showing top {len(important)}"
        )
        for index, issue in enumerate(important, start=1):
            severity = str(issue.get("severity") or "info").casefold()
            iid = f"issue:{index}"
            self.issue_tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    severity.upper(),
                    issue.get("rule", ""),
                    self._element_text(issue),
                    issue.get("category", ""),
                    issue.get("message", ""),
                ),
                tags=(severity,),
            )
            self._issue_by_iid[iid] = issue

    def _open_selected_issue(self, _event=None):
        if self._on_issue is None:
            return "break"
        selection = self.issue_tree.selection()
        if not selection:
            return "break"
        issue = self._issue_by_iid.get(selection[0])
        if issue is not None:
            self._on_issue(issue)
        return "break"

    def set_snapshot(self, snapshot: dict[str, Any]) -> None:
        project_name = str(snapshot.get("project_name") or "Untitled")
        location = str(snapshot.get("location") or "Unsaved project")
        analyses = max(0, int(snapshot.get("analysis_count") or 0))
        evidence = max(0, int(snapshot.get("evidence_count") or 0))

        errors = max(0, int(snapshot.get("diagnostic_errors") or 0))
        warnings = max(0, int(snapshot.get("diagnostic_warnings") or 0))
        diagnostic_status = str(snapshot.get("diagnostic_status") or "not checked")
        if errors:
            diagnostic_state = "FAIL"
        elif warnings:
            diagnostic_state = "WARNING"
        elif diagnostic_status.casefold() in {"pass", "passed", "ok", "complete"}:
            diagnostic_state = "PASS"
        else:
            diagnostic_state = diagnostic_status.upper()

        current = max(0, int(snapshot.get("verification_current") or 0))
        stale = max(0, int(snapshot.get("verification_stale") or 0))
        not_verified = max(0, int(snapshot.get("verification_not_verified") or 0))
        configured = max(0, int(snapshot.get("verification_configured") or analyses))
        if configured == 0:
            verification_state = "NOT CHECKED"
        elif stale or not_verified:
            verification_state = "STALE" if stale else "UNVERIFIED"
        elif current == configured:
            verification_state = "VERIFIED"
        else:
            verification_state = "INCOMPLETE"

        if configured:
            coverage = max(0.0, min(100.0, (current / configured) * 100.0))
            coverage_text = (
                f"{current} of {configured} configured analyses have current verification "
                f"({coverage:.0f}%)."
            )
        else:
            coverage = 0.0
            coverage_text = "No verification targets configured."

        model_state = str(snapshot.get("model_state") or "ready").upper()
        run_state = str(snapshot.get("run_state") or "idle").upper()

        self._vars["project"].set(project_name)
        self._vars["location"].set(location)
        self._vars["analyses"].set(f"{analyses} configured")
        self._vars["evidence"].set(
            f"{evidence} retained record{'s' if evidence != 1 else ''}"
        )
        self._vars["diagnostics"].set(diagnostic_state)
        self._vars["diagnostic_detail"].set(
            f"{errors} error(s) · {warnings} warning(s)"
        )
        self._vars["verification"].set(verification_state)
        self._vars["verification_detail"].set(
            f"{current}/{configured} current · {stale} stale · "
            f"{not_verified} not verified"
        )
        self._vars["verification_coverage"].set(coverage_text)
        self._vars["model"].set(model_state)
        self._vars["run"].set(run_state)
        self.verification_progress.configure(value=coverage)

        self.model_badge.configure(style=engineering_status_style(model_state))
        self.verification_badge.configure(
            style=engineering_status_style(verification_state)
        )

        system_values = {
            "diagnostics": diagnostic_state,
            "verification": verification_state,
            "analyses": f"{analyses} CONFIGURED",
            "evidence": f"{evidence} RETAINED",
            "run": run_state,
        }
        for key, value in system_values.items():
            self._system_values[key].set(value)

        self._system_badges["diagnostics"].configure(
            style=engineering_status_style(diagnostic_state)
        )
        self._system_badges["verification"].configure(
            style=engineering_status_style(verification_state)
        )
        self._system_badges["analyses"].configure(
            style=(
                "CX.Badge.Running.TLabel"
                if analyses
                else "CX.Badge.Unknown.TLabel"
            )
        )
        self._system_badges["evidence"].configure(
            style=(
                "CX.Badge.Verified.TLabel"
                if evidence
                else "CX.Badge.Unknown.TLabel"
            )
        )
        self._system_badges["run"].configure(
            style=engineering_status_style(run_state)
        )
        self._populate_issues(snapshot.get("issues"))
