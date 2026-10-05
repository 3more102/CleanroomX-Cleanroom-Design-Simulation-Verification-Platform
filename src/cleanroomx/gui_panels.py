from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import tkinter as tk
from tkinter import ttk

from .project_diagnostics import analyze_project_diagnostics
from .gui_theme import status_style_name, theme_palette


def _engineering_detail_pairs(value: Any, *, prefix: str = "") -> list[tuple[str, str]]:
    """Flatten structured diagnostic details into compact engineer-facing fields."""
    if not isinstance(value, dict):
        return []
    pairs: list[tuple[str, str]] = []
    for key in sorted(value):
        item = value[key]
        label = f"{prefix}{str(key).replace('_', ' ').strip().title()}"
        if isinstance(item, dict):
            pairs.append((label, f"{len(item)} field(s)"))
            pairs.extend(_engineering_detail_pairs(item, prefix=f"{label} / "))
        elif isinstance(item, (list, tuple)):
            if all(not isinstance(entry, (dict, list, tuple)) for entry in item):
                values = ", ".join(str(entry) for entry in item)
                pairs.append((label, values if values else "None"))
            else:
                pairs.append((label, f"{len(item)} structured item(s)"))
        elif item not in (None, ""):
            rendered = f"{item:,.4g}" if isinstance(item, float) else str(item)
            pairs.append((label, rendered))
    return pairs


def _diagnostic_target_type(issue: dict[str, Any]) -> str:
    element = issue.get("element")
    if not isinstance(element, dict):
        return "project"
    return str(element.get("type") or "project").strip() or "project"


def diagnostic_filter_options(
    issues: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    field: str,
) -> tuple[str, ...]:
    """Return deterministic GUI filter choices from canonical diagnostic records."""
    values: set[str] = set()
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        if field == "target_type":
            value = _diagnostic_target_type(issue)
        else:
            value = str(issue.get(field) or "").strip()
        if value:
            values.add(value)
    return ("All", *sorted(values, key=str.casefold))


def diagnostic_matches_filters(
    issue: dict[str, Any],
    *,
    severity: str = "All",
    category: str = "All",
    target_type: str = "All",
    query: str = "",
) -> bool:
    """Evaluate diagnostics-panel filters without changing backend diagnostic data."""
    severity_token = str(severity or "").strip().casefold()
    category_token = str(category or "").strip().casefold()
    target_token = str(target_type or "").strip().casefold()
    issue_severity = str(issue.get("severity") or "").strip().casefold()
    issue_category = str(issue.get("category") or "").strip().casefold()
    issue_target = _diagnostic_target_type(issue).casefold()

    if severity_token not in {"", "all"} and issue_severity != severity_token:
        return False
    if category_token not in {"", "all"} and issue_category != category_token:
        return False
    if target_token not in {"", "all"} and issue_target != target_token:
        return False

    query_token = str(query or "").strip().casefold()
    if not query_token:
        return True
    element = issue.get("element")
    if not isinstance(element, dict):
        element = {}
    haystack = " ".join(
        (
            str(issue.get("rule", "")),
            str(issue.get("category", "")),
            str(issue.get("severity", "")),
            str(issue.get("message", "")),
            str(issue.get("suggested_action", "")),
            str(element.get("type", "")),
            str(element.get("id", "")),
            str(element.get("name", "")),
            json.dumps(
                issue.get("details", {}),
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            ),
        )
    ).casefold()
    return all(token in haystack for token in query_token.split())


