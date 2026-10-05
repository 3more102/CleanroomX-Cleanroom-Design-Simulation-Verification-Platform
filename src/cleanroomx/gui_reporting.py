from __future__ import annotations

from typing import Any, Callable

import tkinter as tk
from tkinter import ttk

from .gui_theme import theme_palette


def _safe_count(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        count = int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return max(0, count)


def reporting_status_projection(snapshot: dict[str, Any] | None) -> dict[str, str]:
    """Project current report/release state without inventing engineering values."""
    data = snapshot if isinstance(snapshot, dict) else {}
    project_name = str(data.get("project_name") or "Untitled project")
    source = str(data.get("source") or "Unsaved project")
    save_state = "saved" if data.get("saved") is True else "unsaved"

    diagnostics = data.get("diagnostics")
    diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
    diagnostic_state = str(diagnostics.get("status") or "not checked").strip().lower()

    verification = data.get("verification")
    verification = verification if isinstance(verification, dict) else {}
    configured = _safe_count(verification.get("configured_analysis_count"))
    current = _safe_count(verification.get("current_count"))
    stale = _safe_count(verification.get("stale_count"))
    not_verified = _safe_count(verification.get("not_verified_count"))
    if configured <= 0:
        verification_state = "not configured"
        verification_detail = "No configured project verification"
    elif current == configured and stale == 0 and not_verified == 0:
        verification_state = "current"
        verification_detail = f"{current}/{configured} current"
    elif stale:
        verification_state = "stale"
        verification_detail = f"{stale} stale · {current}/{configured} current"
    else:
        verification_state = "not verified"
        verification_detail = (
            f"{not_verified} not verified · {current}/{configured} current"
        )

    last_run = data.get("last_run")
    if isinstance(last_run, dict):
        analysis_state = str(last_run.get("status") or "unknown").strip().lower()
        analysis_detail = str(last_run.get("title") or "Latest analysis")
    else:
        analysis_state = "not run"
        analysis_detail = "No current-session analysis result"

    records = _safe_count(data.get("evidence_record_count"))
    graphs = _safe_count(data.get("proofgraph_count"))
    return {
        "project_name": project_name,
        "source": source,
        "save_state": save_state,
        "diagnostic_state": diagnostic_state,
        "verification_state": verification_state,
        "verification_detail": verification_detail,
        "analysis_state": analysis_state,
        "analysis_detail": analysis_detail,
        "evidence_detail": f"{records} verification records · {graphs} ProofGraphs",
    }


_REPORT_SECTIONS: tuple[tuple[str, str], ...] = (
    ("project", "Project context"),
    ("diagnostics", "Diagnostics"),
    ("verification", "Verification"),
    ("analysis", "Latest analysis"),
    ("evidence", "Evidence / ProofGraph"),
)

_REPORT_TEMPLATES: dict[str, tuple[str, ...]] = {
    "Executive": ("project", "diagnostics", "verification", "evidence"),
    "Engineering": tuple(key for key, _label in _REPORT_SECTIONS),
    "Verification": ("project", "verification", "diagnostics", "evidence"),
    "Diagnostics": ("project", "diagnostics"),
    "Evidence": ("project", "verification", "evidence"),
    "Analysis": ("project", "analysis"),
    "Custom": (),
}


def reporting_template_sections(value: str | None) -> tuple[str, ...]:
    token = str(value or "Engineering").strip().title()
    return _REPORT_TEMPLATES.get(token, _REPORT_TEMPLATES["Engineering"])


def reporting_section_plan(
    snapshot: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Describe report-section availability from canonical application state."""
    data = snapshot if isinstance(snapshot, dict) else {}
    projected = reporting_status_projection(data)
    verification = data.get("verification")
    verification = verification if isinstance(verification, dict) else {}
    configured = _safe_count(verification.get("configured_analysis_count"))
    records = _safe_count(data.get("evidence_record_count"))
    graphs = _safe_count(data.get("proofgraph_count"))

    return {
        "project": {
            "label": "Project context",
            "available": True,
            "state": projected["save_state"],
            "detail": projected["source"],
        },
        "diagnostics": {
            "label": "Diagnostics",
            "available": projected["diagnostic_state"] != "not checked",
            "state": projected["diagnostic_state"],
            "detail": (
                "Current project diagnostic state"
                if projected["diagnostic_state"] != "not checked"
                else "Diagnostics have not been evaluated"
            ),
        },
        "verification": {
            "label": "Verification",
            "available": configured > 0,
            "state": projected["verification_state"],
            "detail": projected["verification_detail"],
        },
        "analysis": {
            "label": "Latest analysis",
            "available": isinstance(data.get("last_run"), dict),
            "state": projected["analysis_state"],
            "detail": projected["analysis_detail"],
        },
        "evidence": {
            "label": "Evidence / ProofGraph",
            "available": records > 0 or graphs > 0,
            "state": "available" if records > 0 or graphs > 0 else "missing",
            "detail": projected["evidence_detail"],
        },
    }


class ReportingWorkspace(ttk.Frame):
    """Report composition surface over CleanroomX canonical export paths."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_export_dossier: Callable[[], Any],
        on_export_diagnostics: Callable[[], Any],
        on_export_result_json: Callable[[], Any],
        on_export_run_bundle: Callable[[], Any],
        on_export_markdown: Callable[[], Any],
        on_export_html: Callable[[], Any],
        on_export_selected_summary: Callable[[], Any] | None = None,
    ) -> None:
        super().__init__(master, padding=(12, 10))
        self.project_var = tk.StringVar(value="Untitled project")
        self.source_var = tk.StringVar(value="Unsaved project")
        self.save_var = tk.StringVar(value="UNSAVED")
        self.diagnostics_var = tk.StringVar(value="NOT CHECKED")
        self.verification_var = tk.StringVar(value="NOT CONFIGURED")
        self.analysis_var = tk.StringVar(value="NOT RUN")
        self.evidence_var = tk.StringVar(
            value="0 verification records · 0 ProofGraphs"
        )
        self.template_var = tk.StringVar(value="Engineering")
        self.composition_var = tk.StringVar(value="5 sections selected")
        self._snapshot: dict[str, Any] = {}
        self._summary_export_callback = on_export_selected_summary
        self.section_vars = {
            key: tk.BooleanVar(value=True) for key, _label in _REPORT_SECTIONS
        }

        header = ttk.Frame(self, style="CX.PanelHeader.TFrame")
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(
            header,
            text="REPORTING / RELEASE",
            style="CX.PanelHeader.TLabel",
        ).pack(side="left")
        ttk.Label(
            header,
            textvariable=self.project_var,
            style="CX.PanelHeader.TLabel",
        ).pack(side="right", padx=(10, 6))
        ttk.Label(
            header,
            textvariable=self.save_var,
            style="CX.PanelHeader.TLabel",
        ).pack(side="right")

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True)

        context = ttk.Frame(body, padding=(8, 6))
        controls = ttk.Frame(body, padding=(8, 6))
        preview_frame = ttk.Frame(body, padding=(8, 6))
        body.add(context, weight=2)
        body.add(controls, weight=3)
        body.add(preview_frame, weight=5)

        ttk.Label(
            context,
            text="RELEASE CONTEXT",
            style="CX.Section.TLabel",
        ).pack(anchor="w", pady=(0, 7))
        self._kv(context, "Source", self.source_var)
        self._kv(context, "Diagnostics", self.diagnostics_var)
        self._kv(context, "Verification", self.verification_var)
        self._kv(context, "Analysis", self.analysis_var)
        self._kv(context, "Evidence", self.evidence_var)
        ttk.Label(
            context,
            text=(
                "States shown here are current application state. They do not create "
                "a regulatory approval, certification, commissioning, or release verdict."
            ),
            wraplength=250,
            justify="left",
        ).pack(anchor="w", fill="x", pady=(12, 0))

        ttk.Label(
            controls,
            text="REPORT COMPOSITION",
            style="CX.Section.TLabel",
        ).pack(anchor="w", pady=(0, 7))
        template_row = ttk.Frame(controls)
        template_row.pack(fill="x", pady=(0, 6))
        ttk.Label(template_row, text="Template").pack(side="left")
        self.template_combo = ttk.Combobox(
            template_row,
            textvariable=self.template_var,
            values=tuple(_REPORT_TEMPLATES),
            state="readonly",
            width=15,
        )
        self.template_combo.pack(side="right", fill="x", expand=True, padx=(8, 0))
        self.template_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._apply_template(),
        )

        for key, label in _REPORT_SECTIONS:
            ttk.Checkbutton(
                controls,
                text=label,
                variable=self.section_vars[key],
                command=self._on_section_changed,
            ).pack(anchor="w", pady=1)
        ttk.Label(
            controls,
            textvariable=self.composition_var,
        ).pack(anchor="w", pady=(4, 7))

        self.summary_export_button = ttk.Button(
            controls,
            text="Export Selected Summary…",
            command=on_export_selected_summary or (lambda: None),
            state="normal" if on_export_selected_summary is not None else "disabled",
        )
        self.summary_export_button.pack(fill="x", pady=(0, 8))

        ttk.Separator(controls, orient="horizontal").pack(fill="x", pady=(2, 8))
        ttk.Label(
            controls,
            text="AUTHORITATIVE OUTPUTS",
            style="CX.Section.TLabel",
        ).pack(anchor="w", pady=(0, 5))
        self.dossier_button = ttk.Button(
            controls,
            text="Export Engineering Dossier…",
            style="CX.Primary.TButton",
            command=on_export_dossier,
        )
        self.dossier_button.pack(fill="x", pady=2)
        self.diagnostics_button = ttk.Button(
            controls,
            text="Export Project Diagnostics…",
            command=on_export_diagnostics,
        )
        self.diagnostics_button.pack(fill="x", pady=2)

        ttk.Separator(controls, orient="horizontal").pack(fill="x", pady=8)
        ttk.Label(
            controls,
            text="ACTIVE-ANALYSIS OUTPUTS",
            style="CX.Section.TLabel",
        ).pack(anchor="w", pady=(0, 5))
        self.analysis_export_buttons: list[ttk.Button] = []
        for label, callback in (
            ("Result JSON…", on_export_result_json),
            ("Run Bundle JSON…", on_export_run_bundle),
            ("Report Markdown…", on_export_markdown),
            ("Portable HTML Report…", on_export_html),
        ):
            button = ttk.Button(controls, text=label, command=callback)
            button.pack(fill="x", pady=2)
            self.analysis_export_buttons.append(button)

        ttk.Label(
            preview_frame,
            text="COMPOSITION PREVIEW",
            style="CX.Section.TLabel",
        ).pack(anchor="w", pady=(0, 7))
        preview_host = ttk.Frame(preview_frame)
        preview_host.pack(fill="both", expand=True)
        self.preview = tk.Text(preview_host, wrap="word", state="disabled")
        scroll = ttk.Scrollbar(
            preview_host,
            orient="vertical",
            command=self.preview.yview,
        )
        self.preview.configure(yscrollcommand=scroll.set)
        self.preview.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self._apply_template(refresh_preview=False)
        self._set_preview(
            "No project state loaded.\n\n"
            "Reporting uses existing CleanroomX project, diagnostics, verification, "
            "evidence, and analysis outputs. It does not recalculate engineering values."
        )

    @staticmethod
    def _kv(master: ttk.Frame, label: str, variable: tk.StringVar) -> None:
        row = ttk.Frame(master)
        row.pack(fill="x", pady=3)
        ttk.Label(row, text=label).pack(side="left")
        ttk.Label(row, textvariable=variable).pack(side="right", padx=(8, 0))

    def refresh(self, snapshot: dict[str, Any] | None) -> None:
        self._snapshot = dict(snapshot) if isinstance(snapshot, dict) else {}
        projected = reporting_status_projection(self._snapshot)
        plan = reporting_section_plan(self._snapshot)

        self.project_var.set(projected["project_name"])
        self.source_var.set(projected["source"])
        self.save_var.set(projected["save_state"].upper())
        self.diagnostics_var.set(
            projected["diagnostic_state"].upper().replace("_", " ")
        )
        self.verification_var.set(
            projected["verification_state"].upper().replace("_", " ")
        )
        self.analysis_var.set(
            projected["analysis_state"].upper().replace("_", " ")
        )
        self.evidence_var.set(projected["evidence_detail"])

        self.dossier_button.configure(
            state="normal" if projected["save_state"] == "saved" else "disabled"
        )
        self.diagnostics_button.configure(
            state="normal" if plan["diagnostics"]["available"] else "disabled"
        )
        analysis_state = "normal" if plan["analysis"]["available"] else "disabled"
        for button in self.analysis_export_buttons:
            button.configure(state=analysis_state)
        self._refresh_composition()

    def _apply_template(self, *, refresh_preview: bool = True) -> None:
        template = self.template_var.get()
        selected = set(reporting_template_sections(template))
        if template != "Custom":
            for key, _label in _REPORT_SECTIONS:
                self.section_vars[key].set(key in selected)
        if refresh_preview:
            self._refresh_composition()

    def _on_section_changed(self) -> None:
        selected = tuple(
            key for key, _label in _REPORT_SECTIONS if self.section_vars[key].get()
        )
        if selected != reporting_template_sections(self.template_var.get()):
            self.template_var.set("Custom")
        self._refresh_composition()

    def selected_sections(self) -> tuple[str, ...]:
        return tuple(
            key for key, _label in _REPORT_SECTIONS if self.section_vars[key].get()
        )

    def _refresh_composition(self) -> None:
        count = len(self.selected_sections())
        self.composition_var.set(
            f"{count} section{'s' if count != 1 else ''} selected"
            if count
            else "No report sections selected"
        )
        if self._summary_export_callback is not None:
            self.summary_export_button.configure(
                state="normal" if count else "disabled"
            )
        self._set_preview(self.build_selected_summary_markdown())

    def build_selected_summary_markdown(self) -> str:
        projected = reporting_status_projection(self._snapshot)
        plan = reporting_section_plan(self._snapshot)
        selected = self.selected_sections()
        lines = [
            f"# CleanroomX Report Summary — {projected['project_name']}",
            "",
            f"Template: {self.template_var.get()}",
            "",
            (
                "This selected summary presents current CleanroomX workstation state. "
                "It does not replace the canonical engineering dossier, diagnostics "
                "export, run bundle, or persisted verification evidence."
            ),
        ]
        if not selected:
            lines.extend(["", "No report sections selected."])
            return "\n".join(lines).rstrip() + "\n"

        for key in selected:
            section = plan[key]
            lines.extend(
                [
                    "",
                    f"## {section['label']}",
                    f"State: {str(section['state']).upper().replace('_', ' ')}",
                    str(section["detail"]),
                ]
            )
            if key == "project":
                lines.append(
                    f"Source binding: {projected['save_state'].upper()}"
                )
            elif not section["available"]:
                lines.append(
                    "Availability: not available from the current canonical project/session state."
                )

        lines.extend(
            [
                "",
                "## Publication readiness",
                (
                    "Project dossier: source project is saved."
                    if projected["save_state"] == "saved"
                    else "Project dossier: blocked until the project is explicitly saved."
                ),
                (
                    "Active-analysis exports: current session result is available."
                    if plan["analysis"]["available"]
                    else "Active-analysis exports: unavailable until an analysis has a current session result."
                ),
                (
                    "Missing data remains missing; this summary does not synthesize "
                    "engineering values or acceptance verdicts."
                ),
            ]
        )
        return "\n".join(lines).rstrip() + "\n"

    def _set_preview(self, value: str) -> None:
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", value)
        self.preview.configure(state="disabled")

    def apply_theme(self, theme: str) -> None:
        palette = theme_palette(theme)
        self.preview.configure(
            background=palette["field"],
            foreground=palette["field_text"],
            insertbackground=palette["text"],
            selectbackground=palette["selection"],
            selectforeground=palette["selection_text"],
        )
