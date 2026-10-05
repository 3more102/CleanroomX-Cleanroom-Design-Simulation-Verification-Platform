from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import tkinter as tk
from tkinter import ttk

from .project_diagnostics import analyze_project_diagnostics


_SEVERITY_ORDER = {
    "error": 0,
    "warning": 1,
    "info": 2,
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
        self._base_summary = "Project diagnostics not evaluated"
        self._sort_column = "severity"
        self._sort_descending = False

        self.search_var = tk.StringVar()
        self.severity_var = tk.StringVar(value="All")
        self.category_var = tk.StringVar(value="All")
        self.summary_var = tk.StringVar(value=self._base_summary)
        self._build()

        self.search_var.trace_add("write", lambda *_: self._populate())
        self.severity_var.trace_add("write", lambda *_: self._populate())
        self.category_var.trace_add("write", lambda *_: self._populate())

    def _build(self) -> None:
        header = ttk.Frame(self, padding=(7, 5, 7, 2))
        header.pack(fill="x")
        ttk.Label(header, text="PROBLEMS", style="CX.Section.TLabel").pack(
            side="left", padx=(0, 8)
        )
        ttk.Label(
            header,
            textvariable=self.summary_var,
            anchor="e",
        ).pack(side="right", fill="x", expand=True)

        toolbar = ttk.Frame(self, padding=(7, 2, 7, 5))
        toolbar.pack(fill="x")

        ttk.Label(toolbar, text="Search").pack(side="left")
        search = ttk.Entry(toolbar, textvariable=self.search_var, width=23)
        search.pack(side="left", padx=(4, 8))
        self.search_entry = search

        ttk.Label(toolbar, text="Severity").pack(side="left")
        severity = ttk.Combobox(
            toolbar,
            textvariable=self.severity_var,
            values=("All", "Error", "Warning", "Info"),
            state="readonly",
            width=9,
        )
        severity.pack(side="left", padx=(4, 8))
        self.severity_filter = severity

        ttk.Label(toolbar, text="Category").pack(side="left")
        category = ttk.Combobox(
            toolbar,
            textvariable=self.category_var,
            values=("All",),
            state="readonly",
            width=14,
        )
        category.pack(side="left", padx=(4, 8))
        self.category_filter = category

        ttk.Button(toolbar, text="Clear", command=self.clear_filters).pack(
            side="left", padx=2
        )
        ttk.Button(toolbar, text="Refresh", command=self.refresh).pack(
            side="left", padx=2
        )

        self.export_button = ttk.Button(
            toolbar,
            text="Export…",
            command=self._export,
            state="normal" if self._export_callback is not None else "disabled",
        )
        self.export_button.pack(side="right", padx=(2, 0))
        ttk.Button(toolbar, text="Copy", command=self.copy_selected).pack(
            side="right", padx=2
        )
        ttk.Button(toolbar, text="Next ▶", command=self.next_issue).pack(
            side="right", padx=2
        )
        ttk.Button(toolbar, text="◀ Prev", command=self.previous_issue).pack(
            side="right", padx=2
        )

        body = ttk.Panedwindow(self, orient="vertical")
        body.pack(fill="both", expand=True)

        table_frame = ttk.Frame(body)
        detail_frame = ttk.Frame(body)
        body.add(table_frame, weight=4)
        body.add(detail_frame, weight=1)

        columns = (
            "sequence",
            "severity",
            "code",
            "description",
            "object",
            "level",
            "category",
        )
        self.tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
            height=7,
        )
        self._heading_labels = {
            "sequence": "#",
            "severity": "Severity",
            "code": "Diagnostic code / rule",
            "description": "Engineering finding",
            "object": "Affected object",
            "level": "Level",
            "category": "Category",
        }
        widths = {
            "sequence": 55,
            "severity": 85,
            "code": 220,
            "description": 480,
            "object": 180,
            "level": 110,
            "category": 130,
        }
        for column in columns:
            self.tree.heading(
                column,
                text=self._heading_labels[column],
                command=lambda selected=column: self._set_sort(selected),
            )
            self.tree.column(
                column,
                width=widths[column],
                minwidth=45 if column == "sequence" else 70,
                stretch=column == "description",
                anchor="e" if column == "sequence" else "w",
            )
        self._update_heading_labels()

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
        self.tree.bind("<Button-3>", self._show_context_menu)

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

        self._context_menu = tk.Menu(self, tearoff=False)
        self._context_menu.add_command(
            label="Open / Focus affected object",
            command=self._navigate_selected,
        )
        self._context_menu.add_separator()
        self._context_menu.add_command(
            label="Previous diagnostic",
            command=self.previous_issue,
        )
        self._context_menu.add_command(
            label="Next diagnostic",
            command=self.next_issue,
        )
        self._context_menu.add_separator()
        self._context_menu.add_command(
            label="Copy diagnostic JSON",
            command=self.copy_selected,
        )
        self._context_menu.add_command(
            label="Copy diagnostic summary",
            command=self.copy_selected_summary,
        )
        self._context_menu.add_separator()
        self._context_menu.add_command(
            label="Clear filters",
            command=self.clear_filters,
        )

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
    def _source_text(issue: dict[str, Any]) -> str:
        details = issue.get("details")
        if not isinstance(details, dict):
            return ""
        for key in ("source", "source_file", "source_path"):
            value = details.get(key)
            if value not in (None, ""):
                return str(value)
        return ""

    def _refresh_category_values(self) -> None:
        categories = {"All"}
        if isinstance(self.last_result, dict):
            issues = self.last_result.get("issues")
            if isinstance(issues, list):
                for issue in issues:
                    if isinstance(issue, dict):
                        value = str(issue.get("category", "")).strip()
                        if value:
                            categories.add(value)
        ordered = ("All", *sorted(categories - {"All"}, key=str.casefold))
        self.category_filter.configure(values=ordered)
        if self.category_var.get() not in ordered:
            self.category_var.set("All")

    def _filtered_issues(self) -> list[dict[str, Any]]:
        if not isinstance(self.last_result, dict):
            return []
        issues = self.last_result.get("issues")
        if not isinstance(issues, list):
            return []

        severity = self.severity_var.get().strip().casefold()
        category = self.category_var.get().strip().casefold()
        query = self.search_var.get().strip().casefold()
        visible: list[dict[str, Any]] = []
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            issue_severity = str(issue.get("severity", "")).casefold()
            issue_category = str(issue.get("category", "")).casefold()
            if severity and severity != "all" and issue_severity != severity:
                continue
            if category and category != "all" and issue_category != category:
                continue
            if query:
                haystack = " ".join(
                    (
                        str(issue.get("sequence", "")),
                        str(issue.get("rule", "")),
                        str(issue.get("category", "")),
                        str(issue.get("message", "")),
                        str(issue.get("suggested_action", "")),
                        self._element_text(issue),
                        self._level_text(issue),
                        self._source_text(issue),
                        json.dumps(
                            issue.get("details", {}),
                            sort_keys=True,
                            ensure_ascii=False,
                            allow_nan=False,
                        ),
                    )
                ).casefold()
                if query not in haystack:
                    continue
            visible.append(issue)
        return self._sorted_issues(visible)

    def _sort_key(self, issue: dict[str, Any]) -> tuple[Any, ...]:
        column = self._sort_column
        sequence = issue.get("sequence")
        if column == "sequence":
            try:
                return (int(sequence),)
            except (TypeError, ValueError):
                return (10**9, str(sequence))
        if column == "severity":
            severity = str(issue.get("severity", "")).casefold()
            return (_SEVERITY_ORDER.get(severity, 99), severity, int(sequence or 0))
        if column == "code":
            value = issue.get("rule", "")
        elif column == "description":
            value = issue.get("message", "")
        elif column == "object":
            value = self._element_text(issue)
        elif column == "level":
            value = self._level_text(issue)
        elif column == "category":
            value = issue.get("category", "")
        else:
            value = ""
        return (str(value).casefold(), int(sequence or 0))

    def _sorted_issues(
        self,
        issues: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return sorted(
            issues,
            key=self._sort_key,
            reverse=self._sort_descending,
        )

    def _set_sort(self, column: str) -> None:
        if column == self._sort_column:
            self._sort_descending = not self._sort_descending
        else:
            self._sort_column = column
            self._sort_descending = False
        self._update_heading_labels()
        self._populate()

    def _update_heading_labels(self) -> None:
        for column, label in self._heading_labels.items():
            suffix = ""
            if column == self._sort_column:
                suffix = " ▼" if self._sort_descending else " ▲"
            self.tree.heading(column, text=label + suffix)

    def clear_filters(self) -> None:
        self.search_var.set("")
        self.severity_var.set("All")
        self.category_var.set("All")
        self._status_setter("Diagnostic filters cleared")

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
                    sequence,
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

        restored = False
        if selected_sequence is not None:
            for iid, issue in self._issues_by_iid.items():
                if issue.get("sequence") == selected_sequence:
                    self.tree.selection_set(iid)
                    self.tree.focus(iid)
                    self.tree.see(iid)
                    restored = True
                    break
        if not restored and visible_issues:
            first = self.tree.get_children()[0]
            self.tree.selection_set(first)
            self.tree.focus(first)

        total = 0
        if isinstance(self.last_result, dict):
            issues = self.last_result.get("issues")
            if isinstance(issues, list):
                total = len(issues)
        self.summary_var.set(
            f"{self._base_summary} · showing {len(visible_issues)}/{total}"
        )
        self._show_selected_detail()

    def refresh(self) -> dict[str, Any] | None:
        try:
            result = analyze_project_diagnostics(
                self._project_getter(),
                base_dir=self._base_dir_getter(),
            )
        except Exception as exc:
            self.last_result = None
            self._base_summary = f"Diagnostics unavailable: {exc}"
            self.summary_var.set(self._base_summary)
            self._status_setter("Project diagnostics failed")
            self._refresh_category_values()
            self._populate()
            return None

        self.last_result = result
        summary = result.get("summary", {})
        self._base_summary = (
            "{status} · {errors} error(s) · {warnings} warning(s) · {info} info"
        ).format(
            status=str(summary.get("status", "unknown")).upper(),
            errors=summary.get("error_count", 0),
            warnings=summary.get("warning_count", 0),
            info=summary.get("info_count", 0),
        )
        self._refresh_category_values()
        self._populate()
        return result

    def selected_issue(self) -> dict[str, Any] | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return self._issues_by_iid.get(selection[0])

    def _detail_lines(self, issue: dict[str, Any]) -> list[str]:
        element = issue.get("element")
        element_type = ""
        element_id = ""
        if isinstance(element, dict):
            element_type = str(element.get("type", ""))
            element_id = str(element.get("id", ""))

        lines = [
            f"{str(issue.get('severity', 'info')).upper()} · {issue.get('rule', '')}",
            f"Category: {issue.get('category', '') or '—'}",
            (
                "Affected: "
                f"{self._element_text(issue)}"
                + (f" · {element_type}" if element_type else "")
                + (f" · id={element_id}" if element_id else "")
            ),
        ]
        level = self._level_text(issue)
        source = self._source_text(issue)
        if level:
            lines.append(f"Level: {level}")
        if source:
            lines.append(f"Source: {source}")

        lines.extend(("", str(issue.get("message", ""))))

        action = str(issue.get("suggested_action", "")).strip()
        if action:
            lines.extend(("", "Suggested action:", action))

        details = issue.get("details")
        if isinstance(details, dict) and details:
            engineering_keys = (
                ("actual", "Actual"),
                ("required", "Required"),
                ("expected", "Expected"),
                ("minimum", "Minimum"),
                ("maximum", "Maximum"),
                ("tolerance", "Tolerance"),
                ("unit", "Unit"),
            )
            engineering_lines = []
            for key, label in engineering_keys:
                if key in details and details[key] not in (None, ""):
                    engineering_lines.append(f"{label}: {details[key]}")
            if engineering_lines:
                lines.extend(("", "Engineering values:", *engineering_lines))
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
        return lines

    def _show_selected_detail(self, event=None) -> None:
        issue = self.selected_issue()
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        if issue is not None:
            self.detail.insert("1.0", "\n".join(self._detail_lines(issue)))
        else:
            self.detail.insert(
                "1.0",
                "No diagnostic selected. Adjust the filters or refresh project diagnostics.",
            )
        self.detail.configure(state="disabled")

    def _navigate_selected(self, event=None):
        issue = self.selected_issue()
        if issue is None:
            self._status_setter("Select a diagnostic to navigate")
            return "break"
        self._navigate_callback(issue)
        return "break"

    def _select_relative(self, offset: int, *, navigate: bool = True) -> bool:
        children = list(self.tree.get_children())
        if not children:
            self._status_setter("No diagnostics match the current filters")
            return False

        selection = self.tree.selection()
        if selection and selection[0] in children:
            index = children.index(selection[0])
            index = (index + offset) % len(children)
        else:
            index = 0 if offset >= 0 else len(children) - 1

        iid = children[index]
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        self.tree.see(iid)
        self._show_selected_detail()
        if navigate:
            issue = self._issues_by_iid.get(iid)
            if issue is not None:
                self._navigate_callback(issue)
        issue = self._issues_by_iid.get(iid)
        if issue is not None:
            self._status_setter(
                "Diagnostic "
                f"{issue.get('sequence', index + 1)} · "
                f"{str(issue.get('severity', '')).upper()} · "
                f"{issue.get('rule', '')}"
            )
        return True

    def next_issue(self) -> bool:
        return self._select_relative(1)

    def previous_issue(self) -> bool:
        return self._select_relative(-1)

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

    def copy_selected_summary(self) -> None:
        issue = self.selected_issue()
        if issue is None:
            self._status_setter("Select a diagnostic to copy")
            return
        lines = [
            f"[{str(issue.get('severity', 'info')).upper()}] {issue.get('rule', '')}",
            str(issue.get("message", "")),
            f"Affected: {self._element_text(issue)}",
        ]
        action = str(issue.get("suggested_action", "")).strip()
        if action:
            lines.append(f"Suggested action: {action}")
        self.clipboard_clear()
        self.clipboard_append("\n".join(lines))
        self._status_setter("Diagnostic summary copied to clipboard")

    def _show_context_menu(self, event: tk.Event):
        iid = self.tree.identify_row(event.y)
        if iid:
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self._show_selected_detail()
        if not self.tree.selection():
            return "break"
        try:
            self._context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._context_menu.grab_release()
        return "break"

    def _export(self) -> None:
        if self._export_callback is None:
            return
        result = self.last_result or self.refresh()
        if result is not None:
            self._export_callback(result)
