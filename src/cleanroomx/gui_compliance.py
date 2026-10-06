from __future__ import annotations

import copy
import json
from typing import Any, Callable

import tkinter as tk
from tkinter import messagebox, ttk

from .compliance_rulepack import (
    analyze_compliance_check,
    compliance_check_from_dict,
)
from .gui_input_validation import parse_finite_number, parse_json_field


def _json_text(value: Any) -> str:
    if value is None:
        return "null"
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
        separators=(",", ":"),
    )


def _strict_json_value(text: str, field_name: str) -> Any:
    return parse_json_field(text, field_name)


class ComplianceRulePackPanel(ttk.Frame):
    """Editable workstation surface over the canonical compliance rule-pack engine."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        input_getter: Callable[[], dict[str, Any] | None],
        input_setter: Callable[[dict[str, Any], str], bool],
        status_setter: Callable[[str], None] | None = None,
        confirm_delete: Callable[[str], bool] | None = None,
    ) -> None:
        super().__init__(master)
        self._input_getter = input_getter
        self._input_setter = input_setter
        self._status_setter = status_setter or (lambda _message: None)
        self._confirm_delete = confirm_delete or self._confirm_delete_rule
        self._payload: dict[str, Any] | None = None
        self._result: dict[str, Any] | None = None
        self._finding_by_iid: dict[str, dict[str, Any]] = {}
        self._sort_column: str | None = None
        self._sort_descending = False

        self.search_var = tk.StringVar()
        self.status_filter_var = tk.StringVar(value="All")
        self.operator_filter_var = tk.StringVar(value="All")
        self.summary_var = tk.StringVar(value="Select a compliance analysis to inspect its rule pack")
        self.identity_var = tk.StringVar(value="Rule-pack provenance unavailable")
        self.visible_var = tk.StringVar(value="0 visible")
        self.validation_var = tk.StringVar(value="Not evaluated")

        self.title_var = tk.StringVar()
        self.path_var = tk.StringVar()
        self.operator_var = tk.StringVar()
        self.expected_var = tk.StringVar()
        self.unit_var = tk.StringVar()
        self.tolerance_var = tk.StringVar()
        self.source_var = tk.StringVar()
        self.reference_var = tk.StringVar()

        self._build()
        for variable in (self.search_var, self.status_filter_var, self.operator_filter_var):
            variable.trace_add("write", lambda *_: self._populate())

    def _build(self) -> None:
        header = ttk.Frame(self, padding=(10, 8, 10, 6))
        header.pack(fill="x")
        ttk.Label(header, text="COMPLIANCE / RULE PACK", style="CX.Section.TLabel").pack(
            side="left"
        )
        ttk.Label(header, textvariable=self.validation_var).pack(side="right")
        provenance = ttk.Frame(self, padding=(10, 0, 10, 6))
        provenance.pack(fill="x")
        ttk.Label(
            provenance,
            textvariable=self.identity_var,
            anchor="w",
        ).pack(fill="x")

        toolbar = ttk.Frame(self, padding=(10, 0, 10, 7))
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="Refresh", command=self.refresh).pack(side="left")
        ttk.Label(toolbar, textvariable=self.summary_var).pack(
            side="left", fill="x", expand=True, padx=(10, 0)
        )

        filters = ttk.Frame(self, padding=(10, 0, 10, 7))
        filters.pack(fill="x")
        ttk.Label(filters, text="Search").pack(side="left")
        self.search_entry = ttk.Entry(filters, textvariable=self.search_var, width=28)
        self.search_entry.pack(side="left", padx=(4, 8))
        ttk.Label(filters, text="State").pack(side="left")
        self.status_combo = ttk.Combobox(
            filters,
            textvariable=self.status_filter_var,
            values=("All", "Pass", "Fail", "Not checked"),
            state="readonly",
            width=13,
        )
        self.status_combo.pack(side="left", padx=(4, 8))
        ttk.Label(filters, text="Operator").pack(side="left")
        self.operator_combo = ttk.Combobox(
            filters,
            textvariable=self.operator_filter_var,
            values=("All", "exists", "equals", "min", "max", "range", "one_of"),
            state="readonly",
            width=11,
        )
        self.operator_combo.pack(side="left", padx=(4, 8))
        ttk.Button(filters, text="Clear", command=self.clear_filters).pack(side="left")
        ttk.Label(filters, textvariable=self.visible_var).pack(side="right")

        body = ttk.Panedwindow(self, orient="vertical")
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        table_frame = ttk.Frame(body)
        inspector_frame = ttk.Frame(body)
        body.add(table_frame, weight=3)
        body.add(inspector_frame, weight=2)

        columns = (
            "state",
            "id",
            "title",
            "operator",
            "path",
            "expected",
            "actual",
            "unit",
            "tolerance",
            "reference",
        )
        self.tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
            height=10,
        )
        headings = {
            "state": "State",
            "id": "Rule ID",
            "title": "Rule",
            "operator": "Operator",
            "path": "Evidence path",
            "expected": "Expected",
            "actual": "Actual",
            "unit": "Unit",
            "tolerance": "Tolerance",
            "reference": "Reference",
        }
        widths = {
            "state": 95,
            "id": 135,
            "title": 220,
            "operator": 80,
            "path": 250,
            "expected": 150,
            "actual": 150,
            "unit": 80,
            "tolerance": 90,
            "reference": 140,
        }
        self._headings = headings
        for column in columns:
            self.tree.heading(
                column,
                text=headings[column],
                command=lambda selected=column: self._sort_by(selected),
            )
            self.tree.column(
                column,
                width=widths[column],
                minwidth=65,
                stretch=column in {"title", "path"},
            )
        yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", self._show_selected)
        self.tree.bind("<Double-1>", lambda _event: self._focus_editor())
        self.tree.bind("<Button-3>", self._show_context_menu)
        self.tree.bind("<Control-c>", lambda _event: self.copy_selected())
        self.tree.bind("<Delete>", lambda _event: self.delete_selected())

        inspector_frame.columnconfigure(1, weight=1)
        inspector_frame.columnconfigure(3, weight=1)
        row = 0
        ttk.Label(inspector_frame, text="Selected rule", style="CX.Section.TLabel").grid(
            row=row, column=0, columnspan=4, sticky="w", padx=6, pady=(6, 4)
        )
        row += 1

        def field(label: str, variable: tk.StringVar, column: int, *, readonly: bool = False):
            ttk.Label(inspector_frame, text=label).grid(
                row=row, column=column, sticky="w", padx=(6, 4), pady=3
            )
            widget: ttk.Widget
            if label == "Operator":
                widget = ttk.Combobox(
                    inspector_frame,
                    textvariable=variable,
                    values=("exists", "equals", "min", "max", "range", "one_of"),
                    state="readonly",
                )
            else:
                widget = ttk.Entry(
                    inspector_frame,
                    textvariable=variable,
                    state="readonly" if readonly else "normal",
                )
            widget.grid(row=row, column=column + 1, sticky="ew", padx=(0, 8), pady=3)
            return widget

        self.title_entry = field("Title", self.title_var, 0)
        self.path_entry = field("Evidence path", self.path_var, 2)
        row += 1
        self.operator_entry = field("Operator", self.operator_var, 0)
        self.expected_entry = field("Expected JSON", self.expected_var, 2)
        row += 1
        self.unit_entry = field("Unit", self.unit_var, 0)
        self.tolerance_entry = field("Tolerance", self.tolerance_var, 2)
        row += 1
        self.source_entry = field("Source", self.source_var, 0)
        self.reference_entry = field("Reference", self.reference_var, 2)
        row += 1

        actions = ttk.Frame(inspector_frame)
        actions.grid(row=row, column=0, columnspan=4, sticky="ew", padx=6, pady=(6, 3))
        self.apply_button = ttk.Button(actions, text="Apply Rule", command=self.apply_selected)
        self.apply_button.pack(side="left")
        self.duplicate_button = ttk.Button(
            actions, text="Duplicate", command=self.duplicate_selected
        )
        self.duplicate_button.pack(side="left", padx=(5, 0))
        self.delete_button = ttk.Button(actions, text="Delete", command=self.delete_selected)
        self.delete_button.pack(side="left", padx=(5, 0))
        self.copy_button = ttk.Button(actions, text="Copy Finding", command=self.copy_selected)
        self.copy_button.pack(side="left", padx=(5, 0))

        row += 1
        self.detail = tk.Text(
            inspector_frame,
            height=7,
            wrap="word",
            state="disabled",
            borderwidth=0,
        )
        self.detail.grid(
            row=row,
            column=0,
            columnspan=4,
            sticky="nsew",
            padx=6,
            pady=(2, 6),
        )
        inspector_frame.rowconfigure(row, weight=1)
        self._set_editor_enabled(False)

    def apply_theme(self, palette: dict[str, str]) -> None:
        self.detail.configure(
            background=palette["field"],
            foreground=palette["field_text"],
            insertbackground=palette["text"],
            selectbackground=palette["selection"],
            selectforeground=palette["selection_text"],
        )

    def clear_filters(self) -> None:
        self.search_var.set("")
        self.status_filter_var.set("All")
        self.operator_filter_var.set("All")
        self.search_entry.focus_set()

    def _set_editor_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for widget in (
            self.title_entry,
            self.path_entry,
            self.expected_entry,
            self.unit_entry,
            self.tolerance_entry,
            self.source_entry,
            self.reference_entry,
        ):
            widget.configure(state=state)
        self.operator_entry.configure(state="readonly" if enabled else "disabled")
        for button in (self.apply_button, self.duplicate_button, self.delete_button, self.copy_button):
            button.configure(state="normal" if enabled else "disabled")

    def refresh(self) -> dict[str, Any] | None:
        payload = self._input_getter()
        self._payload = copy.deepcopy(payload) if isinstance(payload, dict) else None
        self._result = None
        if self._payload is None:
            self.validation_var.set("No active compliance analysis")
            self.identity_var.set("Rule-pack provenance unavailable")
            self.summary_var.set(
                "Select a compliance rule-pack analysis to inspect backend-authoritative criteria."
            )
            self._populate()
            return None
        try:
            check = compliance_check_from_dict(copy.deepcopy(self._payload))
            self._result = analyze_compliance_check(check)
        except Exception as exc:
            self.validation_var.set("INVALID INPUT")
            self.identity_var.set("Rule-pack provenance unavailable until the input is valid")
            self.summary_var.set(str(exc))
            self._populate()
            self._status_setter(f"Compliance rule pack invalid: {exc}")
            return None

        summary = self._result["summary"]
        pack = self._result["rule_pack"]
        self.validation_var.set(str(self._result["status"]).upper())
        self.identity_var.set(
            f"Pack {pack['id']} v{pack['version']} · "
            f"criteria SHA-256 {pack['sha256']} · "
            f"evidence SHA-256 {self._result['evidence_sha256']}"
        )
        self.summary_var.set(
            f"{self._result['rule_pack']['title']} · "
            f"{summary['pass_count']} pass · {summary['fail_count']} fail · "
            f"{summary['not_checked_count']} not checked"
        )
        self._populate()
        return self._result

    @staticmethod
    def _state_rank(value: Any) -> int:
        return {"fail": 0, "not_checked": 1, "pass": 2}.get(
            str(value or "").casefold(),
            99,
        )

    def _sort_value(self, finding: dict[str, Any]):
        column = self._sort_column
        if column == "state":
            return (
                self._state_rank(finding.get("status")),
                str(finding.get("id", "")).casefold(),
            )
        if column == "id":
            return str(finding.get("id", "")).casefold()
        if column == "title":
            return str(finding.get("title", "")).casefold()
        if column == "operator":
            return str(finding.get("operator", "")).casefold()
        if column == "path":
            return str(finding.get("evidence_path", "")).casefold()
        if column == "expected":
            return _json_text(finding.get("expected")).casefold()
        if column == "actual":
            return _json_text(finding.get("actual")).casefold()
        if column == "unit":
            return str(finding.get("unit") or "").casefold()
        if column == "tolerance":
            value = finding.get("tolerance", 0.0)
            return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0
        if column == "reference":
            return str(finding.get("reference") or "").casefold()
        return 0

    def _sort_by(self, column: str) -> None:
        if column == self._sort_column:
            self._sort_descending = not self._sort_descending
        else:
            self._sort_column = column
            self._sort_descending = False
        for key, label in self._headings.items():
            suffix = ""
            if key == self._sort_column:
                suffix = " ▼" if self._sort_descending else " ▲"
            self.tree.heading(key, text=label + suffix)
        self._populate()

    def _filtered_findings(self) -> list[dict[str, Any]]:
        if not isinstance(self._result, dict):
            return []
        findings = [
            item
            for item in self._result.get("findings", [])
            if isinstance(item, dict)
        ]
        query = self.search_var.get().strip().casefold()
        status_filter = self.status_filter_var.get().strip().casefold().replace(" ", "_")
        operator_filter = self.operator_filter_var.get().strip().casefold()
        visible: list[dict[str, Any]] = []
        for item in findings:
            status = str(item.get("status", "")).casefold()
            operator = str(item.get("operator", "")).casefold()
            if status_filter and status_filter != "all" and status != status_filter:
                continue
            if operator_filter and operator_filter != "all" and operator != operator_filter:
                continue
            if query:
                haystack = " ".join(
                    (
                        str(item.get("id", "")),
                        str(item.get("title", "")),
                        str(item.get("evidence_path", "")),
                        operator,
                        _json_text(item.get("expected")),
                        _json_text(item.get("actual")),
                        str(item.get("unit") or ""),
                        str(item.get("source") or ""),
                        str(item.get("reference") or ""),
                    )
                ).casefold()
                if query not in haystack:
                    continue
            visible.append(item)
        return visible

    def _populate(self) -> None:
        selected_id = None
        selected = self.selected_finding()
        if selected is not None:
            selected_id = str(selected.get("id", ""))

        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._finding_by_iid.clear()

        visible = self._filtered_findings()
        if self._sort_column is not None:
            visible.sort(
                key=self._sort_value,
                reverse=self._sort_descending,
            )
        for index, finding in enumerate(visible):
            iid = f"rule:{index}:{finding.get('id', '')}"
            self.tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    str(finding.get("status", "")).replace("_", " ").upper(),
                    finding.get("id", ""),
                    finding.get("title", ""),
                    finding.get("operator", ""),
                    finding.get("evidence_path", ""),
                    _json_text(finding.get("expected")),
                    _json_text(finding.get("actual")),
                    finding.get("unit") or "",
                    finding.get("tolerance", 0.0),
                    finding.get("reference") or "",
                ),
                tags=(str(finding.get("status", "")),),
            )
            self._finding_by_iid[iid] = finding

        total = (
            int(self._result.get("summary", {}).get("rule_count", 0))
            if isinstance(self._result, dict)
            else 0
        )
        self.visible_var.set(f"{len(visible)} of {total} visible")

        target = None
        if selected_id:
            for iid, finding in self._finding_by_iid.items():
                if str(finding.get("id", "")) == selected_id:
                    target = iid
                    break
        if target is None and visible:
            target = next(iter(self._finding_by_iid))
        if target is not None:
            self.tree.selection_set(target)
            self.tree.focus(target)
            self.tree.see(target)
        self._show_selected()

    def selected_finding(self) -> dict[str, Any] | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return self._finding_by_iid.get(selection[0])

    def _raw_rule(self, rule_id: str) -> dict[str, Any] | None:
        if not isinstance(self._payload, dict):
            return None
        pack = self._payload.get("rule_pack")
        rules = pack.get("rules") if isinstance(pack, dict) else None
        if not isinstance(rules, list):
            return None
        for rule in rules:
            if isinstance(rule, dict) and str(rule.get("id", "")) == rule_id:
                return rule
        return None

    def _show_selected(self, _event=None) -> None:
        finding = self.selected_finding()
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        if finding is None:
            self._set_editor_enabled(False)
            for variable in (
                self.title_var,
                self.path_var,
                self.operator_var,
                self.expected_var,
                self.unit_var,
                self.tolerance_var,
                self.source_var,
                self.reference_var,
            ):
                variable.set("")
            if self._result is None:
                self.detail.insert(
                    "1.0",
                    "No evaluated compliance rule pack is available for the active analysis.",
                )
            elif self._result.get("findings") and not self._filtered_findings():
                self.detail.insert(
                    "1.0",
                    "No rule-pack findings match the active filters.",
                )
            self.detail.configure(state="disabled")
            return

        rule = self._raw_rule(str(finding.get("id", ""))) or {}
        self.title_var.set(str(rule.get("title", "")))
        self.path_var.set(str(rule.get("evidence_path", "")))
        self.operator_var.set(str(rule.get("operator", "")))
        self.expected_var.set(
            "" if rule.get("operator") == "exists" else _json_text(rule.get("expected"))
        )
        self.unit_var.set(str(rule.get("unit") or ""))
        self.tolerance_var.set(str(rule.get("tolerance", 0.0)))
        self.source_var.set(str(rule.get("source") or ""))
        self.reference_var.set(str(rule.get("reference") or ""))
        self._set_editor_enabled(True)

        lines = [
            f"{str(finding.get('status', '')).replace('_', ' ').upper()} · {finding.get('id', '')}",
            str(finding.get("title", "")),
            "",
            f"Evidence path: {finding.get('evidence_path', '')}",
            f"Operator: {finding.get('operator', '')}",
            f"Expected: {_json_text(finding.get('expected'))}",
            f"Actual: {_json_text(finding.get('actual'))}",
            f"Delta: {_json_text(finding.get('delta'))}",
            f"Unit: {finding.get('unit') or '—'}",
            f"Tolerance: {finding.get('tolerance', 0.0)}",
            f"Source: {finding.get('source') or '—'}",
            f"Reference: {finding.get('reference') or '—'}",
        ]
        if finding.get("note"):
            lines.extend(("", f"Note: {finding['note']}"))
        self.detail.insert("1.0", "\n".join(lines))
        self.detail.configure(state="disabled")

    def _focus_editor(self) -> str:
        if self.selected_finding() is not None:
            self.title_entry.focus_set()
            self.title_entry.selection_range(0, "end")
        return "break"

    def _show_context_menu(self, event: tk.Event) -> str:
        iid = self.tree.identify_row(event.y)
        if iid:
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self._show_selected()
        menu = tk.Menu(self, tearoff=False)
        finding = self.selected_finding()
        state = "normal" if finding is not None else "disabled"
        menu.add_command(
            label="Edit rule",
            state=state,
            command=self._focus_editor,
        )
        menu.add_command(
            label="Duplicate rule",
            state=state,
            command=self.duplicate_selected,
        )
        menu.add_command(
            label="Delete rule",
            state=state,
            command=self.delete_selected,
        )
        menu.add_separator()
        menu.add_command(
            label="Copy finding",
            state=state,
            command=self.copy_selected,
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _candidate_from_editor(self) -> tuple[dict[str, Any], str]:
        finding = self.selected_finding()
        if finding is None or not isinstance(self._payload, dict):
            raise ValueError("select a compliance rule first")
        rule_id = str(finding.get("id", ""))
        candidate = copy.deepcopy(self._payload)
        pack = candidate.get("rule_pack")
        rules = pack.get("rules") if isinstance(pack, dict) else None
        if not isinstance(rules, list):
            raise ValueError("rule_pack.rules is unavailable")
        rule = next(
            (
                item
                for item in rules
                if isinstance(item, dict) and str(item.get("id", "")) == rule_id
            ),
            None,
        )
        if rule is None:
            raise ValueError(f"rule {rule_id!r} is no longer available")

        rule["title"] = self.title_var.get().strip()
        rule["evidence_path"] = self.path_var.get().strip()
        operator = self.operator_var.get().strip()
        rule["operator"] = operator
        tolerance_text = self.tolerance_var.get().strip() or "0"
        tolerance = parse_finite_number(tolerance_text, "tolerance")
        rule["tolerance"] = tolerance

        if operator == "exists":
            rule.pop("expected", None)
        else:
            rule["expected"] = _strict_json_value(
                self.expected_var.get().strip(),
                "expected",
            )
        for key, variable in (
            ("unit", self.unit_var),
            ("source", self.source_var),
            ("reference", self.reference_var),
        ):
            value = variable.get().strip()
            if value:
                rule[key] = value
            else:
                rule.pop(key, None)

        compliance_check_from_dict(copy.deepcopy(candidate))
        return candidate, rule_id

    def apply_selected(self) -> bool:
        try:
            candidate, rule_id = self._candidate_from_editor()
        except Exception as exc:
            self.validation_var.set("EDIT INVALID")
            self._status_setter(f"Compliance rule edit rejected: {exc}")
            return False
        if not self._input_setter(candidate, f"Edit compliance rule {rule_id}"):
            return False
        self._status_setter(f"Updated compliance rule {rule_id}")
        self.refresh()
        self._select_rule_id(rule_id)
        return True

    def duplicate_selected(self) -> bool:
        finding = self.selected_finding()
        if finding is None or not isinstance(self._payload, dict):
            return False
        rule_id = str(finding.get("id", ""))
        candidate = copy.deepcopy(self._payload)
        pack = candidate.get("rule_pack")
        rules = pack.get("rules") if isinstance(pack, dict) else None
        if not isinstance(rules, list):
            return False
        source_index = next(
            (
                index
                for index, item in enumerate(rules)
                if isinstance(item, dict) and str(item.get("id", "")) == rule_id
            ),
            None,
        )
        if source_index is None:
            return False
        existing_ids = {
            str(item.get("id", ""))
            for item in rules
            if isinstance(item, dict)
        }
        suffix = 1
        new_id = f"{rule_id}-copy"
        while new_id in existing_ids:
            suffix += 1
            new_id = f"{rule_id}-copy-{suffix}"
        duplicate = copy.deepcopy(rules[source_index])
        duplicate["id"] = new_id
        duplicate["title"] = f"{duplicate.get('title', rule_id)} copy"
        rules.insert(source_index + 1, duplicate)
        try:
            compliance_check_from_dict(copy.deepcopy(candidate))
        except Exception as exc:
            self._status_setter(f"Could not duplicate compliance rule: {exc}")
            return False
        if not self._input_setter(candidate, f"Duplicate compliance rule {rule_id}"):
            return False
        self.refresh()
        self._select_rule_id(new_id)
        self._status_setter(f"Duplicated compliance rule as {new_id}")
        return True

    def _confirm_delete_rule(self, rule_id: str) -> bool:
        return bool(
            messagebox.askyesno(
                "Delete compliance rule",
                (
                    f"Delete compliance rule {rule_id!r}?\n\n"
                    "This changes the analysis input and can invalidate retained "
                    "current-run results. The edit can be restored with Undo."
                ),
                parent=self.winfo_toplevel(),
            )
        )

    def delete_selected(self) -> bool:
        finding = self.selected_finding()
        if finding is None or not isinstance(self._payload, dict):
            return False
        rule_id = str(finding.get("id", ""))
        candidate = copy.deepcopy(self._payload)
        pack = candidate.get("rule_pack")
        rules = pack.get("rules") if isinstance(pack, dict) else None
        if not isinstance(rules, list):
            return False
        if len(rules) <= 1:
            self._status_setter("A compliance rule pack must contain at least one rule")
            return False
        if not self._confirm_delete(rule_id):
            self._status_setter(f"Delete cancelled for compliance rule {rule_id}")
            return False
        pack["rules"] = [
            item
            for item in rules
            if not (isinstance(item, dict) and str(item.get("id", "")) == rule_id)
        ]
        try:
            compliance_check_from_dict(copy.deepcopy(candidate))
        except Exception as exc:
            self._status_setter(f"Could not delete compliance rule: {exc}")
            return False
        if not self._input_setter(candidate, f"Delete compliance rule {rule_id}"):
            return False
        self.refresh()
        self._status_setter(f"Deleted compliance rule {rule_id}")
        return True

    def _select_rule_id(self, rule_id: str) -> None:
        for iid, finding in self._finding_by_iid.items():
            if str(finding.get("id", "")) == rule_id:
                self.tree.selection_set(iid)
                self.tree.focus(iid)
                self.tree.see(iid)
                self._show_selected()
                break

    def copy_selected(self) -> bool:
        finding = self.selected_finding()
        if finding is None:
            return False
        self.clipboard_clear()
        self.clipboard_append(
            json.dumps(
                finding,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            )
        )
        self._status_setter(f"Copied compliance finding {finding.get('id', '')}")
        return True
