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
        self._theme_name = "dark"

        self.search_var = tk.StringVar()
        self.severity_var = tk.StringVar(value="All")
        self.category_var = tk.StringVar(value="All")
        self._sort_column = "severity"
        self._sort_descending = False
        self.summary_var = tk.StringVar(value="Project diagnostics not evaluated")
        self.error_count_var = tk.StringVar(value="ERROR 0")
        self.warning_count_var = tk.StringVar(value="WARNING 0")
        self.info_count_var = tk.StringVar(value="INFO 0")
        self._build()

        self.search_var.trace_add("write", lambda *_: self._populate())
        self.severity_var.trace_add("write", lambda *_: self._populate())
        self.category_var.trace_add("write", lambda *_: self._populate())

    def _build(self) -> None:
        header = ttk.Frame(self, style="CX.PanelHeader.TFrame")
        header.pack(fill="x")
        ttk.Label(
            header,
            text="ENGINEERING PROBLEMS",
            style="CX.PanelHeader.TLabel",
        ).pack(side="left")
        ttk.Label(
            header,
            textvariable=self.summary_var,
            style="CX.Muted.TLabel",
        ).pack(side="right", padx=(10, 4))

        filterbar = ttk.Frame(self, style="CX.Toolbar.TFrame", padding=(7, 4))
        filterbar.pack(fill="x", pady=(4, 2))
        ttk.Label(filterbar, text="SEARCH", style="CX.Toolbar.TLabel").pack(
            side="left", padx=(0, 5)
        )
        ttk.Entry(filterbar, textvariable=self.search_var, width=28).pack(
            side="left", padx=(0, 8)
        )
        ttk.Label(filterbar, text="SEVERITY", style="CX.Toolbar.TLabel").pack(
            side="left", padx=(2, 5)
        )
        severity = ttk.Combobox(
            filterbar,
            textvariable=self.severity_var,
            values=("All", "Error", "Warning", "Info"),
            state="readonly",
            width=10,
        )
        severity.pack(side="left", padx=(0, 8))
        ttk.Label(filterbar, text="DOMAIN", style="CX.Toolbar.TLabel").pack(
            side="left", padx=(2, 5)
        )
        self.category_picker = ttk.Combobox(
            filterbar,
            textvariable=self.category_var,
            values=("All",),
            state="readonly",
            width=18,
        )
        self.category_picker.pack(side="left", padx=(0, 8))
        ttk.Button(
            filterbar,
            text="Clear filters",
            style="CX.Compact.TButton",
            command=self.clear_filters,
        ).pack(side="left", padx=2)

        toolbar = ttk.Frame(self, style="CX.Toolbar.TFrame", padding=(7, 4))
        toolbar.pack(fill="x", pady=(0, 4))
        ttk.Button(
            toolbar,
            text="Refresh",
            style="CX.Compact.TButton",
            command=self.refresh,
        ).pack(side="left", padx=2)
        ttk.Button(
            toolbar,
            text="Previous",
            style="CX.Compact.TButton",
            command=lambda: self.select_relative(-1),
        ).pack(side="left", padx=2)
        ttk.Button(
            toolbar,
            text="Next",
            style="CX.Compact.TButton",
            command=lambda: self.select_relative(1),
        ).pack(side="left", padx=2)
        self.locate_button = ttk.Button(
            toolbar,
            text="Locate / Inspect",
            style="CX.Primary.TButton",
            command=self.locate_selected,
        )
        self.locate_button.pack(side="left", padx=2)
        ttk.Button(
            toolbar,
            text="Copy",
            style="CX.Compact.TButton",
            command=self.copy_selected,
        ).pack(side="left", padx=2)
        self.export_button = ttk.Button(
            toolbar,
            text="Export…",
            style="CX.Compact.TButton",
            command=self._export,
            state="normal" if self._export_callback is not None else "disabled",
        )
        self.export_button.pack(side="left", padx=2)

        badges = ttk.Frame(self)
        badges.pack(fill="x", padx=6, pady=(0, 4))
        ttk.Label(
            badges,
            textvariable=self.error_count_var,
            style="CX.Status.Fail.TLabel",
        ).pack(side="left", padx=(0, 4))
        ttk.Label(
            badges,
            textvariable=self.warning_count_var,
            style="CX.Status.Warning.TLabel",
        ).pack(side="left", padx=(0, 4))
        ttk.Label(
            badges,
            textvariable=self.info_count_var,
            style="CX.Status.Unknown.TLabel",
        ).pack(side="left")

        body = ttk.Panedwindow(self, orient="vertical")
        body.pack(fill="both", expand=True)

        table_frame = ttk.Frame(body)
        detail_frame = ttk.Frame(body)
        body.add(table_frame, weight=4)
        body.add(detail_frame, weight=2)

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
            "description": "Engineering finding",
            "object": "Affected object",
            "level": "Level",
            "source": "Domain",
        }
        widths = {
            "severity": 86,
            "code": 190,
            "description": 520,
            "object": 180,
            "level": 110,
            "source": 140,
        }
        for column in columns:
            self.tree.heading(
                column,
                text=headings[column],
                command=lambda selected=column: self.set_sort(selected),
            )
            self.tree.column(
                column,
                width=widths[column],
                minwidth=70,
                stretch=column == "description",
                anchor="w",
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

        self.tree.bind("<<TreeviewSelect>>", self._show_selected_detail)
        self.tree.bind("<Double-1>", self._navigate_selected)
        self.tree.bind("<Return>", self._navigate_selected)

        detail_header = ttk.Frame(detail_frame, style="CX.PanelHeader.TFrame")
        detail_header.pack(fill="x", padx=(0, 2), pady=(2, 0))
        ttk.Label(
            detail_header,
            text="DIAGNOSTIC DETAIL",
            style="CX.PanelHeader.TLabel",
        ).pack(side="left")
        ttk.Label(
            detail_header,
            text="Canonical diagnostic payload remains available via Copy / Export",
            style="CX.Muted.TLabel",
        ).pack(side="right", padx=5)

        self.detail = tk.Text(
            detail_frame,
            wrap="word",
            height=5,
            state="disabled",
            borderwidth=0,
            padx=8,
            pady=6,
        )
        detail_scroll = ttk.Scrollbar(
            detail_frame,
            orient="vertical",
            command=self.detail.yview,
        )
        self.detail.configure(yscrollcommand=detail_scroll.set)
        self.detail.pack(side="left", fill="both", expand=True, padx=(2, 0), pady=4)
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
            if severity and severity != "all" and issue_severity != severity:
                continue
            issue_category = str(issue.get("category", "")).strip().casefold()
            if category and category != "all" and issue_category != category:
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

        severity_order = {"error": 0, "warning": 1, "info": 2}
        def sort_key(issue: dict[str, Any]):
            column = self._sort_column
            if column == "severity":
                return severity_order.get(
                    str(issue.get("severity", "")).casefold(),
                    9,
                )
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

        visible.sort(key=sort_key, reverse=self._sort_descending)
        return visible

    def set_sort(self, column: str) -> None:
        if column == self._sort_column:
            self._sort_descending = not self._sort_descending
        else:
            self._sort_column = column
            self._sort_descending = False
        self._populate()

    def clear_filters(self) -> None:
        self.search_var.set("")
        self.severity_var.set("All")
        self.category_var.set("All")

    def select_relative(self, direction: int) -> None:
        rows = list(self.tree.get_children())
        if not rows:
            self._status_setter("No diagnostics match the current filters")
            return
        selection = self.tree.selection()
        if selection and selection[0] in rows:
            index = rows.index(selection[0])
            index = (index + (1 if direction >= 0 else -1)) % len(rows)
        else:
            index = 0 if direction >= 0 else len(rows) - 1
        iid = rows[index]
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        self.tree.see(iid)
        self._show_selected_detail()
        issue = self._issues_by_iid.get(iid)
        if issue is not None:
            self._status_setter(
                f"Diagnostic {index + 1}/{len(rows)} · {issue.get('rule', '')}"
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

        for index, issue in enumerate(self._filtered_issues(), start=1):
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
                tags=(severity, f"row-{index % 2}"),
            )
            self._issues_by_iid[iid] = issue

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
            self.error_count_var.set("ERROR —")
            self.warning_count_var.set("WARNING —")
            self.info_count_var.set("INFO —")
            self._status_setter("Project diagnostics failed")
            self._populate()
            return None

        self.last_result = result
        issues = result.get("issues", [])
        categories = sorted(
            {
                str(issue.get("category", "")).strip()
                for issue in issues
                if isinstance(issue, dict) and str(issue.get("category", "")).strip()
            },
            key=str.casefold,
        ) if isinstance(issues, list) else []
        self.category_picker.configure(values=("All", *categories))
        if self.category_var.get() not in {"All", *categories}:
            self.category_var.set("All")
        summary = result.get("summary", {})
        status = str(summary.get("status", "unknown")).upper()
        errors = int(summary.get("error_count", 0) or 0)
        warnings = int(summary.get("warning_count", 0) or 0)
        info = int(summary.get("info_count", 0) or 0)
        self.summary_var.set(
            f"{status} · {len(result.get('issues', [])) if isinstance(result.get('issues'), list) else 0} finding(s)"
        )
        self.error_count_var.set(f"ERROR {errors}")
        self.warning_count_var.set(f"WARNING {warnings}")
        self.info_count_var.set(f"INFO {info}")
        self._populate()
        return result

    def selected_issue(self) -> dict[str, Any] | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return self._issues_by_iid.get(selection[0])

    @staticmethod
    def _detail_pairs(details: dict[str, Any]) -> list[str]:
        lines: list[str] = []
        for key in sorted(details):
            value = details[key]
            if isinstance(value, (dict, list)):
                rendered = json.dumps(
                    value,
                    sort_keys=True,
                    ensure_ascii=False,
                    allow_nan=False,
                )
            else:
                rendered = str(value)
            lines.append(f"{key.replace('_', ' ').title()}: {rendered}")
        return lines

    def _show_selected_detail(self, event=None) -> None:
        issue = self.selected_issue()
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        if issue is None:
            self.detail.insert(
                "1.0",
                "Select a diagnostic to inspect its engineering context and recovery action.",
            )
        else:
            severity = str(issue.get("severity", "info")).upper()
            code = str(issue.get("rule", ""))
            category = str(issue.get("category", ""))
            element = self._element_text(issue)
            lines = [
                f"{severity}  ·  {code}",
                str(issue.get("message", "")),
                "",
                f"Affected object: {element}",
                f"Engineering domain: {category or 'Unspecified'}",
            ]
            level = self._level_text(issue)
            if level:
                lines.append(f"Level: {level}")
            action = str(issue.get("suggested_action", "")).strip()
            if action:
                lines.extend(("", "Recommended recovery", action))
            details = issue.get("details")
            if isinstance(details, dict) and details:
                lines.extend(("", "Engineering details"))
                lines.extend(self._detail_pairs(details))
            self.detail.insert("1.0", "\n".join(lines))
        self.detail.configure(state="disabled")

    def locate_selected(self) -> None:
        issue = self.selected_issue()
        if issue is None:
            self._status_setter("Select a diagnostic to locate")
            return
        self._navigate_callback(issue)

    def _navigate_selected(self, event=None):
        self.locate_selected()
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
        if result is not None:
            self._export_callback(result)

    def apply_theme(self, value: str) -> None:
        """Retheme Tk-native diagnostic surfaces and semantic tree rows."""
        self._theme_name = value
        palette = theme_palette(value)
        self.detail.configure(
            background=palette["field"],
            foreground=palette["field_text"],
            insertbackground=palette["text"],
            selectbackground=palette["selection"],
            selectforeground=palette["selection_text"],
            highlightbackground=palette["border"],
        )
        self.tree.tag_configure(
            "error",
            foreground=palette["error"],
            font=("TkDefaultFont", 9, "bold"),
        )
        self.tree.tag_configure(
            "warning",
            foreground=palette["warning"],
        )
        self.tree.tag_configure(
            "info",
            foreground=palette["muted"],
        )
