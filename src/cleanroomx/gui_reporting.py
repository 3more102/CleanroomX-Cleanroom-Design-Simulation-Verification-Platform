from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from typing import Any
import tkinter as tk
from tkinter import ttk

from .gui_theme import status_style_name, theme_palette


REPORT_PROJECT_DOSSIER = "project_dossier"
REPORT_PROJECT_DIAGNOSTICS = "project_diagnostics"
REPORT_CURRENT_ANALYSIS = "current_analysis"

REPORT_TYPES = (
    (REPORT_PROJECT_DOSSIER, "Project Engineering Dossier"),
    (REPORT_PROJECT_DIAGNOSTICS, "Project Diagnostics Report"),
    (REPORT_CURRENT_ANALYSIS, "Current Analysis Report"),
)


@dataclass(frozen=True)
class ReportPreview:
    report_type: str
    title: str
    content: str
    available: bool
    status: str = "ready"
    note: str = ""
    source: str = ""


def normalize_report_preview(value: Any, report_type: str) -> ReportPreview:
    if isinstance(value, ReportPreview):
        return value
    return ReportPreview(
        report_type=report_type,
        title="Report unavailable",
        content="",
        available=False,
        status="unavailable",
        note="The report provider did not return a valid preview.",
    )


def report_status_semantic(value: Any) -> str:
    token = str(value or "").strip().casefold().replace(" ", "_")
    if token in {"error", "fail", "failed"}:
        return "error"
    if token in {"warning", "warn", "stale", "completed_with_warning"}:
        return "warning"
    if token in {"pass", "passed", "success", "completed", "ready", "ok"}:
        return "pass"
    return "neutral"


