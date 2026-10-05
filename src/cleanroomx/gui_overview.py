from __future__ import annotations

from typing import Any, Callable

import tkinter as tk
from tkinter import ttk

from .gui_theme import status_style_name


def _count(mapping: dict[str, Any], key: str) -> int:
    try:
        return max(0, int(mapping.get(key, 0) or 0))
    except (TypeError, ValueError):
        return 0


def engineering_overview_snapshot(
    *,
    project_name: str,
    project_path: str | None,
    analysis_count: int,
    diagnostics: dict[str, Any] | None,
    verification_currency: dict[str, Any] | None,
    evidence_record_count: int | None,
    running: bool,
    unsaved: bool,
) -> dict[str, Any]:
    """Build a truthful GUI-only health projection from canonical backend results.

    This helper deliberately does not recalculate engineering quantities.  It only
    summarizes diagnostics, verification-currency output, persisted evidence
    counts, project state, and execution state supplied by the application shell.
    """
    diagnostic_summary = (
        diagnostics.get("summary", {})
        if isinstance(diagnostics, dict)
        else {}
    )
    if not isinstance(diagnostic_summary, dict):
        diagnostic_summary = {}
    errors = _count(diagnostic_summary, "error_count")
    warnings = _count(diagnostic_summary, "warning_count")

    currency_summary = (
        verification_currency.get("summary", {})
        if isinstance(verification_currency, dict)
        else {}
    )
    if not isinstance(currency_summary, dict):
        currency_summary = {}
    configured = _count(currency_summary, "configured_analysis_count")
    current = _count(currency_summary, "current_count")
    stale = _count(currency_summary, "stale_count")
    not_verified = _count(currency_summary, "not_verified_count")
    not_configured = _count(currency_summary, "not_configured_count")
    unverifiable = _count(
        currency_summary,
        "dependency_freshness_unverifiable_count",
    )

    if errors:
        diagnostic_state = "fail"
        diagnostic_detail = f"{errors} error(s), {warnings} warning(s)"
    elif warnings:
        diagnostic_state = "warning"
        diagnostic_detail = f"{warnings} warning(s), no errors"
    elif diagnostics is None:
        diagnostic_state = "neutral"
        diagnostic_detail = "Diagnostics unavailable"
    else:
        diagnostic_state = "pass"
        diagnostic_detail = "No open errors or warnings"

    if verification_currency is None:
        verification_state = "neutral"
        verification_detail = "Verification currency unavailable"
    elif stale or not_verified or not_configured or unverifiable:
        verification_state = "warning"
        verification_detail = (
            f"{current}/{configured} current · {stale} stale · "
            f"{not_verified} not verified · {not_configured} unconfigured · "
            f"{unverifiable} freshness unknown"
        )
    elif configured == 0:
        verification_state = "neutral"
        verification_detail = "No configured verification analyses"
    else:
        verification_state = "pass"
        verification_detail = f"{current}/{configured} configured analyses current"

    evidence_available = evidence_record_count is not None
    evidence_count = (
        max(0, int(evidence_record_count or 0))
        if evidence_available
        else 0
    )
    evidence_state = "pass" if evidence_count else "neutral"
    evidence_detail = (
        f"{evidence_count} retained verification record(s)"
        if evidence_count
        else (
            "No persisted verification evidence"
            if evidence_available
            else "Verification evidence history unavailable"
        )
    )

    project_state = "warning" if unsaved else "pass"
    project_detail = "Unsaved project changes" if unsaved else "Saved state synchronized"
    execution_state = "running" if running else "neutral"
    execution_detail = "Analysis currently running" if running else "No analysis running"

    actions: list[dict[str, str]] = []
    if diagnostics is None:
        actions.append(
            {
                "severity": "warning",
                "title": "Project diagnostics unavailable",
                "detail": "Open Problems and refresh the canonical diagnostics service.",
                "target": "problems",
            }
        )
    if verification_currency is None:
        actions.append(
            {
                "severity": "warning",
                "title": "Verification currency unavailable",
                "detail": "Open Verification and refresh the current project state.",
                "target": "verification",
            }
        )
    if not evidence_available:
        actions.append(
            {
                "severity": "warning",
                "title": "Verification evidence history unavailable",
                "detail": "Open Evidence and inspect persisted verification history.",
                "target": "evidence",
            }
        )
    if errors:
        actions.append(
            {
                "severity": "error",
                "title": f"Resolve {errors} diagnostic error(s)",
                "detail": "Open Problems and navigate to affected engineering objects.",
                "target": "problems",
            }
        )
    if warnings:
        actions.append(
            {
                "severity": "warning",
                "title": f"Review {warnings} diagnostic warning(s)",
                "detail": "Filter the issue browser by severity, rule, category, or object.",
                "target": "problems",
            }
        )
    if stale:
        actions.append(
            {
                "severity": "warning",
                "title": f"Refresh {stale} stale verification result(s)",
                "detail": "Open Verification and rerun the affected canonical workflow.",
                "target": "verification",
            }
        )
    if not_verified:
        actions.append(
            {
                "severity": "warning",
                "title": f"Verify {not_verified} analysis result(s)",
                "detail": "Persist verification evidence after review where appropriate.",
                "target": "verification",
            }
        )
    if unverifiable:
        actions.append(
            {
                "severity": "warning",
                "title": f"Review {unverifiable} dependency freshness state(s)",
                "detail": "Verification currency could not establish dependency freshness.",
                "target": "verification",
            }
        )
    if not_configured:
        actions.append(
            {
                "severity": "info",
                "title": f"Review {not_configured} unconfigured analysis result(s)",
                "detail": "Open Simulation or project requirements to confirm intended coverage.",
                "target": "simulation",
            }
        )
    if evidence_available and not evidence_count:
        actions.append(
            {
                "severity": "info",
                "title": "No retained verification evidence",
                "detail": "Open Evidence after a reviewed verification has been persisted.",
                "target": "evidence",
            }
        )
    if unsaved:
        actions.append(
            {
                "severity": "warning",
                "title": "Save current project changes",
                "detail": "Verification and evidence should reference the intended saved revision.",
                "target": "save",
            }
        )
    if not actions:
        actions.append(
            {
                "severity": "info",
                "title": "No immediate workstation actions",
                "detail": "Current diagnostics and verification-currency summaries show no pending attention.",
                "target": "design",
            }
        )

    unavailable = (
        diagnostics is None
        or verification_currency is None
        or not evidence_available
    )
    overall_state = "fail" if errors else (
        "warning"
        if (
            warnings
            or stale
            or not_verified
            or not_configured
            or unverifiable
            or unsaved
            or unavailable
            or (configured > 0 and evidence_available and evidence_count == 0)
        )
        else "pass"
    )
    overall_text = {
        "fail": "Engineering attention required",
        "warning": "Review recommended",
        "pass": "Workspace ready",
    }[overall_state]

    return {
        "project": {
            "name": str(project_name or "Untitled Project"),
            "path": project_path or "Unsaved project",
            "analysis_count": max(0, int(analysis_count or 0)),
        },
        "overall": {
            "state": overall_state,
            "text": overall_text,
            "note": (
                "Derived from canonical diagnostics, verification currency, "
                "persisted evidence, and application state. This is not a compliance verdict."
            ),
        },
        "cards": [
            {
                "id": "diagnostics",
                "title": "Diagnostics",
                "value": f"{errors}E · {warnings}W",
                "detail": diagnostic_detail,
                "state": diagnostic_state,
                "target": "problems",
            },
            {
                "id": "verification",
                "title": "Verification currency",
                "value": f"{current}/{configured} current" if configured else "Not configured",
                "detail": verification_detail,
                "state": verification_state,
                "target": "verification",
            },
            {
                "id": "evidence",
                "title": "Persisted evidence",
                "value": str(evidence_count) if evidence_available else "Unavailable",
                "detail": evidence_detail,
                "state": evidence_state,
                "target": "evidence",
            },
            {
                "id": "analyses",
                "title": "Configured analyses",
                "value": str(max(0, int(analysis_count or 0))),
                "detail": "Open Simulation for scenario/run controls and retained history.",
                "state": "neutral",
                "target": "simulation",
            },
            {
                "id": "project",
                "title": "Project state",
                "value": "Unsaved" if unsaved else "Saved",
                "detail": project_detail,
                "state": project_state,
                "target": "save" if unsaved else "design",
            },
            {
                "id": "execution",
                "title": "Execution",
                "value": "Running" if running else "Idle",
                "detail": execution_detail,
                "state": execution_state,
                "target": "simulation",
            },
        ],
        "actions": actions,
    }


