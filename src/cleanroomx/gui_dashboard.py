from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import tkinter as tk
from tkinter import ttk


@dataclass(frozen=True)
class ReadinessMetric:
    name: str
    score: int
    state: str
    detail: str


def _bounded_percent(value: float) -> int:
    return max(0, min(100, int(round(value))))


def _diagnostics_metric(diagnostics: dict[str, Any] | None) -> ReadinessMetric:
    summary = diagnostics.get("summary", {}) if isinstance(diagnostics, dict) else {}
    if not isinstance(summary, dict) or not summary:
        return ReadinessMetric("Diagnostics", 0, "UNKNOWN", "Not evaluated")
    errors = int(summary.get("error_count", 0) or 0)
    warnings = int(summary.get("warning_count", 0) or 0)
    if errors:
        return ReadinessMetric(
            "Diagnostics",
            max(10, 45 - min(35, errors * 8)),
            "FAIL",
            f"{errors} error(s) · {warnings} warning(s)",
        )
    if warnings:
        return ReadinessMetric(
            "Diagnostics",
            max(55, 82 - min(25, warnings * 3)),
            "WARNING",
            f"{warnings} warning(s)",
        )
    return ReadinessMetric("Diagnostics", 100, "PASS", "No error/warning findings")


def _verification_metric(currency: dict[str, Any] | None) -> ReadinessMetric:
    summary = currency.get("summary", {}) if isinstance(currency, dict) else {}
    if not isinstance(summary, dict) or not summary:
        return ReadinessMetric("Verification", 0, "UNKNOWN", "Not evaluated")
    configured = int(summary.get("configured_analysis_count", 0) or 0)
    current = int(summary.get("current_count", 0) or 0)
    stale = int(summary.get("stale_count", 0) or 0)
    not_verified = int(summary.get("not_verified_count", 0) or 0)
    if configured <= 0:
        return ReadinessMetric("Verification", 0, "UNKNOWN", "No configured analyses")
    score = _bounded_percent((current / configured) * 100)
    if current == configured and not stale and not not_verified:
        state = "VERIFIED"
    elif stale:
        state = "STALE"
    elif current:
        state = "WARNING"
    else:
        state = "UNVERIFIED"
    detail = f"{current}/{configured} current"
    if stale:
        detail += f" · {stale} stale"
    if not_verified:
        detail += f" · {not_verified} not verified"
    return ReadinessMetric("Verification", score, state, detail)


def compute_readiness_metrics(
    *,
    analysis_count: int,
    diagnostics: dict[str, Any] | None,
    verification_currency: dict[str, Any] | None,
    verification_record_count: int,
    last_run_status: str | None,
    proofgraph_count: int,
) -> tuple[int, tuple[ReadinessMetric, ...]]:
    """Return a presentation-only operational readiness score.

    This score intentionally does not claim regulatory compliance, qualification,
    commissioning acceptance, or engineering certification. It summarizes whether
    the project has enough current application state for productive review.
    """
    analysis_metric = ReadinessMetric(
        "Analyses",
        100 if analysis_count > 0 else 0,
        "PASS" if analysis_count > 0 else "INCOMPLETE",
        f"{analysis_count} configured",
    )
    diagnostics_metric = _diagnostics_metric(diagnostics)
    verification_metric = _verification_metric(verification_currency)

    evidence_score = 100 if verification_record_count > 0 else 0
    evidence_metric = ReadinessMetric(
        "Evidence",
        evidence_score,
        "VERIFIED" if evidence_score else "INCOMPLETE",
        (
            f"{verification_record_count} retained verification record(s)"
            if verification_record_count
            else "No retained verification record"
        ),
    )

    normalized_run = str(last_run_status or "").strip().casefold()
    if normalized_run in {"pass", "passed", "success", "completed", "ok"}:
        run_score, run_state = 100, "PASS"
    elif normalized_run in {"fail", "failed", "error"}:
        run_score, run_state = 20, "FAIL"
    elif normalized_run in {"running", "queued"}:
        run_score, run_state = 65, "RUNNING"
    elif normalized_run:
        run_score, run_state = 50, "WARNING"
    else:
        run_score, run_state = 0, "NOT CHECKED"
    run_metric = ReadinessMetric(
        "Analysis run",
        run_score,
        run_state,
        str(last_run_status or "No run in current session"),
    )

    graph_metric = ReadinessMetric(
        "ProofGraph",
        100 if proofgraph_count > 0 else 0,
        "VERIFIED" if proofgraph_count > 0 else "INCOMPLETE",
        (
            f"{proofgraph_count} persisted graph(s)"
            if proofgraph_count
            else "No persisted graph"
        ),
    )

    metrics = (
        analysis_metric,
        diagnostics_metric,
        verification_metric,
        evidence_metric,
        run_metric,
        graph_metric,
    )
    weighted = (
        analysis_metric.score * 0.10
        + diagnostics_metric.score * 0.25
        + verification_metric.score * 0.30
        + evidence_metric.score * 0.15
        + run_metric.score * 0.10
        + graph_metric.score * 0.10
    )
    return _bounded_percent(weighted), metrics


