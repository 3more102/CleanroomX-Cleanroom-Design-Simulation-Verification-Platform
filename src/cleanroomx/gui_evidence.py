from __future__ import annotations

from typing import Any, Callable

import tkinter as tk
from tkinter import ttk

from .gui_theme import attach_tooltip, status_style_name


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
            command=on_open_proofgraph,
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
        ).pack(side="left")
        attach_tooltip(
            actions,
            "Evidence is read from the persisted verification ledger. "
            "Record and verification hashes are integrity evidence, not digital signatures.",
        )

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

        self._rows.clear()
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        for index, row in enumerate(state["rows"]):
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

        if state["rows"]:
            first = next(iter(self.tree.get_children()), None)
            if first is not None:
                self.tree.selection_set(first)
                self.tree.focus(first)
                self._show_selected()
        else:
            self._show_selected()
