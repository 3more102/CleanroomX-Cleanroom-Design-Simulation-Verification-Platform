from __future__ import annotations

from typing import Any

import tkinter as tk
from tkinter import ttk

from .gui_theme import engineering_status_style


class ProjectDashboard(ttk.Frame):
    """Dense project-health dashboard derived only from canonical app state."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, padding=(14, 12))
        self._vars = {
            "project": tk.StringVar(value="Untitled"),
            "location": tk.StringVar(value="Unsaved project"),
            "diagnostics": tk.StringVar(value="NOT CHECKED"),
            "diagnostic_detail": tk.StringVar(value="No diagnostics evaluated"),
            "analyses": tk.StringVar(value="0 configured"),
            "verification": tk.StringVar(value="NOT CHECKED"),
            "verification_detail": tk.StringVar(value="No verification currency"),
            "evidence": tk.StringVar(value="0 retained records"),
            "model": tk.StringVar(value="READY"),
        }

        header = ttk.Frame(self, style="CX.PanelHeader.TFrame")
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(
            header,
            text="PROJECT HEALTH",
            style="CX.PanelHeader.TLabel",
        ).pack(side="left")
        self.model_badge = ttk.Label(
            header,
            textvariable=self._vars["model"],
            style="CX.Badge.Unknown.TLabel",
        )
        self.model_badge.pack(side="right")

        identity = ttk.LabelFrame(
            self,
            text="Active project",
            padding=(12, 9),
            style="CX.Card.TLabelframe",
        )
        identity.pack(fill="x", pady=(0, 10))
        ttk.Label(
            identity,
            textvariable=self._vars["project"],
            style="CX.ViewTitle.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            identity,
            textvariable=self._vars["location"],
            style="CX.Muted.TLabel",
        ).pack(anchor="w", pady=(3, 0))

        grid = ttk.Frame(self)
        grid.pack(fill="both", expand=True)
        for col in range(2):
            grid.columnconfigure(col, weight=1, uniform="dashboard")
        for row in range(2):
            grid.rowconfigure(row, weight=1)

        self.diagnostics_badge = self._card(
            grid,
            0,
            0,
            "DIAGNOSTICS / DRC",
            "diagnostics",
            "diagnostic_detail",
        )
        self.verification_badge = self._card(
            grid,
            0,
            1,
            "VERIFICATION",
            "verification",
            "verification_detail",
        )
        self._metric_card(
            grid,
            1,
            0,
            "ANALYSIS WORKSPACE",
            "analyses",
            "Configured solver / verification analyses",
        )
        self._metric_card(
            grid,
            1,
            1,
            "EVIDENCE / TRACEABILITY",
            "evidence",
            "Persisted verification evidence records",
        )

        footer = ttk.Frame(self, style="CX.Toolbar.TFrame", padding=(8, 5))
        footer.pack(fill="x", pady=(10, 0))
        ttk.Label(
            footer,
            text=(
                "Dashboard values are projections of project diagnostics, "
                "verification currency, configured analyses, and retained evidence."
            ),
            style="CX.Muted.TLabel",
        ).pack(anchor="w")

    def _card(
        self,
        parent: tk.Misc,
        row: int,
        column: int,
        title: str,
        state_key: str,
        detail_key: str,
    ) -> ttk.Label:
        card = ttk.LabelFrame(
            parent,
            text=title,
            padding=(12, 10),
            style="CX.Card.TLabelframe",
        )
        card.grid(
            row=row,
            column=column,
            sticky="nsew",
            padx=(0 if column == 0 else 5, 5 if column == 0 else 0),
            pady=(0 if row == 0 else 5, 5 if row == 0 else 0),
        )
        badge = ttk.Label(
            card,
            textvariable=self._vars[state_key],
            style="CX.Badge.Unknown.TLabel",
        )
        badge.pack(anchor="w")
        ttk.Label(
            card,
            textvariable=self._vars[detail_key],
            style="CX.Muted.TLabel",
            wraplength=430,
            justify="left",
        ).pack(anchor="w", pady=(8, 0))
        return badge

    def _metric_card(
        self,
        parent: tk.Misc,
        row: int,
        column: int,
        title: str,
        value_key: str,
        detail: str,
    ) -> None:
        card = ttk.LabelFrame(
            parent,
            text=title,
            padding=(12, 10),
            style="CX.Card.TLabelframe",
        )
        card.grid(
            row=row,
            column=column,
            sticky="nsew",
            padx=(0 if column == 0 else 5, 5 if column == 0 else 0),
            pady=(0 if row == 0 else 5, 5 if row == 0 else 0),
        )
        ttk.Label(
            card,
            textvariable=self._vars[value_key],
            style="CX.ViewTitle.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            card,
            text=detail,
            style="CX.Muted.TLabel",
            wraplength=430,
            justify="left",
        ).pack(anchor="w", pady=(8, 0))

    def set_snapshot(self, snapshot: dict[str, Any]) -> None:
        project_name = str(snapshot.get("project_name") or "Untitled")
        location = str(snapshot.get("location") or "Unsaved project")
        analyses = max(0, int(snapshot.get("analysis_count") or 0))
        evidence = max(0, int(snapshot.get("evidence_count") or 0))

        errors = max(0, int(snapshot.get("diagnostic_errors") or 0))
        warnings = max(0, int(snapshot.get("diagnostic_warnings") or 0))
        diagnostic_status = str(snapshot.get("diagnostic_status") or "not checked")
        if errors:
            diagnostic_state = "FAIL"
        elif warnings:
            diagnostic_state = "WARNING"
        elif diagnostic_status.casefold() in {"pass", "passed", "ok", "complete"}:
            diagnostic_state = "PASS"
        else:
            diagnostic_state = diagnostic_status.upper()

        current = max(0, int(snapshot.get("verification_current") or 0))
        stale = max(0, int(snapshot.get("verification_stale") or 0))
        not_verified = max(0, int(snapshot.get("verification_not_verified") or 0))
        configured = max(0, int(snapshot.get("verification_configured") or analyses))
        if configured == 0:
            verification_state = "NOT CHECKED"
        elif stale or not_verified:
            verification_state = "STALE" if stale else "UNVERIFIED"
        elif current == configured:
            verification_state = "VERIFIED"
        else:
            verification_state = "INCOMPLETE"

        model_state = str(snapshot.get("model_state") or "ready").upper()
        self._vars["project"].set(project_name)
        self._vars["location"].set(location)
        self._vars["analyses"].set(f"{analyses} configured")
        self._vars["evidence"].set(
            f"{evidence} retained record{'s' if evidence != 1 else ''}"
        )
        self._vars["diagnostics"].set(diagnostic_state)
        self._vars["diagnostic_detail"].set(
            f"{errors} error(s) · {warnings} warning(s)"
        )
        self._vars["verification"].set(verification_state)
        self._vars["verification_detail"].set(
            f"{current}/{configured} current · {stale} stale · "
            f"{not_verified} not verified"
        )
        self._vars["model"].set(model_state)

        self.diagnostics_badge.configure(
            style=engineering_status_style(diagnostic_state)
        )
        self.verification_badge.configure(
            style=engineering_status_style(verification_state)
        )
        self.model_badge.configure(style=engineering_status_style(model_state))
