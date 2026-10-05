from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable

import tkinter as tk
from tkinter import ttk

from .project_diagnostics import analyze_project_diagnostics


_SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


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
        self._sort_column = "sequence"
        self._sort_reverse = False

        self.search_var = tk.StringVar()
        self.severity_var = tk.StringVar(value="All")
        self.category_var = tk.StringVar(value="All")
        self.element_type_var = tk.StringVar(value="All")
        self.summary_var = tk.StringVar(value="Project diagnostics not evaluated")
        self._build()

        for variable in (
            self.search_var,
            self.severity_var,
            self.category_var,
            self.element_type_var,
        ):
            variable.trace_add("write", lambda *_: self._populate())

    def _build(self) -> None:
        toolbar = ttk.Frame(self, padding=(7, 5))
        toolbar.pack(fill="x")

        ttk.Label(toolbar, text="PROBLEMS", style="CX.Section.TLabel").pack(
            side="left", padx=(0, 8)
        )
        ttk.Label(toolbar, text="Search").pack(side="left")
        search = ttk.Entry(toolbar, textvariable=self.search_var, width=24)
        search.pack(side="left", padx=(4, 8))

        ttk.Label(toolbar, text="Severity").pack(side="left")
        self.severity_picker = ttk.Combobox(
            toolbar,
            textvariable=self.severity_var,
            values=("All", "Error", "Warning", "Info"),
            state="readonly",
            width=9,
        )
        self.severity_picker.pack(side="left", padx=(4, 8))

        ttk.Label(toolbar, text="Category").pack(side="left")
        self.category_picker = ttk.Combobox(
            toolbar,
            textvariable=self.category_var,
            values=("All",),
            state="readonly",
            width=14,
        )
        self.category_picker.pack(side="left", padx=(4, 8))

        ttk.Label(toolbar, text="Object").pack(side="left")
        self.element_type_picker = ttk.Combobox(
            toolbar,
            textvariable=self.element_type_var,
            values=("All",),
            state="readonly",
            width=13,
        )
        self.element_type_picker.pack(side="left", padx=(4, 8))

        ttk.Button(toolbar, text="Refresh", command=self.refresh).pack(
            side="left", padx=2
        )
        ttk.Button(toolbar, text="◀", width=3, command=lambda: self.select_relative(-1)).pack(
            side="left", padx=(6, 1)
        )
        ttk.Button(toolbar, text="▶", width=3, command=lambda: self.select_relative(1)).pack(
            side="left", padx=1
        )
        ttk.Button(toolbar, text="Copy", command=self.copy_selected).pack(
            side="left", padx=(6, 2)
        )
        self.export_button = ttk.Button(
            toolbar,
            text="Export View…",
            command=self._export,
            state="normal" if self._export_callback is not None else "disabled",
        )
        self.export_button.pack(side="left", padx=2)

        ttk.Label(
            toolbar,
            textvariable=self.summary_var,
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
            self.tree.heading(
                column,
                text=headings[column],
                command=lambda selected=column: self.sort_by(selected),
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
        self.tree.bind("<F4>", lambda _event: self.select_relative(1))
        self.tree.bind("<Shift-F4>", lambda _event: self.select_relative(-1))
        self.tree.bind("<Button-3>", self._show_context_menu)

        self.context_menu = tk.Menu(self.tree, tearoff=False)
        self.context_menu.add_command(label="Open / Focus", command=self._navigate_selected)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Copy Diagnostic", command=self.copy_selected)
        self.context_menu.add_command(label="Copy Message", command=self.copy_selected_message)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Previous Diagnostic", command=lambda: self.select_relative(-1))
        self.context_menu.add_command(label="Next Diagnostic", command=lambda: self.select_relative(1))

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
        search.bind("<Escape>", lambda _event: self.search_var.set(""))

    def apply_palette(self, palette: dict[str, str]) -> None:
        """Apply semantic state colors without changing diagnostic meaning."""
        self.detail.configure(
            background=palette["field"],
            foreground=palette["field_text"],
            insertbackground=palette["text"],
            selectbackground=palette["selection"],
            selectforeground=palette["selection_text"],
        )
        for severity, key in (
            ("error", "error"),
            ("warning", "warning"),
            ("info", "info"),
        ):
            self.tree.tag_configure(severity, foreground=palette[key])
        try:
            self.context_menu.configure(
                background=palette["surface"],
                foreground=palette["text"],
                activebackground=palette["selection"],
                activeforeground=palette["selection_text"],
                disabledforeground=palette["disabled"],
            )
        except tk.TclError:
            pass

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
        value = str(element.get("type") or "project").strip()
        return value or "project"

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

    def _filtered_issues(self) -> list[dict[str, Any]]:
        issues = self._all_issues()
        severity = self.severity_var.get().strip().casefold()
        category = self.category_var.get().strip().casefold()
        element_type = self.element_type_var.get().strip().casefold()
        query = self.search_var.get().strip().casefold()
        visible: list[dict[str, Any]] = []

        for issue in issues:
            issue_severity = str(issue.get("severity", "")).casefold()
            issue_category = str(issue.get("category", "")).casefold()
            issue_element_type = self._element_type(issue).casefold()
            if severity and severity != "all" and issue_severity != severity:
                continue
            if category and category != "all" and issue_category != category:
                continue
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
                if query not in haystack:
                    continue
            visible.append(issue)
        return visible

    def _sort_key(self, issue: dict[str, Any]) -> tuple[Any, ...]:
        column = self._sort_column
        if column == "severity":
            value: Any = _SEVERITY_ORDER.get(
                str(issue.get("severity", "")).casefold(),
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
        elif column == "source":
            value = str(issue.get("category", "")).casefold()
        else:
            raw_sequence = issue.get("sequence", 0)
            value = raw_sequence if isinstance(raw_sequence, int) else 0
        return (value, str(issue.get("rule", "")).casefold())

    def sort_by(self, column: str) -> None:
        if column == self._sort_column:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = column
            self._sort_reverse = False
        self._populate()

    def _update_filter_values(self) -> None:
        issues = self._all_issues()
        categories = sorted(
            {
                str(issue.get("category", "")).strip()
                for issue in issues
                if str(issue.get("category", "")).strip()
            },
            key=str.casefold,
        )
        element_types = sorted(
            {self._element_type(issue) for issue in issues},
            key=str.casefold,
        )
        self.category_picker.configure(values=("All", *categories))
        self.element_type_picker.configure(values=("All", *element_types))
        if self.category_var.get() not in {"All", *categories}:
            self.category_var.set("All")
        if self.element_type_var.get() not in {"All", *element_types}:
            self.element_type_var.set("All")

    def _update_summary(self, visible_count: int) -> None:
        if not isinstance(self.last_result, dict):
            self.summary_var.set("Project diagnostics not evaluated")
            return
        summary = self.last_result.get("summary", {})
        if not isinstance(summary, dict):
            summary = {}
        total = len(self._all_issues())
        self.summary_var.set(
            "{status} · {shown}/{total} shown · {errors} error(s) · "
            "{warnings} warning(s) · {info} info".format(
                status=str(summary.get("status", "unknown")).upper(),
                shown=visible_count,
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

        visible = sorted(
            self._filtered_issues(),
            key=self._sort_key,
            reverse=self._sort_reverse,
        )
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
        self._update_summary(len(visible))
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
        self._update_filter_values()
        self._populate()
        return result

    def selected_issue(self) -> dict[str, Any] | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return self._issues_by_iid.get(selection[0])

    def select_relative(self, delta: int) -> str:
        children = list(self.tree.get_children())
        if not children:
            self._status_setter("No diagnostics match the current filters")
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

    def _show_selected_detail(self, event=None) -> None:
        issue = self.selected_issue()
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        if issue is not None:
            lines = [
                f"{str(issue.get('severity', 'info')).upper()} · {issue.get('rule', '')}",
                f"Category: {issue.get('category', '') or '—'}",
                f"Affected: {self._element_text(issue)} ({self._element_type(issue)})",
            ]
            level = self._level_text(issue)
            if level:
                lines.append(f"Level: {level}")
            lines.extend(
                (
                    "",
                    str(issue.get("message", "")),
                    "",
                    "Suggested action:",
                    str(issue.get("suggested_action", "") or "No remediation text supplied by the canonical diagnostic."),
                )
            )
            details = issue.get("details")
            if isinstance(details, dict) and details:
                lines.extend(
                    (
                        "",
                        "Engineering details:",
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
            return "break"
        self._navigate_callback(issue)
        return "break"

    def _show_context_menu(self, event: tk.Event) -> str:
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
            self.tree.focus(row)
            self._show_selected_detail()
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()
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

    def copy_selected_message(self) -> None:
        issue = self.selected_issue()
        if issue is None:
            self._status_setter("Select a diagnostic to copy")
            return
        message = str(issue.get("message", ""))
        self.clipboard_clear()
        self.clipboard_append(message)
        self._status_setter("Diagnostic message copied to clipboard")

    def filtered_result(self) -> dict[str, Any] | None:
        """Return a presentation-only filtered projection over the canonical result."""
        if not isinstance(self.last_result, dict):
            return None
        projection = copy.deepcopy(self.last_result)
        visible = self._filtered_issues()
        projection["issues"] = copy.deepcopy(visible)
        projection["view_filter"] = {
            "search": self.search_var.get(),
            "severity": self.severity_var.get(),
            "category": self.category_var.get(),
            "element_type": self.element_type_var.get(),
            "displayed_issue_count": len(visible),
            "total_issue_count": len(self._all_issues()),
        }
        return projection

    def _export(self) -> None:
        if self._export_callback is None:
            return
        if self.refresh() is None:
            return
        result = self.filtered_result()
        if result is not None:
            self._export_callback(result)
