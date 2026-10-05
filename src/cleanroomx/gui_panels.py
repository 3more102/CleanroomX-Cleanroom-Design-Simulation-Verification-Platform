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
        self._sort_column: str | None = None
        self._sort_reverse = False
        self._tree_headings: dict[str, str] = {}
        self.last_result: dict[str, Any] | None = None
        self._theme_name = "dark"
        self._palette = theme_palette(self._theme_name)

        self.search_var = tk.StringVar()
        self.severity_var = tk.StringVar(value="All")
        self.domain_var = tk.StringVar(value="All")
        self.summary_var = tk.StringVar(value="Project diagnostics not evaluated")
        self.error_count_var = tk.StringVar(value="ERROR 0")
        self.warning_count_var = tk.StringVar(value="WARNING 0")
        self.info_count_var = tk.StringVar(value="INFO 0")
        self._build()

        self.search_var.trace_add("write", lambda *_: self._populate())
        self.severity_var.trace_add("write", lambda *_: self._populate())
        self.domain_var.trace_add("write", lambda *_: self._populate())

    def _build(self) -> None:
        toolbar = ttk.Frame(self, style="CX.Toolbar.TFrame", padding=(7, 5))
        toolbar.pack(fill="x")

        ttk.Label(toolbar, text="PROBLEMS", style="CX.Section.TLabel").pack(
            side="left", padx=(0, 8)
        )
        ttk.Label(toolbar, text="Search").pack(side="left")
        ttk.Entry(toolbar, textvariable=self.search_var, width=28).pack(
            side="left", padx=(4, 8)
        )
        ttk.Label(toolbar, text="Severity").pack(side="left")
        self.severity_picker = ttk.Combobox(
            toolbar,
            textvariable=self.severity_var,
            values=("All", "Critical", "Error", "Warning", "Info"),
            state="readonly",
            width=10,
        )
        self.severity_picker.pack(side="left", padx=(4, 8))
        ttk.Label(toolbar, text="Domain").pack(side="left")
        self.domain_picker = ttk.Combobox(
            toolbar,
            textvariable=self.domain_var,
            values=("All",),
            state="readonly",
            width=15,
        )
        self.domain_picker.pack(side="left", padx=(4, 8))
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
            state="disabled",
        )
        self.locate_button.pack(side="left", padx=2)
        self.previous_button = ttk.Button(
            toolbar,
            text="Previous",
            style="CX.Compact.TButton",
            command=lambda: self._select_relative(-1),
            state="disabled",
        )
        self.previous_button.pack(side="left", padx=2)
        self.next_button = ttk.Button(
            toolbar,
            text="Next",
            style="CX.Compact.TButton",
            command=lambda: self._select_relative(1),
            state="disabled",
        )
        self.next_button.pack(side="left", padx=2)
        self.copy_button = ttk.Button(
            toolbar,
            text="Copy",
            style="CX.Compact.TButton",
            command=self.copy_selected,
            state="disabled",
        )
        self.copy_button.pack(side="left", padx=2)
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
            text="Select a row to inspect · Double-click to locate",
            style="CX.Muted.TLabel",
        ).pack(side="right")

        body = ttk.Panedwindow(self, orient="vertical")
        body.pack(fill="both", expand=True)

        table_frame = ttk.Frame(body)
        detail_frame = ttk.Frame(body)
        body.add(table_frame, weight=4)
        body.add(detail_frame, weight=1)

        columns = ("severity", "code", "description", "object", "level", "domain")
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
            "domain": "Domain",
        }
        self._tree_headings = dict(headings)
        widths = {
            "severity": 90,
            "code": 220,
            "description": 520,
            "object": 180,
            "level": 120,
            "domain": 150,
        }
        for column in columns:
            self.tree.heading(
                column,
                text=headings[column],
                command=lambda key=column: self._set_sort_column(key),
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

        self._configure_tree_tags()
        self.tree.bind("<<TreeviewSelect>>", self._show_selected_detail)
        self.tree.bind("<Double-1>", self._navigate_selected)
        self.tree.bind("<Return>", self._navigate_selected)
        self.tree.bind("<Alt-Up>", lambda event: self._select_relative(-1))
        self.tree.bind("<Alt-Down>", lambda event: self._select_relative(1))

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

        severity = self.severity_var.get().strip().casefold()
        domain = self.domain_var.get().strip().casefold()
        query = self.search_var.get().strip().casefold()
        visible: list[dict[str, Any]] = []
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            issue_severity = str(issue.get("severity", "")).casefold()
            if severity and severity != "all" and issue_severity != severity:
                continue
            issue_domain = str(issue.get("category", "")).strip().casefold()
            if domain and domain != "all" and issue_domain != domain:
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
        if self._sort_column is not None:
            visible.sort(
                key=lambda issue: self._diagnostic_sort_value(
                    issue,
                    self._sort_column or "code",
                ),
                reverse=self._sort_reverse,
            )
        return visible

    @staticmethod
    def _diagnostic_sort_value(
        issue: dict[str, Any],
        column: str,
    ) -> tuple[Any, ...]:
        severity_order = {
            "critical": 0,
            "error": 1,
            "warning": 2,
            "info": 3,
        }
        if column == "severity":
            severity = str(issue.get("severity", "")).strip().casefold()
            return (severity_order.get(severity, 99), severity)
        if column == "code":
            return (str(issue.get("rule", "")).casefold(),)
        if column == "description":
            return (str(issue.get("message", "")).casefold(),)
        if column == "object":
            element = issue.get("element")
            if isinstance(element, dict):
                value = (
                    element.get("name")
                    or element.get("id")
                    or element.get("type")
                    or ""
                )
            else:
                value = ""
            return (str(value).casefold(),)
        if column == "level":
            details = issue.get("details")
            if isinstance(details, dict):
                for key in ("level", "level_name", "floor", "floor_name"):
                    if details.get(key) not in (None, ""):
                        return (str(details.get(key)).casefold(),)
            return ("",)
        if column == "domain":
            return (str(issue.get("category", "")).casefold(),)
        return ("",)

    def _set_sort_column(self, column: str) -> None:
        if column not in self._tree_headings:
            return
        if self._sort_column == column:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = column
            self._sort_reverse = False
        for key, label in self._tree_headings.items():
            suffix = ""
            if key == self._sort_column:
                suffix = " ▼" if self._sort_reverse else " ▲"
            self.tree.heading(
                key,
                text=label + suffix,
                command=lambda selected=key: self._set_sort_column(selected),
            )
        self._populate()

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
        self._show_selected_detail()

    def _refresh_domain_values(self) -> None:
        result = self.last_result if isinstance(self.last_result, dict) else {}
        issues = result.get("issues", [])
        domains = sorted(
            {
                str(issue.get("category", "")).strip()
                for issue in issues
                if isinstance(issue, dict) and str(issue.get("category", "")).strip()
            },
            key=str.casefold,
        )
        values = ("All", *domains)
        self.domain_picker.configure(values=values)
        if self.domain_var.get() not in values:
            self.domain_var.set("All")

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
            self._update_summary_style()
            return None

        self.last_result = result
        self._refresh_domain_values()
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
        enabled = "normal" if issue is not None else "disabled"
        self.locate_button.configure(state=enabled)
        self.copy_button.configure(state=enabled)
        rows = self.tree.get_children()
        navigation_state = "normal" if len(rows) > 1 else "disabled"
        self.previous_button.configure(state=navigation_state)
        self.next_button.configure(state=navigation_state)
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

    def _select_relative(self, direction: int):
        rows = list(self.tree.get_children())
        if not rows:
            return "break"
        selection = self.tree.selection()
        if selection and selection[0] in rows:
            index = rows.index(selection[0])
            target_index = (index + (-1 if direction < 0 else 1)) % len(rows)
        else:
            target_index = 0 if direction >= 0 else len(rows) - 1
        target = rows[target_index]
        self.tree.selection_set(target)
        self.tree.focus(target)
        self.tree.see(target)
        self._show_selected_detail()
        return "break"

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

def _evidence_value_text(value: Any) -> str:
    """Render retained evidence values without exposing raw structured payloads."""
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "YES" if value else "NO"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.4g}"
    if isinstance(value, dict):
        return f"{len(value)} field(s)"
    if isinstance(value, (list, tuple)):
        if all(not isinstance(item, (dict, list, tuple)) for item in value):
            rendered = ", ".join(str(item) for item in value[:6])
            if len(value) > 6:
                rendered += f", … (+{len(value) - 6})"
            return rendered or "Empty collection"
        return f"{len(value)} structured item(s)"
    text = str(value)
    return text if len(text) <= 120 else text[:117] + "…"


