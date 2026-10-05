from __future__ import annotations

from typing import Any, Callable

import tkinter as tk
from tkinter import ttk

from .gui_theme import attach_tooltip, status_style_name


def evidence_record_matches_filters(
    row: dict[str, Any],
    *,
    verdict: str = "All",
    analysis_kind: str = "All",
    query: str = "",
) -> bool:
    """Filter retained ledger rows without reinterpreting verification evidence."""
    verdict_token = str(verdict or "").strip().casefold()
    kind_token = str(analysis_kind or "").strip().casefold()
    if verdict_token not in {"", "all"} and str(row.get("status") or "").casefold() != verdict_token:
        return False
    if kind_token not in {"", "all"} and str(row.get("analysis_kind") or "").casefold() != kind_token:
        return False

    tokens = [token for token in str(query or "").strip().casefold().split() if token]
    if not tokens:
        return True
    haystack = " ".join(
        (
            str(row.get("sequence") or ""),
            str(row.get("completed") or ""),
            str(row.get("analysis_id") or ""),
            str(row.get("analysis_name") or ""),
            str(row.get("analysis_kind") or ""),
            str(row.get("status") or ""),
            str(row.get("identity") or ""),
            str(row.get("record_sha256") or ""),
        )
    ).casefold()
    return all(token in haystack for token in tokens)


