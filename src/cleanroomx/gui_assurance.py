from __future__ import annotations

import json
from typing import Any, Callable

import tkinter as tk
from tkinter import ttk

from .gui_theme import status_style_name, theme_palette


def verification_summary_projection(currency: dict[str, Any] | None) -> dict[str, Any]:
    """Project canonical verification-currency state without inventing a verdict."""
    data = currency if isinstance(currency, dict) else {}
    summary = data.get("summary", {})
    summary = summary if isinstance(summary, dict) else {}

    def count(key: str) -> int:
        value = summary.get(key)
        return int(value) if isinstance(value, int) and not isinstance(value, bool) else 0

    configured = count("configured_analysis_count")
    current = count("current_count")
    stale = count("stale_count")
    unverifiable = count("dependency_freshness_unverifiable_count")
    not_verified = count("not_verified_count")
    not_configured = count("not_configured_count")
    orphaned = count("orphaned_record_count")

    if configured <= 0:
        state = "not configured"
        detail = "No configured requirement-verification analyses"
    elif current == configured and stale == 0 and unverifiable == 0 and not_verified == 0:
        state = "current"
        detail = f"{current}/{configured} configured analyses current"
    elif stale:
        state = "stale"
        detail = f"{stale} stale · {current}/{configured} current"
    elif unverifiable:
        state = "dependency freshness unverifiable"
        detail = f"{unverifiable} dependency-freshness unverifiable"
    elif not_verified:
        state = "not verified"
        detail = f"{not_verified} not verified · {current}/{configured} current"
    else:
        state = "attention"
        detail = f"{current}/{configured} current"

    return {
        "state": state,
        "detail": detail,
        "configured": configured,
        "current": current,
        "stale": stale,
        "unverifiable": unverifiable,
        "not_verified": not_verified,
        "not_configured": not_configured,
        "orphaned": orphaned,
    }


def evidence_record_projection(
    record: dict[str, Any],
    current_assessment: dict[str, Any] | None,
) -> dict[str, Any]:
    """Project one retained verification record for read-only evidence browsing."""
    verification = record.get("verification")
    verification = verification if isinstance(verification, dict) else {}
    evidence = record.get("evidence")
    evidence = evidence if isinstance(evidence, list) else []
    findings = verification.get("findings")
    findings = findings if isinstance(findings, list) else []

    if not isinstance(current_assessment, dict):
        currency_state = "not in current project"
    else:
        latest = current_assessment.get("latest_record")
        if isinstance(latest, dict) and latest.get("sequence") == record.get("sequence"):
            currency_state = str(current_assessment.get("state") or "unknown")
        else:
            currency_state = "historical"

    return {
        "sequence": record.get("sequence"),
        "completed_at_utc": str(record.get("completed_at_utc") or ""),
        "analysis_id": str(record.get("analysis_id") or ""),
        "analysis_name": str(record.get("analysis_name") or record.get("analysis_id") or "analysis"),
        "analysis_kind": str(record.get("analysis_kind") or ""),
        "verification_status": str(verification.get("status") or "unknown"),
        "verified": verification.get("verified"),
        "complete": verification.get("complete"),
        "evidence_count": len(evidence),
        "finding_count": len(findings),
        "currency_state": currency_state,
        "record_sha256": str(record.get("record_sha256") or ""),
        "source_revision": str(record.get("project_source_revision") or ""),
    }