def _diagnostic_detail_lines(issue: dict[str, Any]) -> list[str]:
    """Render one canonical diagnostic as a compact engineering inspector summary."""
    severity = str(issue.get("severity") or "info").upper()
    rule = str(issue.get("rule") or "UNSPECIFIED")
    category_token = str(issue.get("category") or "General").strip()
    category = (
        category_token.replace("_", " ")
        if "_" in category_token
        else category_token.title()
    )
    element = issue.get("element")
    if isinstance(element, dict):
        target = str(
            element.get("name")
            or element.get("id")
            or element.get("type")
            or "Project"
        )
    else:
        target = "Project"

    lines = [
        f"{severity}  |  {rule}",
        str(issue.get("message") or "No diagnostic description supplied."),
        "",
        f"Affected object: {target}",
        f"Engineering domain: {category}",
    ]
    action = str(issue.get("suggested_action") or "").strip()
    if action:
        lines.extend(("", "RECOMMENDED RECOVERY", action))

    details = _engineering_detail_pairs(issue.get("details"))
    if details:
        lines.extend(("", "ENGINEERING DETAILS"))
        for label, rendered in details[:16]:
            lines.append(f"• {label}: {rendered}")
        if len(details) > 16:
            lines.append(f"• … {len(details) - 16} additional field(s)")
    return lines


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
        self._palette = theme_palette(self._theme_name)

        self.search_var = tk.StringVar()
        self.severity_var = tk.StringVar(value="All")
        self.category_var = tk.StringVar(value="All")
        self.target_type_var = tk.StringVar(value="All")
        self.summary_var = tk.StringVar(value="Project diagnostics not evaluated")
        self.visible_count_var = tk.StringVar(value="SHOWING 0 / 0")
        self.error_count_var = tk.StringVar(value="ERROR 0")
        self.warning_count_var = tk.StringVar(value="WARNING 0")
        self.info_count_var = tk.StringVar(value="INFO 0")
        self._build()

        self.search_var.trace_add("write", lambda *_: self._populate())
        self.severity_var.trace_add("write", lambda *_: self._populate())
        self.category_var.trace_add("write", lambda *_: self._populate())
        self.target_type_var.trace_add("write", lambda *_: self._populate())

    def _build(self) -> None:
        toolbar = ttk.Frame(self, style="CX.Toolbar.TFrame", padding=(7, 5))
        toolbar.pack(fill="x")

        ttk.Label(toolbar, text="PROBLEMS", style="CX.Section.TLabel").pack(
            side="left", padx=(0, 8)
        )
        ttk.Label(toolbar, text="Search").pack(side="left")
        ttk.Entry(toolbar, textvariable=self.search_var, width=22).pack(
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
        self.category_picker = ttk.Combobox(
            toolbar,
            textvariable=self.category_var,
            values=("All",),
            state="readonly",
            width=16,
        )
        self.category_picker.pack(side="left", padx=(4, 8))
        ttk.Label(toolbar, text="Target").pack(side="left")
        self.target_picker = ttk.Combobox(
            toolbar,
            textvariable=self.target_type_var,
            values=("All",),
            state="readonly",
            width=15,
        )
        self.target_picker.pack(side="left", padx=(4, 8))
        ttk.Button(
            toolbar,
            text="Refresh",
            style="CX.Compact.TButton",
            command=self.refresh,
        ).pack(side="left", padx=2)
        self.locate_button = ttk.Button(
            toolbar,
            text="Locate",
            style="CX.Primary.TButton",
            command=self._navigate_selected,
        )
        self.locate_button.pack(side="left", padx=2)
        ttk.Button(
            toolbar,
            text="Previous",
            style="CX.Compact.TButton",
            command=self.select_previous,
        ).pack(side="left", padx=2)
        ttk.Button(
            toolbar,
            text="Next",
            style="CX.Compact.TButton",
            command=self.select_next,
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
            command=self._export,
            state="normal" if self._export_callback is not None else "disabled",
        )
        self.export_button.pack(side="left", padx=2)

        self.summary_label = ttk.Label(
            toolbar,
            textvariable=self.summary_var,
            anchor="e",
            style="CX.Status.Neutral.TLabel",
        )
        self.summary_label.pack(side="right", padx=(12, 0))

        counters = ttk.Frame(
            self,
            style="CX.SubtlePanel.TFrame",
            padding=(7, 4),
        )
        counters.pack(fill="x", padx=7, pady=(0, 5))
        ttk.Label(
            counters,
            textvariable=self.error_count_var,
            style="CX.Status.Fail.TLabel",
        ).pack(side="left", padx=(0, 4))
        ttk.Label(
            counters,
            textvariable=self.warning_count_var,
            style="CX.Status.Warning.TLabel",
        ).pack(side="left", padx=4)
        ttk.Label(
            counters,
            textvariable=self.info_count_var,
            style="CX.Status.Info.TLabel",
        ).pack(side="left", padx=4)
        ttk.Label(
            counters,
            textvariable=self.visible_count_var,
            style="CX.Status.Neutral.TLabel",
        ).pack(side="left", padx=(8, 0))
        ttk.Label(
            counters,
            text="Select a row to inspect · Double-click to locate · Enter locates",
            style="CX.Muted.TLabel",
        ).pack(side="right")

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
            "source": "Domain",
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

        self._configure_tree_tags()
        self.tree.bind("<<TreeviewSelect>>", self._show_selected_detail)
        self.tree.bind("<Double-1>", self._navigate_selected)
        self.tree.bind("<Return>", self._navigate_selected)
        self.tree.bind("<Control-c>", self._copy_selected_event)
        self.tree.bind("<Alt-Up>", lambda _event: self._select_relative(-1, locate=True))
        self.tree.bind("<Alt-Down>", lambda _event: self._select_relative(1, locate=True))

        detail_header = ttk.Frame(
            detail_frame,
            style="CX.PanelHeader.TFrame",
        )
        detail_header.pack(fill="x", padx=6, pady=(4, 0))
        ttk.Label(
            detail_header,
            text="DIAGNOSTIC DETAIL",
            style="CX.PanelHeader.TLabel",
        ).pack(side="left")
        ttk.Label(
            detail_header,
            text="Double-click a row or use Locate to focus its engineering object.",
            style="CX.PanelHeader.TLabel",
        ).pack(side="right")

        detail_body = ttk.Frame(detail_frame)
        detail_body.pack(fill="both", expand=True)
        self.detail = tk.Text(
            detail_body,
            wrap="word",
            height=4,
            state="disabled",
            borderwidth=0,
        )
        detail_scroll = ttk.Scrollbar(
            detail_body,
            orient="vertical",
            command=self.detail.yview,
        )
        self.detail.configure(yscrollcommand=detail_scroll.set)
        self.detail.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=4)
        detail_scroll.pack(side="right", fill="y", pady=4)

    def _configure_tree_tags(self) -> None:
        palette = self._palette
        self.tree.tag_configure(
            "row_even",
            background=palette["tree"],
        )
        self.tree.tag_configure(
            "row_odd",
            background=palette["surface_alt"],
        )
        self.tree.tag_configure(
            "critical",
            foreground=palette["error"],
            font=("TkDefaultFont", 9, "bold"),
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
            foreground=palette["info"],
        )

    def apply_theme(self, value: Any) -> None:
        self._theme_name = str(value or "dark")
        self._palette = theme_palette(self._theme_name)
        self._configure_tree_tags()
        self.detail.configure(
            background=self._palette["field"],
            foreground=self._palette["field_text"],
            insertbackground=self._palette["text"],
            selectbackground=self._palette["selection"],
            selectforeground=self._palette["selection_text"],
        )
        self._update_summary_style()

    def _update_summary_style(self) -> None:
        result = self.last_result if isinstance(self.last_result, dict) else {}
        summary = result.get("summary", {})
        summary = summary if isinstance(summary, dict) else {}
        errors = int(summary.get("error_count", 0) or 0)
        warnings = int(summary.get("warning_count", 0) or 0)
        status = str(summary.get("status") or "").strip().lower()
        effective = "error" if errors else "warning" if warnings else status
        self.summary_label.configure(style=status_style_name(effective))

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
        return [
            issue
            for issue in issues
            if isinstance(issue, dict)
            and diagnostic_matches_filters(
                issue,
                severity=self.severity_var.get(),
                category=self.category_var.get(),
                target_type=self.target_type_var.get(),
                query=self.search_var.get(),
            )
        ]

    def _refresh_filter_choices(self) -> None:
        issues = (
            self.last_result.get("issues", [])
            if isinstance(self.last_result, dict)
            else []
        )
        if not isinstance(issues, list):
            issues = []
        categories = diagnostic_filter_options(issues, "category")
        targets = diagnostic_filter_options(issues, "target_type")
        self.category_picker.configure(values=categories)
        self.target_picker.configure(values=targets)
        if self.category_var.get() not in categories:
            self.category_var.set("All")
        if self.target_type_var.get() not in targets:
            self.target_type_var.set("All")

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
        total_issues = (
            len(self.last_result.get("issues", []))
            if isinstance(self.last_result, dict)
            and isinstance(self.last_result.get("issues"), list)
            else 0
        )
        self.visible_count_var.set(f"SHOWING {len(visible_issues)} / {total_issues}")
        for index, issue in enumerate(visible_issues, start=1):
            sequence = issue.get("sequence", index)
            iid = f"issue:{sequence}"
            if self.tree.exists(iid):
                iid = f"{iid}:{index}"
            severity = str(issue.get("severity", "info")).lower()
            row_tag = "row_even" if index % 2 == 0 else "row_odd"
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
                tags=(row_tag, severity),
            )
            self._issues_by_iid[iid] = issue

        if selected_sequence is not None:
            for iid, issue in self._issues_by_iid.items():
                if issue.get("sequence") == selected_sequence:
                    self.tree.selection_set(iid)
                    self.tree.focus(iid)
                    self.tree.see(iid)
                    break
        if selected_sequence is None and self.tree.get_children():
            first = self.tree.get_children()[0]
            self.tree.selection_set(first)
            self.tree.focus(first)
        self._show_selected_detail()

    def _select_relative(self, delta: int, *, locate: bool = False):
        rows = list(self.tree.get_children())
        if not rows:
            self._status_setter("No diagnostics match the current filters")
            return "break"
        selection = self.tree.selection()
        if selection and selection[0] in rows:
            index = rows.index(selection[0])
            target_index = max(0, min(len(rows) - 1, index + int(delta)))
        else:
            target_index = 0 if delta >= 0 else len(rows) - 1
        iid = rows[target_index]
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        self.tree.see(iid)
        self._show_selected_detail()
        if locate:
            issue = self._issues_by_iid.get(iid)
            if issue is not None:
                self._navigate_callback(issue)
        self._status_setter(
            f"Diagnostic {target_index + 1} of {len(rows)} in current filter"
        )
        return "break"

    def select_previous(self) -> None:
        self._select_relative(-1, locate=True)

    def select_next(self) -> None:
        self._select_relative(1, locate=True)

    def _copy_selected_event(self, _event=None):
        self.copy_selected()
        return "break"

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
            self._refresh_filter_choices()
            self._populate()
            self._update_summary_style()
            return None

        self.last_result = result
        summary = result.get("summary", {})
        self.error_count_var.set(f"ERROR {int(summary.get('error_count', 0) or 0)}")
        self.warning_count_var.set(f"WARNING {int(summary.get('warning_count', 0) or 0)}")
        self.info_count_var.set(f"INFO {int(summary.get('info_count', 0) or 0)}")
        self.summary_var.set(
            "{status} · {errors} error(s) · {warnings} warning(s) · {info} info".format(
                status=str(summary.get("status", "unknown")).upper(),
                errors=summary.get("error_count", 0),
                warnings=summary.get("warning_count", 0),
                info=summary.get("info_count", 0),
            )
        )
        self._refresh_filter_choices()
        self._populate()
        self._update_summary_style()
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
            self.detail.insert("1.0", "\n".join(_diagnostic_detail_lines(issue)))
        else:
            issues = (
                self.last_result.get("issues", [])
                if isinstance(self.last_result, dict)
                else None
            )
            if isinstance(issues, list) and not issues:
                empty = (
                    "No violations detected.\n\n"
                    "All currently enabled project diagnostic rules passed."
                )
            elif isinstance(issues, list):
                empty = (
                    "No diagnostic selected.\n\n"
                    "Select an issue to inspect its engineering context, recovery action, "
                    "and affected object."
                )
            else:
                empty = (
                    "Project diagnostics have not been evaluated yet.\n\n"
                    "Use Refresh or press F8 to evaluate the current project."
                )
            self.detail.insert("1.0", empty)
        self.detail.configure(state="disabled")

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

    def _export(self) -> None:
        if self._export_callback is None:
            return
        result = self.last_result or self.refresh()
        if result is not None:
            self._export_callback(result)