def verification_evidence_projection(records: Any) -> list[dict[str, Any]]:
    """Project canonical verification history into engineer-facing evidence rows."""
    if not isinstance(records, (list, tuple)):
        return []
    projected: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        verification = record.get("verification")
        verification = verification if isinstance(verification, dict) else {}
        evidence_items = record.get("evidence")
        evidence_items = evidence_items if isinstance(evidence_items, list) else []
        evidence_rows: list[dict[str, str]] = []
        for item in evidence_items:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source") or "")
            source_revision = str(item.get("source_revision") or "")
            if source_revision:
                source = f"{source} · {source_revision}" if source else source_revision
            calculation_source = str(item.get("calculation_source") or "")
            if calculation_source and calculation_source not in source:
                source = (
                    f"{source} · {calculation_source}"
                    if source
                    else calculation_source
                )
            evidence_rows.append(
                {
                    "id": str(item.get("id") or ""),
                    "requirement": str(item.get("requirement_id") or ""),
                    "subject": str(item.get("subject_ref") or "project"),
                    "property": str(item.get("property_name") or ""),
                    "value": _evidence_value_text(item.get("value")),
                    "unit": str(item.get("unit") or ""),
                    "freshness": str(item.get("freshness") or ""),
                    "source": source,
                    "locator": str(item.get("evidence_locator") or ""),
                }
            )
        projected.append(
            {
                "sequence": record.get("sequence"),
                "analysis": str(
                    record.get("analysis_name")
                    or record.get("analysis_id")
                    or "analysis"
                ),
                "analysis_kind": str(record.get("analysis_kind") or ""),
                "status": str(verification.get("status") or "unknown"),
                "verified": bool(verification.get("verified")),
                "completed": str(record.get("completed_at_utc") or ""),
                "version": str(record.get("cleanroomx_version") or ""),
                "evidence": evidence_rows,
            }
        )
    return projected


