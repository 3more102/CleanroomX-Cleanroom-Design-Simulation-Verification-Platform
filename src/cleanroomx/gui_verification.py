from __future__ import annotations

from typing import Any, Callable

import tkinter as tk
from tkinter import ttk

from .gui_theme import attach_tooltip, status_style_name


def _integer(mapping: Any, key: str) -> int:
    if not isinstance(mapping, dict):
        return 0
    try:
        return int(mapping.get(key) or 0)
    except (TypeError, ValueError, OverflowError):
        return 0


def verification_workspace_projection(
    snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    """Project canonical verification-currency state without re-evaluating verdicts."""
    data = snapshot if isinstance(snapshot, dict) else {}
    summary = data.get("verification")
    summary = summary if isinstance(summary, dict) else {}
    items = data.get("verification_items")
    items = items if isinstance(items, list) else []
    diagnostics = data.get("diagnostics")
    diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
    diagnostic_summary = diagnostics.get("summary")
    diagnostic_summary = (
        diagnostic_summary if isinstance(diagnostic_summary, dict) else {}
    )
    evidence = data.get("evidence")
    evidence = evidence if isinstance(evidence, dict) else {}

    configured = _integer(summary, "configured_analysis_count")
    current = _integer(summary, "current_count")
    stale = _integer(summary, "stale_count")
    not_verified = _integer(summary, "not_verified_count")
    not_configured = _integer(summary, "not_configured_count")
    unverifiable = _integer(summary, "dependency_freshness_unverifiable_count")

    if configured == 0:
        state = "not configured"
    elif current == configured and stale == 0 and not_verified == 0 and unverifiable == 0:
        state = "current"
    elif stale:
        state = "stale"
    elif unverifiable:
        state = "dependency freshness unverifiable"
    else:
        state = "incomplete"

    rows: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        mismatch_reasons = item.get("mismatch_reasons")
        active_mapping_ids = item.get("active_mapping_ids")
        latest_record = item.get("latest_record")
        explanation = str(
            item.get("explanation")
            or item.get("reason")
            or item.get("detail")
            or item.get("message")
            or ""
        )
        reasons = tuple(
            str(reason)
            for reason in mismatch_reasons
            if isinstance(reason, str) and reason
        ) if isinstance(mismatch_reasons, list) else ()
        detail = explanation
        if reasons:
            reason_text = "; ".join(reasons)
            detail = f"{explanation} — {reason_text}" if explanation else reason_text
        rows.append(
            {
                "analysis_id": str(item.get("analysis_id") or ""),
                "name": str(item.get("analysis_name") or item.get("analysis_id") or "analysis"),
                "kind": str(item.get("analysis_kind") or "unknown"),
                "state": str(item.get("state") or "unknown"),
                "detail": detail,
                "explanation": explanation,
                "mismatch_reasons": reasons,
                "mapping_count": (
                    len(active_mapping_ids)
                    if isinstance(active_mapping_ids, list)
                    else 0
                ),
                "external_dependency_count": _integer(
                    item, "external_dependency_count"
                ),
                "latest_record": (
                    latest_record if isinstance(latest_record, dict) else None
                ),
            }
        )

    return {
        "state": state,
        "configured": configured,
        "current": current,
        "stale": stale,
        "not_verified": not_verified,
        "not_configured": not_configured,
        "unverifiable": unverifiable,
        "issue_count": _integer(diagnostic_summary, "issue_count"),
        "error_count": _integer(diagnostic_summary, "error_count"),
        "warning_count": _integer(diagnostic_summary, "warning_count"),
        "evidence_count": _integer(evidence, "record_count"),
        "proofgraph_count": _integer(evidence, "proofgraph_count"),
        "rows": tuple(rows),
    }


class VerificationWorkspace(ttk.Frame):
    """Operator-facing workspace over existing verification and evidence services."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_refresh: Callable[[], Any],
        on_verify: Callable[[], Any],
        on_persist: Callable[[], Any],
        on_traceability: Callable[[], Any],
        on_history: Callable[[], Any],
    ) -> None:
        super().__init__(master, padding=10)
        self._snapshot: dict[str, Any] = {}

        self.state_var = tk.StringVar(value="NOT CONFIGURED")
        self.coverage_var = tk.StringVar(value="0 / 0 current")
        self.stale_var = tk.StringVar(value="0")
        self.not_verified_var = tk.StringVar(value="0")
        self.unverifiable_var = tk.StringVar(value="0")
        self.diagnostics_var = tk.StringVar(value="0 issues")
        self.evidence_var = tk.StringVar(value="0 records")

        header = ttk.Frame(self, style="CX.PanelHeader.TFrame", padding=(10, 7))
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(
            header,
            text="VERIFICATION & COMPLIANCE TRACEABILITY",
            style="CX.PanelHeader.TLabel",
        ).pack(side="left")
        self.state_label = ttk.Label(
            header,
            textvariable=self.state_var,
            style="CX.Status.Neutral.TLabel",
        )
        self.state_label.pack(side="right")

        actions = ttk.Frame(self, style="CX.Toolbar.TFrame", padding=(8, 5))
        actions.pack(fill="x", pady=(0, 8))
        for text, callback, style in (
            ("Refresh currency", on_refresh, "CX.Compact.TButton"),
            ("Verify requirements", on_verify, "CX.Primary.TButton"),
            ("Verify & persist", on_persist, "CX.Compact.TButton"),
            ("Traceability…", on_traceability, "CX.Compact.TButton"),
            ("History…", on_history, "CX.Compact.TButton"),
        ):
            ttk.Button(
                actions,
                text=text,
                command=callback,
                style=style,
            ).pack(side="left", padx=(0, 4))
        attach_tooltip(
            actions,
            "Verification actions delegate to CleanroomX's existing requirement, "
            "currency, persistence, and evidence services.",
        )

        summary = ttk.Frame(self, style="CX.SubtlePanel.TFrame", padding=(10, 8))
        summary.pack(fill="x", pady=(0, 8))
        ttk.Label(summary, text="VERIFICATION CURRENCY", style="CX.PanelSection.TLabel").grid(
            row=0, column=0, columnspan=8, sticky="w", pady=(0, 6)
        )
        self._metric(summary, 1, 0, "CURRENT", self.coverage_var)
        self._metric(summary, 1, 2, "STALE", self.stale_var)
        self._metric(summary, 1, 4, "NOT VERIFIED", self.not_verified_var)
        self._metric(summary, 1, 6, "UNVERIFIABLE", self.unverifiable_var)
        for column in (1, 3, 5, 7):
            summary.columnconfigure(column, weight=1)

        self.progress = ttk.Progressbar(summary, mode="determinate", maximum=100)
        self.progress.grid(row=2, column=0, columnspan=8, sticky="ew", pady=(8, 2))
        ttk.Label(
            summary,
            text=(
                "Currency is a freshness/coverage projection of persisted verification "
                "records. It is not a new engineering verdict."
            ),
            style="CX.PanelMuted.TLabel",
        ).grid(row=3, column=0, columnspan=8, sticky="w", pady=(2, 0))

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=4)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        table_host = ttk.Frame(body, style="CX.Panel.TFrame", padding=(10, 8))
        table_host.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        ttk.Label(
            table_host,
            text="ANALYSIS VERIFICATION STATE",
            style="CX.PanelSection.TLabel",
        ).pack(anchor="w", pady=(0, 6))

        self.tree = ttk.Treeview(
            table_host,
            columns=("kind", "state", "mappings", "dependencies", "detail"),
            show="tree headings",
            selectmode="browse",
        )
        self.tree.heading("#0", text="Analysis")
        self.tree.heading("kind", text="Kind")
        self.tree.heading("state", text="Currency")
        self.tree.heading("mappings", text="Mappings")
        self.tree.heading("dependencies", text="External deps")
        self.tree.heading("detail", text="Canonical explanation")
        self.tree.column("#0", width=210, minwidth=155)
        self.tree.column("kind", width=145, minwidth=110)
        self.tree.column("state", width=150, minwidth=110, stretch=False)
        self.tree.column("mappings", width=75, minwidth=65, stretch=False)
        self.tree.column("dependencies", width=90, minwidth=80, stretch=False)
        self.tree.column("detail", width=400, minwidth=240)
        scroll = ttk.Scrollbar(table_host, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        assurance = ttk.Frame(body, style="CX.Panel.TFrame", padding=(10, 8))
        assurance.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        ttk.Label(
            assurance,
            text="ASSURANCE CONTEXT",
            style="CX.PanelSection.TLabel",
        ).pack(anchor="w", pady=(0, 8))
        self._readout(assurance, "Project diagnostics", self.diagnostics_var)
        self._readout(assurance, "Retained evidence", self.evidence_var)
        ttk.Label(
            assurance,
            text=(
                "Requirements verification, project diagnostics, historical evidence, "
                "and ProofGraph remain separate canonical sources. This workspace only "
                "coordinates them and reports their current state."
            ),
            style="CX.PanelMuted.TLabel",
            justify="left",
            wraplength=360,
        ).pack(fill="x", pady=(12, 0))

    @staticmethod
    def _metric(
        master: ttk.Frame,
        row: int,
        column: int,
        title: str,
        variable: tk.StringVar,
    ) -> None:
        ttk.Label(master, text=title, style="CX.PanelMuted.TLabel").grid(
            row=row, column=column, sticky="w", padx=(0, 5)
        )
        ttk.Label(master, textvariable=variable, style="CX.PanelSecondary.TLabel").grid(
            row=row, column=column + 1, sticky="w", padx=(0, 18)
        )

    @staticmethod
    def _readout(master: ttk.Frame, title: str, variable: tk.StringVar) -> None:
        row = ttk.Frame(master, style="CX.Panel.TFrame")
        row.pack(fill="x", pady=3)
        ttk.Label(row, text=title, style="CX.PanelMuted.TLabel").pack(side="left")
        ttk.Label(row, textvariable=variable, style="CX.PanelSecondary.TLabel").pack(
            side="right"
        )

    def refresh(self, snapshot: dict[str, Any] | None) -> None:
        self._snapshot = snapshot if isinstance(snapshot, dict) else {}
        state = verification_workspace_projection(self._snapshot)

        self.state_var.set(state["state"].upper().replace("_", " "))
        overall_style = (
            "warning"
            if state["state"] == "dependency freshness unverifiable"
            else state["state"]
        )
        self.state_label.configure(style=status_style_name(overall_style))
        self.coverage_var.set(f"{state['current']} / {state['configured']} current")
        self.stale_var.set(str(state["stale"]))
        self.not_verified_var.set(str(state["not_verified"]))
        self.unverifiable_var.set(str(state["unverifiable"]))
        self.diagnostics_var.set(
            f"{state['issue_count']} issues · {state['error_count']}E / "
            f"{state['warning_count']}W"
        )
        self.evidence_var.set(
            f"{state['evidence_count']} records · {state['proofgraph_count']} ProofGraph"
        )
        percent = (
            round(100 * state["current"] / state["configured"])
            if state["configured"]
            else 0
        )
        self.progress.configure(value=percent)

        for iid in self.tree.get_children():
            self.tree.delete(iid)
        for index, row in enumerate(state["rows"]):
            self.tree.insert(
                "",
                "end",
                iid=f"verification-analysis-{index}",
                text=row["name"],
                values=(
                    row["kind"],
                    row["state"].upper().replace("_", " "),
                    row["mapping_count"],
                    row["external_dependency_count"],
                    row["detail"] or "—",
                ),
            )
