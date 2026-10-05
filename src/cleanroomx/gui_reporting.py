from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import tkinter as tk
from tkinter import ttk


def _count(summary: Mapping[str, Any], key: str) -> int:
    try:
        return max(0, int(summary.get(key, 0) or 0))
    except (TypeError, ValueError):
        return 0


def build_reporting_snapshot(
    *,
    project_name: str,
    project_path: str | None,
    project_dirty: bool,
    running: bool,
    analysis_name: str | None,
    analysis_kind: str | None,
    run_title: str | None,
    run_status: str | None,
    run_markdown: str | None,
    run_is_current: bool,
    freshness_error: str | None = None,
    diagnostics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Project backend-authoritative reporting state into presentation-only GUI data."""

    if analysis_name is None:
        analysis_state = "no_analysis"
        analysis_status = "[ACTION] No analysis selected"
        analysis_detail = "Select an analysis before generating an analysis report."
        analysis_ready = False
        preview = "No analysis is selected. Select an analysis to review its report readiness."
    elif run_title is None:
        analysis_state = "not_run"
        analysis_status = "[ACTION] Analysis not calculated"
        analysis_detail = "Run the selected analysis to generate backend report evidence."
        analysis_ready = False
        preview = (
            f"No completed current report is available for {analysis_name}.\n\n"
            "Run the analysis to generate a report. Missing results are not shown as zero."
        )
    elif freshness_error:
        analysis_state = "freshness_unavailable"
        analysis_status = "[UNAVAILABLE] Result freshness could not be verified"
        analysis_detail = freshness_error
        analysis_ready = False
        preview = (
            "A previous report exists, but its freshness could not be verified. "
            "Rerun the analysis before publication."
        )
    elif not run_is_current:
        analysis_state = "stale"
        analysis_status = "[STALE] Report is out of date"
        analysis_detail = "The retained result no longer matches the current analysis input."
        analysis_ready = False
        preview = (
            "The previous report is stale and is intentionally not presented as publishable. "
            "Run the analysis again."
        )
    else:
        analysis_state = "ready"
        analysis_status = "[READY] Current analysis report"
        status = str(run_status or "unknown").strip() or "unknown"
        analysis_detail = f"{run_title} — backend status: {status}"
        analysis_ready = True
        preview = str(run_markdown or "").strip()
        if not preview:
            preview = (
                "The current backend run contains no Markdown report text. "
                "No report content has been synthesized by the GUI."
            )

    if running:
        dossier_state = "running"
        dossier_status = "[ACTION] Dossier export waits for the active run"
        dossier_detail = "Abandon or complete the active analysis before exporting the project dossier."
        dossier_ready = False
    elif not project_path:
        dossier_state = "save_required"
        dossier_status = "[ACTION] Save project before dossier export"
        dossier_detail = (
            "The project-native dossier must bind to exact saved project bytes and a source SHA-256."
        )
        dossier_ready = False
    elif project_dirty:
        dossier_state = "unsaved"
        dossier_status = "[ACTION] Save project changes"
        dossier_detail = (
            "Unsaved changes must be committed before the dossier can bind to the saved revision."
        )
        dossier_ready = False
    else:
        dossier_state = "ready"
        dossier_status = "[READY] Project dossier can be generated"
        dossier_detail = (
            "Export will validate the saved project revision before and after dossier generation."
        )
        dossier_ready = True

    diagnostic_summary: Mapping[str, Any] = {}
    diagnostic_status = "unavailable"
    if isinstance(diagnostics, Mapping):
        candidate = diagnostics.get("summary", {})
        if isinstance(candidate, Mapping):
            diagnostic_summary = candidate
            diagnostic_status = str(candidate.get("status", "unknown") or "unknown")

    error_count = _count(diagnostic_summary, "error_count")
    warning_count = _count(diagnostic_summary, "warning_count")
    info_count = _count(diagnostic_summary, "info_count")
    issue_count = _count(diagnostic_summary, "issue_count")

    return {
        "project": {
            "name": str(project_name or "Untitled project"),
            "location": str(project_path or "Unsaved project"),
        },
        "analysis": {
            "state": analysis_state,
            "status": analysis_status,
            "detail": analysis_detail,
            "name": analysis_name or "—",
            "kind": analysis_kind or "—",
            "run_status": run_status or "—",
            "export_ready": analysis_ready,
        },
        "dossier": {
            "state": dossier_state,
            "status": dossier_status,
            "detail": dossier_detail,
            "export_ready": dossier_ready,
        },
        "diagnostics": {
            "status": diagnostic_status,
            "issue_count": issue_count,
            "error_count": error_count,
            "warning_count": warning_count,
            "info_count": info_count,
        },
        "preview": preview,
    }


class ReportingWorkspace(ttk.Frame):
    """Read-only publication hub over existing CleanroomX report authorities."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        snapshot_getter: Callable[[], dict[str, Any]],
        export_dossier: Callable[[], Any],
        export_markdown: Callable[[], Any],
        export_html: Callable[[], Any],
        export_result: Callable[[], Any],
        status_setter: Callable[[str], Any] | None = None,
    ) -> None:
        super().__init__(parent, padding=(8, 6))
        self.snapshot_getter = snapshot_getter
        self.export_dossier = export_dossier
        self.export_markdown = export_markdown
        self.export_html = export_html
        self.export_result = export_result
        self.status_setter = status_setter
        self.last_snapshot: dict[str, Any] = {}

        self.analysis_status_var = tk.StringVar(value="[ACTION] No analysis selected")
        self.analysis_detail_var = tk.StringVar(value="")
        self.analysis_meta_var = tk.StringVar(value="")
        self.dossier_status_var = tk.StringVar(value="[ACTION] Save project before dossier export")
        self.dossier_detail_var = tk.StringVar(value="")
        self.project_var = tk.StringVar(value="")
        self.diagnostics_var = tk.StringVar(value="Project diagnostics: unavailable")
        self.preview_status_var = tk.StringVar(value="Backend report preview")

        self._build()
        self.refresh()

    def _build(self) -> None:
        header = ttk.Frame(self)
        header.pack(fill="x", pady=(0, 6))
        ttk.Label(
            header,
            text="REPORTING / PUBLICATION",
            style="CX.ViewTitle.TLabel",
        ).pack(side="left")
        ttk.Label(
            header,
            text="Backend-authoritative reports · revision-bound dossier · explicit readiness",
        ).pack(side="left", padx=(12, 0))

        actions = ttk.Frame(self, style="CX.Toolbar.TFrame")
        actions.pack(fill="x", pady=(0, 7))
        ttk.Button(
            actions,
            text="Refresh",
            style="CX.Compact.TButton",
            command=lambda: self.refresh(announce=True),
        ).pack(side="left", padx=(0, 4))
        self.dossier_button = ttk.Button(
            actions,
            text="Export Project Dossier…",
            command=lambda: self._run_action(self.export_dossier),
        )
        self.dossier_button.pack(side="left", padx=2)
        self.markdown_button = ttk.Button(
            actions,
            text="Export Markdown…",
            command=lambda: self._run_action(self.export_markdown),
        )
        self.markdown_button.pack(side="left", padx=2)
        self.html_button = ttk.Button(
            actions,
            text="Export Portable HTML…",
            command=lambda: self._run_action(self.export_html),
        )
        self.html_button.pack(side="left", padx=2)
        self.result_button = ttk.Button(
            actions,
            text="Export Result JSON…",
            command=lambda: self._run_action(self.export_result),
        )
        self.result_button.pack(side="left", padx=2)

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True)

        readiness = ttk.Frame(body, padding=(0, 0, 8, 0))
        preview = ttk.Frame(body)
        body.add(readiness, weight=2)
        body.add(preview, weight=5)

        project_box = ttk.LabelFrame(readiness, text="Project")
        project_box.pack(fill="x", pady=(0, 7))
        ttk.Label(
            project_box,
            textvariable=self.project_var,
            justify="left",
            wraplength=340,
        ).pack(fill="x", padx=8, pady=7)

        analysis_box = ttk.LabelFrame(readiness, text="Analysis report")
        analysis_box.pack(fill="x", pady=(0, 7))
        ttk.Label(
            analysis_box,
            textvariable=self.analysis_status_var,
            style="CX.ViewTitle.TLabel",
            justify="left",
        ).pack(fill="x", padx=8, pady=(7, 2))
        ttk.Label(
            analysis_box,
            textvariable=self.analysis_detail_var,
            justify="left",
            wraplength=340,
        ).pack(fill="x", padx=8, pady=(0, 4))
        ttk.Label(
            analysis_box,
            textvariable=self.analysis_meta_var,
            justify="left",
            wraplength=340,
        ).pack(fill="x", padx=8, pady=(0, 7))

        dossier_box = ttk.LabelFrame(readiness, text="Project engineering dossier")
        dossier_box.pack(fill="x", pady=(0, 7))
        ttk.Label(
            dossier_box,
            textvariable=self.dossier_status_var,
            style="CX.ViewTitle.TLabel",
            justify="left",
        ).pack(fill="x", padx=8, pady=(7, 2))
        ttk.Label(
            dossier_box,
            textvariable=self.dossier_detail_var,
            justify="left",
            wraplength=340,
        ).pack(fill="x", padx=8, pady=(0, 7))

        health_box = ttk.LabelFrame(readiness, text="Project health at publication")
        health_box.pack(fill="x")
        ttk.Label(
            health_box,
            textvariable=self.diagnostics_var,
            justify="left",
            wraplength=340,
        ).pack(fill="x", padx=8, pady=7)

        preview_header = ttk.Frame(preview, style="CX.PanelHeader.TFrame")
        preview_header.pack(fill="x")
        ttk.Label(
            preview_header,
            text="REPORT PREVIEW",
            style="CX.PanelHeader.TLabel",
        ).pack(side="left")
        ttk.Label(
            preview_header,
            textvariable=self.preview_status_var,
            style="CX.PanelHeader.TLabel",
        ).pack(side="right")

        preview_body = ttk.Frame(preview)
        preview_body.pack(fill="both", expand=True)
        self.preview_text = tk.Text(
            preview_body,
            wrap="word",
            state="disabled",
            padx=10,
            pady=8,
        )
        yscroll = ttk.Scrollbar(
            preview_body,
            orient="vertical",
            command=self.preview_text.yview,
        )
        xscroll = ttk.Scrollbar(
            preview_body,
            orient="horizontal",
            command=self.preview_text.xview,
        )
        self.preview_text.configure(
            yscrollcommand=yscroll.set,
            xscrollcommand=xscroll.set,
        )
        self.preview_text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        preview_body.rowconfigure(0, weight=1)
        preview_body.columnconfigure(0, weight=1)

        ttk.Label(
            preview,
            text=(
                "Publication rule: missing, stale, or unverifiable engineering results remain "
                "explicitly unavailable; the GUI does not synthesize report values."
            ),
            justify="left",
            wraplength=760,
        ).pack(fill="x", pady=(6, 0))

    def _set_preview(self, value: str) -> None:
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", value)
        self.preview_text.configure(state="disabled")

    @staticmethod
    def _set_enabled(button: ttk.Button, enabled: bool) -> None:
        button.configure(state="normal" if enabled else "disabled")

    def _run_action(self, action: Callable[[], Any]) -> None:
        action()
        self.refresh()

    def refresh(self, *, announce: bool = False) -> dict[str, Any]:
        snapshot = dict(self.snapshot_getter() or {})
        self.last_snapshot = snapshot

        project = snapshot.get("project", {})
        analysis = snapshot.get("analysis", {})
        dossier = snapshot.get("dossier", {})
        diagnostics = snapshot.get("diagnostics", {})

        self.project_var.set(
            f"{project.get('name', 'Untitled project')}\n{project.get('location', 'Unsaved project')}"
        )
        self.analysis_status_var.set(str(analysis.get("status", "[UNAVAILABLE] Report state unavailable")))
        self.analysis_detail_var.set(str(analysis.get("detail", "")))
        self.analysis_meta_var.set(
            "Analysis: {name}\nKind: {kind}\nBackend run status: {status}".format(
                name=analysis.get("name", "—"),
                kind=analysis.get("kind", "—"),
                status=analysis.get("run_status", "—"),
            )
        )
        self.dossier_status_var.set(str(dossier.get("status", "[UNAVAILABLE] Dossier state unavailable")))
        self.dossier_detail_var.set(str(dossier.get("detail", "")))
        self.diagnostics_var.set(
            "Status: {status}\nIssues: {issues}  ·  Errors: {errors}  ·  "
            "Warnings: {warnings}  ·  Info: {info}".format(
                status=str(diagnostics.get("status", "unavailable")).upper(),
                issues=diagnostics.get("issue_count", 0),
                errors=diagnostics.get("error_count", 0),
                warnings=diagnostics.get("warning_count", 0),
                info=diagnostics.get("info_count", 0),
            )
        )

        analysis_ready = bool(analysis.get("export_ready"))
        dossier_ready = bool(dossier.get("export_ready"))
        self._set_enabled(self.markdown_button, analysis_ready)
        self._set_enabled(self.html_button, analysis_ready)
        self._set_enabled(self.result_button, analysis_ready)
        self._set_enabled(self.dossier_button, dossier_ready)
        self.preview_status_var.set(
            "Current backend report" if analysis_ready else "Not publishable"
        )
        self._set_preview(str(snapshot.get("preview", "Reporting state unavailable.")))

        if announce and self.status_setter is not None:
            self.status_setter(
                "Reporting workspace refreshed — "
                + ("analysis report ready" if analysis_ready else "analysis report not ready")
                + "; "
                + ("dossier ready" if dossier_ready else "dossier action required")
            )
        return snapshot
