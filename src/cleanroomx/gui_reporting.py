from __future__ import annotations

from typing import Any, Callable

import tkinter as tk
from tkinter import ttk

from .gui_theme import status_style_name, theme_palette


def reporting_status_projection(snapshot: dict[str, Any] | None) -> dict[str, str]:
    """Project explicit project/report state without inventing report readiness."""
    data = snapshot if isinstance(snapshot, dict) else {}
    saved = data.get("saved") is True
    project_name = str(data.get("project_name") or "Untitled project")
    source = str(data.get("source") or "Unsaved project")

    diagnostics = data.get("diagnostics")
    diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
    diagnostic_state = str(diagnostics.get("status") or "not checked")

    verification = data.get("verification")
    verification = verification if isinstance(verification, dict) else {}
    configured = int(verification.get("configured_analysis_count") or 0)
    current = int(verification.get("current_count") or 0)
    stale = int(verification.get("stale_count") or 0)
    not_verified = int(verification.get("not_verified_count") or 0)
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
        verification_detail = f"{not_verified} not verified · {current}/{configured} current"

    last_run = data.get("last_run")
    if isinstance(last_run, dict):
        analysis_state = str(last_run.get("status") or "unknown")
        analysis_detail = str(last_run.get("title") or "Latest analysis")
    else:
        analysis_state = "not run"
        analysis_detail = "No current-session analysis result"

    records = int(data.get("evidence_record_count") or 0)
    graphs = int(data.get("proofgraph_count") or 0)

    return {
        "project_name": project_name,
        "source": source,
        "save_state": "saved" if saved else "unsaved",
        "diagnostic_state": diagnostic_state,
        "verification_state": verification_state,
        "verification_detail": verification_detail,
        "analysis_state": analysis_state,
        "analysis_detail": analysis_detail,
        "evidence_detail": f"{records} verification records · {graphs} ProofGraphs",
    }


