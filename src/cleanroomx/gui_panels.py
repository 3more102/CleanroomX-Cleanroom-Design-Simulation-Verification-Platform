from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import tkinter as tk
from tkinter import ttk

from .project_diagnostics import analyze_project_diagnostics
from .run_history import run_history_records
from .gui_theme import theme_palette


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
        self.object_type_var = tk.StringVar(value="All")
        self.summary_var = tk.StringVar(value="Project diagnostics not evaluated")
        self.scope_var = tk.StringVar(value="0 visible / 0 total")
        self._sort_column = "severity"
        self._sort_descending = False
        self._build()
        self.apply_palette(theme_palette("light"))

        self.search_var.trace_add("write", lambda *_: self._populate())
        self.severity_var.trace_add("write", lambda *_: self._populate())
        self.category_var.trace_add("write", lambda *_: self._populate())
        self.object_type_var.trace_add("write", lambda *_: self._populate())

    def _build(self) -> None:
        toolbar = ttk.Frame(self, style="CX.Toolbar.TFrame", padding=(7, 5))
        toolbar.pack(fill="x")

        ttk.Label(toolbar, text="PROBLEMS", style="CX.ToolbarGroup.TLabel").pack(
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

        ttk.Label(toolbar, text="Domain").pack(side="left")
        self.category_filter = ttk.Combobox(
            toolbar,
            textvariable=self.category_var,
            values=("All",),
            state="readonly",
            width=15,
        )
        self.category_filter.pack(side="left", padx=(4, 8))

        ttk.Label(toolbar, text="Object").pack(side="left")
        self.object_filter = ttk.Combobox(
            toolbar,
            textvariable=self.object_type_var,
            values=("All",),
            state="readonly",
            width=15,
        )
        self.object_filter.pack(side="left", padx=(4, 8))

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

        self.summary_label = ttk.Label(
            toolbar,
            textvariable=self.summary_var,
            anchor="e",
            style="CX.Status.Unknown.TLabel",
        )
        self.summary_label.pack(side="right", padx=(12, 0))
        ttk.Label(
            toolbar,
            textvariable=self.scope_var,
            style="CX.CardHint.TLabel",
        ).pack(side="right", padx=(12, 0))

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
            self.tree.heading(
                column,
                text=headings[column],
                command=lambda key=column: self._set_sort(key),
            )
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
        self.tree.bind("<F8>", lambda _event: self.select_relative(1))
        self.tree.bind("<Shift-F8>", lambda _event: self.select_relative(-1))
        self.tree.bind("<Control-c>", self._copy_selected_event)
        self.tree.bind("<Button-3>", self._show_context_menu)

        self.context_menu = tk.Menu(self, tearoff=False)
        self.context_menu.add_command(label="Go to diagnostic", command=self._navigate_selected)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Copy diagnostic JSON", command=self.copy_selected)

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

    def apply_palette(self, palette: dict[str, str]) -> None:
        """Apply centralized engineering severity colors to native Tk widgets."""
        self.tree.tag_configure("error", foreground=palette["error"])
        self.tree.tag_configure("warning", foreground=palette["warning"])
        self.tree.tag_configure("info", foreground=palette["info"])
        self.detail.configure(
            background=palette["field"],
            foreground=palette["field_text"],
            insertbackground=palette["text"],
            selectbackground=palette["selection"],
            selectforeground=palette["selection_text"],
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
    def _object_type_text(issue: dict[str, Any]) -> str:
        element = issue.get("element")
        if not isinstance(element, dict):
            return "project"
        return str(element.get("type") or "project")

    def _refresh_filter_values(self) -> None:
        issues = (
            self.last_result.get("issues", [])
            if isinstance(self.last_result, dict)
            else []
        )
        categories = sorted(
            {
                str(issue.get("category") or "uncategorized")
                for issue in issues
                if isinstance(issue, dict)
            },
            key=str.casefold,
        )
        object_types = sorted(
            {
                self._object_type_text(issue)
                for issue in issues
                if isinstance(issue, dict)
            },
            key=str.casefold,
        )
        category_values = ("All", *categories)
        object_values = ("All", *object_types)
        self.category_filter.configure(values=category_values)
        self.object_filter.configure(values=object_values)
        if self.category_var.get() not in category_values:
            self.category_var.set("All")
        if self.object_type_var.get() not in object_values:
            self.object_type_var.set("All")

    def _sort_key(self, issue: dict[str, Any]) -> tuple[Any, ...]:
        sequence = issue.get("sequence", 0)
        column = self._sort_column
        if column == "severity":
            order = {"error": 0, "warning": 1, "info": 2}
            value: Any = order.get(
                str(issue.get("severity", "")).strip().casefold(),
                99,
            )
        elif column == "code":
            value = str(issue.get("rule", "")).casefold()
        elif column == "description":
            value = str(issue.get("message", "")).casefold()
        elif column == "object":
            value = self._element_text(issue).casefold()
        elif column == "level":
            value = self._level_text(issue).casefold()
        else:
            value = str(issue.get("category", "")).casefold()
        return (value, sequence)

    def _set_sort(self, column: str) -> None:
        if column == self._sort_column:
            self._sort_descending = not self._sort_descending
        else:
            self._sort_column = column
            self._sort_descending = False
        self._populate()

    def _filtered_issues(self) -> list[dict[str, Any]]:
        if not isinstance(self.last_result, dict):
            return []
        issues = self.last_result.get("issues")
        if not isinstance(issues, list):
            return []

        severity = self.severity_var.get().strip().casefold()
        category = self.category_var.get().strip().casefold()
        object_type = self.object_type_var.get().strip().casefold()
        query = self.search_var.get().strip().casefold()
        visible: list[dict[str, Any]] = []
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            issue_severity = str(issue.get("severity", "")).casefold()
            if severity and severity != "all" and issue_severity != severity:
                continue
            issue_category = str(issue.get("category", "")).casefold()
            if category and category != "all" and issue_category != category:
                continue
            issue_object_type = self._object_type_text(issue).casefold()
            if (
                object_type
                and object_type != "all"
                and issue_object_type != object_type
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
                        self._object_type_text(issue),
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
        return sorted(
            visible,
            key=self._sort_key,
            reverse=self._sort_descending,
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
        total_count = 0
        if isinstance(self.last_result, dict):
            source_issues = self.last_result.get("issues")
            if isinstance(source_issues, list):
                total_count = len(source_issues)
        self.scope_var.set(f"{len(visible_issues)} visible / {total_count} total")

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
        self._refresh_filter_values()
        summary = result.get("summary", {})
        errors = int(summary.get("error_count", 0) or 0)
        warnings = int(summary.get("warning_count", 0) or 0)
        status = str(summary.get("status", "unknown")).upper()
        self.summary_var.set(
            "{status} · {errors} ERR · {warnings} WARN · {info} INFO".format(
                status=status,
                errors=errors,
                warnings=warnings,
                info=summary.get("info_count", 0),
            )
        )
        self.summary_label.configure(
            style=(
                "CX.Status.Fail.TLabel"
                if errors
                else (
                    "CX.Status.Warning.TLabel"
                    if warnings
                    else (
                        "CX.Status.Pass.TLabel"
                        if status == "PASS"
                        else "CX.Status.Unknown.TLabel"
                    )
                )
            )
        )
        self._populate()
        return result

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
            lines = [
                f"{str(issue.get('severity', 'info')).upper()} · {issue.get('rule', '')}",
                str(issue.get("message", "")),
                "",
                "Suggested action:",
                str(issue.get("suggested_action", "")),
            ]
            details = issue.get("details")
            if isinstance(details, dict) and details:
                lines.extend(("", "Engineering details:"))
                for key, value in sorted(details.items()):
                    label = str(key).replace("_", " ").strip().title()
                    if isinstance(value, (dict, list)):
                        rendered = json.dumps(
                            value,
                            sort_keys=True,
                            ensure_ascii=False,
                            allow_nan=False,
                        )
                    else:
                        rendered = str(value)
                    lines.append(f"  {label}: {rendered}")
            self.detail.insert("1.0", "\n".join(lines))
        self.detail.configure(state="disabled")

    def _navigate_selected(self, event=None):
        issue = self.selected_issue()
        if issue is None:
            return "break"
        self._navigate_callback(issue)
        return "break"

    def select_relative(self, delta: int):
        children = list(self.tree.get_children())
        if not children:
            return "break"
        selection = self.tree.selection()
        if selection and selection[0] in children:
            current = children.index(selection[0])
            target = (current + int(delta)) % len(children)
        else:
            target = 0 if int(delta) >= 0 else len(children) - 1
        iid = children[target]
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        self.tree.see(iid)
        self._show_selected_detail()
        return "break"

    def _show_context_menu(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self._show_selected_detail()
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()
        return "break"

    def _copy_selected_event(self, _event=None):
        self.copy_selected()
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

    def _export_payload(self) -> dict[str, Any] | None:
        result = self.last_result or self.refresh()
        if result is None:
            return None
        query = self.search_var.get().strip()
        severity = self.severity_var.get().strip()
        category = self.category_var.get().strip()
        object_type = self.object_type_var.get().strip()
        filters_active = any(
            (
                query,
                severity.casefold() != "all",
                category.casefold() != "all",
                object_type.casefold() != "all",
            )
        )
        if not filters_active:
            return result

        payload = json.loads(
            json.dumps(
                result,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            )
        )
        visible = json.loads(
            json.dumps(
                self._filtered_issues(),
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            )
        )
        errors = sum(
            1
            for issue in visible
            if str(issue.get("severity", "")).casefold() == "error"
        )
        warnings = sum(
            1
            for issue in visible
            if str(issue.get("severity", "")).casefold() == "warning"
        )
        infos = sum(
            1
            for issue in visible
            if str(issue.get("severity", "")).casefold() == "info"
        )
        source_issues = result.get("issues")
        payload["issues"] = visible
        payload["summary"] = {
            **(payload.get("summary") if isinstance(payload.get("summary"), dict) else {}),
            "status": "error" if errors else "warning" if warnings else "pass",
            "issue_count": len(visible),
            "error_count": errors,
            "warning_count": warnings,
            "info_count": infos,
        }
        payload["view_filter"] = {
            "search": query,
            "severity": severity,
            "category": category,
            "object_type": object_type,
            "source_issue_count": len(source_issues) if isinstance(source_issues, list) else 0,
            "visible_issue_count": len(visible),
        }
        return payload

    def _export(self) -> None:
        if self._export_callback is None:
            return
        result = self._export_payload()
        if result is not None:
            self._export_callback(result)


def _flatten_json_scalar_rows(
    value: Any,
    *,
    limit: int = 800,
) -> tuple[list[tuple[str, str]], bool]:
    """Flatten strict-JSON values for view-only run comparison."""
    rows: list[tuple[str, str]] = []
    truncated = False

    def visit(current: Any, path: str) -> None:
        nonlocal truncated
        if len(rows) >= limit:
            truncated = True
            return
        if isinstance(current, dict):
            for key in sorted(current):
                child = f"{path}.{key}" if path != "$" else f"$.{key}"
                visit(current[key], child)
                if truncated:
                    return
            return
        if isinstance(current, list):
            for index, item in enumerate(current):
                visit(item, f"{path}[{index}]")
                if truncated:
                    return
            return
        rows.append(
            (
                path,
                json.dumps(
                    current,
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                ),
            )
        )

    visit(value, "$")
    return rows, truncated


class RunHistoryPanel(ttk.Frame):
    """Integrated validated retained-run browser with exact-value comparison."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        project_getter: Callable[[], Any],
        open_analysis_callback: Callable[[str], None] | None = None,
        status_setter: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(master)
        self._project_getter = project_getter
        self._open_analysis_callback = open_analysis_callback
        self._status_setter = status_setter or (lambda _message: None)
        self._records: list[dict[str, Any]] = []
        self._records_by_iid: dict[str, dict[str, Any]] = {}
        self._analysis_filter_ids: dict[str, str] = {}

        self.search_var = tk.StringVar()
        self.analysis_var = tk.StringVar(value="All")
        self.status_filter_var = tk.StringVar(value="All")
        self.summary_var = tk.StringVar(value="No retained analysis runs")
        self.compare_summary_var = tk.StringVar(
            value="Select exactly two retained runs to compare exact stored result values."
        )

        self._build()
        self.apply_palette(theme_palette("light"))
        self.search_var.trace_add("write", lambda *_: self._populate())
        self.analysis_var.trace_add("write", lambda *_: self._populate())
        self.status_filter_var.trace_add("write", lambda *_: self._populate())

    def _build(self) -> None:
        toolbar = ttk.Frame(self, style="CX.Toolbar.TFrame", padding=(7, 5))
        toolbar.pack(fill="x")
        ttk.Label(
            toolbar,
            text="RUN HISTORY",
            style="CX.ToolbarGroup.TLabel",
        ).pack(side="left", padx=(0, 8))
        ttk.Label(toolbar, text="Search").pack(side="left")
        ttk.Entry(toolbar, textvariable=self.search_var, width=24).pack(
            side="left", padx=(4, 8)
        )
        ttk.Label(toolbar, text="Analysis").pack(side="left")
        self.analysis_filter = ttk.Combobox(
            toolbar,
            textvariable=self.analysis_var,
            values=("All",),
            state="readonly",
            width=24,
        )
        self.analysis_filter.pack(side="left", padx=(4, 8))
        ttk.Label(toolbar, text="Status").pack(side="left")
        self.status_filter = ttk.Combobox(
            toolbar,
            textvariable=self.status_filter_var,
            values=("All",),
            state="readonly",
            width=12,
        )
        self.status_filter.pack(side="left", padx=(4, 8))
        ttk.Button(
            toolbar,
            text="Refresh",
            style="CX.Compact.TButton",
            command=self.refresh,
        ).pack(side="left", padx=2)
        ttk.Button(
            toolbar,
            text="Open Analysis",
            style="CX.Compact.TButton",
            command=self.open_selected_analysis,
        ).pack(side="left", padx=2)
        ttk.Button(
            toolbar,
            text="Copy Record",
            style="CX.Compact.TButton",
            command=self.copy_selected_record,
        ).pack(side="left", padx=2)
        ttk.Label(toolbar, textvariable=self.summary_var).pack(
            side="right", padx=(10, 0)
        )

        panes = ttk.Panedwindow(self, orient="vertical")
        panes.pack(fill="both", expand=True)
        list_host = ttk.Frame(panes)
        detail_host = ttk.Frame(panes)
        panes.add(list_host, weight=2)
        panes.add(detail_host, weight=3)

        columns = (
            "completed",
            "analysis",
            "kind",
            "status",
            "input",
            "result",
        )
        self.tree = ttk.Treeview(
            list_host,
            columns=columns,
            show="tree headings",
            selectmode="extended",
            height=7,
        )
        self.tree.heading("#0", text="#")
        for column, label in (
            ("completed", "Completed UTC"),
            ("analysis", "Analysis"),
            ("kind", "Kind"),
            ("status", "Status"),
            ("input", "Input SHA-256"),
            ("result", "Result SHA-256"),
        ):
            self.tree.heading(column, text=label)
        self.tree.column("#0", width=55, stretch=False)
        self.tree.column("completed", width=180, stretch=False)
        self.tree.column("analysis", width=230)
        self.tree.column("kind", width=160)
        self.tree.column("status", width=100, stretch=False)
        self.tree.column("input", width=145, stretch=False)
        self.tree.column("result", width=145, stretch=False)
        yscroll = ttk.Scrollbar(list_host, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(list_host, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        list_host.rowconfigure(0, weight=1)
        list_host.columnconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", self._render_selection)
        self.tree.bind("<Double-1>", self._open_selected_event)
        self.tree.bind("<Return>", self._open_selected_event)

        detail_tabs = ttk.Notebook(detail_host)
        detail_tabs.pack(fill="both", expand=True)

        comparison_tab = ttk.Frame(detail_tabs)
        record_tab = ttk.Frame(detail_tabs)
        detail_tabs.add(comparison_tab, text="Compare Stored Results")
        detail_tabs.add(record_tab, text="Canonical Record")

        ttk.Label(
            comparison_tab,
            textvariable=self.compare_summary_var,
            style="CX.Section.TLabel",
        ).pack(fill="x", padx=7, pady=(5, 3))
        compare_host = ttk.Frame(comparison_tab)
        compare_host.pack(fill="both", expand=True)
        self.compare_tree = ttk.Treeview(
            compare_host,
            columns=("left", "right"),
            show="tree headings",
            selectmode="browse",
        )
        self.compare_tree.heading("#0", text="JSON result path")
        self.compare_tree.heading("left", text="Run A")
        self.compare_tree.heading("right", text="Run B")
        self.compare_tree.column("#0", width=390, minwidth=220)
        self.compare_tree.column("left", width=260, minwidth=120)
        self.compare_tree.column("right", width=260, minwidth=120)
        compare_y = ttk.Scrollbar(
            compare_host,
            orient="vertical",
            command=self.compare_tree.yview,
        )
        compare_x = ttk.Scrollbar(
            compare_host,
            orient="horizontal",
            command=self.compare_tree.xview,
        )
        self.compare_tree.configure(
            yscrollcommand=compare_y.set,
            xscrollcommand=compare_x.set,
        )
        self.compare_tree.grid(row=0, column=0, sticky="nsew")
        compare_y.grid(row=0, column=1, sticky="ns")
        compare_x.grid(row=1, column=0, sticky="ew")
        compare_host.rowconfigure(0, weight=1)
        compare_host.columnconfigure(0, weight=1)

        self.detail = tk.Text(
            record_tab,
            wrap="none",
            state="disabled",
            borderwidth=0,
        )
        detail_y = ttk.Scrollbar(record_tab, orient="vertical", command=self.detail.yview)
        detail_x = ttk.Scrollbar(record_tab, orient="horizontal", command=self.detail.xview)
        self.detail.configure(yscrollcommand=detail_y.set, xscrollcommand=detail_x.set)
        self.detail.grid(row=0, column=0, sticky="nsew")
        detail_y.grid(row=0, column=1, sticky="ns")
        detail_x.grid(row=1, column=0, sticky="ew")
        record_tab.rowconfigure(0, weight=1)
        record_tab.columnconfigure(0, weight=1)

    def apply_palette(self, palette: dict[str, str]) -> None:
        self.compare_tree.tag_configure("different", foreground=palette["warning"])
        self.detail.configure(
            background=palette["field"],
            foreground=palette["field_text"],
            insertbackground=palette["text"],
            selectbackground=palette["selection"],
            selectforeground=palette["selection_text"],
        )

    def _refresh_filter_values(self) -> None:
        analysis_entries: list[tuple[str, str]] = []
        seen_ids: set[str] = set()
        for record in self._records:
            analysis_id = str(record.get("analysis_id") or "")
            if not analysis_id or analysis_id in seen_ids:
                continue
            seen_ids.add(analysis_id)
            name = str(record.get("analysis_name") or analysis_id)
            analysis_entries.append((f"{name} · {analysis_id}", analysis_id))
        analysis_entries.sort(key=lambda item: item[0].casefold())
        self._analysis_filter_ids = dict(analysis_entries)
        analysis_values = ("All", *(label for label, _id in analysis_entries))
        self.analysis_filter.configure(values=analysis_values)
        if self.analysis_var.get() not in analysis_values:
            self.analysis_var.set("All")

        statuses = sorted(
            {
                str(record.get("status") or "unknown")
                for record in self._records
            },
            key=str.casefold,
        )
        status_values = ("All", *statuses)
        self.status_filter.configure(values=status_values)
        if self.status_filter_var.get() not in status_values:
            self.status_filter_var.set("All")

    def _filtered_records(self) -> list[dict[str, Any]]:
        query = self.search_var.get().strip().casefold()
        analysis_label = self.analysis_var.get()
        analysis_id = self._analysis_filter_ids.get(analysis_label)
        status = self.status_filter_var.get().strip().casefold()
        visible: list[dict[str, Any]] = []
        for record in self._records:
            if analysis_id and str(record.get("analysis_id") or "") != analysis_id:
                continue
            record_status = str(record.get("status") or "").casefold()
            if status and status != "all" and record_status != status:
                continue
            if query:
                haystack = " ".join(
                    (
                        str(record.get("sequence") or ""),
                        str(record.get("completed_at_utc") or ""),
                        str(record.get("analysis_id") or ""),
                        str(record.get("analysis_name") or ""),
                        str(record.get("analysis_kind") or ""),
                        str(record.get("run_title") or ""),
                        str(record.get("status") or ""),
                        str(record.get("input_sha256") or ""),
                        str(record.get("result_sha256") or ""),
                    )
                ).casefold()
                if query not in haystack:
                    continue
            visible.append(record)
        return list(reversed(visible))

    def _populate(self) -> None:
        selected_sequences = {
            self._records_by_iid[iid].get("sequence")
            for iid in self.tree.selection()
            if iid in self._records_by_iid
        }
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._records_by_iid.clear()
        visible = self._filtered_records()
        for index, record in enumerate(visible):
            sequence = record.get("sequence", index + 1)
            iid = f"run:{sequence}"
            if self.tree.exists(iid):
                iid = f"{iid}:{index}"
            self.tree.insert(
                "",
                "end",
                iid=iid,
                text=str(sequence),
                values=(
                    record.get("completed_at_utc", ""),
                    record.get("analysis_name", ""),
                    record.get("analysis_kind", ""),
                    record.get("status", ""),
                    str(record.get("input_sha256") or "")[:16] + "…",
                    str(record.get("result_sha256") or "")[:16] + "…",
                ),
            )
            self._records_by_iid[iid] = record
            if sequence in selected_sequences:
                self.tree.selection_add(iid)
        self.summary_var.set(
            f"{len(visible)} visible / {len(self._records)} validated retained runs"
        )
        self._render_selection()

    def refresh(self) -> list[dict[str, Any]]:
        try:
            self._records = run_history_records(self._project_getter().metadata)
        except Exception as exc:
            self._records = []
            self._records_by_iid.clear()
            self.summary_var.set(f"Run history unavailable: {exc}")
            self._populate()
            return []
        self._refresh_filter_values()
        self._populate()
        return list(self._records)

    def selected_records(self) -> list[dict[str, Any]]:
        return [
            self._records_by_iid[iid]
            for iid in self.tree.selection()
            if iid in self._records_by_iid
        ]

    def _clear_compare(self) -> None:
        for iid in self.compare_tree.get_children():
            self.compare_tree.delete(iid)

    def _render_selection(self, _event=None) -> None:
        selected = self.selected_records()
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        if selected:
            self.detail.insert(
                "1.0",
                json.dumps(
                    selected[0],
                    indent=2,
                    sort_keys=True,
                    ensure_ascii=False,
                    allow_nan=False,
                ),
            )
        self.detail.configure(state="disabled")

        self._clear_compare()
        if len(selected) != 2:
            self.compare_summary_var.set(
                "Select exactly two retained runs to compare exact stored result values."
            )
            return
        left, right = selected
        left_result = left.get("result")
        right_result = right.get("result")
        if not isinstance(left_result, dict) or not isinstance(right_result, dict):
            self.compare_summary_var.set(
                "At least one selected legacy record does not retain reopenable result evidence."
            )
            return

        left_rows, left_truncated = _flatten_json_scalar_rows(left_result)
        right_rows, right_truncated = _flatten_json_scalar_rows(right_result)
        left_map = dict(left_rows)
        right_map = dict(right_rows)
        paths = sorted(set(left_map) | set(right_map))
        different_count = 0
        for index, path in enumerate(paths):
            left_value = left_map.get(path, "— missing —")
            right_value = right_map.get(path, "— missing —")
            different = left_value != right_value
            if different:
                different_count += 1
            self.compare_tree.insert(
                "",
                "end",
                iid=f"compare:{index}",
                text=path,
                values=(left_value, right_value),
                tags=("different",) if different else (),
            )
        suffix = (
            " · display limited to first 800 scalar paths per run"
            if left_truncated or right_truncated
            else ""
        )
        self.compare_summary_var.set(
            "Run #{left} vs #{right} · {paths} paths · {different} exact-value differences{suffix}".format(
                left=left.get("sequence", "?"),
                right=right.get("sequence", "?"),
                paths=len(paths),
                different=different_count,
                suffix=suffix,
            )
        )

    def open_selected_analysis(self) -> None:
        selected = self.selected_records()
        if not selected:
            self._status_setter("Select a retained run first")
            return
        analysis_id = str(selected[0].get("analysis_id") or "")
        if not analysis_id or self._open_analysis_callback is None:
            self._status_setter("Retained run has no navigable current analysis")
            return
        self._open_analysis_callback(analysis_id)

    def _open_selected_event(self, _event=None):
        self.open_selected_analysis()
        return "break"

    def copy_selected_record(self) -> None:
        selected = self.selected_records()
        if not selected:
            self._status_setter("Select a retained run to copy")
            return
        payload = json.dumps(
            selected[0],
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        self.clipboard_clear()
        self.clipboard_append(payload)
        self._status_setter("Retained run record copied to clipboard")


class SimulationSummaryPanel(ttk.Frame):
    """Readable primary surface for one analysis run; raw JSON remains an advanced tab."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, padding=(8, 7))
        header = ttk.Frame(self, style="CX.Toolbar.TFrame", padding=(7, 5))
        header.pack(fill="x")
        ttk.Label(
            header,
            text="SIMULATION / ANALYSIS",
            style="CX.ToolbarGroup.TLabel",
        ).pack(side="left")
        self.status_var = tk.StringVar(value="NOT CHECKED")
        self.status_label = ttk.Label(
            header,
            textvariable=self.status_var,
            style="CX.Status.Unknown.TLabel",
        )
        self.status_label.pack(side="right")

        identity = ttk.Frame(self, style="CX.Card.TFrame", padding=(10, 8))
        identity.pack(fill="x", pady=(7, 6))
        self.title_var = tk.StringVar(value="No analysis run in this session")
        self.kind_var = tk.StringVar(value="Select an analysis and run it to inspect calculated results.")
        ttk.Label(
            identity,
            textvariable=self.title_var,
            style="CX.CardHeader.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            identity,
            textvariable=self.kind_var,
            style="CX.CardHint.TLabel",
        ).pack(anchor="w", pady=(3, 0))

        meta = ttk.Frame(self)
        meta.pack(fill="x", pady=(0, 6))
        self.result_count_var = tk.StringVar(value="Calculated values: —")
        self.diagnostic_count_var = tk.StringVar(value="Diagnostic values: —")
        self.visualization_var = tk.StringVar(value="Visualization: —")
        for variable in (
            self.result_count_var,
            self.diagnostic_count_var,
            self.visualization_var,
        ):
            ttk.Label(meta, textvariable=variable, style="CX.Section.TLabel").pack(
                side="left", padx=(0, 16)
            )

        table_host = ttk.Frame(self)
        table_host.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            table_host,
            columns=("value", "unit"),
            show="tree headings",
            selectmode="browse",
        )
        self.tree.heading("#0", text="Calculated result")
        self.tree.heading("value", text="Value")
        self.tree.heading("unit", text="Unit")
        self.tree.column("#0", width=460, minwidth=220)
        self.tree.column("value", width=220, minwidth=120)
        self.tree.column("unit", width=90, minwidth=70, stretch=False)
        yscroll = ttk.Scrollbar(table_host, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(table_host, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        table_host.rowconfigure(0, weight=1)
        table_host.columnconfigure(0, weight=1)

        self.empty_var = tk.StringVar(
            value="No calculated result is available. Run the selected analysis."
        )
        ttk.Label(
            self,
            textvariable=self.empty_var,
            style="CX.Section.TLabel",
            anchor="w",
        ).pack(fill="x", pady=(5, 0))

    @staticmethod
    def _status_style(status: str) -> str:
        key = str(status or "").strip().casefold()
        if key in {"pass", "passed", "success", "completed", "ok"}:
            return "CX.Status.Pass.TLabel"
        if key in {"fail", "failed", "error"}:
            return "CX.Status.Fail.TLabel"
        if key in {"running", "queued"}:
            return "CX.Status.Running.TLabel"
        if key in {"warning", "warn", "abandoned"}:
            return "CX.Status.Warning.TLabel"
        return "CX.Status.Unknown.TLabel"

    def _set_status(self, status: str) -> None:
        text = str(status or "unknown").strip().upper()
        self.status_var.set(text)
        self.status_label.configure(style=self._status_style(text))

    def _clear_rows(self) -> None:
        for iid in self.tree.get_children():
            self.tree.delete(iid)

    def set_running(self, *, title: str, kind: str) -> None:
        self._set_status("RUNNING")
        self.title_var.set(title or "Running analysis")
        self.kind_var.set(f"{kind or 'analysis'} · solver execution in progress")
        self.result_count_var.set("Calculated values: pending")
        self.diagnostic_count_var.set("Diagnostic values: pending")
        self.visualization_var.set("Visualization: pending")
        self.empty_var.set("Solver running… calculated results will appear here when complete.")
        self._clear_rows()

    def set_failure(self, message: str) -> None:
        self._set_status("FAILED")
        self.empty_var.set(f"Analysis failed: {str(message).strip() or 'unknown error'}")
        self.result_count_var.set("Calculated values: unavailable")
        self.diagnostic_count_var.set("Diagnostic values: unavailable")
        self.visualization_var.set("Visualization: unavailable")
        self._clear_rows()

    def set_run(
        self,
        *,
        title: str,
        kind: str,
        status: str,
        result_rows: list[tuple[str, str, str]],
        diagnostic_row_count: int,
        has_plot: bool,
    ) -> None:
        self._set_status(status)
        self.title_var.set(title or "Analysis result")
        self.kind_var.set(f"{kind or 'analysis'} · calculated result")
        self.result_count_var.set(f"Calculated values: {len(result_rows)}")
        self.diagnostic_count_var.set(
            f"Diagnostic values: {max(0, int(diagnostic_row_count))}"
        )
        self.visualization_var.set(
            "Visualization: plot available" if has_plot else "Visualization: no plot"
        )
        self._clear_rows()
        for index, (path, value, unit) in enumerate(result_rows):
            display_path = str(path).removeprefix("$.")
            self.tree.insert(
                "",
                "end",
                iid=f"result-{index}",
                text=display_path or "$",
                values=(value, unit or "—"),
            )
        self.empty_var.set(
            "Select a row to inspect calculated engineering output."
            if result_rows
            else "The solver completed without scalar calculated values to display."
        )
