from __future__ import annotations

from typing import Any, Callable

import tkinter as tk
from tkinter import ttk

from .gui_theme import status_style_name


class ReportingWorkspace(ttk.Frame):
    """Central reporting surface over existing CleanroomX export workflows."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_export_dossier: Callable[[], None],
        on_export_markdown: Callable[[], None],
        on_export_html: Callable[[], None],
        on_export_result_json: Callable[[], None],
        on_export_run_bundle: Callable[[], None],
    ) -> None:
        super().__init__(master, padding=(14, 12))
        self._on_export_dossier = on_export_dossier

        self.project_var = tk.StringVar(value="No project")
        self.project_state_var = tk.StringVar(value="NOT SAVED")
        self.run_state_var = tk.StringVar(value="NO FRESH RUN")
        self.report_state_var = tk.StringVar(value="NOT AVAILABLE")
        self.preview_state_var = tk.StringVar(
            value="Run the active analysis to preview its canonical report."
        )

        header = ttk.Frame(self, style="CX.PanelHeader.TFrame", padding=(10, 7))
        header.pack(fill="x", pady=(0, 8))
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header,
            text="REPORTING / PUBLICATION",
            style="CX.PanelHeader.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            textvariable=self.project_var,
            style="CX.PanelHeader.TLabel",
        ).grid(row=0, column=1, sticky="e", padx=(12, 8))
        self.project_state_badge = ttk.Label(
            header,
            textvariable=self.project_state_var,
            style="CX.Status.Neutral.TLabel",
        )
        self.project_state_badge.grid(row=0, column=2, sticky="e")

        actions = ttk.Frame(self, style="CX.Toolbar.TFrame", padding=(8, 5))
        actions.pack(fill="x", pady=(0, 8))
        ttk.Label(actions, text="PROJECT", style="CX.ToolbarSection.TLabel").pack(
            side="left", padx=(0, 8)
        )
        self.dossier_button = ttk.Button(
            actions,
            text="Export Engineering Dossier…",
            style="CX.Primary.TButton",
            command=on_export_dossier,
            state="disabled",
        )
        self.dossier_button.pack(side="left", padx=2)
        ttk.Separator(actions, orient="vertical").pack(side="left", fill="y", padx=7)
        ttk.Label(actions, text="CURRENT RUN", style="CX.ToolbarSection.TLabel").pack(
            side="left", padx=(0, 8)
        )
        self.markdown_button = ttk.Button(
            actions,
            text="Markdown…",
            style="CX.Compact.TButton",
            command=on_export_markdown,
            state="disabled",
        )
        self.markdown_button.pack(side="left", padx=2)
        self.html_button = ttk.Button(
            actions,
            text="Portable HTML…",
            style="CX.Compact.TButton",
            command=on_export_html,
            state="disabled",
        )
        self.html_button.pack(side="left", padx=2)
        self.result_button = ttk.Button(
            actions,
            text="Result JSON…",
            style="CX.Compact.TButton",
            command=on_export_result_json,
            state="disabled",
        )
        self.result_button.pack(side="left", padx=2)
        self.bundle_button = ttk.Button(
            actions,
            text="Run Bundle…",
            style="CX.Compact.TButton",
            command=on_export_run_bundle,
            state="disabled",
        )
        self.bundle_button.pack(side="left", padx=2)

        status = ttk.Frame(self, style="CX.SubtlePanel.TFrame", padding=(10, 8))
        status.pack(fill="x", pady=(0, 8))
        status.columnconfigure(1, weight=1)
        ttk.Label(status, text="PROJECT PUBLICATION", style="CX.SurfaceSection.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 8)
        )
        ttk.Label(
            status,
            textvariable=self.project_state_var,
            style="CX.SurfaceSecondary.TLabel",
        ).grid(row=0, column=1, sticky="w")
        ttk.Label(status, text="ANALYSIS REPORT", style="CX.SurfaceSection.TLabel").grid(
            row=1, column=0, sticky="w", padx=(0, 8), pady=(5, 0)
        )
        self.run_state_label = ttk.Label(
            status,
            textvariable=self.run_state_var,
            style="CX.Status.Neutral.TLabel",
        )
        self.run_state_label.grid(row=1, column=1, sticky="w", pady=(5, 0))
        ttk.Label(status, text="PREVIEW", style="CX.SurfaceSection.TLabel").grid(
            row=2, column=0, sticky="w", padx=(0, 8), pady=(5, 0)
        )
        ttk.Label(
            status,
            textvariable=self.preview_state_var,
            style="CX.SurfaceMuted.TLabel",
        ).grid(row=2, column=1, sticky="w", pady=(5, 0))

        preview_host = ttk.Frame(self, style="CX.Panel.TFrame", padding=(8, 7))
        preview_host.pack(fill="both", expand=True)
        ttk.Label(
            preview_host,
            text="CANONICAL ANALYSIS REPORT PREVIEW",
            style="CX.PanelSection.TLabel",
        ).pack(anchor="w", pady=(0, 6))
        body = ttk.Frame(preview_host)
        body.pack(fill="both", expand=True)
        self.preview = tk.Text(
            body,
            wrap="word",
            state="disabled",
            borderwidth=0,
            undo=False,
        )
        scroll = ttk.Scrollbar(body, orient="vertical", command=self.preview.yview)
        self.preview.configure(yscrollcommand=scroll.set)
        self.preview.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def set_context(
        self,
        *,
        project_name: str,
        project_saved: bool,
        project_dirty: bool,
        run: Any = None,
    ) -> None:
        self.project_var.set(str(project_name or "Untitled project"))

        dossier_ready = bool(project_saved and not project_dirty)
        if not project_saved:
            project_state = "SAVE REQUIRED"
            project_style = "warning"
        elif project_dirty:
            project_state = "UNSAVED CHANGES"
            project_style = "warning"
        else:
            project_state = "SAVED REVISION READY"
            project_style = "pass"
        self.project_state_var.set(project_state)
        self.project_state_badge.configure(style=status_style_name(project_style))
        self.dossier_button.configure(state="normal" if dossier_ready else "disabled")

        has_run = run is not None
        for button in (
            self.markdown_button,
            self.html_button,
            self.result_button,
            self.bundle_button,
        ):
            button.configure(state="normal" if has_run else "disabled")

        if not has_run:
            self.run_state_var.set("NO FRESH RUN")
            self.run_state_label.configure(style="CX.Status.Neutral.TLabel")
            self.report_state_var.set("NOT AVAILABLE")
            self.preview_state_var.set(
                "Run the active analysis to preview its canonical report."
            )
            self._set_preview(
                "No fresh analysis report is available.\n\n"
                "CleanroomX will not synthesize a report from missing or stale results."
            )
            return

        status = str(getattr(run, "status", None) or "completed").strip().lower()
        title = str(getattr(run, "title", None) or "Analysis")
        markdown = str(getattr(run, "markdown", None) or "")
        self.run_state_var.set(f"{status.upper()} · {title}")
        self.run_state_label.configure(style=status_style_name(status))
        self.report_state_var.set("AVAILABLE" if markdown else "EMPTY")
        if markdown:
            self.preview_state_var.set(
                "Preview reflects the current fresh run report exactly."
            )
            self._set_preview(markdown)
        else:
            self.preview_state_var.set(
                "The current run did not provide Markdown report content."
            )
            self._set_preview("The current run contains no Markdown report content.")

    def _set_preview(self, value: str) -> None:
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", str(value))
        self.preview.configure(state="disabled")
