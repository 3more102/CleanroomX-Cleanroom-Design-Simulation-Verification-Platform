from __future__ import annotations

from typing import Any, Callable

import tkinter as tk
from tkinter import ttk

from .gui_theme import attach_tooltip, status_style_name


def _count(mapping: Any, key: str) -> int:
    if not isinstance(mapping, dict):
        return 0
    try:
        return int(mapping.get(key) or 0)
    except (TypeError, ValueError, OverflowError):
        return 0


def reporting_status_projection(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    """Project canonical application state into reporting-workspace presentation data.

    This function does not derive engineering verdicts or compliance. It only reports
    whether the existing project/run/verification/evidence artifacts required by each
    export path are currently present.
    """
    data = snapshot if isinstance(snapshot, dict) else {}
    project = data.get("project") if isinstance(data.get("project"), dict) else {}
    diagnostics = (
        data.get("diagnostics") if isinstance(data.get("diagnostics"), dict) else {}
    )
    diagnostic_summary = (
        diagnostics.get("summary")
        if isinstance(diagnostics.get("summary"), dict)
        else {}
    )
    verification = (
        data.get("verification") if isinstance(data.get("verification"), dict) else {}
    )
    evidence = data.get("evidence") if isinstance(data.get("evidence"), dict) else {}
    last_run = data.get("last_run") if isinstance(data.get("last_run"), dict) else None

    configured = _count(verification, "configured_analysis_count")
    current = _count(verification, "current_count")
    stale = _count(verification, "stale_count")
    not_verified = _count(verification, "not_verified_count")
    records = _count(evidence, "record_count")
    proofgraphs = _count(evidence, "proofgraph_count")
    issues = _count(diagnostic_summary, "issue_count")
    errors = _count(diagnostic_summary, "error_count")
    warnings = _count(diagnostic_summary, "warning_count")

    if configured == 0:
        verification_state = "not configured"
    elif current == configured and stale == 0 and not_verified == 0:
        verification_state = "current"
    elif stale:
        verification_state = "stale"
    else:
        verification_state = "incomplete"

    run_status = (
        str(last_run.get("status") or "unknown").strip().lower()
        if last_run is not None
        else "not run"
    )

    return {
        "project_name": str(project.get("name") or "Untitled project"),
        "project_location": str(project.get("location") or "Unsaved project"),
        "analysis_count": int(data.get("analysis_count") or 0),
        "has_run": last_run is not None,
        "run_title": str(last_run.get("title") or "") if last_run else "",
        "run_status": run_status,
        "diagnostic_status": str(
            diagnostic_summary.get("status") or "not checked"
        ).strip().lower(),
        "issue_count": issues,
        "error_count": errors,
        "warning_count": warnings,
        "verification_state": verification_state,
        "verification_current": current,
        "verification_configured": configured,
        "evidence_count": records,
        "proofgraph_count": proofgraphs,
    }


def reporting_artifacts(snapshot: dict[str, Any] | None) -> tuple[dict[str, Any], ...]:
    state = reporting_status_projection(snapshot)
    has_run = bool(state["has_run"])
    return (
        {
            "id": "dossier",
            "name": "Project engineering dossier",
            "scope": "Project-level engineering dossier from existing project services",
            "requires": "Project data",
            "available": True,
        },
        {
            "id": "result_json",
            "name": "Result JSON",
            "scope": "Canonical calculated result for the active fresh run",
            "requires": "Fresh analysis run",
            "available": has_run,
        },
        {
            "id": "run_bundle",
            "name": "Run bundle JSON",
            "scope": "Input, result, diagnostics, provenance, and run metadata",
            "requires": "Fresh analysis run",
            "available": has_run,
        },
        {
            "id": "markdown",
            "name": "Analysis report Markdown",
            "scope": "Backend-generated Markdown report for the active fresh run",
            "requires": "Fresh analysis run",
            "available": has_run,
        },
        {
            "id": "html",
            "name": "Portable HTML report",
            "scope": "Portable engineering report built from the active fresh run",
            "requires": "Fresh analysis run",
            "available": has_run,
        },
        {
            "id": "diagnostics",
            "name": "Project diagnostics",
            "scope": "Canonical project diagnostics in JSON or Markdown",
            "requires": "Project diagnostics",
            "available": True,
        },
    )


class ReportingWorkspace(ttk.Frame):
    """First-class reporting/export workspace over existing CleanroomX services."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_export_dossier: Callable[[], None],
        on_export_result_json: Callable[[], None],
        on_export_run_bundle: Callable[[], None],
        on_export_markdown: Callable[[], None],
        on_export_html: Callable[[], None],
        on_export_diagnostics: Callable[[], None],
        on_open_output: Callable[[], None],
    ) -> None:
        super().__init__(master, padding=10)
        self._snapshot: dict[str, Any] = {}
        self._callbacks = {
            "dossier": on_export_dossier,
            "result_json": on_export_result_json,
            "run_bundle": on_export_run_bundle,
            "markdown": on_export_markdown,
            "html": on_export_html,
            "diagnostics": on_export_diagnostics,
        }
        self._artifact_buttons: dict[str, ttk.Button] = {}

        self.project_var = tk.StringVar(value="Untitled project")
        self.location_var = tk.StringVar(value="Unsaved project")
        self.analysis_var = tk.StringVar(value="0 analyses")
        self.run_var = tk.StringVar(value="NOT RUN")
        self.diagnostics_var = tk.StringVar(value="NOT CHECKED")
        self.verification_var = tk.StringVar(value="NOT CONFIGURED")
        self.evidence_var = tk.StringVar(value="0 records")
        self.traceability_var = tk.StringVar(
            value="No retained verification evidence is available."
        )

        header = ttk.Frame(self, style="CX.PanelHeader.TFrame", padding=(10, 7))
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(
            header,
            text="REPORTING & ENGINEERING DELIVERABLES",
            style="CX.PanelHeader.TLabel",
        ).pack(side="left")
        ttk.Button(
            header,
            text="Open report output",
            style="CX.Compact.TButton",
            command=on_open_output,
        ).pack(side="right")
        attach_tooltip(
            header,
            "Exports use existing CleanroomX report/diagnostics services. "
            "This workspace does not synthesize engineering values.",
        )

        context = ttk.Frame(self, style="CX.SubtlePanel.TFrame", padding=(10, 8))
        context.pack(fill="x", pady=(0, 8))
        ttk.Label(context, text="DELIVERABLE CONTEXT", style="CX.PanelSection.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 6)
        )
        self._kv(context, 1, 0, "Project", self.project_var)
        self._kv(context, 1, 1, "Location", self.location_var)
        self._kv(context, 2, 0, "Analyses", self.analysis_var)
        self._kv(context, 2, 1, "Evidence", self.evidence_var)
        context.columnconfigure(1, weight=1)
        context.columnconfigure(3, weight=1)

        state = ttk.Frame(self, style="CX.SubtlePanel.TFrame", padding=(10, 8))
        state.pack(fill="x", pady=(0, 8))
        ttk.Label(state, text="SOURCE STATE", style="CX.PanelSection.TLabel").grid(
            row=0, column=0, columnspan=6, sticky="w", pady=(0, 6)
        )
        self.run_label = self._state_cell(state, 1, 0, "ANALYSIS RUN", self.run_var)
        self.diagnostics_label = self._state_cell(
            state, 1, 2, "DIAGNOSTICS", self.diagnostics_var
        )
        self.verification_label = self._state_cell(
            state, 1, 4, "VERIFICATION", self.verification_var
        )
        for column in (1, 3, 5):
            state.columnconfigure(column, weight=1)

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        deliverables = ttk.Frame(body, style="CX.Panel.TFrame", padding=(10, 8))
        deliverables.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        ttk.Label(
            deliverables,
            text="AVAILABLE DELIVERABLES",
            style="CX.PanelSection.TLabel",
        ).pack(anchor="w", pady=(0, 6))

        self.artifact_tree = ttk.Treeview(
            deliverables,
            columns=("scope", "requires", "state"),
            show="tree headings",
            selectmode="browse",
            height=10,
        )
        self.artifact_tree.heading("#0", text="Deliverable")
        self.artifact_tree.heading("scope", text="Content")
        self.artifact_tree.heading("requires", text="Requires")
        self.artifact_tree.heading("state", text="State")
        self.artifact_tree.column("#0", width=180, minwidth=150)
        self.artifact_tree.column("scope", width=360, minwidth=240)
        self.artifact_tree.column("requires", width=130, minwidth=100)
        self.artifact_tree.column("state", width=90, minwidth=80, stretch=False)
        scroll = ttk.Scrollbar(
            deliverables, orient="vertical", command=self.artifact_tree.yview
        )
        self.artifact_tree.configure(yscrollcommand=scroll.set)
        self.artifact_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="left", fill="y")

        actions = ttk.Frame(deliverables)
        actions.pack(side="right", fill="y", padx=(8, 0))
        for artifact_id, label in (
            ("dossier", "Dossier…"),
            ("result_json", "Result JSON…"),
            ("run_bundle", "Run bundle…"),
            ("markdown", "Markdown…"),
            ("html", "HTML…"),
            ("diagnostics", "Diagnostics…"),
        ):
            button = ttk.Button(
                actions,
                text=label,
                width=15,
                style="CX.Compact.TButton",
                command=self._callbacks[artifact_id],
            )
            button.pack(fill="x", pady=2)
            self._artifact_buttons[artifact_id] = button

        traceability = ttk.Frame(body, style="CX.Panel.TFrame", padding=(10, 8))
        traceability.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        ttk.Label(
            traceability,
            text="TRACEABILITY SUMMARY",
            style="CX.PanelSection.TLabel",
        ).pack(anchor="w", pady=(0, 6))
        ttk.Label(
            traceability,
            textvariable=self.traceability_var,
            style="CX.PanelSecondary.TLabel",
            justify="left",
            wraplength=380,
        ).pack(fill="x")
        ttk.Label(
            traceability,
            text=(
                "Calculated results, configured requirements, verification verdicts, "
                "diagnostics, and retained evidence remain distinct artifacts. Export "
                "availability reflects only whether the corresponding canonical source "
                "currently exists."
            ),
            style="CX.PanelMuted.TLabel",
            justify="left",
            wraplength=380,
        ).pack(fill="x", pady=(12, 0))

    @staticmethod
    def _kv(
        master: ttk.Frame,
        row: int,
        pair: int,
        label: str,
        variable: tk.StringVar,
    ) -> None:
        base = pair * 2
        ttk.Label(master, text=label, style="CX.PanelMuted.TLabel").grid(
            row=row, column=base, sticky="w", padx=(0, 6), pady=2
        )
        ttk.Label(master, textvariable=variable, style="CX.PanelSecondary.TLabel").grid(
            row=row, column=base + 1, sticky="ew", padx=(0, 12), pady=2
        )

    @staticmethod
    def _state_cell(
        master: ttk.Frame,
        row: int,
        column: int,
        title: str,
        variable: tk.StringVar,
    ) -> ttk.Label:
        ttk.Label(master, text=title, style="CX.PanelMuted.TLabel").grid(
            row=row, column=column, sticky="w", padx=(0, 6)
        )
        label = ttk.Label(
            master, textvariable=variable, style="CX.Status.Neutral.TLabel"
        )
        label.grid(row=row, column=column + 1, sticky="w", padx=(0, 18))
        return label

    def refresh(self, snapshot: dict[str, Any] | None) -> None:
        self._snapshot = snapshot if isinstance(snapshot, dict) else {}
        state = reporting_status_projection(self._snapshot)

        self.project_var.set(state["project_name"])
        self.location_var.set(state["project_location"])
        count = int(state["analysis_count"])
        self.analysis_var.set(f"{count} analysis{'es' if count != 1 else ''}")
        self.evidence_var.set(
            f"{state['evidence_count']} records · {state['proofgraph_count']} ProofGraph"
        )

        if state["has_run"]:
            self.run_var.set(
                f"{state['run_status'].upper().replace('_', ' ')} · {state['run_title']}"
            )
        else:
            self.run_var.set("NOT RUN")
        self.run_label.configure(style=status_style_name(state["run_status"]))

        diagnostic_text = (
            f"{state['diagnostic_status'].upper().replace('_', ' ')} · "
            f"{state['error_count']}E / {state['warning_count']}W"
        )
        self.diagnostics_var.set(diagnostic_text)
        diagnostic_style = (
            "error"
            if state["error_count"]
            else "warning"
            if state["warning_count"]
            else state["diagnostic_status"]
        )
        self.diagnostics_label.configure(style=status_style_name(diagnostic_style))

        self.verification_var.set(
            f"{state['verification_state'].upper().replace('_', ' ')} · "
            f"{state['verification_current']}/{state['verification_configured']}"
        )
        self.verification_label.configure(
            style=status_style_name(state["verification_state"])
        )

        for item in self.artifact_tree.get_children():
            self.artifact_tree.delete(item)
        for artifact in reporting_artifacts(self._snapshot):
            state_text = "AVAILABLE" if artifact["available"] else "NEEDS RUN"
            self.artifact_tree.insert(
                "",
                "end",
                iid=f"report-{artifact['id']}",
                text=artifact["name"],
                values=(artifact["scope"], artifact["requires"], state_text),
                tags=("available" if artifact["available"] else "blocked",),
            )
            button = self._artifact_buttons.get(artifact["id"])
            if button is not None:
                button.configure(state="normal" if artifact["available"] else "disabled")

        if state["evidence_count"]:
            evidence_text = (
                f"{state['evidence_count']} persisted verification record(s) and "
                f"{state['proofgraph_count']} ProofGraph artifact(s) are retained."
            )
        else:
            evidence_text = "No persisted verification evidence is retained."

        run_text = (
            f"The active result source is {state['run_title']} "
            f"({state['run_status'].upper()})."
            if state["has_run"]
            else "No fresh analysis run is currently available for run-specific exports."
        )
        self.traceability_var.set(
            f"{run_text}\n\n"
            f"Project diagnostics: {state['issue_count']} issue(s). "
            f"Verification currency: {state['verification_current']}/"
            f"{state['verification_configured']} configured analyses current.\n\n"
            f"{evidence_text}"
        )