def evidence_workspace_projection(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    """Project retained verification evidence without reinterpreting engineering results."""
    data = snapshot if isinstance(snapshot, dict) else {}
    records = data.get("evidence_records")
    records = records if isinstance(records, list) else []

    rows: list[dict[str, Any]] = []
    total_evidence = 0
    total_graphs = 0
    for record in reversed(records):
        if not isinstance(record, dict):
            continue
        verification = record.get("verification")
        verification = verification if isinstance(verification, dict) else {}
        evidence = record.get("evidence")
        evidence = evidence if isinstance(evidence, list) else []
        proofgraphs = record.get("proofgraphs")
        proofgraphs = proofgraphs if isinstance(proofgraphs, list) else []
        graph_digests = record.get("proofgraph_sha256")
        graph_digests = graph_digests if isinstance(graph_digests, list) else []
        graph_count = len(proofgraphs) if proofgraphs else len(graph_digests)
        total_evidence += len(evidence)
        total_graphs += graph_count
        rows.append(
            {
                "sequence": record.get("sequence"),
                "completed": str(record.get("completed_at_utc") or ""),
                "analysis_id": str(record.get("analysis_id") or ""),
                "analysis_name": str(
                    record.get("analysis_name")
                    or record.get("analysis_id")
                    or "analysis"
                ),
                "analysis_kind": str(record.get("analysis_kind") or "unknown"),
                "status": str(verification.get("status") or "unknown"),
                "verified": bool(verification.get("verified")),
                "evidence_count": len(evidence),
                "proofgraph_count": graph_count,
                "identity": str(record.get("verification_identity_sha256") or ""),
                "record_sha256": str(record.get("record_sha256") or ""),
            }
        )

    return {
        "record_count": len(rows),
        "evidence_count": total_evidence,
        "proofgraph_count": total_graphs,
        "rows": tuple(rows),
    }


class EvidenceWorkspace(ttk.Frame):
    """Read-only evidence ledger workspace backed by persisted canonical records."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_open_proofgraph: Callable[[], Any],
        on_open_history: Callable[[], Any],
        on_open_traceability: Callable[[], Any],
    ) -> None:
        super().__init__(master, padding=10)
        self._snapshot: dict[str, Any] = {}
        self._rows: dict[str, dict[str, Any]] = {}
        self._on_open_proofgraph = on_open_proofgraph

        self.search_var = tk.StringVar(value="")
        self.verdict_var = tk.StringVar(value="All")
        self.kind_var = tk.StringVar(value="All")
        self.visible_var = tk.StringVar(value="0 / 0 visible")
        self.records_var = tk.StringVar(value="0")
        self.evidence_var = tk.StringVar(value="0")
        self.graphs_var = tk.StringVar(value="0")
        self.status_var = tk.StringVar(value="NO RETAINED EVIDENCE")
        self.detail_title_var = tk.StringVar(value="No evidence record selected")
        self.detail_var = tk.StringVar(
            value=(
                "Persisted project-verification records will appear here after a "
                "verification workflow is successfully persisted."
            )
        )

        header = ttk.Frame(self, style="CX.PanelHeader.TFrame", padding=(10, 7))
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(
            header,
            text="EVIDENCE LEDGER & TRACEABILITY",
            style="CX.PanelHeader.TLabel",
        ).pack(side="left")
        self.status_label = ttk.Label(
            header,
            textvariable=self.status_var,
            style="CX.Status.Neutral.TLabel",
        )
        self.status_label.pack(side="right")

        actions = ttk.Frame(self, style="CX.Toolbar.TFrame", padding=(8, 5))
        actions.pack(fill="x", pady=(0, 8))
        ttk.Button(
            actions,
            text="Open ProofGraph",
            style="CX.Primary.TButton",
            command=self._open_proofgraph,
        ).pack(side="left", padx=(0, 4))
        ttk.Button(
            actions,
            text="Verification history…",
            style="CX.Compact.TButton",
            command=on_open_history,
        ).pack(side="left", padx=(0, 4))
        ttk.Button(
            actions,
            text="Requirements traceability…",
            style="CX.Compact.TButton",
            command=on_open_traceability,
        ).pack(side="left", padx=(0, 4))
        ttk.Button(
            actions,
            text="Previous",
            style="CX.Compact.TButton",
            command=lambda: self._select_relative(-1),
        ).pack(side="left", padx=(0, 4))
        ttk.Button(
            actions,
            text="Next",
            style="CX.Compact.TButton",
            command=lambda: self._select_relative(1),
        ).pack(side="left")
        attach_tooltip(
            actions,
            "Evidence is read from the persisted verification ledger. "
            "Record and verification hashes are integrity evidence, not digital signatures.",
        )

        filters = ttk.Frame(self, style="CX.Toolbar.TFrame", padding=(8, 5))
        filters.pack(fill="x", pady=(0, 8))
        ttk.Label(filters, text="Search").pack(side="left")
        ttk.Entry(filters, textvariable=self.search_var, width=28).pack(
            side="left", padx=(4, 8)
        )
        ttk.Label(filters, text="Verdict").pack(side="left")
        self.verdict_combo = ttk.Combobox(
            filters,
            textvariable=self.verdict_var,
            values=("All",),
            state="readonly",
            width=14,
        )
        self.verdict_combo.pack(side="left", padx=(4, 8))
        ttk.Label(filters, text="Analysis kind").pack(side="left")
        self.kind_combo = ttk.Combobox(
            filters,
            textvariable=self.kind_var,
            values=("All",),
            state="readonly",
            width=18,
        )
        self.kind_combo.pack(side="left", padx=(4, 8))
        ttk.Label(
            filters,
            textvariable=self.visible_var,
            style="CX.PanelMuted.TLabel",
        ).pack(side="right")

        metrics = ttk.Frame(self, style="CX.SubtlePanel.TFrame", padding=(10, 8))
        metrics.pack(fill="x", pady=(0, 8))
        self._metric(metrics, 0, "RECORDS", self.records_var)
        self._metric(metrics, 2, "EVIDENCE ITEMS", self.evidence_var)
        self._metric(metrics, 4, "PROOFGRAPHS", self.graphs_var)
        for column in (1, 3, 5):
            metrics.columnconfigure(column, weight=1)

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True)

        list_host = ttk.Frame(body, style="CX.Panel.TFrame", padding=(10, 8))
        detail_host = ttk.Frame(body, style="CX.Panel.TFrame", padding=(10, 8))
        body.add(list_host, weight=3)
        body.add(detail_host, weight=2)

        ttk.Label(
            list_host,
            text="PERSISTED VERIFICATION RECORDS",
            style="CX.PanelSection.TLabel",
        ).pack(anchor="w", pady=(0, 6))
        self.tree = ttk.Treeview(
            list_host,
            columns=("analysis", "kind", "status", "evidence", "graphs", "completed"),
            show="tree headings",
            selectmode="browse",
        )
        self.tree.heading("#0", text="#")
        self.tree.heading("analysis", text="Analysis")
        self.tree.heading("kind", text="Kind")
        self.tree.heading("status", text="Verdict")
        self.tree.heading("evidence", text="Evidence")
        self.tree.heading("graphs", text="Graphs")
        self.tree.heading("completed", text="Completed UTC")
        self.tree.column("#0", width=48, minwidth=42, stretch=False)
        self.tree.column("analysis", width=200, minwidth=140)
        self.tree.column("kind", width=150, minwidth=110)
        self.tree.column("status", width=90, minwidth=75, stretch=False)
        self.tree.column("evidence", width=72, minwidth=60, stretch=False)
        self.tree.column("graphs", width=65, minwidth=55, stretch=False)
        self.tree.column("completed", width=180, minwidth=150)
        scroll = ttk.Scrollbar(list_host, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._show_selected)
        self.tree.bind("<Double-1>", self._open_proofgraph)
        self.tree.bind("<Return>", self._open_proofgraph)
        self.tree.bind("<Alt-Up>", lambda _event: self._select_relative(-1))
        self.tree.bind("<Alt-Down>", lambda _event: self._select_relative(1))

        ttk.Label(
            detail_host,
            text="RECORD INTEGRITY",
            style="CX.PanelSection.TLabel",
        ).pack(anchor="w", pady=(0, 6))
        ttk.Label(
            detail_host,
            textvariable=self.detail_title_var,
            style="CX.PanelTitle.TLabel",
            justify="left",
            wraplength=430,
        ).pack(fill="x", pady=(0, 8))
        ttk.Label(
            detail_host,
            textvariable=self.detail_var,
            style="CX.PanelSecondary.TLabel",
            justify="left",
            wraplength=430,
        ).pack(fill="x")
        ttk.Label(
            detail_host,
            text=(
                "Historical records are immutable engineering evidence. Hashes detect "
                "mutation and chain discontinuity, but do not authenticate a signer."
            ),
            style="CX.PanelMuted.TLabel",
            justify="left",
            wraplength=430,
        ).pack(fill="x", pady=(14, 0))

        self.search_var.trace_add("write", lambda *_: self._populate())
        self.verdict_var.trace_add("write", lambda *_: self._populate())
        self.kind_var.trace_add("write", lambda *_: self._populate())

    @staticmethod
    def _metric(
        master: ttk.Frame,
        column: int,
        title: str,
        variable: tk.StringVar,
    ) -> None:
        ttk.Label(master, text=title, style="CX.PanelMuted.TLabel").grid(
            row=0, column=column, sticky="w", padx=(0, 6)
        )
        ttk.Label(master, textvariable=variable, style="CX.PanelTitle.TLabel").grid(
            row=0, column=column + 1, sticky="w", padx=(0, 22)
        )

    def _filtered_rows(self) -> list[dict[str, Any]]:
        state = evidence_workspace_projection(self._snapshot)
        return [
            row
            for row in state["rows"]
            if evidence_record_matches_filters(
                row,
                verdict=self.verdict_var.get(),
                analysis_kind=self.kind_var.get(),
                query=self.search_var.get(),
            )
        ]

    def _populate(self) -> None:
        selection = self.tree.selection()
        selected_row = self._rows.get(selection[0]) if selection else None
        selected_sequence = selected_row.get("sequence") if selected_row else None
        state = evidence_workspace_projection(self._snapshot)
        visible = self._filtered_rows()

        self._rows.clear()
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        for index, row in enumerate(visible):
            iid = f"evidence-record-{index}"
            self._rows[iid] = row
            self.tree.insert(
                "",
                "end",
                iid=iid,
                text=str(row["sequence"] if row["sequence"] is not None else "—"),
                values=(
                    row["analysis_name"],
                    row["analysis_kind"],
                    row["status"].upper().replace("_", " "),
                    row["evidence_count"],
                    row["proofgraph_count"],
                    row["completed"] or "—",
                ),
            )

        self.visible_var.set(f"{len(visible)} / {state['record_count']} visible")
        restored = False
        if selected_sequence is not None:
            restored = self.select_record_sequence(selected_sequence)
        if not restored and visible:
            first = next(iter(self.tree.get_children()), None)
            if first is not None:
                self.tree.selection_set(first)
                self.tree.focus(first)
                self._show_selected()
        elif not visible:
            self._show_selected()

    def _select_relative(self, delta: int):
        children = list(self.tree.get_children())
        if not children:
            return "break"
        selection = self.tree.selection()
        if selection and selection[0] in children:
            index = (children.index(selection[0]) + int(delta)) % len(children)
        else:
            index = 0 if int(delta) >= 0 else len(children) - 1
        iid = children[index]
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        self.tree.see(iid)
        self._show_selected()
        return "break"

    def _open_proofgraph(self, _event=None):
        self._on_open_proofgraph()
        return "break"

    def select_record_sequence(self, sequence: Any) -> bool:
        for iid, row in self._rows.items():
            if row.get("sequence") != sequence:
                continue
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self.tree.see(iid)
            self._show_selected()
            return True
        return False

    def _show_selected(self, _event=None) -> None:
        selection = self.tree.selection()
        row = self._rows.get(selection[0]) if selection else None
        if row is None:
            self.detail_title_var.set("No evidence record selected")
            self.detail_var.set("Select a persisted record to inspect its identities.")
            return

        identity = row["identity"]
        record_sha = row["record_sha256"]
        self.detail_title_var.set(
            f"Record #{row['sequence']} · {row['analysis_name']} · "
            f"{row['status'].upper()}"
        )
        self.detail_var.set(
            f"Completed: {row['completed'] or 'unknown'}\n"
            f"Evidence items: {row['evidence_count']}\n"
            f"ProofGraph documents: {row['proofgraph_count']}\n\n"
            f"Verification identity SHA-256:\n{identity or 'not available'}\n\n"
            f"Ledger record SHA-256:\n{record_sha or 'not available'}"
        )

    def refresh(self, snapshot: dict[str, Any] | None) -> None:
        self._snapshot = snapshot if isinstance(snapshot, dict) else {}
        state = evidence_workspace_projection(self._snapshot)

        self.records_var.set(str(state["record_count"]))
        self.evidence_var.set(str(state["evidence_count"]))
        self.graphs_var.set(str(state["proofgraph_count"]))
        if state["record_count"]:
            self.status_var.set("RETAINED")
            self.status_label.configure(style=status_style_name("available"))
        else:
            self.status_var.set("NO RETAINED EVIDENCE")
            self.status_label.configure(style=status_style_name("neutral"))

        verdicts = (
            "All",
            *sorted(
                {
                    str(row.get("status") or "unknown")
                    for row in state["rows"]
                },
                key=str.casefold,
            ),
        )
        kinds = (
            "All",
            *sorted(
                {
                    str(row.get("analysis_kind") or "unknown")
                    for row in state["rows"]
                },
                key=str.casefold,
            ),
        )
        self.verdict_combo.configure(values=verdicts)
        self.kind_combo.configure(values=kinds)
        if self.verdict_var.get() not in verdicts:
            self.verdict_var.set("All")
        if self.kind_var.get() not in kinds:
            self.kind_var.set("All")
        self._populate()
