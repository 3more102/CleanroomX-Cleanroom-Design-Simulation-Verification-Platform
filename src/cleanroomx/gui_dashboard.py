from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any
import tkinter as tk
from tkinter import ttk


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def project_health_snapshot(
    project: Any,
    diagnostics: dict[str, Any] | None,
    proofgraph_documents: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Aggregate existing project/evidence state for presentation only."""
    metadata = getattr(project, "metadata", {})
    layout = metadata.get("spatial_layout", {}) if isinstance(metadata, dict) else {}
    rooms = _list(layout.get("rooms")) if isinstance(layout, dict) else []
    devices = _list(layout.get("devices")) if isinstance(layout, dict) else []

    payload = diagnostics if isinstance(diagnostics, dict) else {}
    summary = payload.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
    issues = _list(payload.get("issues"))
    currency = payload.get("verification_currency", {})
    currency_summary = (
        currency.get("summary", {})
        if isinstance(currency, dict)
        else {}
    )
    if not isinstance(currency_summary, dict):
        currency_summary = {}

    documents = [item for item in proofgraph_documents if isinstance(item, dict)]
    latest = documents[0] if documents else {}
    requirement_set = latest.get("requirement_set", {}) if latest else {}
    requirements = (
        _list(requirement_set.get("requirements"))
        if isinstance(requirement_set, dict)
        else []
    )
    evidence = _list(latest.get("evidence")) if latest else []
    findings = _list(latest.get("findings")) if latest else []
    verdicts = _list(latest.get("verdicts")) if latest else []

    evidence_present = sum(
        isinstance(item, dict) and item.get("evidence_present") is True
        for item in findings
    )
    unresolved_evidence = sum(
        isinstance(item, dict) and item.get("evidence_present") is False
        for item in findings
    )
    evidence_completeness = (
        round(100.0 * evidence_present / len(findings), 1)
        if findings
        else None
    )
    verdict_pass = sum(
        isinstance(item, dict)
        and str(item.get("status", "")).casefold() == "pass"
        for item in verdicts
    )
    verdict_fail = sum(
        isinstance(item, dict)
        and str(item.get("status", "")).casefold()
        in {"fail", "failed", "error"}
        for item in verdicts
    )
    stale_result_issues = sum(
        isinstance(item, dict)
        and str(item.get("rule", "")).casefold()
        in {
            "run_history.current_input_not_run",
            "run_history.external_dependency_stale",
            "verification_currency.stale",
        }
        for item in issues
    )

    return {
        "project_name": str(getattr(project, "name", "") or "Untitled project"),
        "analysis_count": len(getattr(project, "analyses", ())),
        "room_count": len(rooms),
        "device_count": len(devices),
        "diagnostic_status": str(summary.get("status", "unavailable")),
        "error_count": int(summary.get("error_count", 0) or 0),
        "warning_count": int(summary.get("warning_count", 0) or 0),
        "info_count": int(summary.get("info_count", 0) or 0),
        "configured_analysis_count": int(
            currency_summary.get("configured_analysis_count", 0) or 0
        ),
        "current_verification_count": int(
            currency_summary.get("current_count", 0) or 0
        ),
        "stale_verification_count": int(
            currency_summary.get("stale_count", 0) or 0
        ),
        "not_verified_count": int(
            currency_summary.get("not_verified_count", 0) or 0
        ),
        "proofgraph_count": len(documents),
        "requirement_count": len(requirements),
        "evidence_count": len(evidence),
        "finding_count": len(findings),
        "evidence_present_count": evidence_present,
        "unresolved_evidence_count": unresolved_evidence,
        "evidence_completeness_percent": evidence_completeness,
        "verdict_count": len(verdicts),
        "verdict_pass_count": verdict_pass,
        "verdict_fail_count": verdict_fail,
        "stale_result_issue_count": stale_result_issues,
        "issues": issues,
    }


class ProjectHealthDashboard(ttk.Frame):
    """Actionable project health view backed only by canonical project evidence."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_design: Callable[[], None],
        on_analysis: Callable[[], None],
        on_problems: Callable[[], None],
        on_verification: Callable[[], None],
        on_evidence: Callable[[], None],
        on_reporting: Callable[[], None],
        on_diagnostic: Callable[[object], None] | None = None,
    ) -> None:
        super().__init__(master, padding=(18, 14))
        self._on_diagnostic = on_diagnostic
        self._issue_sequences: dict[str, object] = {}
        self.title_var = tk.StringVar(value="Project Health")
        self.summary_var = tk.StringVar(value="No project health data")
        self._metrics: dict[str, tk.StringVar] = {}
        self._details: dict[str, tk.StringVar] = {}

        header = ttk.Frame(self)
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(
            header,
            textvariable=self.title_var,
            style="CX.Brand.TLabel",
        ).pack(side="left")
        ttk.Label(
            header,
            textvariable=self.summary_var,
            anchor="e",
        ).pack(side="right", fill="x", expand=True)

        metrics = ttk.Frame(self)
        metrics.pack(fill="x")
        for column in range(3):
            metrics.columnconfigure(column, weight=1)

        cards = (
            ("model", "MODEL", on_design),
            ("diagnostics", "DIAGNOSTICS", on_problems),
            ("verification", "VERIFICATION", on_verification),
            ("evidence", "EVIDENCE", on_evidence),
            ("verdicts", "VERDICTS", on_evidence),
            ("results", "RESULT FRESHNESS", on_analysis),
        )
        for index, (key, title, callback) in enumerate(cards):
            card = ttk.LabelFrame(metrics, text=title, padding=(10, 8))
            card.grid(
                row=index // 3,
                column=index % 3,
                sticky="nsew",
                padx=4,
                pady=4,
            )
            value = tk.StringVar(value="—")
            detail = tk.StringVar(value="")
            self._metrics[key] = value
            self._details[key] = detail
            ttk.Label(
                card,
                textvariable=value,
                style="CX.ViewTitle.TLabel",
            ).pack(anchor="w")
            ttk.Label(
                card,
                textvariable=detail,
                wraplength=300,
                justify="left",
            ).pack(anchor="w", fill="x", expand=True, pady=(4, 6))
            ttk.Button(
                card,
                text="Open",
                style="CX.Compact.TButton",
                command=callback,
            ).pack(anchor="e")

        attention = ttk.LabelFrame(self, text="Attention", padding=8)
        attention.pack(fill="both", expand=True, pady=(10, 0))
        columns = ("severity", "rule", "object", "finding")
        self.tree = ttk.Treeview(
            attention,
            columns=columns,
            show="headings",
            selectmode="browse",
            height=7,
        )
        for column, label, width in (
            ("severity", "Severity", 90),
            ("rule", "Rule", 220),
            ("object", "Object", 160),
            ("finding", "Finding", 520),
        ):
            self.tree.heading(column, text=label)
            self.tree.column(
                column,
                width=width,
                minwidth=70,
                stretch=column == "finding",
            )
        scroll = ttk.Scrollbar(
            attention,
            orient="vertical",
            command=self.tree.yview,
        )
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self._open_selected_issue)
        self.tree.bind("<Return>", self._open_selected_issue)

        footer = ttk.Frame(self)
        footer.pack(fill="x", pady=(8, 0))
        ttk.Button(
            footer,
            text="Open Reports",
            command=on_reporting,
        ).pack(side="right")

    def refresh(
        self,
        project: Any,
        diagnostics: dict[str, Any] | None,
        proofgraph_documents: Iterable[dict[str, Any]] = (),
    ) -> dict[str, Any]:
        snapshot = project_health_snapshot(
            project,
            diagnostics,
            proofgraph_documents,
        )
        self.title_var.set(f"Project Health · {snapshot['project_name']}")
        self.summary_var.set(
            f"{snapshot['diagnostic_status'].upper()} · "
            f"{snapshot['error_count']} errors · "
            f"{snapshot['warning_count']} warnings"
        )

        self._metrics["model"].set(
            f"{snapshot['room_count']} rooms · {snapshot['device_count']} devices"
        )
        self._details["model"].set(
            f"{snapshot['analysis_count']} configured analyses"
        )
        self._metrics["diagnostics"].set(
            f"{snapshot['error_count']} errors · "
            f"{snapshot['warning_count']} warnings"
        )
        self._details["diagnostics"].set(
            f"{snapshot['info_count']} informational findings"
        )

        configured = snapshot["configured_analysis_count"]
        current = snapshot["current_verification_count"]
        self._metrics["verification"].set(
            f"{current}/{configured} current" if configured else "Not configured"
        )
        self._details["verification"].set(
            f"{snapshot['stale_verification_count']} stale · "
            f"{snapshot['not_verified_count']} not verified"
        )

        completeness = snapshot["evidence_completeness_percent"]
        self._metrics["evidence"].set(
            f"{completeness:g}% complete"
            if completeness is not None
            else "No finding evidence"
        )
        self._details["evidence"].set(
            f"{snapshot['evidence_count']} evidence nodes · "
            f"{snapshot['unresolved_evidence_count']} unresolved · "
            f"{snapshot['proofgraph_count']} graphs"
        )
        self._metrics["verdicts"].set(
            f"{snapshot['verdict_pass_count']} pass · "
            f"{snapshot['verdict_fail_count']} fail"
        )
        self._details["verdicts"].set(
            f"{snapshot['verdict_count']} persisted verdicts · "
            f"{snapshot['requirement_count']} requirements"
        )
        self._metrics["results"].set(
            f"{snapshot['stale_result_issue_count']} stale"
            if snapshot["stale_result_issue_count"]
            else "Current / no stale finding"
        )
        self._details["results"].set(
            "Derived from run-history and dependency diagnostics"
        )

        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._issue_sequences.clear()
        issues = [
            item
            for item in snapshot["issues"]
            if isinstance(item, dict)
            and str(item.get("severity", "")).casefold() in {"error", "warning"}
        ]
        severity_order = {"error": 0, "warning": 1}
        issues.sort(
            key=lambda item: (
                severity_order.get(
                    str(item.get("severity", "")).casefold(),
                    99,
                ),
                int(item.get("sequence") or 0),
            )
        )
        for index, issue in enumerate(issues[:20]):
            element = issue.get("element")
            object_text = "project"
            if isinstance(element, dict):
                object_text = str(
                    element.get("name")
                    or element.get("id")
                    or element.get("type")
                    or "project"
                )
            iid = f"issue-{index}"
            self._issue_sequences[iid] = issue.get("sequence")
            self.tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    str(issue.get("severity", "info")).upper(),
                    issue.get("rule", ""),
                    object_text,
                    issue.get("message", ""),
                ),
            )
        if not issues:
            self.tree.insert(
                "",
                "end",
                iid="empty",
                values=("PASS", "—", "Project", "No error or warning diagnostics."),
            )
        return snapshot

    def _open_selected_issue(self, _event=None):
        if self._on_diagnostic is None:
            return "break"
        selection = self.tree.selection()
        if not selection:
            return "break"
        sequence = self._issue_sequences.get(selection[0])
        if sequence is not None:
            self._on_diagnostic(sequence)
        return "break"
