from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import tkinter as tk
from tkinter import ttk

from .gui_table import TreeviewTableBehavior
from .project_diagnostics import analyze_project_diagnostics


_SEVERITY_RANK = {"error": 0, "warning": 1, "info": 2}
_DIAGNOSTIC_STATE_RANK = {
    "stale": 0,
    "unverifiable": 1,
    "unverified": 2,
    "open": 3,
}
_STALE_RULES = {
    "verification_currency.stale",
    "run_history.current_input_not_run",
    "run_history.external_dependency_stale",
}
_UNVERIFIED_RULES = {
    "verification_currency.not_verified",
    "run_history.analysis_not_run",
}
_UNVERIFIABLE_RULES = {
    "verification_currency.dependency_freshness_unverifiable",
}


class ProjectDiagnosticsPanel(ttk.Frame):
    """IDE-style view over the canonical CleanroomX project diagnostics service."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        project_getter: Callable[[], Any],
        base_dir_getter: Callable[[], str | Path | None],
        navigate_callback: Callable[[dict[str, Any]], None],
        export_callback: Callable[[dict[str, Any]], None] | None = None,
        status_setter: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(master)
        self._project_getter = project_getter
        self._base_dir_getter = base_dir_getter
        self._navigate_callback = navigate_callback
        self._export_callback = export_callback
        self._status_setter = status_setter or (lambda _message: None)
        self._issues_by_iid: dict[str, dict[str, Any]] = {}
        self.last_result: dict[str, Any] | None = None
        self._sort_column = "severity"
        self._sort_descending = False

        self.search_var = tk.StringVar()
        self.severity_var = tk.StringVar(value="All")
        self.state_var = tk.StringVar(value="All")
        self.rule_var = tk.StringVar(value="All")
        self.category_var = tk.StringVar(value="All")
        self.object_var = tk.StringVar(value="All")
        self.summary_var = tk.StringVar(value="Project diagnostics not evaluated")
        self.visible_var = tk.StringVar(value="0 visible")
        self._build()

        for variable in (
            self.search_var,
            self.severity_var,
            self.state_var,
            self.rule_var,
            self.category_var,
            self.object_var,
        ):
            variable.trace_add("write", lambda *_: self._populate())

    def _build(self) -> None:
        toolbar = ttk.Frame(self, padding=(7, 5))
        toolbar.pack(fill="x")

        action_row = ttk.Frame(toolbar)
        action_row.pack(fill="x")
        ttk.Label(action_row, text="PROBLEMS", style="CX.Section.TLabel").pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(action_row, text="Refresh", command=self.refresh).pack(
            side="left", padx=2
        )
        ttk.Button(
            action_row,
            text="Previous",
            command=lambda: self.navigate_relative(-1),
        ).pack(side="left", padx=2)
        ttk.Button(
            action_row,
            text="Next",
            command=lambda: self.navigate_relative(1),
        ).pack(side="left", padx=2)
        ttk.Button(action_row, text="Copy", command=self.copy_selected).pack(
            side="left", padx=2
        )
        self.export_button = ttk.Button(
            action_row,
            text="Export…",
            command=self._export,
            state="normal" if self._export_callback is not None else "disabled",
        )
        self.export_button.pack(side="left", padx=2)
        ttk.Label(
            action_row,
            textvariable=self.summary_var,
            anchor="e",
        ).pack(side="right", fill="x", expand=True, padx=(12, 0))

        filter_row = ttk.Frame(toolbar)
        filter_row.pack(fill="x", pady=(5, 0))
        ttk.Label(filter_row, text="Search").pack(side="left")
        self.search_entry = ttk.Entry(
            filter_row,
            textvariable=self.search_var,
            width=28,
        )
        self.search_entry.pack(side="left", padx=(4, 8))
        ttk.Label(filter_row, text="Severity").pack(side="left")
        self.severity_combo = ttk.Combobox(
            filter_row,
            textvariable=self.severity_var,
            values=("All", "Error", "Warning", "Info"),
            state="readonly",
            width=9,
        )
        self.severity_combo.pack(side="left", padx=(4, 8))
        ttk.Label(filter_row, text="State").pack(side="left")
        self.state_combo = ttk.Combobox(
            filter_row,
            textvariable=self.state_var,
            values=("All", "Open", "Stale", "Unverified", "Unverifiable"),
            state="readonly",
            width=11,
        )
        self.state_combo.pack(side="left", padx=(4, 8))
        ttk.Label(filter_row, text="Rule").pack(side="left")
        self.rule_combo = ttk.Combobox(
            filter_row,
            textvariable=self.rule_var,
            values=("All",),
            state="readonly",
            width=20,
        )
        self.rule_combo.pack(side="left", padx=(4, 8))
        ttk.Label(filter_row, text="Category").pack(side="left")
        self.category_combo = ttk.Combobox(
            filter_row,
            textvariable=self.category_var,
            values=("All",),
            state="readonly",
            width=16,
        )
        self.category_combo.pack(side="left", padx=(4, 8))
        ttk.Label(filter_row, text="Object").pack(side="left")
        self.object_combo = ttk.Combobox(
            filter_row,
            textvariable=self.object_var,
            values=("All",),
            state="readonly",
            width=18,
        )
        self.object_combo.pack(side="left", padx=(4, 8))
        ttk.Button(
            filter_row,
            text="Clear filters",
            command=self.clear_filters,
        ).pack(side="left", padx=2)
        ttk.Label(
            filter_row,
            textvariable=self.visible_var,
            anchor="e",
        ).pack(side="right", fill="x", expand=True, padx=(12, 0))

        body = ttk.Panedwindow(self, orient="vertical")
        body.pack(fill="both", expand=True)

        table_frame = ttk.Frame(body)
        detail_frame = ttk.Frame(body)
        body.add(table_frame, weight=4)
        body.add(detail_frame, weight=1)

        columns = ("severity", "state", "code", "description", "object", "level", "source")
        self.tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            selectmode="extended",
            height=7,
        )
        headings = {
            "severity": "Severity",
            "state": "State",
            "code": "Rule / code",
            "description": "Engineering finding",
            "object": "Object",
            "level": "Level",
            "source": "Category",
        }
        widths = {
            "severity": 88,
            "state": 98,
            "code": 220,
            "description": 520,
            "object": 180,
            "level": 120,
            "source": 150,
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(
                column,
                width=widths[column],
                minwidth=70,
                stretch=column == "description",
            )

        yscroll = ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=self.tree.yview,
        )
        xscroll = ttk.Scrollbar(
            table_frame,
            orient="horizontal",
            command=self.tree.xview,
        )
        self.tree.configure(
            yscrollcommand=yscroll.set,
            xscrollcommand=xscroll.set,
        )
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        self.table_behavior = TreeviewTableBehavior(
            self.tree,
            sortable_columns=columns,
            copy_columns=columns,
            bind_copy=False,
            bind_context_menu=False,
            sort_key_overrides={
                "severity": lambda raw: (
                    0,
                    _SEVERITY_RANK.get(str(raw).casefold(), 99),
                ),
                "state": lambda raw: (
                    0,
                    _DIAGNOSTIC_STATE_RANK.get(str(raw).casefold(), 99),
                ),
            },
        )
        self.table_behavior.sort_column = "severity"
        self.table_behavior.sort_descending = False
        self.table_behavior.reapply_sort()

        self.tree.tag_configure("error", font=("TkDefaultFont", 9, "bold"))
        self.tree.bind("<<TreeviewSelect>>", self._show_selected_detail)
        self.tree.bind("<Double-1>", self._navigate_selected)
        self.tree.bind("<Return>", self._navigate_selected)
        self.tree.bind("<F4>", lambda _event: self.navigate_relative(1))
        self.tree.bind("<Shift-F4>", lambda _event: self.navigate_relative(-1))
        self.tree.bind("<Control-c>", lambda _event: self._copy_shortcut())
        self.tree.bind("<Control-C>", lambda _event: self._copy_shortcut())
        self.tree.bind("<Button-3>", self._show_context_menu)

        self.detail = tk.Text(
            detail_frame,
            wrap="word",
            height=4,
            state="disabled",
            borderwidth=0,
        )
        detail_scroll = ttk.Scrollbar(
            detail_frame,
            orient="vertical",
            command=self.detail.yview,
        )
        self.detail.configure(yscrollcommand=detail_scroll.set)
        self.detail.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=4)
        detail_scroll.pack(side="right", fill="y", pady=4)

    @staticmethod
    def _element_text(issue: dict[str, Any]) -> str:
        element = issue.get("element")
        if not isinstance(element, dict):
            return "project"
        return str(
            element.get("name")
            or element.get("id")
            or element.get("type")
            or "project"
        )

    @staticmethod
    def _element_type(issue: dict[str, Any]) -> str:
        element = issue.get("element")
        if not isinstance(element, dict):
            return "project"
        return str(element.get("type") or "project")

    @staticmethod
    def _state_text(issue: dict[str, Any]) -> str:
        """Project only explicit canonical freshness/run-state rules into UI state."""
        rule = str(issue.get("rule") or "").strip().casefold()
        if rule in _STALE_RULES:
            return "stale"
        if rule in _UNVERIFIED_RULES:
            return "unverified"
        if rule in _UNVERIFIABLE_RULES:
            return "unverifiable"
        return "open"

    @staticmethod
    def _level_text(issue: dict[str, Any]) -> str:
        details = issue.get("details")
        if not isinstance(details, dict):
            return ""
        for key in ("level", "level_name", "floor", "floor_name"):
            value = details.get(key)
            if value not in (None, ""):
                return str(value)
        return ""

    def _all_issues(self) -> list[dict[str, Any]]:
        if not isinstance(self.last_result, dict):
            return []
        issues = self.last_result.get("issues")
        if not isinstance(issues, list):
            return []
        return [issue for issue in issues if isinstance(issue, dict)]

    def _refresh_filter_values(self) -> None:
        issues = self._all_issues()
        rules = sorted(
            {
                str(issue.get("rule", "")).strip()
                for issue in issues
                if str(issue.get("rule", "")).strip()
            },
            key=str.casefold,
        )
        categories = sorted(
            {
                str(issue.get("category", "")).strip()
                for issue in issues
                if str(issue.get("category", "")).strip()
            },
            key=str.casefold,
        )
        objects = sorted(
            {self._element_type(issue) for issue in issues},
            key=str.casefold,
        )
        self.rule_combo.configure(values=("All", *rules))
        self.category_combo.configure(values=("All", *categories))
        self.object_combo.configure(values=("All", *objects))
        if self.rule_var.get() not in {"All", *rules}:
            self.rule_var.set("All")
        if self.category_var.get() not in {"All", *categories}:
            self.category_var.set("All")
        if self.object_var.get() not in {"All", *objects}:
            self.object_var.set("All")

    def _filtered_issues(self) -> list[dict[str, Any]]:
        issues = self._all_issues()
        severity = self.severity_var.get().strip().casefold()
        state = self.state_var.get().strip().casefold()
        rule = self.rule_var.get().strip().casefold()
        category = self.category_var.get().strip().casefold()
        object_type = self.object_var.get().strip().casefold()
        query_tokens = [
            token
            for token in self.search_var.get().strip().casefold().split()
            if token
        ]
        visible: list[dict[str, Any]] = []
        for issue in issues:
            issue_severity = str(issue.get("severity", "")).casefold()
            if severity and severity != "all" and issue_severity != severity:
                continue
            issue_state = self._state_text(issue)
            if state and state != "all" and issue_state != state:
                continue
            issue_rule = str(issue.get("rule", "")).casefold()
            if rule and rule != "all" and issue_rule != rule:
                continue
            issue_category = str(issue.get("category", "")).casefold()
            if category and category != "all" and issue_category != category:
                continue
            issue_object_type = self._element_type(issue).casefold()
            if (
                object_type
                and object_type != "all"
                and issue_object_type != object_type
            ):
                continue
            if query_tokens:
                haystack = " ".join(
                    (
                        str(issue.get("rule", "")),
                        str(issue.get("category", "")),
                        str(issue.get("message", "")),
                        str(issue.get("suggested_action", "")),
                        self._state_text(issue),
                        self._element_text(issue),
                        self._element_type(issue),
                        self._level_text(issue),
                        json.dumps(
                            issue.get("details", {}),
                            sort_keys=True,
                            ensure_ascii=False,
                            allow_nan=False,
                        ),
                    )
                ).casefold()
                if not all(token in haystack for token in query_tokens):
                    continue
            visible.append(issue)
        return visible

    def _sort_value(self, issue: dict[str, Any]):
        column = self._sort_column
        if column == "severity":
            return (
                _SEVERITY_RANK.get(str(issue.get("severity", "")).casefold(), 99),
                str(issue.get("rule", "")).casefold(),
            )
        if column == "state":
            state = self._state_text(issue)
            return (_DIAGNOSTIC_STATE_RANK.get(state, 99), state)
        if column == "code":
            return str(issue.get("rule", "")).casefold()
        if column == "description":
            return str(issue.get("message", "")).casefold()
        if column == "object":
            return self._element_text(issue).casefold()
        if column == "level":
            return self._level_text(issue).casefold()
        if column == "source":
            return str(issue.get("category", "")).casefold()
        return str(issue.get("sequence", ""))

    def _sort_by(self, column: str) -> None:
        self.table_behavior.sort_by(column)
        self._sort_column = self.table_behavior.sort_column or "severity"
        self._sort_descending = self.table_behavior.sort_descending

    def clear_filters(self) -> None:
        self.search_var.set("")
        self.severity_var.set("All")
        self.state_var.set("All")
        self.rule_var.set("All")
        self.category_var.set("All")
        self.object_var.set("All")
        self.search_entry.focus_set()

    def _populate(self) -> None:
        selection = self.tree.selection()
        selected_sequence = None
        if selection:
            selected = self._issues_by_iid.get(selection[0])
            if selected is not None:
                selected_sequence = selected.get("sequence")

        for item in self.tree.get_children():
            self.tree.delete(item)
        self._issues_by_iid.clear()

        visible = self._filtered_issues()
        total_count = len(self._all_issues())
        self.visible_var.set(f"{len(visible)} of {total_count} visible")

        for index, issue in enumerate(visible, start=1):
            sequence = issue.get("sequence", index)
            iid = f"issue:{sequence}"
            if self.tree.exists(iid):
                iid = f"{iid}:{index}"
            severity = str(issue.get("severity", "info")).lower()
            self.tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    severity.upper(),
                    self._state_text(issue).upper(),
                    issue.get("rule", ""),
                    issue.get("message", ""),
                    self._element_text(issue),
                    self._level_text(issue),
                    issue.get("category", ""),
                ),
                tags=(severity,),
            )
            self._issues_by_iid[iid] = issue

        self.table_behavior.reapply_sort()

        if selected_sequence is not None:
            for iid, issue in self._issues_by_iid.items():
                if issue.get("sequence") == selected_sequence:
                    self.tree.selection_set(iid)
                    self.tree.focus(iid)
                    self.tree.see(iid)
                    break
        self._show_selected_detail()

    def refresh(self) -> dict[str, Any] | None:
        try:
            result = analyze_project_diagnostics(
                self._project_getter(),
                base_dir=self._base_dir_getter(),
            )
        except Exception as exc:
            self.last_result = None
            self.summary_var.set(f"Diagnostics unavailable: {exc}")
            self.visible_var.set("0 visible")
            self._status_setter("Project diagnostics failed")
            self._populate()
            return None

        self.last_result = result
        summary = result.get("summary", {})
        self.summary_var.set(
            "{status} · {errors} error(s) · {warnings} warning(s) · {info} info".format(
                status=str(summary.get("status", "unknown")).upper(),
                errors=summary.get("error_count", 0),
                warnings=summary.get("warning_count", 0),
                info=summary.get("info_count", 0),
            )
        )
        self._refresh_filter_values()
        self._populate()
        return result

    def selected_issues(self) -> list[dict[str, Any]]:
        return [
            issue
            for iid in self.tree.selection()
            if (issue := self._issues_by_iid.get(iid)) is not None
        ]

    def selected_issue(self) -> dict[str, Any] | None:
        selected = self.selected_issues()
        return selected[0] if selected else None

    def _show_selected_detail(self, event=None) -> None:
        issue = self.selected_issue()
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        if issue is not None:
            selected_count = len(self.selected_issues())
            element = issue.get("element")
            element_type = self._element_type(issue)
            lines = []
            if selected_count > 1:
                lines.extend((f"{selected_count} diagnostics selected", ""))
            lines.extend([
                f"{str(issue.get('severity', 'info')).upper()} · {issue.get('rule', '')}",
                f"State: {self._state_text(issue).upper()}",
                str(issue.get("message", "")),
                "",
                f"Category: {issue.get('category', '')}",
                f"Object: {self._element_text(issue)} ({element_type})",
            ])
            if isinstance(element, dict) and element.get("id") not in (None, ""):
                lines.append(f"Object ID: {element.get('id')}")
            level = self._level_text(issue)
            if level:
                lines.append(f"Level: {level}")
            lines.extend(
                (
                    "",
                    "Suggested action:",
                    str(issue.get("suggested_action", "")),
                )
            )
            details = issue.get("details")
            if isinstance(details, dict) and details:
                lines.extend(
                    (
                        "",
                        "Details:",
                        json.dumps(
                            details,
                            indent=2,
                            sort_keys=True,
                            ensure_ascii=False,
                            allow_nan=False,
                        ),
                    )
                )
            self.detail.insert("1.0", "\n".join(lines))
        else:
            if self._all_issues() and not self._filtered_issues():
                self.detail.insert(
                    "1.0",
                    "No diagnostics match the active filters. Clear or adjust the filters to continue.",
                )
            elif self.last_result is not None:
                self.detail.insert(
                    "1.0",
                    "No project diagnostics are currently reported.",
                )
        self.detail.configure(state="disabled")

    def _navigate_selected(self, event=None):
        issue = self.selected_issue()
        if issue is None:
            return "break"
        self._navigate_callback(issue)
        return "break"

    def select_relative(self, step: int) -> dict[str, Any] | None:
        items = list(self.tree.get_children())
        if not items:
            self._status_setter("No visible diagnostics to navigate")
            return None
        selection = self.tree.selection()
        if selection and selection[0] in items:
            index = items.index(selection[0])
            target = items[(index + step) % len(items)]
        else:
            target = items[0 if step >= 0 else -1]
        self.tree.selection_set(target)
        self.tree.focus(target)
        self.tree.see(target)
        self._show_selected_detail()
        return self._issues_by_iid.get(target)

    def navigate_relative(self, step: int):
        issue = self.select_relative(step)
        if issue is None:
            return "break"
        self._navigate_callback(issue)
        return "break"

    def _show_context_menu(self, event: tk.Event):
        iid = self.tree.identify_row(event.y)
        if iid:
            if iid not in set(self.tree.selection()):
                self.tree.selection_set(iid)
            self.tree.focus(iid)
            self._show_selected_detail()
        elif self.tree.identify_region(event.x, event.y) != "heading":
            return None

        self.table_behavior.prepare_columns_menu()
        menu = tk.Menu(self, tearoff=False)
        if iid:
            menu.add_command(label="Go to object", command=self._navigate_selected)
            menu.add_command(
                label="Copy diagnostic record(s)",
                command=self.copy_selected,
            )
            menu.add_command(
                label="Copy visible row(s)",
                command=self.table_behavior.copy_selected,
            )
            menu.add_command(
                label="Copy visible row(s) with headers",
                command=lambda: self.table_behavior.copy_selected(with_headers=True),
            )
            menu.add_command(
                label="Select all visible",
                command=self.table_behavior.select_all,
            )
            menu.add_separator()
        menu.add_cascade(label="Columns", menu=self.table_behavior.columns_menu)
        menu.add_command(
            label="Reset column layout",
            command=self.table_behavior.reset_column_layout,
        )
        if iid:
            menu.add_separator()
            menu.add_command(
                label="Previous diagnostic",
                command=lambda: self.navigate_relative(-1),
            )
            menu.add_command(
                label="Next diagnostic",
                command=lambda: self.navigate_relative(1),
            )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _copy_shortcut(self):
        self.copy_selected()
        return "break"

    def copy_selected(self) -> None:
        issues = self.selected_issues()
        if not issues:
            self._status_setter("Select a diagnostic to copy")
            return
        payload: Any = issues[0] if len(issues) == 1 else issues
        self.clipboard_clear()
        self.clipboard_append(
            json.dumps(
                payload,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            )
        )
        self._status_setter(
            "Diagnostic copied to clipboard"
            if len(issues) == 1
            else f"{len(issues)} diagnostics copied to clipboard"
        )

    def _export(self) -> None:
        if self._export_callback is None:
            return
        result = self.last_result or self.refresh()
        if result is not None:
            self._export_callback(result)
