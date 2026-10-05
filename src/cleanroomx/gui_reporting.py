from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import ttk


class ReportingWorkspace(ttk.Frame):
    """Integrated report review/export surface over existing CleanroomX outputs."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        export_dossier: Callable[[], None],
        export_result_json: Callable[[], None],
        export_run_bundle: Callable[[], None],
        export_markdown: Callable[[], None],
        export_html: Callable[[], None],
        status_setter: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(master, padding=(10, 8))
        self._status_setter = status_setter or (lambda _message: None)

        self.project_var = tk.StringVar(value="Project: —")
        self.source_var = tk.StringVar(value="Source: unsaved")
        self.dossier_var = tk.StringVar(value="Project dossier: save project first")
        self.run_var = tk.StringVar(value="Analysis report: no current result")

        header = ttk.Frame(self, style="CX.PanelHeader.TFrame")
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(
            header,
            text="REPORTING WORKSPACE",
            style="CX.PanelHeader.TLabel",
        ).pack(side="left")
        ttk.Label(
            header,
            text="Saved-source traceability + current analysis outputs",
            style="CX.Section.TLabel",
        ).pack(side="right")

        summary = ttk.LabelFrame(self, text="Report readiness", padding=(10, 8))
        summary.pack(fill="x", pady=(0, 8))
        ttk.Label(summary, textvariable=self.project_var).grid(
            row=0, column=0, sticky="w", padx=(0, 16), pady=2
        )
        ttk.Label(summary, textvariable=self.source_var).grid(
            row=1, column=0, sticky="w", padx=(0, 16), pady=2
        )
        ttk.Label(summary, textvariable=self.dossier_var).grid(
            row=0, column=1, sticky="w", padx=(0, 16), pady=2
        )
        ttk.Label(summary, textvariable=self.run_var).grid(
            row=1, column=1, sticky="w", padx=(0, 16), pady=2
        )
        summary.columnconfigure(0, weight=1)
        summary.columnconfigure(1, weight=1)

        actions = ttk.Frame(self, style="CX.Toolbar.TFrame", padding=(6, 4))
        actions.pack(fill="x", pady=(0, 8))
        self.dossier_button = ttk.Button(
            actions,
            text="Project Dossier…",
            style="CX.Primary.TButton",
            command=export_dossier,
        )
        self.dossier_button.pack(side="left", padx=2)
        self.markdown_button = ttk.Button(
            actions,
            text="Markdown…",
            command=export_markdown,
        )
        self.markdown_button.pack(side="left", padx=2)
        self.html_button = ttk.Button(
            actions,
            text="Portable HTML…",
            command=export_html,
        )
        self.html_button.pack(side="left", padx=2)
        self.result_button = ttk.Button(
            actions,
            text="Result JSON…",
            command=export_result_json,
        )
        self.result_button.pack(side="left", padx=(10, 2))
        self.bundle_button = ttk.Button(
            actions,
            text="Run Bundle…",
            command=export_run_bundle,
        )
        self.bundle_button.pack(side="left", padx=2)

        preview_frame = ttk.LabelFrame(
            self,
            text="Current analysis report preview",
            padding=(6, 6),
        )
        preview_frame.pack(fill="both", expand=True)
        self.preview = tk.Text(
            preview_frame,
            wrap="word",
            state="disabled",
            borderwidth=0,
        )
        yscroll = ttk.Scrollbar(
            preview_frame,
            orient="vertical",
            command=self.preview.yview,
        )
        self.preview.configure(yscrollcommand=yscroll.set)
        self.preview.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")

        footer = ttk.Label(
            self,
            text=(
                "Preview content comes from the canonical completed analysis report. "
                "Project dossiers are generated only by the existing saved-project "
                "dossier service so source SHA-256 traceability is preserved."
            ),
            wraplength=1000,
            justify="left",
            style="CX.Section.TLabel",
        )
        footer.pack(fill="x", pady=(7, 0))

        self.set_context(
            project_name="Untitled Project",
            project_path=None,
            unsaved_changes=False,
            run=None,
        )

    def set_context(
        self,
        *,
        project_name: str,
        project_path: str | Path | None,
        unsaved_changes: bool,
        run: Any | None,
    ) -> None:
        path = Path(project_path) if project_path is not None else None
        self.project_var.set(f"Project: {project_name or 'Untitled Project'}")
        self.source_var.set(
            f"Source: {path}"
            if path is not None
            else "Source: unsaved project"
        )

        dossier_ready = path is not None and not unsaved_changes
        if path is None:
            dossier_text = "Project dossier: save project first"
        elif unsaved_changes:
            dossier_text = "Project dossier: save changes first"
        else:
            dossier_text = "Project dossier: ready · bound to saved project bytes"
        self.dossier_var.set(dossier_text)
        self.dossier_button.configure(state="normal" if dossier_ready else "disabled")

        run_ready = run is not None
        for button in (
            self.markdown_button,
            self.html_button,
            self.result_button,
            self.bundle_button,
        ):
            button.configure(state="normal" if run_ready else "disabled")

        if run_ready:
            title = str(getattr(run, "title", "") or "Current analysis")
            status = str(getattr(run, "status", "") or "complete")
            self.run_var.set(f"Analysis report: {title} · {status}")
            report = str(getattr(run, "markdown", "") or "")
            preview_text = report or "The current analysis did not produce a Markdown report."
        else:
            self.run_var.set("Analysis report: no current result")
            preview_text = (
                "No current analysis report is available. Run the selected analysis "
                "to populate this preview and enable result/report exports."
            )

        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", preview_text)
        self.preview.configure(state="disabled")

    def apply_theme(self, palette: dict[str, str]) -> None:
        self.preview.configure(
            background=palette["field"],
            foreground=palette["field_text"],
            insertbackground=palette["text"],
            selectbackground=palette["selection"],
            selectforeground=palette["selection_text"],
        )
