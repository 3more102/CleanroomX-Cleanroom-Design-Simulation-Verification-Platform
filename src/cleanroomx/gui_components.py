from __future__ import annotations

from typing import Any, Callable

import tkinter as tk
from tkinter import ttk


def diagnostic_issue_rows(report: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Project the canonical project-diagnostics report into stable GUI rows."""
    if not isinstance(report, dict):
        return []
    issues = report.get("issues")
    if not isinstance(issues, list):
        return []

    rows: list[dict[str, Any]] = []
    for index, issue in enumerate(issues, start=1):
        if not isinstance(issue, dict):
            continue
        element = issue.get("element")
        if not isinstance(element, dict):
            element = {}
        details = issue.get("details")
        if not isinstance(details, dict):
            details = {}
        element_id = element.get("id")
        element_name = element.get("name")
        element_type = str(element.get("type") or "project")
        object_text = str(element_name or element_id or element_type)
        level = (
            details.get("level")
            or details.get("level_name")
            or details.get("floor")
            or details.get("floor_name")
            or ""
        )
        rows.append(
            {
                "sequence": int(issue.get("sequence") or index),
                "severity": str(issue.get("severity") or "info").lower(),
                "code": str(issue.get("rule") or ""),
                "description": str(issue.get("message") or ""),
                "object": object_text,
                "level": str(level),
                "source": str(issue.get("category") or ""),
                "issue": issue,
            }
        )
    return rows


def verification_rows(report: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Project canonical verification-currency state into GUI rows."""
    if not isinstance(report, dict):
        return []
    currency = report.get("verification_currency")
    if not isinstance(currency, dict):
        return []
    analyses = currency.get("analyses")
    if not isinstance(analyses, list):
        return []

    rows: list[dict[str, Any]] = []
    for item in analyses:
        if not isinstance(item, dict):
            continue
        latest = item.get("latest_record")
        if not isinstance(latest, dict):
            latest = {}
        rows.append(
            {
                "analysis_id": str(item.get("analysis_id") or ""),
                "analysis_name": str(
                    item.get("analysis_name") or item.get("analysis_id") or ""
                ),
                "state": str(item.get("state") or ""),
                "current": bool(item.get("current") is True),
                "complete": bool(item.get("complete") is True),
                "latest_sequence": latest.get("sequence"),
                "latest_status": str(latest.get("status") or ""),
                "mismatch_reasons": tuple(
                    str(value)
                    for value in item.get("mismatch_reasons", [])
                    if str(value)
                ),
                "record": item,
            }
        )
    return rows


class DiagnosticsPanel(ttk.Frame):
    """IDE-style view over the canonical deterministic project diagnostics."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_navigate: Callable[[dict[str, Any]], None] | None = None,
        on_refresh: Callable[[], None] | None = None,
    ):
        super().__init__(master)
        self._on_navigate = on_navigate
        self._on_refresh = on_refresh
        self._report: dict[str, Any] | None = None
        self._rows_by_iid: dict[str, dict[str, Any]] = {}

        self.search_var = tk.StringVar()
        self.severity_var = tk.StringVar(value="All")
        self.summary_var = tk.StringVar(value="No diagnostics loaded")

        toolbar = ttk.Frame(self, padding=(6, 5))
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="Search").pack(side="left")
        search = ttk.Entry(toolbar, textvariable=self.search_var, width=28)
        search.pack(side="left", padx=(5, 8))
        ttk.Label(toolbar, text="Severity").pack(side="left")
        severity = ttk.Combobox(
            toolbar,
            textvariable=self.severity_var,
            values=("All", "Error", "Warning", "Info"),
            state="readonly",
            width=10,
        )
        severity.pack(side="left", padx=(5, 8))
        if on_refresh is not None:
            ttk.Button(toolbar, text="Refresh", command=on_refresh).pack(
                side="right", padx=(4, 0)
            )
        ttk.Button(toolbar, text="Copy", command=self.copy_selected).pack(
            side="right"
        )
        ttk.Label(toolbar, textvariable=self.summary_var).pack(
            side="right", padx=(8, 12)
        )

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        columns = ("severity", "code", "description", "object", "level", "source")
        self.tree = ttk.Treeview(
            body,
            columns=columns,
            show="headings",
            selectmode="browse",
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
            "severity": 82,
            "code": 205,
            "description": 520,
            "object": 160,
            "level": 105,
            "source": 130,
        }
        for name in columns:
            self.tree.heading(name, text=headings[name])
            self.tree.column(
                name,
                width=widths[name],
                minwidth=70,
                stretch=name == "description",
            )
        yscroll = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(body, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        self.tree.tag_configure("error", foreground="#b42318")
        self.tree.tag_configure("warning", foreground="#9a6700")
        self.tree.tag_configure("info", foreground="#57606a")
        self.tree.bind("<Double-1>", self._activate_selected)
        self.tree.bind("<Return>", self._activate_selected)
        self.search_var.trace_add("write", lambda *_: self._refresh_rows())
        self.severity_var.trace_add("write", lambda *_: self._refresh_rows())

    def clear(self) -> None:
        self._report = None
        self._rows_by_iid.clear()
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self.summary_var.set("No diagnostics loaded")

    def set_error(self, message: str) -> None:
        self.clear()
        self.summary_var.set(f"Diagnostics unavailable: {message}")

    def set_report(self, report: dict[str, Any]) -> None:
        self._report = report
        self._refresh_rows()

    def _refresh_rows(self) -> None:
        rows = diagnostic_issue_rows(self._report)
        query = self.search_var.get().strip().casefold()
        severity = self.severity_var.get().strip().lower()
        if severity == "all":
            severity = ""

        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._rows_by_iid.clear()

        visible = 0
        for row in rows:
            if severity and row["severity"] != severity:
                continue
            haystack = " ".join(
                str(row[key])
                for key in ("severity", "code", "description", "object", "level", "source")
            ).casefold()
            if query and query not in haystack:
                continue
            iid = f"issue:{row['sequence']}:{visible}"
            self._rows_by_iid[iid] = row
            self.tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    row["severity"].upper(),
                    row["code"],
                    row["description"],
                    row["object"],
                    row["level"],
                    row["source"],
                ),
                tags=(row["severity"],),
            )
            visible += 1

        summary = (
            self._report.get("summary", {})
            if isinstance(self._report, dict)
            else {}
        )
        total = int(summary.get("issue_count", len(rows)) or 0)
        errors = int(summary.get("error_count", 0) or 0)
        warnings = int(summary.get("warning_count", 0) or 0)
        self.summary_var.set(
            f"{visible}/{total} shown · {errors} error · {warnings} warning"
        )

    def selected_issue(self) -> dict[str, Any] | None:
        selection = self.tree.selection()
        if not selection:
            return None
        row = self._rows_by_iid.get(selection[0])
        if row is None:
            return None
        issue = row.get("issue")
        return issue if isinstance(issue, dict) else None

    def _activate_selected(self, event=None):
        issue = self.selected_issue()
        if issue is not None and self._on_navigate is not None:
            self._on_navigate(issue)
        return "break"

    def copy_selected(self) -> None:
        issue = self.selected_issue()
        if issue is None:
            return
        element = issue.get("element")
        if not isinstance(element, dict):
            element = {}
        object_text = element.get("name") or element.get("id") or element.get("type") or "project"
        text = (
            f"{str(issue.get('severity') or '').upper()} "
            f"{issue.get('rule') or ''}: {issue.get('message') or ''} "
            f"[{object_text}]"
        )
        self.clipboard_clear()
        self.clipboard_append(text)


class VerificationPanel(ttk.Frame):
    """Read-only current verification/currency view over canonical project evidence."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_navigate_analysis: Callable[[str], None] | None = None,
    ):
        super().__init__(master)
        self._on_navigate_analysis = on_navigate_analysis
        self._rows_by_iid: dict[str, dict[str, Any]] = {}
        self.summary_var = tk.StringVar(value="No verification state loaded")

        header = ttk.Frame(self, padding=(6, 5))
        header.pack(fill="x")
        ttk.Label(header, textvariable=self.summary_var).pack(side="left")

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        columns = ("analysis", "state", "current", "complete", "latest", "reasons")
        self.tree = ttk.Treeview(body, columns=columns, show="headings", selectmode="browse")
        headings = {
            "analysis": "Analysis",
            "state": "State",
            "current": "Current",
            "complete": "Complete",
            "latest": "Latest evidence",
            "reasons": "Mismatch / notes",
        }
        widths = {
            "analysis": 220,
            "state": 145,
            "current": 85,
            "complete": 85,
            "latest": 140,
            "reasons": 460,
        }
        for name in columns:
            self.tree.heading(name, text=headings[name])
            self.tree.column(
                name,
                width=widths[name],
                minwidth=70,
                stretch=name == "reasons",
            )
        yscroll = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(body, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        self.tree.bind("<Double-1>", self._activate_selected)
        self.tree.bind("<Return>", self._activate_selected)

    def set_report(self, report: dict[str, Any]) -> None:
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._rows_by_iid.clear()

        rows = verification_rows(report)
        for index, row in enumerate(rows):
            iid = f"verification:{index}"
            self._rows_by_iid[iid] = row
            latest = (
                f"#{row['latest_sequence']} {row['latest_status']}".strip()
                if row["latest_sequence"] is not None
                else "—"
            )
            self.tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    row["analysis_name"],
                    row["state"],
                    "Yes" if row["current"] else "No",
                    "Yes" if row["complete"] else "No",
                    latest,
                    ", ".join(row["mismatch_reasons"]) or "—",
                ),
            )

        currency = report.get("verification_currency", {}) if isinstance(report, dict) else {}
        summary = currency.get("summary", {}) if isinstance(currency, dict) else {}
        self.summary_var.set(
            "Verification currency · "
            f"{summary.get('current_count', 0)} current · "
            f"{summary.get('stale_count', 0)} stale · "
            f"{summary.get('not_verified_count', 0)} not verified"
        )

    def _activate_selected(self, event=None):
        selection = self.tree.selection()
        if not selection:
            return "break"
        row = self._rows_by_iid.get(selection[0])
        if row is None:
            return "break"
        analysis_id = row.get("analysis_id")
        if analysis_id and self._on_navigate_analysis is not None:
            self._on_navigate_analysis(str(analysis_id))
        return "break"
