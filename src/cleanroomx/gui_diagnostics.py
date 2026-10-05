from __future__ import annotations

import json
from typing import Any, Callable

import tkinter as tk
from tkinter import ttk

from .gui_theme import attach_tooltip, status_style_name


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


def diagnostics_workspace_projection(
    result: dict[str, Any] | None,
) -> dict[str, Any]:
    """Normalize the canonical project-diagnostics payload for presentation only."""
    data = result if isinstance(result, dict) else {}
    summary = data.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    raw_issues = data.get("issues")
    raw_issues = raw_issues if isinstance(raw_issues, list) else []
    issues = tuple(item for item in raw_issues if isinstance(item, dict))
    categories = tuple(
        sorted(
            {
                str(item.get("category") or "general")
                for item in issues
            },
            key=str.casefold,
        )
    )
    return {
        "status": str(summary.get("status") or "not checked").strip().lower(),
        "issue_count": int(summary.get("issue_count", len(issues)) or 0),
        "error_count": int(summary.get("error_count", 0) or 0),
        "warning_count": int(summary.get("warning_count", 0) or 0),
        "info_count": int(summary.get("info_count", 0) or 0),
        "issues": issues,
        "categories": categories,
    }


class DiagnosticsWorkspace(ttk.Frame):
    """Central workbench over the canonical project diagnostics snapshot."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_refresh: Callable[[], Any],
        on_navigate: Callable[[dict[str, Any]], Any],
        on_export: Callable[[dict[str, Any] | None], Any],
        status_setter: Callable[[str], Any] | None = None,
    ) -> None:
        super().__init__(master, padding=10)
        self._on_refresh = on_refresh
        self._on_navigate = on_navigate
        self._on_export = on_export
        self._status_setter = status_setter or (lambda _message: None)
        self._result: dict[str, Any] | None = None
        self._issues_by_iid: dict[str, dict[str, Any]] = {}

        self.search_var = tk.StringVar()
        self.severity_var = tk.StringVar(value="All")
        self.category_var = tk.StringVar(value="All")
        self.state_var = tk.StringVar(value="NOT CHECKED")
        self.error_var = tk.StringVar(value="0")
        self.warning_var = tk.StringVar(value="0")
        self.info_var = tk.StringVar(value="0")
        self.visible_var = tk.StringVar(value="0 visible")

        header = ttk.Frame(self, style="CX.PanelHeader.TFrame", padding=(10, 7))
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(
            header,
            text="DIAGNOSTICS / DRC WORKBENCH",
            style="CX.PanelHeader.TLabel",
        ).pack(side="left")
        self.state_label = ttk.Label(
            header,
            textvariable=self.state_var,
            style="CX.Status.Neutral.TLabel",
        )
        self.state_label.pack(side="right")
        attach_tooltip(
            header,
            "This workbench displays the canonical deterministic project diagnostics "
            "payload; it does not implement a separate diagnostics engine.",
        )

        filters = ttk.Frame(self, style="CX.Toolbar.TFrame", padding=(8, 5))
        filters.pack(fill="x", pady=(0, 8))
        ttk.Label(filters, text="Search").pack(side="left")
        ttk.Entry(filters, textvariable=self.search_var, width=28).pack(
            side="left", padx=(4, 8)
        )
        ttk.Label(filters, text="Severity").pack(side="left")
        ttk.Combobox(
            filters,
            textvariable=self.severity_var,
            values=("All", "Error", "Warning", "Info"),
            state="readonly",
            width=10,
        ).pack(side="left", padx=(4, 8))
        ttk.Label(filters, text="Category").pack(side="left")
        self.category_combo = ttk.Combobox(
            filters,
            textvariable=self.category_var,
            values=("All",),
            state="readonly",
            width=18,
        )
        self.category_combo.pack(side="left", padx=(4, 8))
        ttk.Button(
            filters,
            text="Refresh",
            style="CX.Compact.TButton",
            command=self._refresh_requested,
        ).pack(side="left", padx=2)
        ttk.Button(
            filters,
            text="Locate",
            style="CX.Primary.TButton",
            command=self._locate_selected,
        ).pack(side="left", padx=2)
        ttk.Button(
            filters,
            text="Copy",
            style="CX.Compact.TButton",
            command=self._copy_selected,
        ).pack(side="left", padx=2)
        ttk.Button(
            filters,
            text="Export…",
            style="CX.Compact.TButton",
            command=self._export_requested,
        ).pack(side="left", padx=2)

        counters = ttk.Frame(self, style="CX.SubtlePanel.TFrame", padding=(10, 6))
        counters.pack(fill="x", pady=(0, 8))
        self._counter(counters, "ERROR", self.error_var, "CX.Status.Fail.TLabel")
        self._counter(counters, "WARNING", self.warning_var, "CX.Status.Warning.TLabel")
        self._counter(counters, "INFO", self.info_var, "CX.Status.Info.TLabel")
        ttk.Label(
            counters,
            textvariable=self.visible_var,
            style="CX.PanelMuted.TLabel",
        ).pack(side="right")

        body = ttk.Panedwindow(self, orient="vertical")
        body.pack(fill="both", expand=True)
        table_host = ttk.Frame(body, style="CX.Panel.TFrame")
        detail_host = ttk.Frame(body, style="CX.Panel.TFrame", padding=(10, 7))
        body.add(table_host, weight=4)
        body.add(detail_host, weight=2)

        columns = ("severity", "rule", "category", "object", "description")
        self.tree = ttk.Treeview(
            table_host,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        for key, title, width, stretch in (
            ("severity", "Severity", 85, False),
            ("rule", "Diagnostic code", 220, False),
            ("category", "Domain", 130, False),
            ("object", "Object", 180, False),
            ("description", "Engineering explanation", 600, True),
        ):
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, minwidth=70, stretch=stretch)
        yscroll = ttk.Scrollbar(table_host, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(table_host, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        table_host.rowconfigure(0, weight=1)
        table_host.columnconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", self._show_selected)
        self.tree.bind("<Double-1>", self._locate_selected)
        self.tree.bind("<Return>", self._locate_selected)

        self.detail_title_var = tk.StringVar(value="No diagnostic selected")
        ttk.Label(
            detail_host,
            textvariable=self.detail_title_var,
            style="CX.PanelSection.TLabel",
        ).pack(anchor="w", pady=(0, 6))
        self.detail = tk.Text(detail_host, wrap="word", height=7, state="disabled")
        detail_scroll = ttk.Scrollbar(
            detail_host, orient="vertical", command=self.detail.yview
        )
        self.detail.configure(yscrollcommand=detail_scroll.set)
        self.detail.pack(side="left", fill="both", expand=True)
        detail_scroll.pack(side="right", fill="y")

        self.search_var.trace_add("write", lambda *_: self._populate())
        self.severity_var.trace_add("write", lambda *_: self._populate())
        self.category_var.trace_add("write", lambda *_: self._populate())

    @staticmethod
    def _counter(
        master: ttk.Frame,
        title: str,
        variable: tk.StringVar,
        style: str,
    ) -> None:
        ttk.Label(master, text=title, style="CX.PanelMuted.TLabel").pack(
            side="left", padx=(0, 4)
        )
        ttk.Label(master, textvariable=variable, style=style).pack(
            side="left", padx=(0, 14)
        )

    def _refresh_requested(self) -> None:
        self._on_refresh()

    def _export_requested(self) -> None:
        self._on_export(self._result)

    def selected_issue(self) -> dict[str, Any] | None:
        selection = self.tree.selection()
        return self._issues_by_iid.get(selection[0]) if selection else None

    def _locate_selected(self, _event=None):
        issue = self.selected_issue()
        if issue is not None:
            self._on_navigate(issue)
        return "break"

    def _copy_selected(self) -> None:
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

    def _filtered_issues(self) -> list[dict[str, Any]]:
        state = diagnostics_workspace_projection(self._result)
        severity = self.severity_var.get().strip().casefold()
        category = self.category_var.get().strip().casefold()
        query = self.search_var.get().strip().casefold()
        visible: list[dict[str, Any]] = []
        for issue in state["issues"]:
            issue_severity = str(issue.get("severity") or "info").casefold()
            issue_category = str(issue.get("category") or "general").casefold()
            if severity != "all" and issue_severity != severity:
                continue
            if category != "all" and issue_category != category:
                continue
            if query:
                haystack = " ".join(
                    (
                        str(issue.get("rule") or ""),
                        str(issue.get("category") or ""),
                        str(issue.get("message") or ""),
                        str(issue.get("suggested_action") or ""),
                        _element_text(issue),
                        json.dumps(
                            issue.get("details") or {},
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
        selected = self.selected_issue()
        selected_sequence = selected.get("sequence") if selected else None
        self._issues_by_iid.clear()
        for iid in self.tree.get_children():
            self.tree.delete(iid)

        visible = self._filtered_issues()
        for index, issue in enumerate(visible, start=1):
            iid = f"diagnostic-{index}"
            severity = str(issue.get("severity") or "info").lower()
            self.tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    severity.upper(),
                    str(issue.get("rule") or ""),
                    str(issue.get("category") or ""),
                    _element_text(issue),
                    str(issue.get("message") or ""),
                ),
            )
            self._issues_by_iid[iid] = issue
        self.visible_var.set(f"{len(visible)} visible")

        if selected_sequence is not None:
            for iid, issue in self._issues_by_iid.items():
                if issue.get("sequence") == selected_sequence:
                    self.tree.selection_set(iid)
                    self.tree.focus(iid)
                    break
        self._show_selected()

    def _show_selected(self, _event=None) -> None:
        issue = self.selected_issue()
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        if issue is None:
            state = diagnostics_workspace_projection(self._result)
            if self._result is None:
                message = "Diagnostics have not been evaluated yet."
            elif not state["issues"]:
                message = "No current diagnostic issues are reported."
            else:
                message = "Select a diagnostic to inspect its context and recovery guidance."
            self.detail_title_var.set("No diagnostic selected")
            self.detail.insert("1.0", message)
        else:
            severity = str(issue.get("severity") or "info").upper()
            rule = str(issue.get("rule") or "UNSPECIFIED")
            self.detail_title_var.set(f"{severity} · {rule}")
            lines = [
                str(issue.get("message") or "No diagnostic description supplied."),
                "",
                f"Affected object: {_element_text(issue)}",
                f"Engineering domain: {issue.get('category') or 'general'}",
            ]
            action = str(issue.get("suggested_action") or "").strip()
            if action:
                lines.extend(("", "SUGGESTED RECOVERY", action))
            details = issue.get("details")
            if isinstance(details, dict) and details:
                lines.extend(
                    (
                        "",
                        "TECHNICAL DETAILS",
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

    def apply_theme(self, palette: dict[str, str]) -> None:
        if not isinstance(palette, dict):
            return
        self.detail.configure(
            background=palette.get("field", "#101820"),
            foreground=palette.get("field_text", palette.get("text", "#ffffff")),
            insertbackground=palette.get("text", "#ffffff"),
            selectbackground=palette.get("selection", "#2b6cb0"),
            selectforeground=palette.get("selection_text", "#ffffff"),
        )

    def refresh(self, result: dict[str, Any] | None) -> None:
        self._result = result if isinstance(result, dict) else None
        state = diagnostics_workspace_projection(self._result)
        self.state_var.set(state["status"].upper().replace("_", " "))
        effective = (
            "error"
            if state["error_count"]
            else "warning"
            if state["warning_count"]
            else state["status"]
        )
        self.state_label.configure(style=status_style_name(effective))
        self.error_var.set(str(state["error_count"]))
        self.warning_var.set(str(state["warning_count"]))
        self.info_var.set(str(state["info_count"]))

        categories = ("All",) + tuple(state["categories"])
        self.category_combo.configure(values=categories)
        if self.category_var.get() not in categories:
            self.category_var.set("All")
        self._populate()
