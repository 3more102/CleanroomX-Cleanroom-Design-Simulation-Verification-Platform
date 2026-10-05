from __future__ import annotations

import json
from typing import Any, Callable

import tkinter as tk
from tkinter import ttk

from .compliance_rulepack import compliance_check_from_dict
from .gui_table import TreeviewTableBehavior
from .gui_theme import status_style_name, theme_palette


def _cell(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, str):
        return value or "—"
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def compliance_input_projection(value: Any) -> dict[str, Any]:
    """Project a compliance analysis input without evaluating engineering criteria."""
    if not isinstance(value, dict):
        return {
            "valid": False,
            "error": "Compliance analysis input must be a JSON object.",
            "name": "—",
            "pack": None,
            "rules": [],
        }
    try:
        check = compliance_check_from_dict(value)
    except Exception as exc:
        return {
            "valid": False,
            "error": str(exc),
            "name": str(value.get("name") or "—"),
            "pack": None,
            "rules": [],
        }

    pack = check.rule_pack
    rules = [
        {
            "id": rule.id,
            "title": rule.title,
            "evidence_path": rule.evidence_path,
            "operator": rule.operator,
            "expected": rule.expected,
            "unit": rule.unit,
            "tolerance": rule.tolerance,
            "source": rule.source or pack.source,
            "reference": rule.reference,
        }
        for rule in pack.rules
    ]
    return {
        "valid": True,
        "error": None,
        "name": check.name,
        "pack": {
            "id": pack.id,
            "version": pack.version,
            "title": pack.title,
            "source": pack.source,
        },
        "rules": rules,
    }


def compliance_result_projection(value: Any) -> dict[str, Any]:
    """Project an already-computed canonical compliance result for display."""
    if not isinstance(value, dict):
        return {
            "available": False,
            "status": "not_run",
            "complete": None,
            "verified": None,
            "summary": {},
            "rule_pack_sha256": None,
            "evidence_sha256": None,
            "findings": [],
            "engineering_note": None,
        }

    summary = value.get("summary")
    pack = value.get("rule_pack")
    findings = value.get("findings")
    return {
        "available": True,
        "status": str(value.get("status") or "unknown"),
        "complete": value.get("complete") if isinstance(value.get("complete"), bool) else None,
        "verified": value.get("verified") if isinstance(value.get("verified"), bool) else None,
        "summary": dict(summary) if isinstance(summary, dict) else {},
        "rule_pack_sha256": (
            str(pack.get("sha256")) if isinstance(pack, dict) and pack.get("sha256") else None
        ),
        "evidence_sha256": str(value.get("evidence_sha256")) if value.get("evidence_sha256") else None,
        "findings": [item for item in findings if isinstance(item, dict)]
        if isinstance(findings, list)
        else [],
        "engineering_note": (
            str(value.get("engineering_note")) if value.get("engineering_note") else None
        ),
    }


