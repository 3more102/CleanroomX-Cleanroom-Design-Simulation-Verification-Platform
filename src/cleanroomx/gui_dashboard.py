from __future__ import annotations

from collections.abc import Callable
from typing import Any

import tkinter as tk
from tkinter import ttk


class EngineeringDashboard(ttk.Frame):
    """Actionable project-health dashboard backed by existing engineering services."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        open_design: Callable[[], None],
        open_simulation: Callable[[], None],
        open_verification: Callable[[], None],
        open_evidence: Callable[[], None],
        open_reporting: Callable[[], None],
    ) -> None:
        super().__init__(master, padding=(12, 10))
        self._vars: dict[str, tk.StringVar] = {
            "project": tk.StringVar(value="Project health unavailable"),
            "issues": tk.StringVar(value="Diagnostics: not evaluated"),
            "verification": tk.StringVar(value="Verification: not evaluated"),
            "evidence": tk.StringVar(value="Evidence: not evaluated"),
            "model": tk.StringVar(value="Model: not loaded"),
            "analysis": tk.StringVar(value="Analysis result: none"),
        }

        header = ttk.Frame(self, style="CX.PanelHeader.TFrame")
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(
            header,
            text="PROJECT OVERVIEW",
            style="CX.PanelHeader.TLabel",
        ).pack(side="left")
        ttk.Label(
            header,
            text="Actionable engineering health · no inferred values",
            style="CX.Section.TLabel",
        ).pack(side="right")

        ttk.Label(
            self,
            textvariable=self._vars["project"],
            style="CX.ViewTitle.TLabel",
        ).pack(fill="x", pady=(0, 9))

        cards = ttk.Frame(self)
        cards.pack(fill="both", expand=True)
        for column in range(2):
            cards.columnconfigure(column, weight=1)
        for row in range(3):
            cards.rowconfigure(row, weight=1)

        self._card(
            cards,
            row=0,
            column=0,
            title="Diagnostics",
            variable=self._vars["issues"],
            action_text="Open Verification",
            action=open_verification,
        )
        self._card(
            cards,
            row=0,
            column=1,
            title="Verification currency",
            variable=self._vars["verification"],
            action_text="Inspect Verification",
            action=open_verification,
        )
        self._card(
            cards,
            row=1,
            column=0,
            title="Evidence / ProofGraph",
            variable=self._vars["evidence"],
            action_text="Open Evidence",
            action=open_evidence,
        )
        self._card(
            cards,
            row=1,
            column=1,
            title="Model",
            variable=self._vars["model"],
            action_text="Open Design",
            action=open_design,
        )
        self._card(
            cards,
            row=2,
            column=0,
            title="Analysis",
            variable=self._vars["analysis"],
            action_text="Open Simulation",
            action=open_simulation,
        )
        self._card(
            cards,
            row=2,
            column=1,
            title="Reporting",
            variable=tk.StringVar(
                value="Review current canonical report output and bound project dossier readiness."
            ),
            action_text="Open Reporting",
            action=open_reporting,
        )

    @staticmethod
    def _card(
        parent: ttk.Frame,
        *,
        row: int,
        column: int,
        title: str,
        variable: tk.StringVar,
        action_text: str,
        action: Callable[[], None],
    ) -> None:
        frame = ttk.LabelFrame(parent, text=title, padding=(12, 10))
        frame.grid(
            row=row,
            column=column,
            sticky="nsew",
            padx=(0, 5) if column == 0 else (5, 0),
            pady=5,
        )
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        ttk.Label(
            frame,
            textvariable=variable,
            justify="left",
            wraplength=520,
        ).grid(row=0, column=0, sticky="nw")
        ttk.Button(
            frame,
            text=action_text,
            style="CX.Compact.TButton",
            command=action,
        ).grid(row=1, column=0, sticky="e", pady=(10, 0))

    def set_snapshot(self, snapshot: dict[str, Any]) -> None:
        project_name = str(snapshot.get("project_name") or "Untitled Project")
        project_location = str(snapshot.get("project_location") or "Unsaved project")
        self._vars["project"].set(f"{project_name} · {project_location}")

        diagnostics = snapshot.get("diagnostics")
        if isinstance(diagnostics, dict):
            status = str(diagnostics.get("status") or "unknown").upper()
            errors = int(diagnostics.get("error_count", 0) or 0)
            warnings = int(diagnostics.get("warning_count", 0) or 0)
            info = int(diagnostics.get("info_count", 0) or 0)
            self._vars["issues"].set(
                f"{status} · {errors} error(s) · {warnings} warning(s) · {info} info"
            )
        else:
            self._vars["issues"].set("Diagnostics: unavailable")

        verification = snapshot.get("verification")
        if isinstance(verification, dict):
            configured = int(verification.get("configured_analysis_count", 0) or 0)
            current = int(verification.get("current_count", 0) or 0)
            stale = int(verification.get("stale_count", 0) or 0)
            not_verified = int(verification.get("not_verified_count", 0) or 0)
            self._vars["verification"].set(
                f"{current}/{configured} current · {stale} stale · "
                f"{not_verified} not verified"
            )
        else:
            self._vars["verification"].set("Verification currency: unavailable")

        retained = int(snapshot.get("retained_verification_records", 0) or 0)
        proofgraphs = int(snapshot.get("proofgraph_count", 0) or 0)
        self._vars["evidence"].set(
            f"{retained} retained verification run(s) · {proofgraphs} ProofGraph(s)"
        )

        rooms = int(snapshot.get("room_count", 0) or 0)
        devices = int(snapshot.get("device_count", 0) or 0)
        analyses = int(snapshot.get("analysis_count", 0) or 0)
        self._vars["model"].set(
            f"{rooms} room(s) · {devices} device(s) · {analyses} analysis definition(s)"
        )

        run = snapshot.get("current_run")
        if run is None:
            self._vars["analysis"].set("No current analysis result")
        else:
            title = str(getattr(run, "title", "") or "Current analysis")
            status = str(getattr(run, "status", "") or "complete")
            self._vars["analysis"].set(f"{title} · {status}")

    def value(self, key: str) -> str:
        variable = self._vars.get(key)
        return variable.get() if variable is not None else ""