def _status_style(state: str) -> str:
    key = str(state or "").strip().casefold()
    if key in {"pass", "passed", "success", "ok"}:
        return "CX.Status.Pass.TLabel"
    if key in {"verified", "current"}:
        return "CX.Status.Verified.TLabel"
    if key in {"fail", "failed", "error", "critical"}:
        return "CX.Status.Fail.TLabel"
    if key in {"warning", "warn", "incomplete", "unverified", "not checked"}:
        return "CX.Status.Warning.TLabel"
    if key in {"running", "queued"}:
        return "CX.Status.Running.TLabel"
    if key == "stale":
        return "CX.Status.Stale.TLabel"
    return "CX.Status.Unknown.TLabel"


class EngineeringDashboard(ttk.Frame):
    """Information-dense presentation surface for current project engineering state."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_open_design: Callable[[], None],
        on_open_problems: Callable[[], None],
        on_verify: Callable[[], None],
        on_run: Callable[[], None],
        on_open_proofgraph: Callable[[], None],
    ) -> None:
        super().__init__(master, padding=(10, 9))
        self._metric_widgets: dict[str, tuple[tk.StringVar, ttk.Label, tk.StringVar]] = {}

        header = ttk.Frame(self)
        header.pack(fill="x", pady=(0, 8))
        title_group = ttk.Frame(header)
        title_group.pack(side="left", fill="x", expand=True)
        ttk.Label(
            title_group,
            text="ENGINEERING DASHBOARD",
            style="CX.ViewTitle.TLabel",
        ).pack(anchor="w")
        self.project_var = tk.StringVar(value="Unsaved project")
        ttk.Label(
            title_group,
            textvariable=self.project_var,
            style="CX.Section.TLabel",
        ).pack(anchor="w", pady=(1, 0))

        actions = ttk.Frame(header)
        actions.pack(side="right")
        ttk.Button(
            actions,
            text="Design",
            style="CX.Compact.TButton",
            command=on_open_design,
        ).pack(side="left", padx=2)
        ttk.Button(
            actions,
            text="Problems",
            style="CX.Compact.TButton",
            command=on_open_problems,
        ).pack(side="left", padx=2)
        ttk.Button(
            actions,
            text="Verify",
            style="CX.Compact.TButton",
            command=on_verify,
        ).pack(side="left", padx=2)
        ttk.Button(
            actions,
            text="▶ Run",
            style="CX.Primary.TButton",
            command=on_run,
        ).pack(side="left", padx=2)
        ttk.Button(
            actions,
            text="ProofGraph",
            style="CX.Compact.TButton",
            command=on_open_proofgraph,
        ).pack(side="left", padx=2)

        readiness = ttk.Frame(self, style="CX.Card.TFrame", padding=(10, 8))
        readiness.pack(fill="x", pady=(0, 8))
        ttk.Label(
            readiness,
            text="PROJECT READINESS",
            style="CX.CardHeader.TLabel",
        ).grid(row=0, column=0, sticky="w")
        self.readiness_var = tk.StringVar(value="0%")
        ttk.Label(
            readiness,
            textvariable=self.readiness_var,
            style="CX.CardValue.TLabel",
        ).grid(row=1, column=0, rowspan=2, sticky="w", padx=(0, 16))
        self.readiness_progress = ttk.Progressbar(
            readiness,
            orient="horizontal",
            mode="determinate",
            maximum=100,
        )
        self.readiness_progress.grid(row=1, column=1, sticky="ew", pady=(4, 2))
        ttk.Label(
            readiness,
            text="Operational UI readiness only — not regulatory compliance or certification.",
            style="CX.CardHint.TLabel",
        ).grid(row=2, column=1, sticky="w")
        readiness.columnconfigure(1, weight=1)

        metrics_host = ttk.Frame(self)
        metrics_host.pack(fill="x", pady=(0, 8))
        for index, name in enumerate(
            ("Analyses", "Diagnostics", "Verification", "Evidence", "Analysis run", "ProofGraph")
        ):
            card = ttk.Frame(metrics_host, style="CX.Card.TFrame", padding=(8, 7))
            card.grid(
                row=0,
                column=index,
                sticky="nsew",
                padx=(0 if index == 0 else 3, 0),
            )
            ttk.Label(card, text=name.upper(), style="CX.CardHeader.TLabel").pack(anchor="w")
            state_var = tk.StringVar(value="UNKNOWN")
            state_label = ttk.Label(
                card,
                textvariable=state_var,
                style="CX.Status.Unknown.TLabel",
            )
            state_label.pack(anchor="w", pady=(6, 4))
            detail_var = tk.StringVar(value="—")
            ttk.Label(
                card,
                textvariable=detail_var,
                style="CX.CardHint.TLabel",
                wraplength=175,
                justify="left",
            ).pack(anchor="w")
            self._metric_widgets[name] = (state_var, state_label, detail_var)
            metrics_host.columnconfigure(index, weight=1, uniform="metric")

        lower = ttk.Panedwindow(self, orient="horizontal")
        lower.pack(fill="both", expand=True)

        issues_host = ttk.Frame(lower, padding=(0, 0, 5, 0))
        history_host = ttk.Frame(lower, padding=(5, 0, 0, 0))
        lower.add(issues_host, weight=3)
        lower.add(history_host, weight=2)

        issue_header = ttk.Frame(issues_host, style="CX.PanelHeader.TFrame")
        issue_header.pack(fill="x")
        ttk.Label(
            issue_header,
            text="CRITICAL ENGINEERING ISSUES",
            style="CX.PanelHeader.TLabel",
        ).pack(side="left")
        self.issue_summary_var = tk.StringVar(value="Not evaluated")
        ttk.Label(
            issue_header,
            textvariable=self.issue_summary_var,
            style="CX.PanelHeader.TLabel",
        ).pack(side="right")

        self.issue_tree = ttk.Treeview(
            issues_host,
            columns=("severity", "code", "message", "object"),
            show="headings",
            selectmode="browse",
            height=10,
        )
        for column, label, width in (
            ("severity", "Severity", 82),
            ("code", "Code", 190),
            ("message", "Description", 420),
            ("object", "Object", 150),
        ):
            self.issue_tree.heading(column, text=label)
            self.issue_tree.column(
                column,
                width=width,
                minwidth=70,
                stretch=column == "message",
            )
        self.issue_tree.pack(fill="both", expand=True)

        history_header = ttk.Frame(history_host, style="CX.PanelHeader.TFrame")
        history_header.pack(fill="x")
        ttk.Label(
            history_header,
            text="VERIFICATION / EVIDENCE ACTIVITY",
            style="CX.PanelHeader.TLabel",
        ).pack(side="left")
        self.history_tree = ttk.Treeview(
            history_host,
            columns=("sequence", "analysis", "status", "time"),
            show="headings",
            selectmode="browse",
            height=10,
        )
        for column, label, width in (
            ("sequence", "#", 48),
            ("analysis", "Analysis", 150),
            ("status", "Status", 95),
            ("time", "Completed", 180),
        ):
            self.history_tree.heading(column, text=label)
            self.history_tree.column(
                column,
                width=width,
                minwidth=45,
                stretch=column in {"analysis", "time"},
            )
        self.history_tree.pack(fill="both", expand=True)

    @staticmethod
    def _element_text(issue: dict[str, Any]) -> str:
        element = issue.get("element")
        if not isinstance(element, dict):
            return "project"
        return str(element.get("name") or element.get("id") or element.get("type") or "project")

    def set_snapshot(
        self,
        *,
        project_name: str,
        analysis_count: int,
        diagnostics: dict[str, Any] | None,
        verification_currency: dict[str, Any] | None,
        verification_records: list[dict[str, Any]],
        last_run_status: str | None,
        proofgraph_count: int,
    ) -> None:
        self.project_var.set(
            f"Project: {project_name or 'Untitled'} · {analysis_count} configured analysis/analyses"
        )
        score, metrics = compute_readiness_metrics(
            analysis_count=analysis_count,
            diagnostics=diagnostics,
            verification_currency=verification_currency,
            verification_record_count=len(verification_records),
            last_run_status=last_run_status,
            proofgraph_count=proofgraph_count,
        )
        self.readiness_var.set(f"{score}%")
        self.readiness_progress.configure(value=score)

        for metric in metrics:
            widgets = self._metric_widgets.get(metric.name)
            if widgets is None:
                continue
            state_var, state_label, detail_var = widgets
            state_var.set(metric.state)
            state_label.configure(style=_status_style(metric.state))
            detail_var.set(metric.detail)

        for iid in self.issue_tree.get_children():
            self.issue_tree.delete(iid)
        issues = diagnostics.get("issues", []) if isinstance(diagnostics, dict) else []
        ranked = {"error": 0, "critical": 0, "warning": 1, "info": 2}
        visible = sorted(
            (issue for issue in issues if isinstance(issue, dict)),
            key=lambda issue: (
                ranked.get(str(issue.get("severity", "")).casefold(), 3),
                int(issue.get("sequence", 0) or 0),
            ),
        )[:12]
        for index, issue in enumerate(visible, start=1):
            severity = str(issue.get("severity", "info")).upper()
            self.issue_tree.insert(
                "",
                "end",
                iid=f"dashboard-issue:{index}",
                values=(
                    severity,
                    issue.get("rule", ""),
                    issue.get("message", ""),
                    self._element_text(issue),
                ),
            )
        summary = diagnostics.get("summary", {}) if isinstance(diagnostics, dict) else {}
        if isinstance(summary, dict) and summary:
            self.issue_summary_var.set(
                "{errors} ERR · {warnings} WARN · {info} INFO".format(
                    errors=summary.get("error_count", 0),
                    warnings=summary.get("warning_count", 0),
                    info=summary.get("info_count", 0),
                )
            )
        else:
            self.issue_summary_var.set("Not evaluated")

        for iid in self.history_tree.get_children():
            self.history_tree.delete(iid)
        for index, record in enumerate(reversed(verification_records[-12:]), start=1):
            verification = record.get("verification", {})
            if not isinstance(verification, dict):
                verification = {}
            self.history_tree.insert(
                "",
                "end",
                iid=f"verification-record:{index}",
                values=(
                    record.get("sequence", "?"),
                    record.get("analysis_name") or record.get("analysis_id") or "analysis",
                    str(verification.get("status", "unknown")).upper(),
                    record.get("completed_at_utc", ""),
                ),
            )
