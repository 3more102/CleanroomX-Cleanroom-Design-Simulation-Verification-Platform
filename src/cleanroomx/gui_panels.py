from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable

import tkinter as tk
from tkinter import ttk

from .project_diagnostics import analyze_project_diagnostics


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

        self.search_var = tk.StringVar()
        self.severity_var = tk.StringVar(value="All")
        self.category_var = tk.StringVar(value="All")
        self.rule_var = tk.StringVar(value="All")
        self.summary_var = tk.StringVar(value="Project diagnostics not evaluated")
        self._build()

        self.search_var.trace_add("write", lambda *_: self._populate())
        self.severity_var.trace_add("write", lambda *_: self._populate())
        self.category_var.trace_add("write", lambda *_: self._populate())
        self.rule_var.trace_add("write", lambda *_: self._populate())

    def _build(self) -> None:
        toolbar = ttk.Frame(self, padding=(7, 5))
        toolbar.pack(fill="x")

        header = ttk.Frame(toolbar)
        header.pack(fill="x")
        ttk.Label(header, text="PROBLEMS", style="CX.Section.TLabel").pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(
            header,
            text="Previous",
            command=lambda: self._step_selection(-1),
        ).pack(side="left", padx=2)
        ttk.Button(
            header,
            text="Next",
            command=lambda: self._step_selection(1),
        ).pack(side="left", padx=2)
        ttk.Button(header, text="Refresh", command=self.refresh).pack(
            side="left", padx=(8, 2)
        )
        ttk.Button(header, text="Copy", command=self.copy_selected).pack(
            side="left", padx=2
        )
        self.export_button = ttk.Button(
            header,
            text="Export filtered…",
            command=self._export,
            state="normal" if self._export_callback is not None else "disabled",
        )
        self.export_button.pack(side="left", padx=2)

        ttk.Label(
            header,
            textvariable=self.summary_var,
            anchor="e",
        ).pack(side="right", fill="x", expand=True, padx=(12, 0))

        filters = ttk.Frame(toolbar)
        filters.pack(fill="x", pady=(5, 0))
        ttk.Label(filters, text="Search").pack(side="left")
        ttk.Entry(filters, textvariable=self.search_var, width=24).pack(
            side="left", padx=(4, 8)
        )
        ttk.Label(filters, text="Severity").pack(side="left")
        self.severity_picker = ttk.Combobox(
            filters,
            textvariable=self.severity_var,
            values=("All", "Error", "Warning", "Info"),
            state="readonly",
            width=9,
        )
        self.severity_picker.pack(side="left", padx=(4, 8))
        ttk.Label(filters, text="Category").pack(side="left")
        self.category_picker = ttk.Combobox(
            filters,
            textvariable=self.category_var,
            values=("All",),
            state="readonly",
            width=18,
        )
        self.category_picker.pack(side="left", padx=(4, 8))
        ttk.Label(filters, text="Rule").pack(side="left")
        self.rule_picker = ttk.Combobox(
            filters,
            textvariable=self.rule_var,
            values=("All",),
            state="readonly",
            width=28,
        )
        self.rule_picker.pack(side="left", padx=(4, 8))
        ttk.Button(filters, text="Clear filters", command=self.clear_filters).pack(
            side="left", padx=2
        )

        body = ttk.Panedwindow(self, orient="vertical")
        body.pack(fill="both", expand=True)

        table_frame = ttk.Frame(body)
        detail_frame = ttk.Frame(body)
        body.add(table_frame, weight=4)
        body.add(detail_frame, weight=1)

        columns = ("severity", "code", "description", "object", "level", "source")
        self.tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
            height=7,
        )
        headings = {
            "severity": "Severity",
            "code": "Rule / diagnostic code",
            "description": "Engineering finding",
            "object": "Affected object",
            "level": "Level",
            "source": "Category / source",
        }
        widths = {
            "severity": 90,
            "code": 235,
            "description": 520,
            "object": 180,
            "level": 120,
            "source": 160,
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

        self.tree.tag_configure("error", font=("TkDefaultFont", 9, "bold"))
        self.tree.bind("<<TreeviewSelect>>", self._show_selected_detail)
        self.tree.bind("<Double-1>", self._navigate_selected)
        self.tree.bind("<Return>", self._navigate_selected)
        self.tree.bind("<F4>", lambda event: self._step_selection(1))
        self.tree.bind("<Shift-F4>", lambda event: self._step_selection(-1))
        self.tree.bind("<Button-3>", self._show_context_menu)

        self._context_menu = tk.Menu(self, tearoff=False)
        self._context_menu.add_command(
            label="Go to affected object",
            command=self._navigate_selected,
        )
        self._context_menu.add_command(
            label="Copy diagnostic",
            command=self.copy_selected,
        )

        self.detail = tk.Text(
            detail_frame,
            wrap="word",
            height=5,
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
    def _level_text(issue: dict[str, Any]) -> str:
        details = issue.get("details")
        if not isinstance(details, dict):
            return ""
        for key in ("level", "level_name", "floor", "floor_name"):
            value = details.get(key)
            if value not in (None, ""):
                return str(value)
        return ""

    @staticmethod
    def _issues_from_result(result: Any) -> list[dict[str, Any]]:
        if not isinstance(result, dict):
            return []
        issues = result.get("issues")
        if not isinstance(issues, list):
            return []
        return [issue for issue in issues if isinstance(issue, dict)]

    def _refresh_filter_choices(self) -> None:
        issues = self._issues_from_result(self.last_result)
        categories = sorted(
            {
                str(issue.get("category") or "").strip()
                for issue in issues
                if str(issue.get("category") or "").strip()
            },
            key=str.casefold,
        )
        rules = sorted(
            {
                str(issue.get("rule") or "").strip()
                for issue in issues
                if str(issue.get("rule") or "").strip()
            },
            key=str.casefold,
        )
        self.category_picker.configure(values=("All", *categories))
        self.rule_picker.configure(values=("All", *rules))
        if self.category_var.get() not in {"All", *categories}:
            self.category_var.set("All")
        if self.rule_var.get() not in {"All", *rules}:
            self.rule_var.set("All")

    def _issue_matches_filters(self, issue: dict[str, Any]) -> bool:
        severity = self.severity_var.get().strip().casefold()
        category = self.category_var.get().strip().casefold()
        rule = self.rule_var.get().strip().casefold()
        issue_severity = str(issue.get("severity", "")).casefold()
        issue_category = str(issue.get("category", "")).casefold()
        issue_rule = str(issue.get("rule", "")).casefold()
        if severity and severity != "all" and issue_severity != severity:
            return False
        if category and category != "all" and issue_category != category:
            return False
        if rule and rule != "all" and issue_rule != rule:
            return False

        query = self.search_var.get().strip().casefold()
        if not query:
            return True
        haystack = " ".join(
            (
                str(issue.get("rule", "")),
                str(issue.get("category", "")),
                str(issue.get("severity", "")),
                str(issue.get("message", "")),
                str(issue.get("suggested_action", "")),
                self._element_text(issue),
                self._level_text(issue),
                json.dumps(
                    issue.get("details", {}),
                    sort_keys=True,
                    ensure_ascii=False,
                    allow_nan=False,
                ),
            )
        ).casefold()
        return all(token in haystack for token in query.split() if token)

    def _filtered_issues(
        self,
        result: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        source = self.last_result if result is None else result
        return [
            issue
            for issue in self._issues_from_result(source)
            if self._issue_matches_filters(issue)
        ]

    def _update_summary(self, visible_count: int) -> None:
        if not isinstance(self.last_result, dict):
            self.summary_var.set("Project diagnostics not evaluated")
            return
        summary = self.last_result.get("summary", {})
        total = len(self._issues_from_result(self.last_result))
        self.summary_var.set(
            "{status} · {visible}/{total} shown · {errors} error · "
            "{warnings} warning · {info} info".format(
                status=str(summary.get("status", "unknown")).upper(),
                visible=visible_count,
                total=total,
                errors=summary.get("error_count", 0),
                warnings=summary.get("warning_count", 0),
                info=summary.get("info_count", 0),
            )
        )

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

        visible_issues = self._filtered_issues()
        for index, issue in enumerate(visible_issues, start=1):
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
                    issue.get("rule", ""),
                    issue.get("message", ""),
                    self._element_text(issue),
                    self._level_text(issue),
                    issue.get("category", ""),
                ),
                tags=(severity,),
            )
            self._issues_by_iid[iid] = issue

        if selected_sequence is not None:
            for iid, issue in self._issues_by_iid.items():
                if issue.get("sequence") == selected_sequence:
                    self.tree.selection_set(iid)
                    self.tree.focus(iid)
                    self.tree.see(iid)
                    break
        self._update_summary(len(visible_issues))
        self._show_selected_detail()

    def clear_filters(self) -> None:
        self.search_var.set("")
        self.severity_var.set("All")
        self.category_var.set("All")
        self.rule_var.set("All")
        self._populate()

    def refresh(self) -> dict[str, Any] | None:
        try:
            result = analyze_project_diagnostics(
                self._project_getter(),
                base_dir=self._base_dir_getter(),
            )
        except Exception as exc:
            self.last_result = None
            self.summary_var.set(f"Diagnostics unavailable: {exc}")
            self._status_setter("Project diagnostics failed")
            self._populate()
            return None

        self.last_result = result
        self._refresh_filter_choices()
        self._populate()
        return result

    def filtered_result(
        self,
        result: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        source = self.last_result if result is None else result
        if not isinstance(source, dict):
            return None
        filtered = copy.deepcopy(source)
        issues = self._filtered_issues(source)
        filtered["issues"] = copy.deepcopy(issues)
        error_count = sum(issue.get("severity") == "error" for issue in issues)
        warning_count = sum(issue.get("severity") == "warning" for issue in issues)
        info_count = sum(issue.get("severity") == "info" for issue in issues)
        summary = dict(filtered.get("summary", {}))
        summary.update(
            {
                "status": (
                    "error"
                    if error_count
                    else ("warning" if warning_count else "pass")
                ),
                "issue_count": len(issues),
                "error_count": error_count,
                "warning_count": warning_count,
                "info_count": info_count,
            }
        )
        filtered["summary"] = summary
        return filtered

    def selected_issue(self) -> dict[str, Any] | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return self._issues_by_iid.get(selection[0])

    def _show_selected_detail(self, event=None) -> None:
        issue = self.selected_issue()
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        if issue is not None:
            category = str(issue.get("category", "") or "—")
            affected = self._element_text(issue)
            level = self._level_text(issue) or "—"
            lines = [
                f"{str(issue.get('severity', 'info')).upper()} · {issue.get('rule', '')}",
                f"Category: {category} · Object: {affected} · Level: {level}",
                "",
                str(issue.get("message", "")),
                "",
                "Suggested action:",
                str(issue.get("suggested_action", "")),
            ]
            details = issue.get("details")
            if isinstance(details, dict) and details:
                lines.extend(
                    (
                        "",
                        "Canonical details:",
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
        self.detail.configure(state="disabled")

    def _step_selection(self, delta: int):
        children = list(self.tree.get_children())
        if not children:
            self._status_setter("No diagnostics match the active filters")
            return "break"

        selection = self.tree.selection()
        if selection and selection[0] in children:
            index = children.index(selection[0])
            target_index = (index + delta) % len(children)
        else:
            target_index = 0 if delta >= 0 else len(children) - 1

        iid = children[target_index]
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        self.tree.see(iid)
        self._show_selected_detail()
        issue = self._issues_by_iid.get(iid)
        if issue is not None:
            self._navigate_callback(issue)
        return "break"

    def _navigate_selected(self, event=None):
        issue = self.selected_issue()
        if issue is None:
            return "break"
        self._navigate_callback(issue)
        return "break"

    def _show_context_menu(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self._show_selected_detail()
        try:
            self._context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._context_menu.grab_release()
        return "break"

    def copy_selected(self) -> None:
        issue = self.selected_issue()
        if issue is None:
            self._status_setter("Select a diagnostic to copy")
            return
        payload = json.dumps(
            issue,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        self.clipboard_clear()
        self.clipboard_append(payload)
        self._status_setter("Diagnostic copied to clipboard")

    def _export(self) -> None:
        if self._export_callback is None:
            return
        result = self.last_result or self.refresh()
        filtered = self.filtered_result(result)
        if filtered is not None:
            self._export_callback(filtered)