class VerificationWorkspace(ttk.Frame):
    """First-class operator workspace for canonical verification currency."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_verify: Callable[[], Any],
        on_persist: Callable[[], Any],
        on_traceability: Callable[[], Any],
        on_history: Callable[[], Any],
        on_problems: Callable[[], Any],
        on_proofgraph: Callable[[], Any],
    ) -> None:
        super().__init__(master, padding=(14, 12))
        self._currency: dict[str, Any] = {}
        self._analysis_by_iid: dict[str, dict[str, Any]] = {}

        self.state_var = tk.StringVar(value="NOT CONFIGURED")
        self.detail_var = tk.StringVar(value="No verification assessment loaded")
        self.configured_var = tk.StringVar(value="0")
        self.current_var = tk.StringVar(value="0")
        self.stale_var = tk.StringVar(value="0")
        self.unverifiable_var = tk.StringVar(value="0")
        self.not_verified_var = tk.StringVar(value="0")

        header = ttk.Frame(self, style="CX.PanelHeader.TFrame", padding=(10, 7))
        header.pack(fill="x", pady=(0, 8))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="VERIFICATION / ASSURANCE", style="CX.PanelHeader.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(header, textvariable=self.detail_var, style="CX.SurfaceMuted.TLabel").grid(
            row=0, column=1, sticky="e", padx=(12, 8)
        )
        self.state_badge = ttk.Label(
            header,
            textvariable=self.state_var,
            style="CX.Status.Neutral.TLabel",
        )
        self.state_badge.grid(row=0, column=2, sticky="e")

        actions = ttk.Frame(self, style="CX.Toolbar.TFrame", padding=(8, 5))
        actions.pack(fill="x", pady=(0, 8))
        ttk.Label(actions, text="ASSURANCE", style="CX.ToolbarSection.TLabel").pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(actions, text="Verify", style="CX.Primary.TButton", command=on_verify).pack(
            side="left", padx=2
        )
        ttk.Button(
            actions,
            text="Verify & Persist",
            style="CX.Compact.TButton",
            command=on_persist,
        ).pack(side="left", padx=2)
        ttk.Separator(actions, orient="vertical").pack(side="left", fill="y", padx=7)
        for label, callback in (
            ("Traceability", on_traceability),
            ("History", on_history),
            ("Problems", on_problems),
            ("ProofGraph", on_proofgraph),
        ):
            ttk.Button(
                actions,
                text=label,
                style="CX.Compact.TButton",
                command=callback,
            ).pack(side="left", padx=2)

        metrics = ttk.Frame(self)
        metrics.pack(fill="x", pady=(0, 8))
        for index, (title, variable) in enumerate(
            (
                ("CONFIGURED", self.configured_var),
                ("CURRENT", self.current_var),
                ("STALE", self.stale_var),
                ("UNVERIFIABLE", self.unverifiable_var),
                ("NOT VERIFIED", self.not_verified_var),
            )
        ):
            card = ttk.Frame(metrics, style="CX.Panel.TFrame", padding=(10, 7))
            card.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 3, 0))
            metrics.columnconfigure(index, weight=1)
            ttk.Label(card, text=title, style="CX.InstrumentName.TLabel").pack(anchor="w")
            ttk.Label(card, textvariable=variable, style="CX.InstrumentValue.TLabel").pack(anchor="w")

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True)

        table_frame = ttk.Frame(body, style="CX.Panel.TFrame", padding=(8, 8))
        detail_frame = ttk.Frame(body, style="CX.Panel.TFrame", padding=(8, 8))
        body.add(table_frame, weight=5)
        body.add(detail_frame, weight=3)

        ttk.Label(table_frame, text="CONFIGURED ANALYSES", style="CX.PanelSection.TLabel").pack(
            anchor="w", pady=(0, 6)
        )
        table_host = ttk.Frame(table_frame, style="CX.Panel.TFrame")
        table_host.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            table_host,
            columns=("kind", "state", "record", "dependencies"),
            show="tree headings",
            selectmode="browse",
        )
        self.tree.heading("#0", text="Analysis")
        self.tree.heading("kind", text="Kind")
        self.tree.heading("state", text="Currency")
        self.tree.heading("record", text="Latest record")
        self.tree.heading("dependencies", text="Dependencies")
        self.tree.column("#0", width=240)
        self.tree.column("kind", width=180)
        self.tree.column("state", width=180, stretch=False)
        self.tree.column("record", width=110, stretch=False)
        self.tree.column("dependencies", width=105, stretch=False, anchor="center")
        scroll = ttk.Scrollbar(table_host, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._show_selected)

        ttk.Label(detail_frame, text="ENGINEERING CONTEXT", style="CX.PanelSection.TLabel").pack(
            anchor="w", pady=(0, 6)
        )
        detail_host = ttk.Frame(detail_frame, style="CX.Panel.TFrame")
        detail_host.pack(fill="both", expand=True)
        self.detail = tk.Text(detail_host, wrap="word", state="disabled", height=16)
        detail_scroll = ttk.Scrollbar(detail_host, orient="vertical", command=self.detail.yview)
        self.detail.configure(yscrollcommand=detail_scroll.set)
        self.detail.pack(side="left", fill="both", expand=True)
        detail_scroll.pack(side="right", fill="y")

    def refresh(self, currency: dict[str, Any] | None) -> None:
        self._currency = currency if isinstance(currency, dict) else {}
        projected = verification_summary_projection(self._currency)
        state = str(projected["state"])
        self.state_var.set(state.upper().replace("_", " "))
        self.detail_var.set(str(projected["detail"]))
        self.state_badge.configure(style=status_style_name(state))
        self.configured_var.set(str(projected["configured"]))
        self.current_var.set(str(projected["current"]))
        self.stale_var.set(str(projected["stale"]))
        self.unverifiable_var.set(str(projected["unverifiable"]))
        self.not_verified_var.set(str(projected["not_verified"]))

        self.tree.delete(*self.tree.get_children())
        self._analysis_by_iid.clear()
        analyses = self._currency.get("analyses", [])
        if not isinstance(analyses, list):
            analyses = []
        for index, item in enumerate(analyses):
            if not isinstance(item, dict):
                continue
            analysis_id = str(item.get("analysis_id") or f"analysis-{index}")
            iid = analysis_id
            if self.tree.exists(iid):
                iid = f"{analysis_id}:{index}"
            latest = item.get("latest_record")
            record_text = (
                f"#{latest.get('sequence')}"
                if isinstance(latest, dict) and latest.get("sequence") is not None
                else "—"
            )
            state_text = str(item.get("state") or "unknown")
            self.tree.insert(
                "",
                "end",
                iid=iid,
                text=str(item.get("analysis_name") or analysis_id),
                values=(
                    str(item.get("analysis_kind") or ""),
                    state_text.upper().replace("_", " "),
                    record_text,
                    str(item.get("external_dependency_count") or 0),
                ),
                tags=(state_text,),
            )
            self._analysis_by_iid[iid] = item

        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children[0])
            self.tree.focus(children[0])
            self._show_selected()
        else:
            self._set_detail(
                "No configured analyses are available for verification-currency inspection.\n\n"
                "CleanroomX does not infer a PASS state from missing configuration."
            )

    def selected_analysis(self) -> dict[str, Any] | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return self._analysis_by_iid.get(selection[0])

    def _show_selected(self, _event=None) -> None:
        item = self.selected_analysis()
        if item is None:
            return
        latest = item.get("latest_record")
        mismatch = item.get("mismatch_reasons")
        mismatch = mismatch if isinstance(mismatch, list) else []
        identity = item.get("current_identity")
        identity = identity if isinstance(identity, dict) else {}
        lines = [
            str(item.get("analysis_name") or item.get("analysis_id") or "Analysis"),
            "",
            f"Currency state: {str(item.get('state') or 'unknown').upper().replace('_', ' ')}",
            f"Kind: {item.get('analysis_kind') or '—'}",
            f"Active mappings: {len(item.get('active_mapping_ids') or [])}",
            f"External dependencies: {item.get('external_dependency_count') or 0}",
            "",
            str(item.get("explanation") or "No explanation emitted."),
        ]
        if mismatch:
            lines.extend(["", "Mismatch reasons:", *[f"  • {reason}" for reason in mismatch]])
        lines.extend(
            [
                "",
                "Current engineering identity:",
                f"  Analysis input: {identity.get('analysis_input_sha256') or '—'}",
                f"  Requirements: {identity.get('requirements_sha256') or '—'}",
                f"  Mappings: {identity.get('mappings_sha256') or '—'}",
            ]
        )
        if isinstance(latest, dict):
            lines.extend(
                [
                    "",
                    "Latest retained verification:",
                    f"  Sequence: {latest.get('sequence', '—')}",
                    f"  Completed UTC: {latest.get('completed_at_utc') or '—'}",
                    f"  Verification status: {latest.get('verification_status') or '—'}",
                    f"  Complete: {latest.get('verification_complete')}",
                    f"  Record SHA-256: {latest.get('record_sha256') or '—'}",
                ]
            )
        self._set_detail("\n".join(lines))

    def _set_detail(self, value: str) -> None:
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", value)
        self.detail.configure(state="disabled")

    def apply_theme(self, theme: str) -> None:
        palette = theme_palette(theme)
        self.detail.configure(
            background=palette["field"],
            foreground=palette["field_text"],
            insertbackground=palette["text"],
            selectbackground=palette["selection"],
            selectforeground=palette["selection_text"],
        )
        for state in (
            "current",
            "stale",
            "dependency_freshness_unverifiable",
            "not_verified",
            "not_configured",
        ):
            style = status_style_name(state)
            color = {
                "CX.Status.Pass.TLabel": palette["success"],
                "CX.Status.Fail.TLabel": palette["error"],
                "CX.Status.Warning.TLabel": palette["warning"],
                "CX.Status.Attention.TLabel": palette["attention"],
                "CX.Status.Info.TLabel": palette["info"],
            }.get(style, palette["secondary_text"])
            self.tree.tag_configure(state, foreground=color)


class EvidenceWorkspace(ttk.Frame):
    """First-class retained-evidence browser over canonical verification history."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_history: Callable[[], Any],
        on_proofgraph: Callable[[], Any],
        on_report: Callable[[], Any],
    ) -> None:
        super().__init__(master, padding=(14, 12))
        self._records_by_iid: dict[str, dict[str, Any]] = {}
        self.record_count_var = tk.StringVar(value="0")
        self.proofgraph_count_var = tk.StringVar(value="0")
        self.latest_var = tk.StringVar(value="—")
        self.currency_var = tk.StringVar(value="NOT ASSESSED")

        header = ttk.Frame(self, style="CX.PanelHeader.TFrame", padding=(10, 7))
        header.pack(fill="x", pady=(0, 8))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="EVIDENCE / TRACEABILITY", style="CX.PanelHeader.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            header,
            text="Retained verification evidence is historical; currency is assessed separately.",
            style="CX.SurfaceMuted.TLabel",
        ).grid(row=0, column=1, sticky="e")

        actions = ttk.Frame(self, style="CX.Toolbar.TFrame", padding=(8, 5))
        actions.pack(fill="x", pady=(0, 8))
        ttk.Label(actions, text="TRACEABILITY", style="CX.ToolbarSection.TLabel").pack(
            side="left", padx=(0, 8)
        )
        for label, callback in (
            ("Verification History", on_history),
            ("ProofGraph", on_proofgraph),
            ("Engineering Report", on_report),
        ):
            ttk.Button(
                actions,
                text=label,
                style="CX.Compact.TButton",
                command=callback,
            ).pack(side="left", padx=2)

        metrics = ttk.Frame(self)
        metrics.pack(fill="x", pady=(0, 8))
        for index, (title, variable) in enumerate(
            (
                ("RETAINED RECORDS", self.record_count_var),
                ("PROOFGRAPHS", self.proofgraph_count_var),
                ("LATEST SEQUENCE", self.latest_var),
                ("LATEST CURRENCY", self.currency_var),
            )
        ):
            card = ttk.Frame(metrics, style="CX.Panel.TFrame", padding=(10, 7))
            card.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 3, 0))
            metrics.columnconfigure(index, weight=1)
            ttk.Label(card, text=title, style="CX.InstrumentName.TLabel").pack(anchor="w")
            ttk.Label(card, textvariable=variable, style="CX.InstrumentValue.TLabel").pack(anchor="w")

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True)
        table_frame = ttk.Frame(body, style="CX.Panel.TFrame", padding=(8, 8))
        detail_frame = ttk.Frame(body, style="CX.Panel.TFrame", padding=(8, 8))
        body.add(table_frame, weight=5)
        body.add(detail_frame, weight=3)

        ttk.Label(table_frame, text="RETAINED VERIFICATION RECORDS", style="CX.PanelSection.TLabel").pack(
            anchor="w", pady=(0, 6)
        )
        host = ttk.Frame(table_frame, style="CX.Panel.TFrame")
        host.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            host,
            columns=("completed", "analysis", "status", "currency", "evidence"),
            show="tree headings",
            selectmode="browse",
        )
        self.tree.heading("#0", text="#")
        self.tree.heading("completed", text="Completed UTC")
        self.tree.heading("analysis", text="Analysis")
        self.tree.heading("status", text="Verdict")
        self.tree.heading("currency", text="Current state")
        self.tree.heading("evidence", text="Evidence")
        self.tree.column("#0", width=55, stretch=False)
        self.tree.column("completed", width=175, stretch=False)
        self.tree.column("analysis", width=220)
        self.tree.column("status", width=120, stretch=False)
        self.tree.column("currency", width=175, stretch=False)
        self.tree.column("evidence", width=80, stretch=False, anchor="center")
        scroll = ttk.Scrollbar(host, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._show_selected)

        ttk.Label(detail_frame, text="EVIDENCE RECORD", style="CX.PanelSection.TLabel").pack(
            anchor="w", pady=(0, 6)
        )
        detail_host = ttk.Frame(detail_frame, style="CX.Panel.TFrame")
        detail_host.pack(fill="both", expand=True)
        self.detail = tk.Text(detail_host, wrap="word", state="disabled", height=16)
        detail_scroll = ttk.Scrollbar(detail_host, orient="vertical", command=self.detail.yview)
        self.detail.configure(yscrollcommand=detail_scroll.set)
        self.detail.pack(side="left", fill="both", expand=True)
        detail_scroll.pack(side="right", fill="y")

    def refresh(
        self,
        records: list[dict[str, Any]] | None,
        *,
        proofgraph_count: int = 0,
        currency: dict[str, Any] | None = None,
    ) -> None:
        raw_records = records if isinstance(records, list) else []
        assessments = {}
        if isinstance(currency, dict):
            assessments = {
                str(item.get("analysis_id")): item
                for item in currency.get("analyses", [])
                if isinstance(item, dict) and item.get("analysis_id") is not None
            }

        projected = [
            evidence_record_projection(record, assessments.get(str(record.get("analysis_id"))))
            for record in raw_records
            if isinstance(record, dict)
        ]
        self.record_count_var.set(str(len(projected)))
        self.proofgraph_count_var.set(str(max(0, int(proofgraph_count))))
        self.latest_var.set(
            f"#{projected[-1]['sequence']}" if projected and projected[-1]["sequence"] is not None else "—"
        )
        self.currency_var.set(
            projected[-1]["currency_state"].upper().replace("_", " ")
            if projected
            else "NO RECORDS"
        )

        self.tree.delete(*self.tree.get_children())
        self._records_by_iid.clear()
        for index, item in enumerate(reversed(projected)):
            sequence = item["sequence"]
            iid = f"record:{sequence if sequence is not None else index}:{index}"
            self.tree.insert(
                "",
                "end",
                iid=iid,
                text=str(sequence if sequence is not None else "—"),
                values=(
                    item["completed_at_utc"],
                    item["analysis_name"],
                    item["verification_status"].upper(),
                    item["currency_state"].upper().replace("_", " "),
                    str(item["evidence_count"]),
                ),
                tags=(item["currency_state"], item["verification_status"]),
            )
            self._records_by_iid[iid] = item

        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children[0])
            self.tree.focus(children[0])
            self._show_selected()
        else:
            self._set_detail(
                "No retained canonical verification evidence is present.\n\n"
                "Missing evidence is displayed as missing; CleanroomX does not turn it into zero or PASS."
            )

    def selected_record(self) -> dict[str, Any] | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return self._records_by_iid.get(selection[0])

    def _show_selected(self, _event=None) -> None:
        item = self.selected_record()
        if item is None:
            return
        verified = item["verified"]
        verified_text = "TRUE" if verified is True else "FALSE" if verified is False else "NOT REPORTED"
        complete = item["complete"]
        complete_text = "TRUE" if complete is True else "FALSE" if complete is False else "NOT REPORTED"
        lines = [
            f"Retained verification record #{item['sequence']}",
            "",
            f"Analysis: {item['analysis_name']}",
            f"Kind: {item['analysis_kind'] or '—'}",
            f"Completed UTC: {item['completed_at_utc'] or '—'}",
            f"Historical verdict: {item['verification_status'].upper()}",
            f"Verified flag: {verified_text}",
            f"Complete flag: {complete_text}",
            f"Current currency: {item['currency_state'].upper().replace('_', ' ')}",
            f"Evidence objects: {item['evidence_count']}",
            f"Verification findings: {item['finding_count']}",
            "",
            f"Source project revision: {item['source_revision'] or '—'}",
            f"Record SHA-256: {item['record_sha256'] or '—'}",
            "",
            "A retained historical verdict is not automatically a verdict on the current project state.",
        ]
        self._set_detail("\n".join(lines))

    def _set_detail(self, value: str) -> None:
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", value)
        self.detail.configure(state="disabled")

    def apply_theme(self, theme: str) -> None:
        palette = theme_palette(theme)
        self.detail.configure(
            background=palette["field"],
            foreground=palette["field_text"],
            insertbackground=palette["text"],
            selectbackground=palette["selection"],
            selectforeground=palette["selection_text"],
        )
        for state in (
            "current",
            "stale",
            "dependency freshness unverifiable",
            "dependency_freshness_unverifiable",
            "not verified",
            "not_verified",
            "historical",
            "not in current project",
        ):
            style = status_style_name(state)
            color = {
                "CX.Status.Pass.TLabel": palette["success"],
                "CX.Status.Fail.TLabel": palette["error"],
                "CX.Status.Warning.TLabel": palette["warning"],
                "CX.Status.Attention.TLabel": palette["attention"],
                "CX.Status.Info.TLabel": palette["info"],
            }.get(style, palette["secondary_text"])
            self.tree.tag_configure(state, foreground=color)
