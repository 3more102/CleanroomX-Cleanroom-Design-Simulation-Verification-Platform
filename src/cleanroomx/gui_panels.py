from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import tkinter as tk
from tkinter import ttk

from .gui_theme import theme_palette
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
        self.element_type_var = tk.StringVar(value="All")
        self.summary_var = tk.StringVar(value="Project diagnostics not evaluated")
        self.filter_summary_var = tk.StringVar(value="0 visible")
        self._build()

        self.search_var.trace_add("write", lambda *_: self._populate())
        self.severity_var.trace_add("write", lambda *_: self._populate())
        self.category_var.trace_add("write", lambda *_: self._populate())
        self.element_type_var.trace_add("write", lambda *_: self._populate())

    def _build(self) -> None:
        toolbar = ttk.Frame(self, padding=(7, 5), style="CX.Toolbar.TFrame")
        toolbar.pack(fill="x")

        ttk.Label(toolbar, text="PROBLEMS", style="CX.Section.TLabel").pack(
            side="left", padx=(0, 8)
        )
        ttk.Label(toolbar, text="Search").pack(side="left")
        ttk.Entry(toolbar, textvariable=self.search_var, width=28).pack(
            side="left", padx=(4, 8)
        )
        ttk.Label(toolbar, text="Severity").pack(side="left")
        severity = ttk.Combobox(
            toolbar,
            textvariable=self.severity_var,
            values=("All", "Error", "Warning", "Info"),
            state="readonly",
            width=10,
        )
        severity.pack(side="left", padx=(4, 8))
        ttk.Button(
            toolbar,
            text="Refresh",
            command=self.refresh,
            style="CX.Compact.TButton",
        ).pack(side="left", padx=2)
        self.locate_button = ttk.Button(
            toolbar,
            text="Locate",
            command=self._navigate_selected,
            style="CX.Primary.TButton",
        )
        self.locate_button.pack(side="left", padx=2)
        ttk.Button(
            toolbar,
            text="Copy",
            command=self.copy_selected,
            style="CX.Compact.TButton",
        ).pack(side="left", padx=2)
        self.export_button = ttk.Button(
            toolbar,
            text="Export…",
            command=self._export,
            state="normal" if self._export_callback is not None else "disabled",
        )
        self.export_button.pack(side="left", padx=2)

        ttk.Label(
            toolbar,
            textvariable=self.summary_var,
            anchor="e",
        ).pack(side="right", fill="x", expand=True, padx=(12, 0))

        filterbar = ttk.Frame(self, padding=(7, 0, 7, 5), style="CX.Toolbar.TFrame")
        filterbar.pack(fill="x")
        ttk.Label(filterbar, text="Domain").pack(side="left")
        self.category_filter = ttk.Combobox(
            filterbar,
            textvariable=self.category_var,
            values=("All",),
            state="readonly",
            width=18,
        )
        self.category_filter.pack(side="left", padx=(4, 8))
        ttk.Label(filterbar, text="Object").pack(side="left")
        self.element_type_filter = ttk.Combobox(
            filterbar,
            textvariable=self.element_type_var,
            values=("All",),
            state="readonly",
            width=18,
        )
        self.element_type_filter.pack(side="left", padx=(4, 8))
        ttk.Button(
            filterbar,
            text="Clear filters",
            command=self.clear_filters,
            style="CX.Compact.TButton",
        ).pack(side="left", padx=(0, 8))
        ttk.Button(
            filterbar,
            text="Previous",
            command=lambda: self._select_relative(-1),
            style="CX.Compact.TButton",
        ).pack(side="left", padx=2)
        ttk.Button(
            filterbar,
            text="Next",
            command=lambda: self._select_relative(1),
            style="CX.Compact.TButton",
        ).pack(side="left", padx=2)
        ttk.Label(
            filterbar,
            textvariable=self.filter_summary_var,
            anchor="e",
        ).pack(side="right", fill="x", expand=True, padx=(12, 0))

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
            "code": "Code",
            "description": "Description",
            "object": "Object",
            "level": "Level",
            "source": "Source",
        }
        widths = {
            "severity": 90,
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

        self.tree.tag_configure(
            "error",
            foreground="#EF4444",
            font=("TkDefaultFont", 9, "bold"),
        )
        self.tree.tag_configure(
            "warning",
            foreground="#F59E0B",
            font=("TkDefaultFont", 9, "bold"),
        )
        self.tree.tag_configure("info", foreground="#38BDF8")
        self.tree.bind("<<TreeviewSelect>>", self._show_selected_detail)
        self.tree.bind("<Double-1>", self._navigate_selected)
        self.tree.bind("<Return>", self._navigate_selected)

        ttk.Label(
            detail_frame,
            text="DIAGNOSTIC INSPECTOR",
            style="CX.Section.TLabel",
        ).pack(anchor="w", padx=7, pady=(5, 2))
        self.detail_notebook = ttk.Notebook(detail_frame)
        self.detail_notebook.pack(fill="both", expand=True, padx=5, pady=(0, 4))

        summary_tab = ttk.Frame(self.detail_notebook)
        technical_tab = ttk.Frame(self.detail_notebook)
        self.detail_notebook.add(summary_tab, text="Summary")
        self.detail_notebook.add(technical_tab, text="Technical")

        self.summary_detail = tk.Text(
            summary_tab,
            wrap="word",
            height=5,
            state="disabled",
            borderwidth=0,
        )
        summary_scroll = ttk.Scrollbar(
            summary_tab,
            orient="vertical",
            command=self.summary_detail.yview,
        )
        self.summary_detail.configure(yscrollcommand=summary_scroll.set)
        self.summary_detail.pack(
            side="left",
            fill="both",
            expand=True,
            padx=(6, 0),
            pady=4,
        )
        summary_scroll.pack(side="right", fill="y", pady=4)

        self.technical_detail = tk.Text(
            technical_tab,
            wrap="none",
            height=5,
            state="disabled",
            borderwidth=0,
        )
        technical_y = ttk.Scrollbar(
            technical_tab,
            orient="vertical",
            command=self.technical_detail.yview,
        )
        technical_x = ttk.Scrollbar(
            technical_tab,
            orient="horizontal",
            command=self.technical_detail.xview,
        )
        self.technical_detail.configure(
            yscrollcommand=technical_y.set,
            xscrollcommand=technical_x.set,
        )
        self.technical_detail.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=4)
        technical_y.grid(row=0, column=1, sticky="ns", pady=4)
        technical_x.grid(row=1, column=0, sticky="ew", padx=(6, 0))
        technical_tab.rowconfigure(0, weight=1)
        technical_tab.columnconfigure(0, weight=1)

        # Backward-compatible handle for application-level native-widget theming.
        self.detail = self.summary_detail

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
    def _element_type_text(issue: dict[str, Any]) -> str:
        element = issue.get("element")
        if not isinstance(element, dict):
            return "project"
        return str(element.get("type") or "project")

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

    def _filtered_issues(self) -> list[dict[str, Any]]:
        if not isinstance(self.last_result, dict):
            return []
        issues = self.last_result.get("issues")
        if not isinstance(issues, list):
            return []

        severity = self.severity_var.get().strip().casefold()
        category = self.category_var.get().strip().casefold()
        element_type = self.element_type_var.get().strip().casefold()
        query = self.search_var.get().strip().casefold()
        visible: list[dict[str, Any]] = []
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            issue_severity = str(issue.get("severity", "")).casefold()
            if severity and severity != "all" and issue_severity != severity:
                continue
            issue_category = str(issue.get("category", "") or "General").casefold()
            if category and category != "all" and issue_category != category:
                continue
            issue_element_type = self._element_type_text(issue).casefold()
            if (
                element_type
                and element_type != "all"
                and issue_element_type != element_type
            ):
                continue
            if query:
                haystack = " ".join(
                    (
                        str(issue.get("rule", "")),
                        str(issue.get("category", "")),
                        str(issue.get("message", "")),
                        str(issue.get("suggested_action", "")),
                        self._element_text(issue),
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
        return visible

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
        total = 0
        if isinstance(self.last_result, dict):
            issues = self.last_result.get("issues")
            total = len(issues) if isinstance(issues, list) else 0
        self.filter_summary_var.set(
            f"{len(visible_issues)} visible · {total} total"
            if total
            else "0 visible"
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
            self.summary_var.set(f"Diagnostics unavailable: {exc}")
            self._status_setter("Project diagnostics failed")
            self._populate()
            return None

        self.last_result = result
        self._refresh_filter_choices()
        summary = result.get("summary", {})
        self.summary_var.set(
            "{status} · {errors} error(s) · {warnings} warning(s) · {info} info".format(
                status=str(summary.get("status", "unknown")).upper(),
                errors=summary.get("error_count", 0),
                warnings=summary.get("warning_count", 0),
                info=summary.get("info_count", 0),
            )
        )
        self._populate()
        return result

    def _refresh_filter_choices(self) -> None:
        issues = []
        if isinstance(self.last_result, dict):
            candidate = self.last_result.get("issues")
            if isinstance(candidate, list):
                issues = [issue for issue in candidate if isinstance(issue, dict)]

        categories = sorted(
            {
                str(issue.get("category", "") or "General")
                for issue in issues
            },
            key=str.casefold,
        )
        element_types = sorted(
            {self._element_type_text(issue) for issue in issues},
            key=str.casefold,
        )
        category_values = ("All", *categories)
        element_values = ("All", *element_types)
        self.category_filter.configure(values=category_values)
        self.element_type_filter.configure(values=element_values)
        if self.category_var.get() not in category_values:
            self.category_var.set("All")
        if self.element_type_var.get() not in element_values:
            self.element_type_var.set("All")

    def clear_filters(self) -> None:
        self.search_var.set("")
        self.severity_var.set("All")
        self.category_var.set("All")
        self.element_type_var.set("All")

    def selected_issue(self) -> dict[str, Any] | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return self._issues_by_iid.get(selection[0])

    def _select_relative(self, delta: int) -> None:
        items = list(self.tree.get_children())
        if not items:
            self._status_setter("No visible diagnostics")
            return
        selection = self.tree.selection()
        if selection and selection[0] in items:
            index = (items.index(selection[0]) + delta) % len(items)
        else:
            index = 0 if delta >= 0 else len(items) - 1
        iid = items[index]
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        self.tree.see(iid)
        self._show_selected_detail()
        issue = self._issues_by_iid.get(iid)
        if issue is not None:
            self._status_setter(
                f"Diagnostic {index + 1}/{len(items)} · {issue.get('rule', '')}"
            )

    def _show_selected_detail(self, event=None) -> None:
        issue = self.selected_issue()
        for widget in (self.summary_detail, self.technical_detail):
            widget.configure(state="normal")
            widget.delete("1.0", "end")

        if issue is None:
            self.summary_detail.insert(
                "1.0",
                (
                    "No diagnostic selected.\n\n"
                    "Select an engineering issue to inspect its affected object, "
                    "domain, recovery action, and technical details."
                ),
            )
        else:
            severity = str(issue.get("severity", "info")).upper()
            code = str(issue.get("rule", ""))
            domain = str(issue.get("category", "") or "General")
            affected = self._element_text(issue)
            level = self._level_text(issue)
            suggested = str(issue.get("suggested_action", "") or "No recovery action supplied.")
            lines = [
                f"{severity} · {code}",
                "",
                f"Affected object: {affected}",
                f"Engineering domain: {domain}",
            ]
            if level:
                lines.append(f"Level / floor: {level}")
            lines.extend(
                (
                    "",
                    "Engineering explanation:",
                    str(issue.get("message", "")),
                    "",
                    "Suggested recovery:",
                    suggested,
                )
            )
            self.summary_detail.insert("1.0", "\n".join(lines))

            technical_payload = {
                "sequence": issue.get("sequence"),
                "severity": issue.get("severity"),
                "rule": issue.get("rule"),
                "category": issue.get("category"),
                "element": issue.get("element"),
                "details": issue.get("details"),
            }
            self.technical_detail.insert(
                "1.0",
                json.dumps(
                    technical_payload,
                    indent=2,
                    sort_keys=True,
                    ensure_ascii=False,
                    allow_nan=False,
                ),
            )

        for widget in (self.summary_detail, self.technical_detail):
            widget.configure(state="disabled")

    def _navigate_selected(self, event=None):
        issue = self.selected_issue()
        if issue is None:
            return "break"
        self._navigate_callback(issue)
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

    def apply_theme(self, value: str) -> None:
        """Retheme diagnostics without changing canonical issue state."""
        palette = theme_palette(value)
        for widget in (self.summary_detail, self.technical_detail):
            widget.configure(
                background=palette["field"],
                foreground=palette["field_text"],
                insertbackground=palette["text"],
                selectbackground=palette["selection"],
                selectforeground=palette["selection_text"],
            )
        self.tree.tag_configure(
            "error",
            foreground=palette["error"],
            font=("TkDefaultFont", 9, "bold"),
        )
        self.tree.tag_configure(
            "critical",
            foreground=palette["error"],
            font=("TkDefaultFont", 9, "bold"),
        )
        self.tree.tag_configure(
            "warning",
            foreground=palette["warning"],
            font=("TkDefaultFont", 9, "bold"),
        )
        self.tree.tag_configure("info", foreground=palette["running"])

    def _export(self) -> None:
        if self._export_callback is None:
            return
        result = self.last_result or self.refresh()
        if result is not None:
            self._export_callback(result)
