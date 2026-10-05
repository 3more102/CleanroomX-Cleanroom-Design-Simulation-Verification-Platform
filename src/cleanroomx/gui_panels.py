from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import tkinter as tk
from tkinter import ttk

from .gui_theme import status_style_name, theme_palette
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
        self._theme_palette = theme_palette("light")

        self.search_var = tk.StringVar()
        self.severity_var = tk.StringVar(value="All")
        self.summary_var = tk.StringVar(value="NOT CHECKED")
        self.counts_var = tk.StringVar(value="Project diagnostics not evaluated")
        self._build()

        self.search_var.trace_add("write", lambda *_: self._populate())
        self.severity_var.trace_add("write", lambda *_: self._populate())

    def _build(self) -> None:
        toolbar = ttk.Frame(self, padding=(7, 5), style="CX.Toolbar.TFrame")
        toolbar.pack(fill="x")

        ttk.Label(
            toolbar,
            text="PROBLEMS",
            style="CX.ToolbarLabel.TLabel",
        ).pack(side="left", padx=(0, 10))
        ttk.Label(toolbar, text="Search", style="CX.ToolbarLabel.TLabel").pack(side="left")
        ttk.Entry(toolbar, textvariable=self.search_var, width=27).pack(
            side="left", padx=(4, 8)
        )
        ttk.Label(toolbar, text="Severity", style="CX.ToolbarLabel.TLabel").pack(side="left")
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
            style="CX.Compact.TButton",
            command=self.refresh,
        ).pack(side="left", padx=2)
        ttk.Button(
            toolbar,
            text="Clear filters",
            style="CX.Compact.TButton",
            command=self._clear_filters,
        ).pack(side="left", padx=2)
        self.locate_button = ttk.Button(
            toolbar,
            text="Locate",
            style="CX.Primary.TButton",
            command=self._navigate_selected,
            state="disabled",
        )
        self.locate_button.pack(side="left", padx=(8, 2))
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
            style="CX.MutedBadge.TLabel",
            anchor="center",
        )
        self.summary_label.pack(side="right", padx=(8, 0))
        ttk.Label(
            toolbar,
            textvariable=self.counts_var,
            anchor="e",
            style="CX.ToolbarLabel.TLabel",
        ).pack(side="right", fill="x", expand=True, padx=(12, 0))

        body = ttk.Panedwindow(self, orient="vertical")
        body.pack(fill="both", expand=True)

        table_frame = ttk.Frame(body)
        detail_frame = ttk.Frame(body, style="CX.Panel.TFrame")
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
            "code": "Diagnostic",
            "description": "Engineering issue",
            "object": "Affected object",
            "level": "Level / floor",
            "source": "Domain",
        }
        widths = {
            "severity": 82,
            "code": 210,
            "description": 520,
            "object": 180,
            "level": 120,
            "source": 150,
        }
        for column in columns:
            anchor = "center" if column == "severity" else "w"
            self.tree.heading(column, text=headings[column])
            self.tree.column(
                column,
                width=widths[column],
                minwidth=70,
                stretch=column == "description",
                anchor=anchor,
            )

        yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        self.tree.bind("<<TreeviewSelect>>", self._show_selected_detail)
        self.tree.bind("<Double-1>", self._navigate_selected)
        self.tree.bind("<Return>", self._navigate_selected)

        detail_header = ttk.Frame(detail_frame, style="CX.PanelHeader.TFrame")
        detail_header.pack(fill="x")
        ttk.Label(
            detail_header,
            text="DIAGNOSTIC INSPECTOR",
            style="CX.PanelHeader.TLabel",
        ).pack(side="left")
        ttk.Label(
            detail_header,
            text="Double-click a row to locate the affected engineering object",
            style="CX.PanelHeader.TLabel",
        ).pack(side="right")

        self.detail = tk.Text(
            detail_frame,
            wrap="word",
            height=5,
            state="disabled",
            borderwidth=0,
            padx=10,
            pady=8,
        )
        detail_scroll = ttk.Scrollbar(detail_frame, orient="vertical", command=self.detail.yview)
        self.detail.configure(yscrollcommand=detail_scroll.set)
        self.detail.pack(side="left", fill="both", expand=True)
        detail_scroll.pack(side="right", fill="y")

    def apply_theme(self, value: str) -> None:
        palette = theme_palette(value)
        self._theme_palette = palette
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
            foreground=palette["info"],
        )
        self.detail.configure(
            background=palette["field"],
            foreground=palette["field_text"],
            insertbackground=palette["text"],
            selectbackground=palette["selection"],
            selectforeground=palette["selection_text"],
        )

    def _clear_filters(self) -> None:
        self.search_var.set("")
        self.severity_var.set("All")

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
        query = self.search_var.get().strip().casefold()
        visible: list[dict[str, Any]] = []
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            issue_severity = str(issue.get("severity", "")).casefold()
            if severity and severity != "all" and issue_severity != severity:
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
            self.summary_var.set("UNKNOWN")
            self.summary_label.configure(style=status_style_name("UNKNOWN"))
            self.counts_var.set(f"Diagnostics unavailable: {exc}")
            self._status_setter("Project diagnostics failed")
            self._populate()
            return None

        self.last_result = result
        summary = result.get("summary", {})
        status = str(summary.get("status", "unknown")).upper()
        errors = summary.get("error_count", 0)
        warnings = summary.get("warning_count", 0)
        info = summary.get("info_count", 0)
        self.summary_var.set(status)
        style_status = "FAIL" if errors else ("WARNING" if warnings else "PASS")
        self.summary_label.configure(style=status_style_name(style_status))
        self.counts_var.set(
            f"{errors} error(s)  ·  {warnings} warning(s)  ·  {info} info"
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
        self.locate_button.configure(state="normal" if issue is not None else "disabled")
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        if issue is None:
            if isinstance(self.last_result, dict) and not self._filtered_issues():
                message = (
                    "No diagnostics match the current filters.\n\n"
                    "All currently visible checks are clear, or the filters exclude the remaining findings."
                )
            else:
                message = (
                    "Select a diagnostic to inspect the engineering context, suggested recovery, "
                    "and technical evidence."
                )
            self.detail.insert("1.0", message)
        else:
            severity = str(issue.get("severity", "info")).upper()
            code = str(issue.get("rule", ""))
            category = str(issue.get("category", "")).replace("_", " ").title()
            element = self._element_text(issue)
            lines = [
                f"{severity}  ·  {code}",
                str(issue.get("message", "")),
                "",
                f"Affected object: {element}",
            ]
            if category:
                lines.append(f"Engineering domain: {category}")
            level = self._level_text(issue)
            if level:
                lines.append(f"Level / floor: {level}")
            lines.extend(
                (
                    "",
                    "Suggested recovery",
                    str(issue.get("suggested_action", "") or "Review the affected engineering input."),
                )
            )
            details = issue.get("details")
            if isinstance(details, dict) and details:
                lines.extend(
                    (
                        "",
                        "Technical details",
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