class VerificationEvidencePanel(ttk.Frame):
    """Structured retained-evidence view for project verification history."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_open_proofgraph: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master)
        self._on_open_proofgraph = on_open_proofgraph
        self._records: list[dict[str, Any]] = []
        self._records_by_iid: dict[str, dict[str, Any]] = {}
        self._palette = theme_palette("dark")
        self.summary_var = tk.StringVar(value="No retained verification evidence")
        self.detail_var = tk.StringVar(
            value="Persist a project verification run to retain evidence and provenance."
        )

        header = ttk.Frame(self, style="CX.Toolbar.TFrame", padding=(7, 5))
        header.pack(fill="x")
        ttk.Label(
            header,
            text="VERIFICATION EVIDENCE",
            style="CX.Section.TLabel",
        ).pack(side="left", padx=(0, 8))
        self.summary_label = ttk.Label(
            header,
            textvariable=self.summary_var,
            style="CX.Status.Neutral.TLabel",
        )
        self.summary_label.pack(side="left")
        self.open_graph_button = ttk.Button(
            header,
            text="Open ProofGraph",
            style="CX.Compact.TButton",
            command=self._open_proofgraph,
            state="normal" if on_open_proofgraph is not None else "disabled",
        )
        self.open_graph_button.pack(side="right")

        ttk.Label(
            self,
            textvariable=self.detail_var,
            style="CX.Muted.TLabel",
            anchor="w",
        ).pack(fill="x", padx=8, pady=(5, 4))

        panes = ttk.Panedwindow(self, orient="vertical")
        panes.pack(fill="both", expand=True)

        record_host = ttk.Frame(panes)
        evidence_host = ttk.Frame(panes)
        panes.add(record_host, weight=2)
        panes.add(evidence_host, weight=3)

        record_columns = ("analysis", "status", "evidence", "completed", "version")
        self.record_tree = ttk.Treeview(
            record_host,
            columns=record_columns,
            show="tree headings",
            selectmode="browse",
            height=6,
        )
        self.record_tree.heading("#0", text="#")
        self.record_tree.heading("analysis", text="Analysis")
        self.record_tree.heading("status", text="Verification")
        self.record_tree.heading("evidence", text="Evidence")
        self.record_tree.heading("completed", text="Completed UTC")
        self.record_tree.heading("version", text="Version")
        self.record_tree.column("#0", width=54, stretch=False, anchor="center")
        self.record_tree.column("analysis", width=230, minwidth=140)
        self.record_tree.column("status", width=105, stretch=False, anchor="center")
        self.record_tree.column("evidence", width=85, stretch=False, anchor="e")
        self.record_tree.column("completed", width=190, stretch=False)
        self.record_tree.column("version", width=95, stretch=False)
        record_y = ttk.Scrollbar(
            record_host, orient="vertical", command=self.record_tree.yview
        )
        self.record_tree.configure(yscrollcommand=record_y.set)
        self.record_tree.grid(row=0, column=0, sticky="nsew")
        record_y.grid(row=0, column=1, sticky="ns")
        record_host.rowconfigure(0, weight=1)
        record_host.columnconfigure(0, weight=1)
        self.record_tree.bind("<<TreeviewSelect>>", self._on_record_selected)

        evidence_columns = (
            "requirement",
            "subject",
            "property",
            "value",
            "unit",
            "freshness",
            "source",
            "locator",
        )
        self.evidence_tree = ttk.Treeview(
            evidence_host,
            columns=evidence_columns,
            show="tree headings",
            selectmode="browse",
        )
        self.evidence_tree.heading("#0", text="Evidence ID")
        headings = {
            "requirement": "Requirement",
            "subject": "Subject",
            "property": "Property",
            "value": "Value",
            "unit": "Unit",
            "freshness": "Freshness",
            "source": "Source / provenance",
            "locator": "Locator",
        }
        widths = {
            "requirement": 140,
            "subject": 130,
            "property": 150,
            "value": 130,
            "unit": 75,
            "freshness": 100,
            "source": 290,
            "locator": 220,
        }
        self.evidence_tree.column("#0", width=165, minwidth=110)
        for column in evidence_columns:
            self.evidence_tree.heading(column, text=headings[column])
            self.evidence_tree.column(
                column,
                width=widths[column],
                minwidth=70,
                stretch=column in {"source", "locator"},
            )

        evidence_y = ttk.Scrollbar(
            evidence_host, orient="vertical", command=self.evidence_tree.yview
        )
        evidence_x = ttk.Scrollbar(
            evidence_host, orient="horizontal", command=self.evidence_tree.xview
        )
        self.evidence_tree.configure(
            yscrollcommand=evidence_y.set,
            xscrollcommand=evidence_x.set,
        )
        self.evidence_tree.grid(row=0, column=0, sticky="nsew")
        evidence_y.grid(row=0, column=1, sticky="ns")
        evidence_x.grid(row=1, column=0, sticky="ew")
        evidence_host.rowconfigure(0, weight=1)
        evidence_host.columnconfigure(0, weight=1)

        self.apply_theme("dark")

    def apply_theme(self, value: Any) -> None:
        self._palette = theme_palette(value)
        for tree in (self.record_tree, self.evidence_tree):
            tree.tag_configure("row_even", background=self._palette["tree"])
            tree.tag_configure("row_odd", background=self._palette["surface_alt"])
        self.record_tree.tag_configure("pass", foreground=self._palette["success"])
        self.record_tree.tag_configure("fail", foreground=self._palette["error"])
        self.record_tree.tag_configure("warning", foreground=self._palette["warning"])
        self.record_tree.tag_configure("stale", foreground=self._palette["attention"])
        self.evidence_tree.tag_configure(
            "fresh", foreground=self._palette["success"]
        )
        self.evidence_tree.tag_configure(
            "stale", foreground=self._palette["attention"]
        )

    def set_records(self, records: Any) -> None:
        self._records = verification_evidence_projection(records)
        self._records_by_iid.clear()
        for item in self.record_tree.get_children():
            self.record_tree.delete(item)
        for item in self.evidence_tree.get_children():
            self.evidence_tree.delete(item)

        for index, record in enumerate(reversed(self._records), start=1):
            iid = f"record-{index}"
            status = str(record.get("status") or "unknown").lower()
            row_tag = "row_even" if index % 2 == 0 else "row_odd"
            self.record_tree.insert(
                "",
                "end",
                iid=iid,
                text=str(record.get("sequence") or "—"),
                values=(
                    record.get("analysis", ""),
                    status.upper().replace("_", " "),
                    len(record.get("evidence", [])),
                    record.get("completed", ""),
                    record.get("version", ""),
                ),
                tags=(row_tag, status),
            )
            self._records_by_iid[iid] = record

        if not self._records:
            self.summary_var.set("NO RETAINED EVIDENCE")
            self.summary_label.configure(style="CX.Status.Neutral.TLabel")
            self.detail_var.set(
                "Persist a project verification run to retain evidence, provenance, and ProofGraph traceability."
            )
            return

        latest = self._records[-1]
        status = str(latest.get("status") or "unknown")
        total_evidence = sum(len(record.get("evidence", [])) for record in self._records)
        self.summary_var.set(
            f"{len(self._records)} RECORDS · {total_evidence} EVIDENCE ITEMS"
        )
        self.summary_label.configure(style=status_style_name(status))
        children = self.record_tree.get_children()
        if children:
            self.record_tree.selection_set(children[0])
            self.record_tree.focus(children[0])
            self._on_record_selected()

    def _on_record_selected(self, _event=None) -> None:
        for item in self.evidence_tree.get_children():
            self.evidence_tree.delete(item)
        selection = self.record_tree.selection()
        if not selection:
            return
        record = self._records_by_iid.get(selection[0])
        if record is None:
            return
        evidence = record.get("evidence", [])
        self.detail_var.set(
            f"{record.get('analysis', 'Analysis')} · {str(record.get('status', 'unknown')).upper()} · "
            f"{record.get('completed', '')} · {len(evidence)} retained evidence item(s)"
        )
        for index, item in enumerate(evidence, start=1):
            freshness = str(item.get("freshness") or "")
            row_tag = "row_even" if index % 2 == 0 else "row_odd"
            freshness_tag = freshness.lower() if freshness.lower() in {"fresh", "stale"} else row_tag
            self.evidence_tree.insert(
                "",
                "end",
                iid=f"evidence-{index}",
                text=item.get("id", ""),
                values=(
                    item.get("requirement", ""),
                    item.get("subject", ""),
                    item.get("property", ""),
                    item.get("value", ""),
                    item.get("unit", ""),
                    freshness,
                    item.get("source", ""),
                    item.get("locator", ""),
                ),
                tags=(row_tag, freshness_tag),
            )

    def _open_proofgraph(self) -> None:
        if self._on_open_proofgraph is not None:
            self._on_open_proofgraph()