class ReportingWorkspace(ttk.Frame):
    """Read-only report preview over authoritative CleanroomX report generators."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        preview_provider: Callable[[str], ReportPreview],
        export_callback: Callable[[str], None],
        status_setter: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(master)
        self._preview_provider = preview_provider
        self._export_callback = export_callback
        self._status_setter = status_setter or (lambda _message: None)
        self._theme_name = "dark"
        self._palette = theme_palette(self._theme_name)
        self._current_preview: ReportPreview | None = None

        self.report_type_var = tk.StringVar(value=REPORT_PROJECT_DOSSIER)
        self.title_var = tk.StringVar(value="Reporting workspace")
        self.state_var = tk.StringVar(value="Select a report and refresh preview")
        self.source_var = tk.StringVar(value="Source: —")
        self._label_to_key = {label: key for key, label in REPORT_TYPES}
        self._key_to_label = {key: label for key, label in REPORT_TYPES}
        self.report_label_var = tk.StringVar(
            value=self._key_to_label[REPORT_PROJECT_DOSSIER]
        )
        self._build()

    def _build(self) -> None:
        top = ttk.Frame(self, style="CX.Toolbar.TFrame", padding=(10, 7))
        top.pack(fill="x")

        ttk.Label(
            top,
            text="REPORTING WORKSPACE",
            style="CX.Section.TLabel",
        ).pack(side="left", padx=(0, 10))
        ttk.Label(top, text="Report").pack(side="left")
        picker = ttk.Combobox(
            top,
            textvariable=self.report_label_var,
            values=tuple(label for _key, label in REPORT_TYPES),
            state="readonly",
            width=30,
        )
        picker.pack(side="left", padx=(5, 8))
        picker.bind("<<ComboboxSelected>>", self._on_report_selected)

        ttk.Button(
            top,
            text="Refresh Preview",
            style="CX.Compact.TButton",
            command=self.refresh,
        ).pack(side="left", padx=2)
        self.export_button = ttk.Button(
            top,
            text="Export…",
            style="CX.Primary.TButton",
            command=self.export_current,
            state="disabled",
        )
        self.export_button.pack(side="left", padx=2)

        summary = ttk.Frame(
            self,
            style="CX.SubtlePanel.TFrame",
            padding=(10, 7),
        )
        summary.pack(fill="x", padx=8, pady=(6, 4))
        ttk.Label(
            summary,
            textvariable=self.title_var,
            style="CX.SurfaceSection.TLabel",
        ).pack(side="left")
        self.state_label = ttk.Label(
            summary,
            textvariable=self.state_var,
            style="CX.Status.Neutral.TLabel",
        )
        self.state_label.pack(side="right")

        source = ttk.Frame(
            self,
            style="CX.SubtlePanel.TFrame",
            padding=(10, 5),
        )
        source.pack(fill="x", padx=8, pady=(0, 5))
        ttk.Label(
            source,
            textvariable=self.source_var,
            style="CX.SurfaceMuted.TLabel",
        ).pack(side="left")

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.preview = tk.Text(
            body,
            wrap="word",
            state="disabled",
            borderwidth=0,
            padx=12,
            pady=10,
        )
        yscroll = ttk.Scrollbar(body, orient="vertical", command=self.preview.yview)
        xscroll = ttk.Scrollbar(body, orient="horizontal", command=self.preview.xview)
        self.preview.configure(
            yscrollcommand=yscroll.set,
            xscrollcommand=xscroll.set,
        )
        self.preview.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        self._render_empty(
            "Choose a report type and refresh the preview. "
            "CleanroomX displays only report content generated from current authoritative data."
        )

    def _on_report_selected(self, _event=None) -> None:
        key = self._label_to_key.get(
            self.report_label_var.get(),
            REPORT_PROJECT_DOSSIER,
        )
        self.report_type_var.set(key)
        self.refresh()

    def select_report(self, report_type: str, *, refresh: bool = True) -> None:
        key = (
            report_type
            if report_type in self._key_to_label
            else REPORT_PROJECT_DOSSIER
        )
        self.report_type_var.set(key)
        self.report_label_var.set(self._key_to_label[key])
        if refresh:
            self.refresh()

    def refresh(self) -> ReportPreview:
        report_type = self.report_type_var.get()
        try:
            preview = normalize_report_preview(
                self._preview_provider(report_type),
                report_type,
            )
        except Exception as exc:
            preview = ReportPreview(
                report_type=report_type,
                title=self._key_to_label.get(report_type, "Report"),
                content="",
                available=False,
                status="failed",
                note=str(exc),
            )

        self._current_preview = preview
        self.title_var.set(preview.title)
        self.source_var.set(
            f"Source: {preview.source}" if preview.source else "Source: —"
        )
        self.export_button.configure(
            state="normal" if preview.available else "disabled"
        )

        if preview.available:
            self.state_var.set(preview.status.replace("_", " ").upper())
            self.state_label.configure(
                style=status_style_name(report_status_semantic(preview.status))
            )
            text = preview.content
            if preview.note:
                text = f"{preview.note}\n\n{text}" if text else preview.note
            self._render_text(text)
            self._status_setter(f"Report preview ready: {preview.title}")
        else:
            self.state_var.set(
                preview.status.replace("_", " ").upper() or "UNAVAILABLE"
            )
            semantic = report_status_semantic(preview.status)
            self.state_label.configure(
                style=status_style_name(
                    semantic if semantic != "neutral" else "warning"
                )
            )
            self._render_empty(
                preview.note
                or "This report is not available for the current project state."
            )
            self._status_setter(f"Report unavailable: {preview.title}")
        return preview

    def export_current(self) -> None:
        preview = self._current_preview
        if preview is None or not preview.available:
            self._status_setter("Refresh an available report before exporting")
            return
        self._export_callback(preview.report_type)

    def _render_text(self, text: str) -> None:
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text or "")
        self.preview.configure(state="disabled")

    def _render_empty(self, message: str) -> None:
        self._render_text(
            "REPORT PREVIEW UNAVAILABLE\n\n" + str(message or "No report content.")
        )

    def apply_theme(self, value: Any) -> None:
        self._theme_name = str(value or "dark")
        self._palette = theme_palette(self._theme_name)
        self.preview.configure(
            background=self._palette["field"],
            foreground=self._palette["field_text"],
            insertbackground=self._palette["text"],
            selectbackground=self._palette["selection"],
            selectforeground=self._palette["selection_text"],
        )

    @property
    def current_preview(self) -> ReportPreview | None:
        return self._current_preview