class ComplianceWorkspace(ttk.Frame):
    """Read-only rule-pack workbench over canonical compliance_check analyses."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_run: Callable[[], None],
        on_validate: Callable[[], None],
        on_open_inputs: Callable[[], None],
        on_open_results: Callable[[], None],
        on_open_history: Callable[[], None] | None = None,
        on_open_traceability: Callable[[], None] | None = None,
        on_select_analysis: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(master, padding=(12, 10))
        self._on_select_analysis = on_select_analysis
        self._analysis_id_by_display: dict[str, str] = {}
        self._suppress_selection = False
        self._rows_by_iid: dict[str, dict[str, Any]] = {}

        self.analysis_var = tk.StringVar(value="Select compliance analysis…")
        self.title_var = tk.StringVar(value="No compliance rule pack selected")
        self.state_var = tk.StringVar(value="NOT CONFIGURED")
        self.pack_var = tk.StringVar(value="—")
        self.source_var = tk.StringVar(value="—")
        self.rule_count_var = tk.StringVar(value="0 rules")
        self.summary_var = tk.StringVar(value="No canonical compliance result")
        self.digest_var = tk.StringVar(value="Rule/evidence digests unavailable until run")
        self.boundary_var = tk.StringVar(
            value=(
                "A rule-pack check compares supplied evidence with supplied criteria; "
                "it is not by itself regulatory approval or cleanroom certification."
            )
        )
        self.search_var = tk.StringVar()
        self.state_filter_var = tk.StringVar(value="All states")
        self.visible_var = tk.StringVar(value="0 visible")
        self._rules_current: list[dict[str, Any]] = []
        self._findings_current: list[dict[str, Any]] = []

        header = ttk.Frame(self, style="CX.PanelHeader.TFrame", padding=(10, 7))
        header.pack(fill="x", pady=(0, 8))
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header,
            text="REQUIREMENTS / COMPLIANCE RULE PACKS",
            style="CX.PanelHeader.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            textvariable=self.title_var,
            style="CX.PanelHeader.TLabel",
        ).grid(row=0, column=1, sticky="e", padx=(12, 8))
        self.state_badge = ttk.Label(
            header,
            textvariable=self.state_var,
            style="CX.Status.Neutral.TLabel",
        )
        self.state_badge.grid(row=0, column=2, sticky="e")

        controls = ttk.Frame(self, style="CX.Toolbar.TFrame", padding=(8, 5))
        controls.pack(fill="x", pady=(0, 8))
        ttk.Label(controls, text="CHECK", style="CX.Section.TLabel").pack(
            side="left", padx=(0, 5)
        )
        self.analysis_combo = ttk.Combobox(
            controls,
            textvariable=self.analysis_var,
            values=(),
            state="disabled",
            width=36,
        )
        self.analysis_combo.pack(side="left", padx=(0, 8))
        self.analysis_combo.bind("<<ComboboxSelected>>", self._analysis_selected)
        ttk.Separator(controls, orient="vertical").pack(
            side="left", fill="y", padx=(0, 7)
        )
        self.run_button = ttk.Button(
            controls,
            text="▶ Run Check",
            style="CX.Primary.TButton",
            command=on_run,
            state="disabled",
        )
        self.run_button.pack(side="left", padx=2)
        ttk.Button(
            controls,
            text="Validate Input",
            style="CX.Compact.TButton",
            command=on_validate,
        ).pack(side="left", padx=2)
        ttk.Button(
            controls,
            text="Inputs",
            style="CX.Compact.TButton",
            command=on_open_inputs,
        ).pack(side="left", padx=2)
        ttk.Button(
            controls,
            text="Results",
            style="CX.Compact.TButton",
            command=on_open_results,
        ).pack(side="left", padx=2)
        ttk.Button(
            controls,
            text="Run History",
            style="CX.Compact.TButton",
            command=on_open_history or (lambda: None),
            state="normal" if on_open_history is not None else "disabled",
        ).pack(side="left", padx=2)
        ttk.Button(
            controls,
            text="Project Traceability",
            style="CX.Compact.TButton",
            command=on_open_traceability or (lambda: None),
            state="normal" if on_open_traceability is not None else "disabled",
        ).pack(side="left", padx=2)

        context = ttk.Frame(self, padding=(8, 6))
        context.pack(fill="x", pady=(0, 8))
        context.columnconfigure(1, weight=1)
        self._kv(context, 0, "Rule pack", self.pack_var)
        self._kv(context, 1, "Declared source", self.source_var)
        self._kv(context, 2, "Configured criteria", self.rule_count_var)
        self._kv(context, 3, "Result summary", self.summary_var)
        self._kv(context, 4, "Trace digests", self.digest_var)
        ttk.Label(
            context,
            textvariable=self.boundary_var,
            wraplength=950,
            justify="left",
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(7, 0))

        filters = ttk.Frame(self, style="CX.Toolbar.TFrame", padding=(8, 5))
        filters.pack(fill="x", pady=(0, 8))
        ttk.Label(filters, text="FILTER", style="CX.Section.TLabel").pack(
            side="left", padx=(0, 5)
        )
        self.search_entry = ttk.Entry(filters, textvariable=self.search_var, width=34)
        self.search_entry.pack(side="left", padx=(0, 7))
        self.state_combo = ttk.Combobox(
            filters,
            textvariable=self.state_filter_var,
            values=("All states", "Pass", "Fail", "Not checked", "Not run"),
            state="readonly",
            width=14,
        )
        self.state_combo.pack(side="left", padx=(0, 7))
        ttk.Button(
            filters,
            text="Clear",
            style="CX.Compact.TButton",
            command=self.clear_filters,
        ).pack(side="left")
        ttk.Label(filters, textvariable=self.visible_var, anchor="e").pack(
            side="right"
        )

        body = ttk.Panedwindow(self, orient="vertical")
        body.pack(fill="both", expand=True)
        table_host = ttk.Frame(body)
        detail_host = ttk.Frame(body)
        body.add(table_host, weight=4)
        body.add(detail_host, weight=1)

        columns = (
            "status",
            "id",
            "title",
            "operator",
            "expected",
            "actual",
            "unit",
            "tolerance",
            "path",
            "reference",
            "source",
        )
        self.tree = ttk.Treeview(
            table_host,
            columns=columns,
            show="headings",
            selectmode="browse",
            height=10,
        )
        headings = {
            "status": "State",
            "id": "Rule ID",
            "title": "Criterion",
            "operator": "Operator",
            "expected": "Expected",
            "actual": "Actual",
            "unit": "Unit",
            "tolerance": "Tolerance",
            "path": "Evidence path",
            "reference": "Reference",
            "source": "Source",
        }
        widths = {
            "status": 100,
            "id": 130,
            "title": 240,
            "operator": 90,
            "expected": 130,
            "actual": 130,
            "unit": 75,
            "tolerance": 85,
            "path": 250,
            "reference": 130,
            "source": 250,
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(
                column,
                width=widths[column],
                minwidth=65,
                stretch=column in {"title", "path", "source"},
            )
        yscroll = ttk.Scrollbar(table_host, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(table_host, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        table_host.rowconfigure(0, weight=1)
        table_host.columnconfigure(0, weight=1)
        self.table_behavior = TreeviewTableBehavior(
            self.tree,
            sortable_columns=columns,
            copy_columns=columns,
        )
        self._configure_tree_tags("dark")
        self.tree.bind("<<TreeviewSelect>>", self._show_detail, add="+")

        self.detail = tk.Text(
            detail_host,
            wrap="word",
            height=7,
            state="disabled",
            borderwidth=0,
        )
        detail_scroll = ttk.Scrollbar(
            detail_host,
            orient="vertical",
            command=self.detail.yview,
        )
        self.detail.configure(yscrollcommand=detail_scroll.set)
        self.detail.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=4)
        detail_scroll.pack(side="right", fill="y", pady=4)
        self._set_detail(
            "Select a configured compliance_check analysis. CleanroomX displays "
            "criteria and canonical run findings here without re-evaluating them in the GUI."
        )
        self.search_var.trace_add("write", lambda *_: self._render_rows())
        self.state_filter_var.trace_add("write", lambda *_: self._render_rows())

    @staticmethod
    def _kv(master: ttk.Frame, row: int, label: str, variable: tk.StringVar) -> None:
        ttk.Label(master, text=label, style="CX.Section.TLabel").grid(
            row=row, column=0, sticky="nw", padx=(0, 10), pady=2
        )
        ttk.Label(master, textvariable=variable, wraplength=850, justify="left").grid(
            row=row, column=1, sticky="nw", pady=2
        )

    def set_analysis_options(
        self,
        analyses: list[tuple[str, str]] | tuple[tuple[str, str], ...],
        *,
        active_id: str | None,
    ) -> None:
        mapping: dict[str, str] = {}
        active_display = ""
        for analysis_id, name in analyses:
            display = f"{name} · {analysis_id}"
            mapping[display] = str(analysis_id)
            if active_id is not None and str(analysis_id) == str(active_id):
                active_display = display
        self._analysis_id_by_display = mapping
        self._suppress_selection = True
        try:
            self.analysis_combo.configure(
                values=tuple(mapping),
                state=(
                    "readonly"
                    if mapping and self._on_select_analysis is not None
                    else "disabled"
                ),
            )
            self.analysis_var.set(
                active_display if active_display else "Select compliance analysis…"
            )
        finally:
            self._suppress_selection = False

    def _analysis_selected(self, _event=None):
        if self._suppress_selection or self._on_select_analysis is None:
            return "break"
        analysis_id = self._analysis_id_by_display.get(self.analysis_var.get())
        if analysis_id:
            self._on_select_analysis(analysis_id)
        return "break"

    def set_context(
        self,
        *,
        analysis_name: str | None,
        analysis_input: Any = None,
        last_run: Any = None,
        running: bool = False,
    ) -> None:
        if not analysis_name:
            self.title_var.set("No compliance rule pack selected")
            self.state_var.set("NOT CONFIGURED")
            self.state_badge.configure(style="CX.Status.Neutral.TLabel")
            self.pack_var.set("—")
            self.source_var.set("—")
            self.rule_count_var.set("0 rules")
            self.summary_var.set("No canonical compliance result")
            self.digest_var.set("Rule/evidence digests unavailable until run")
            self.boundary_var.set(
                "Project Requirements and compliance rule packs are separate workflows; "
                "select a compliance_check analysis to inspect supplied criteria."
            )
            self.run_button.configure(state="disabled")
            self._populate([], [])
            self._set_detail(
                "No compliance_check analysis is active. Select a configured check "
                "from the selector above; project Requirements remain a separate workflow."
            )
            return

        projected = compliance_input_projection(analysis_input)
        self.title_var.set(str(analysis_name))
        if not projected["valid"]:
            self.state_var.set("INVALID INPUT")
            self.state_badge.configure(style="CX.Status.Fail.TLabel")
            self.pack_var.set("Invalid rule-pack input")
            self.source_var.set("—")
            self.rule_count_var.set("0 valid rules")
            self.summary_var.set(str(projected["error"]))
            self.digest_var.set("Unavailable")
            self.boundary_var.set(
                "The input is invalid under the canonical compliance parser; no criteria "
                "or verdicts are inferred from it."
            )
            self.run_button.configure(state="disabled")
            self._populate([], [])
            self._set_detail(
                "Input validation failed. The canonical compliance parser reported:\n\n"
                + str(projected["error"])
            )
            return

        pack = projected["pack"] or {}
        rules = projected["rules"]
        self.pack_var.set(
            f"{pack.get('title', '—')} · {pack.get('id', '—')} v{pack.get('version', '—')}"
        )
        self.source_var.set(str(pack.get("source") or "—"))
        self.rule_count_var.set(f"{len(rules)} rule(s)")
        self.run_button.configure(state="disabled" if running else "normal")

        result = compliance_result_projection(getattr(last_run, "result", None))
        if running:
            self.state_var.set("RUNNING")
            self.state_badge.configure(style=status_style_name("running"))
            self.summary_var.set("Canonical compliance analysis is running")
        elif not result["available"]:
            self.state_var.set("NOT RUN")
            self.state_badge.configure(style="CX.Status.Neutral.TLabel")
            self.summary_var.set("No current-session canonical compliance result")
        else:
            status = result["status"]
            self.state_var.set(status.upper().replace("_", " "))
            badge_state = (
                "warning"
                if status in {"pass_with_unchecked", "not_checked"}
                else status
            )
            self.state_badge.configure(style=status_style_name(badge_state))
            summary = result["summary"]
            self.summary_var.set(
                "{passed} pass · {failed} fail · {unchecked} not checked · "
                "verified {verified}".format(
                    passed=summary.get("pass_count", "—"),
                    failed=summary.get("fail_count", "—"),
                    unchecked=summary.get("not_checked_count", "—"),
                    verified=(
                        "YES"
                        if result["verified"] is True
                        else "NO"
                        if result["verified"] is False
                        else "UNKNOWN"
                    ),
                )
            )

        if result["available"]:
            self.digest_var.set(
                f"rule pack {result['rule_pack_sha256'] or '—'} · "
                f"evidence {result['evidence_sha256'] or '—'}"
            )
        else:
            self.digest_var.set("Rule/evidence digests unavailable until run")
        self.boundary_var.set(
            result["engineering_note"]
            or (
                "A rule-pack check compares supplied evidence with supplied criteria; "
                "it is not by itself regulatory approval or cleanroom certification."
            )
        )

        self._populate(rules, result["findings"])

    def clear_filters(self) -> None:
        self.search_var.set("")
        self.state_filter_var.set("All states")
        self.search_entry.focus_set()

    def _populate(
        self,
        rules: list[dict[str, Any]],
        findings: list[dict[str, Any]],
    ) -> None:
        self._rules_current = list(rules)
        self._findings_current = list(findings)
        self._render_rows()

    def _render_rows(self) -> None:
        if not hasattr(self, "tree"):
            return
        selected_id = None
        selection = self.tree.selection()
        if selection:
            selected = self._rows_by_iid.get(selection[0])
            if selected is not None:
                selected_id = selected.get("id")

        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._rows_by_iid.clear()

        finding_by_id = {
            str(item.get("id")): item
            for item in self._findings_current
            if item.get("id") not in (None, "")
        }
        query_tokens = [
            token
            for token in self.search_var.get().strip().casefold().split()
            if token
        ]
        state_filter = (
            self.state_filter_var.get()
            .strip()
            .casefold()
            .replace(" ", "_")
        )
        visible_count = 0
        for index, rule in enumerate(self._rules_current):
            rule_id = str(rule.get("id") or f"rule-{index + 1}")
            finding = finding_by_id.get(rule_id, {})
            status = str(finding.get("status") or "not_run").casefold()
            if state_filter not in {"", "all_states"} and status != state_filter:
                continue
            if query_tokens:
                haystack = " ".join(
                    (
                        rule_id,
                        str(rule.get("title") or ""),
                        str(rule.get("operator") or ""),
                        _cell(rule.get("expected")),
                        _cell(finding.get("actual")) if finding else "",
                        str(rule.get("unit") or ""),
                        _cell(rule.get("tolerance")),
                        str(rule.get("evidence_path") or ""),
                        str(rule.get("reference") or ""),
                        str(rule.get("source") or ""),
                        status,
                    )
                ).casefold()
                if not all(token in haystack for token in query_tokens):
                    continue

            iid = f"rule:{index}:{rule_id}"
            row = {**rule, "finding": finding, "status": status}
            self._rows_by_iid[iid] = row
            self.tree.insert(
                "",
                "end",
                iid=iid,
                tags=(f"state_{status}",),
                values=(
                    status.upper().replace("_", " "),
                    rule_id,
                    rule.get("title") or "",
                    rule.get("operator") or "",
                    _cell(rule.get("expected")),
                    _cell(finding.get("actual")) if finding else "—",
                    rule.get("unit") or "—",
                    _cell(rule.get("tolerance")),
                    rule.get("evidence_path") or "",
                    rule.get("reference") or "—",
                    rule.get("source") or "—",
                ),
            )
            visible_count += 1

        total = len(self._rules_current)
        self.visible_var.set(f"{visible_count} of {total} visible")
        self.table_behavior.reapply_sort()
        restored = False
        if selected_id is not None:
            for iid, row in self._rows_by_iid.items():
                if row.get("id") == selected_id:
                    self.tree.selection_set(iid)
                    self.tree.focus(iid)
                    self.tree.see(iid)
                    restored = True
                    break
        if not restored:
            items = self.tree.get_children()
            if items:
                self.tree.selection_set(items[0])
                self.tree.focus(items[0])
                self.tree.see(items[0])
        if self.tree.selection():
            self._show_detail()
        elif total and not visible_count:
            self._set_detail(
                "No compliance criteria match the active search/state filters."
            )

    def focus_rule(self, rule_id: str) -> bool:
        """Clear presentation filters and focus one configured canonical criterion."""
        target = str(rule_id or "").strip()
        if not target:
            return False
        self.search_var.set("")
        self.state_filter_var.set("All states")
        for iid, row in self._rows_by_iid.items():
            if str(row.get("id") or "") != target:
                continue
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self.tree.see(iid)
            self._show_detail()
            return True
        return False

    def _configure_tree_tags(self, theme: str) -> None:
        palette = theme_palette(theme)
        self.tree.tag_configure(
            "state_pass",
            foreground=palette["success"],
            font=("TkDefaultFont", 9, "bold"),
        )
        self.tree.tag_configure(
            "state_fail",
            foreground=palette["error"],
            font=("TkDefaultFont", 9, "bold"),
        )
        self.tree.tag_configure(
            "state_not_checked",
            foreground=palette["warning"],
        )
        self.tree.tag_configure(
            "state_not_run",
            foreground=palette["muted"],
        )

    def _show_detail(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        row = self._rows_by_iid.get(selection[0])
        if row is None:
            return
        finding = row.get("finding")
        finding = finding if isinstance(finding, dict) else {}
        lines = [
            f"{row.get('title', '')} [{row.get('id', '')}]",
            "",
            f"State: {str(row.get('status') or 'not_run').upper().replace('_', ' ')}",
            f"Evidence path: {row.get('evidence_path') or '—'}",
            f"Operator: {row.get('operator') or '—'}",
            f"Expected: {_cell(row.get('expected'))}",
            f"Actual: {_cell(finding.get('actual')) if finding else '—'}",
            f"Delta: {_cell(finding.get('delta')) if finding else '—'}",
            f"Unit: {row.get('unit') or '—'}",
            f"Tolerance: {_cell(row.get('tolerance'))}",
            f"Source: {row.get('source') or '—'}",
            f"Reference: {row.get('reference') or '—'}",
        ]
        if finding.get("note"):
            lines.extend(["", f"Backend note: {finding.get('note')}"])
        self._set_detail("\n".join(lines))

    def _set_detail(self, value: str) -> None:
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", str(value))
        self.detail.configure(state="disabled")

    def apply_theme(self, theme: str) -> None:
        palette = theme_palette(theme)
        self._configure_tree_tags(theme)
        self.detail.configure(
            background=palette["field"],
            foreground=palette["field_text"],
            insertbackground=palette["text"],
            selectbackground=palette["selection"],
            selectforeground=palette["selection_text"],
        )