class EngineeringOverview(ttk.Frame):
    """Actionable project-health surface for the industrial workstation shell."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_open_design: Callable[[], None],
        on_open_simulation: Callable[[], None],
        on_open_verification: Callable[[], None],
        on_open_evidence: Callable[[], None],
        on_open_problems: Callable[[], None],
        on_save: Callable[[], None],
        on_refresh: Callable[[], None],
    ) -> None:
        super().__init__(master, padding=10)
        self._callbacks = {
            "design": on_open_design,
            "simulation": on_open_simulation,
            "verification": on_open_verification,
            "evidence": on_open_evidence,
            "problems": on_open_problems,
            "save": on_save,
        }
        self._on_refresh = on_refresh
        self._snapshot: dict[str, Any] | None = None

        self.title_var = tk.StringVar(value="Engineering Overview")
        self.location_var = tk.StringVar(value="No project health snapshot available")
        self.overall_var = tk.StringVar(value="Not evaluated")
        self.note_var = tk.StringVar(value="")
        self.action_summary_var = tk.StringVar(value="0 actions")

        self._card_widgets: list[tuple[tk.StringVar, tk.StringVar, ttk.Label, ttk.Button]] = []
        self._actions_by_iid: dict[str, dict[str, str]] = {}
        self._build()

    def _build(self) -> None:
        header = ttk.Frame(self)
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(header, textvariable=self.title_var, style="CX.ViewTitle.TLabel").pack(
            side="left"
        )
        ttk.Button(header, text="Refresh", command=self._on_refresh).pack(side="right")

        ttk.Label(
            self,
            textvariable=self.location_var,
            wraplength=980,
            justify="left",
        ).pack(fill="x", pady=(0, 6))

        readiness = ttk.Frame(self, padding=(0, 4))
        readiness.pack(fill="x")
        self.overall_label = ttk.Label(
            readiness,
            textvariable=self.overall_var,
            style="CX.Status.Neutral.TLabel",
        )
        self.overall_label.pack(side="left")
        ttk.Label(readiness, textvariable=self.note_var, wraplength=900).pack(
            side="left", fill="x", expand=True, padx=(12, 0)
        )

        cards = ttk.Frame(self)
        cards.pack(fill="x", pady=(8, 8))
        for index in range(6):
            container = ttk.Frame(cards, padding=7, relief="ridge")
            row, column = divmod(index, 3)
            container.grid(row=row, column=column, sticky="nsew", padx=3, pady=3)
            cards.columnconfigure(column, weight=1)
            value_var = tk.StringVar(value="—")
            detail_var = tk.StringVar(value="Not evaluated")
            title = ttk.Label(container, text="Status", style="CX.Section.TLabel")
            title.pack(anchor="w")
            value = ttk.Label(
                container,
                textvariable=value_var,
                style="CX.Status.Neutral.TLabel",
            )
            value.pack(anchor="w", pady=(4, 2))
            ttk.Label(
                container,
                textvariable=detail_var,
                wraplength=320,
                justify="left",
            ).pack(anchor="w", fill="x", expand=True)
            button = ttk.Button(container, text="Open", state="disabled")
            button.pack(anchor="e", pady=(6, 0))
            self._card_widgets.append((value_var, detail_var, value, button))
            setattr(self, f"_card_title_{index}", title)

        action_header = ttk.Frame(self)
        action_header.pack(fill="x", pady=(2, 4))
        ttk.Label(
            action_header,
            text="ACTION QUEUE",
            style="CX.Section.TLabel",
        ).pack(side="left")
        ttk.Label(action_header, textvariable=self.action_summary_var).pack(side="right")

        table_host = ttk.Frame(self)
        table_host.pack(fill="both", expand=True)
        self.action_tree = ttk.Treeview(
            table_host,
            columns=("severity", "action", "detail"),
            show="headings",
            selectmode="browse",
            height=6,
        )
        self.action_tree.heading("severity", text="State")
        self.action_tree.heading("action", text="Next action")
        self.action_tree.heading("detail", text="Engineering context")
        self.action_tree.column("severity", width=90, minwidth=70, stretch=False)
        self.action_tree.column("action", width=280, minwidth=180)
        self.action_tree.column("detail", width=620, minwidth=240)
        scroll = ttk.Scrollbar(table_host, orient="vertical", command=self.action_tree.yview)
        self.action_tree.configure(yscrollcommand=scroll.set)
        self.action_tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        table_host.rowconfigure(0, weight=1)
        table_host.columnconfigure(0, weight=1)
        self.action_tree.bind("<Double-1>", self._activate_action)
        self.action_tree.bind("<Return>", self._activate_action)

        footer = ttk.Frame(self)
        footer.pack(fill="x", pady=(6, 0))
        ttk.Button(
            footer,
            text="Open selected action",
            command=self._activate_action,
        ).pack(side="right")

    def _open(self, target: str) -> None:
        callback = self._callbacks.get(str(target or ""))
        if callback is not None:
            callback()

    def _activate_action(self, _event=None) -> None:
        selection = self.action_tree.selection()
        if not selection:
            return
        action = self._actions_by_iid.get(selection[0])
        if action is not None:
            self._open(action.get("target", ""))

    def set_snapshot(self, snapshot: dict[str, Any]) -> None:
        self._snapshot = snapshot
        project = snapshot.get("project", {})
        overall = snapshot.get("overall", {})
        name = str(project.get("name") or "Untitled Project")
        path = str(project.get("path") or "Unsaved project")
        analyses = int(project.get("analysis_count", 0) or 0)
        self.title_var.set(f"{name} — Engineering Overview")
        self.location_var.set(f"{path} · {analyses} configured analysis/analyses")
        self.overall_var.set(str(overall.get("text") or "Not evaluated"))
        self.note_var.set(str(overall.get("note") or ""))
        self.overall_label.configure(
            style=status_style_name(overall.get("state"))
        )

        cards = snapshot.get("cards", [])
        for index, widgets in enumerate(self._card_widgets):
            value_var, detail_var, value_label, button = widgets
            card = cards[index] if index < len(cards) else {}
            title_label = getattr(self, f"_card_title_{index}")
            title_label.configure(text=str(card.get("title") or "Status"))
            value_var.set(str(card.get("value") or "—"))
            detail_var.set(str(card.get("detail") or "Not evaluated"))
            value_label.configure(style=status_style_name(card.get("state")))
            target = str(card.get("target") or "")
            button.configure(
                text="Open",
                state="normal" if target in self._callbacks else "disabled",
                command=lambda selected=target: self._open(selected),
            )

        for iid in self.action_tree.get_children():
            self.action_tree.delete(iid)
        self._actions_by_iid.clear()
        actions = [
            item
            for item in snapshot.get("actions", [])
            if isinstance(item, dict)
        ]
        for index, action in enumerate(actions):
            iid = f"action-{index}"
            severity = str(action.get("severity") or "info").upper()
            self.action_tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    severity,
                    str(action.get("title") or "Review project"),
                    str(action.get("detail") or ""),
                ),
            )
            self._actions_by_iid[iid] = {
                key: str(value)
                for key, value in action.items()
            }
        self.action_summary_var.set(
            f"{len(actions)} action" + ("" if len(actions) == 1 else "s")
        )
        if actions:
            first = self.action_tree.get_children()[0]
            self.action_tree.selection_set(first)
            self.action_tree.focus(first)