class ReportingWorkspace(ttk.Frame):
    """Integrated export control surface over existing canonical report generators."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_preview_dossier: Callable[[], Any],
        on_export_dossier: Callable[[], Any],
        on_export_diagnostics: Callable[[], Any],
        on_export_result_json: Callable[[], Any],
        on_export_run_bundle: Callable[[], Any],
        on_export_markdown: Callable[[], Any],
        on_export_html: Callable[[], Any],
    ) -> None:
        super().__init__(master, padding=(14, 12))
        self.project_var = tk.StringVar(value="Untitled project")
        self.source_var = tk.StringVar(value="Unsaved project")
        self.save_var = tk.StringVar(value="UNSAVED")
        self.diagnostics_var = tk.StringVar(value="NOT CHECKED")
        self.verification_var = tk.StringVar(value="NOT CONFIGURED")
        self.analysis_var = tk.StringVar(value="NOT RUN")
        self.evidence_var = tk.StringVar(value="0 verification records · 0 ProofGraphs")

        header = ttk.Frame(self, style="CX.PanelHeader.TFrame", padding=(10, 7))
        header.pack(fill="x", pady=(0, 8))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="REPORTING / RELEASE", style="CX.PanelHeader.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(header, textvariable=self.project_var, style="CX.SurfaceSecondary.TLabel").grid(
            row=0, column=1, sticky="e", padx=(12, 8)
        )
        self.save_badge = ttk.Label(
            header,
            textvariable=self.save_var,
            style="CX.Status.Warning.TLabel",
        )
        self.save_badge.grid(row=0, column=2, sticky="e")

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True)

        status_frame = ttk.Frame(body, style="CX.Panel.TFrame", padding=(10, 9))
        exports_frame = ttk.Frame(body, style="CX.Panel.TFrame", padding=(10, 9))
        preview_frame = ttk.Frame(body, style="CX.Panel.TFrame", padding=(10, 9))
        body.add(status_frame, weight=2)
        body.add(exports_frame, weight=3)
        body.add(preview_frame, weight=4)

        ttk.Label(status_frame, text="RELEASE CONTEXT", style="CX.PanelSection.TLabel").pack(
            anchor="w", pady=(0, 8)
        )
        self._kv(status_frame, "Source", self.source_var)
        self._kv(status_frame, "Diagnostics", self.diagnostics_var)
        self._kv(status_frame, "Verification", self.verification_var)
        self._kv(status_frame, "Analysis", self.analysis_var)
        self._kv(status_frame, "Evidence", self.evidence_var)
        ttk.Label(
            status_frame,
            text=(
                "These labels report current application state only. They are not a "
                "regulatory approval, certification, commissioning, or release verdict."
            ),
            style="CX.PanelMuted.TLabel",
            wraplength=240,
            justify="left",
        ).pack(anchor="w", pady=(12, 0))

        ttk.Label(exports_frame, text="PROJECT-NATIVE OUTPUTS", style="CX.PanelSection.TLabel").pack(
            anchor="w", pady=(0, 8)
        )
        ttk.Button(
            exports_frame,
            text="Preview Engineering Dossier",
            style="CX.Primary.TButton",
            command=on_preview_dossier,
        ).pack(fill="x", pady=3)
        ttk.Button(
            exports_frame,
            text="Export Engineering Dossier…",
            style="CX.Compact.TButton",
            command=on_export_dossier,
        ).pack(fill="x", pady=3)
        ttk.Button(
            exports_frame,
            text="Export Project Diagnostics…",
            style="CX.Compact.TButton",
            command=on_export_diagnostics,
        ).pack(fill="x", pady=3)

        ttk.Separator(exports_frame, orient="horizontal").pack(fill="x", pady=10)
        ttk.Label(exports_frame, text="ACTIVE-ANALYSIS OUTPUTS", style="CX.PanelSection.TLabel").pack(
            anchor="w", pady=(0, 8)
        )
        for label, callback in (
            ("Result JSON…", on_export_result_json),
            ("Run Bundle JSON…", on_export_run_bundle),
            ("Report Markdown…", on_export_markdown),
            ("Portable HTML Report…", on_export_html),
        ):
            ttk.Button(
                exports_frame,
                text=label,
                style="CX.Compact.TButton",
                command=callback,
            ).pack(fill="x", pady=3)

        ttk.Label(preview_frame, text="REPORT PIPELINE", style="CX.PanelSection.TLabel").pack(
            anchor="w", pady=(0, 8)
        )
        self.preview = tk.Text(preview_frame, wrap="word", state="disabled")
        preview_scroll = ttk.Scrollbar(preview_frame, orient="vertical", command=self.preview.yview)
        self.preview.configure(yscrollcommand=preview_scroll.set)
        self.preview.pack(side="left", fill="both", expand=True)
        preview_scroll.pack(side="right", fill="y")
        self._set_preview(
            "No project state loaded.\n\n"
            "CleanroomX reporting uses existing canonical dossier, diagnostics, result, "
            "and portable-report generators; this workspace does not recalculate engineering values."
        )

    @staticmethod
    def _kv(master: ttk.Frame, label: str, variable: tk.StringVar) -> None:
        row = ttk.Frame(master, style="CX.Panel.TFrame")
        row.pack(fill="x", pady=4)
        ttk.Label(row, text=label, style="CX.PanelMuted.TLabel").pack(side="left")
        ttk.Label(row, textvariable=variable, style="CX.PanelSecondary.TLabel").pack(
            side="right", padx=(8, 0)
        )

    def refresh(self, snapshot: dict[str, Any] | None) -> None:
        projected = reporting_status_projection(snapshot)
        self.project_var.set(projected["project_name"])
        self.source_var.set(projected["source"])
        self.save_var.set(projected["save_state"].upper())
        self.save_badge.configure(style=status_style_name(projected["save_state"]))
        self.diagnostics_var.set(projected["diagnostic_state"].upper().replace("_", " "))
        self.verification_var.set(projected["verification_state"].upper().replace("_", " "))
        self.analysis_var.set(projected["analysis_state"].upper().replace("_", " "))
        self.evidence_var.set(projected["evidence_detail"])

        lines = [
            projected["project_name"],
            "",
            f"Source binding: {projected['save_state'].upper()}",
            f"Source: {projected['source']}",
            "",
            f"Project diagnostics: {projected['diagnostic_state'].upper()}",
            f"Verification currency: {projected['verification_state'].upper()}",
            f"  {projected['verification_detail']}",
            f"Latest session analysis: {projected['analysis_state'].upper()}",
            f"  {projected['analysis_detail']}",
            f"Retained evidence: {projected['evidence_detail']}",
            "",
            "Project engineering dossier",
            "  • Bound to exact saved project bytes by the existing backend exporter.",
            "  • Includes canonical diagnostics, verification currency/history, and evidence.",
            "",
            "Active-analysis reports",
            "  • Use the existing run result/report payload.",
            "  • No missing engineering value is silently converted to zero.",
        ]
        if projected["save_state"] != "saved":
            lines.extend(
                [
                    "",
                    "Project dossier export is expected to require an explicit save before publication.",
                ]
            )
        self._set_preview("\n".join(lines))

    def show_preview(self, title: str, value: str) -> None:
        heading = str(title or "Report preview").strip()
        body = str(value or "").rstrip()
        self._set_preview(f"{heading}\n{'=' * len(heading)}\n\n{body}\n")

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
