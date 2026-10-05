from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import tkinter as tk
from tkinter import ttk

from .project_diagnostics import analyze_project_diagnostics
from .gui_theme import theme_palette


def diagnostic_domain(issue: dict[str, Any]) -> str:
    """Return a stable presentation domain without changing diagnostic semantics."""
    category = str(issue.get("category") or "").strip()
    if category:
        return category.replace("_", " ").replace("-", " ").title()
    rule = str(issue.get("rule") or "").strip()
    if rule:
        prefix = rule.split(".", 1)[0].strip()
        if prefix:
            return prefix.replace("_", " ").replace("-", " ").title()
    element = issue.get("element")
    if isinstance(element, dict):
        element_type = str(element.get("type") or "").strip()
        if element_type:
            return element_type.replace("_", " ").replace("-", " ").title()
    return "General"


def filter_project_diagnostics(
    issues: Any,
    *,
    severity: str = "All",
    domain: str = "All",
    query: str = "",
) -> list[dict[str, Any]]:
    """Filter canonical diagnostics for presentation only; never derive new issues."""
    if not isinstance(issues, list):
        return []
    severity_key = str(severity or "All").strip().casefold()
    domain_key = str(domain or "All").strip().casefold()
    query_key = str(query or "").strip().casefold()
    visible: list[dict[str, Any]] = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        issue_severity = str(issue.get("severity") or "").strip().casefold()
        if severity_key not in {"", "all"} and issue_severity != severity_key:
            continue
        issue_domain = diagnostic_domain(issue).casefold()
        if domain_key not in {"", "all"} and issue_domain != domain_key:
            continue
        if query_key:
            haystack = " ".join(
                (
                    str(issue.get("rule", "")),
                    str(issue.get("category", "")),
                    str(issue.get("message", "")),
                    str(issue.get("suggested_action", "")),
                    ProjectDiagnosticsPanel._element_text(issue),
                    json.dumps(
                        issue.get("details", {}),
                        sort_keys=True,
                        ensure_ascii=False,
                        allow_nan=False,
                    ),
                )
            ).casefold()
            if query_key not in haystack:
                continue
        visible.append(issue)
    return visible


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
        self.domain_var = tk.StringVar(value="All")
        self.summary_var = tk.StringVar(value="Project diagnostics not evaluated")
        self.visible_var = tk.StringVar(value="0 shown")
        self._build()
        self.apply_palette(theme_palette("light"))

        self.search_var.trace_add("write", lambda *_: self._populate())
        self.severity_var.trace_add("write", lambda *_: self._populate())
        self.domain_var.trace_add("write", lambda *_: self._populate())

    def _build(self) -> None:
        toolbar = ttk.Frame(self, style="CX.Toolbar.TFrame", padding=(7, 5))
        toolbar.pack(fill="x")

        ttk.Label(toolbar, text="PROBLEMS", style="CX.ToolbarGroup.TLabel").pack(
            side="left", padx=(0, 8)
        )
        ttk.Label(toolbar, text="Search").pack(side="left")
        ttk.Entry(toolbar, textvariable=self.search_var, width=22).pack(
            side="left", padx=(4, 7)
        )
        ttk.Label(toolbar, text="Severity").pack(side="left")
        severity = ttk.Combobox(
            toolbar,
            textvariable=self.severity_var,
            values=("All", "Error", "Warning", "Info"),
            state="readonly",
            width=9,
        )
        severity.pack(side="left", padx=(4, 7))
        ttk.Label(toolbar, text="Domain").pack(side="left")
        self.domain_picker = ttk.Combobox(
            toolbar,
            textvariable=self.domain_var,
            values=("All",),
            state="readonly",
            width=13,
        )
        self.domain_picker.pack(side="left", padx=(4, 7))
        ttk.Button(
            toolbar,
            text="Clear",
            style="CX.Compact.TButton",
            command=self.clear_filters,
        ).pack(side="left", padx=2)
        ttk.Button(
            toolbar,
            text="Refresh",
            style="CX.Compact.TButton",
            command=self.refresh,
        ).pack(side="left", padx=2)
        self.previous_button = ttk.Button(
            toolbar,
            text="◀",
            width=3,
            style="CX.Compact.TButton",
            command=lambda: self.select_relative(-1),
        )
        self.previous_button.pack(side="left", padx=(6, 1))
        self.next_button = ttk.Button(
            toolbar,
            text="▶",
            width=3,
            style="CX.Compact.TButton",
            command=lambda: self.select_relative(1),
        )
        self.next_button.pack(side="left", padx=1)
        self.locate_button = ttk.Button(
            toolbar,
            text="Locate",
            style="CX.Compact.TButton",
            command=self._navigate_selected,
            state="disabled",
        )
        self.locate_button.pack(side="left", padx=(4, 2))
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
            textvariable=self.visible_var,
            style="CX.Section.TLabel",
        ).pack(side="right", padx=(8, 0))

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

        self.tree.tag_configure("error", font=("TkDefaultFont", 9, "bold"))
        self.tree.bind("<<TreeviewSelect>>", self._show_selected_detail)
        self.tree.bind("<Double-1>", self._navigate_selected)
        self.tree.bind("<Return>", self._navigate_selected)
        self.tree.bind("<F8>", lambda _event: self.select_relative(1))
        self.tree.bind("<Shift-F8>", lambda _event: self.select_relative(-1))

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

    def _filtered_issues(self) -> list[dict[str, Any]]:
        issues = self.last_result.get("issues") if isinstance(self.last_result, dict) else []
        return filter_project_diagnostics(
            issues,
            severity=self.severity_var.get(),
            domain=self.domain_var.get(),
            query=self.search_var.get(),
        )

    def _refresh_domain_values(self) -> None:
        issues = self.last_result.get("issues") if isinstance(self.last_result, dict) else []
        domains = sorted(
            {
                diagnostic_domain(issue)
                for issue in issues
                if isinstance(issue, dict)
            },
            key=str.casefold,
        )
        values = ("All", *domains)
        self.domain_picker.configure(values=values)
        if self.domain_var.get() not in values:
            self.domain_var.set("All")

    def clear_filters(self) -> None:
        self.search_var.set("")
        self.severity_var.set("All")
        self.domain_var.set("All")
        self.tree.focus_set()

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
        self.visible_var.set(f"{len(visible_issues)} shown")
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
        has_selection = self.selected_issue() is not None
        self.locate_button.configure(state="normal" if has_selection else "disabled")
        navigation_state = "normal" if visible_issues else "disabled"
        self.previous_button.configure(state=navigation_state)
        self.next_button.configure(state=navigation_state)

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
        self._refresh_domain_values()
        self._populate()
        return result

    def selected_issue(self) -> dict[str, Any] | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return self._issues_by_iid.get(selection[0])

    def _show_selected_detail(self, event=None) -> None:
        issue = self.selected_issue()
        self.locate_button.configure(state="normal" if issue is not None else "disabled")
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

    def select_relative(self, delta: int):
        items = list(self.tree.get_children())
        if not items:
            return "break"
        selection = self.tree.selection()
        current = items.index(selection[0]) if selection and selection[0] in items else -1
        target = (current + int(delta)) % len(items)
        iid = items[target]
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        self.tree.see(iid)
        self._show_selected_detail()
        return "break"

    def _navigate_selected(self, event=None):
        issue = self.selected_issue()
        if issue is None:
            self._status_setter("Select a diagnostic to locate")
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

    def _export(self) -> None:
        if self._export_callback is None:
            return
        result = self.last_result or self.refresh()
        if result is not None:
            self._export_callback(result)


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
