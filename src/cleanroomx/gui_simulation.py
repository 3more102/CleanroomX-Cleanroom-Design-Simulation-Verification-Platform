from __future__ import annotations

from typing import Any, Callable

import tkinter as tk
from tkinter import ttk


class SimulationWorkspace(ttk.Frame):
    """Control/status surface for the existing CleanroomX analysis runner."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_run: Callable[[], None],
        on_cancel: Callable[[], None],
        on_validate: Callable[[], None],
        on_open_inputs: Callable[[], None],
        on_open_results: Callable[[], None],
    ) -> None:
        super().__init__(master, padding=(14, 12))
        self._on_run = on_run
        self._on_cancel = on_cancel

        self.analysis_var = tk.StringVar(value="No active analysis")
        self.kind_var = tk.StringVar(value="—")
        self.state_var = tk.StringVar(value="NOT CONFIGURED")
        self.execution_var = tk.StringVar(value="Select or configure an analysis to run.")
        self.result_var = tk.StringVar(value="No session result")
        self.diagnostics_var = tk.StringVar(value="Diagnostics: —")
        self.input_var = tk.StringVar(value="Input fields: —")

        header = ttk.Frame(self, style="CX.Surface.TFrame", padding=(12, 9))
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(
            header,
            text="SIMULATION / ANALYSIS",
            style="CX.Section.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            header,
            textvariable=self.analysis_var,
            style="CX.ViewTitle.TLabel",
        ).pack(side="left", anchor="w", pady=(2, 0))
        self.state_badge = ttk.Label(
            header,
            textvariable=self.state_var,
            style="CX.Status.Unknown.TLabel",
        )
        self.state_badge.pack(side="right", padx=(10, 0))

        controls = ttk.Frame(self, style="CX.Toolbar.TFrame", padding=(8, 5))
        controls.pack(fill="x", pady=(0, 8))
        ttk.Label(controls, text="SOLVER", style="CX.Toolbar.TLabel").pack(
            side="left", padx=(0, 7)
        )
        self.run_button = ttk.Button(
            controls,
            text="▶ Run Active",
            style="CX.Primary.TButton",
            command=on_run,
        )
        self.run_button.pack(side="left", padx=2)
        self.cancel_button = ttk.Button(
            controls,
            text="Abandon",
            style="CX.Danger.TButton",
            command=on_cancel,
            state="disabled",
        )
        self.cancel_button.pack(side="left", padx=2)
        ttk.Button(
            controls,
            text="Validate Inputs",
            style="CX.Compact.TButton",
            command=on_validate,
        ).pack(side="left", padx=(8, 2))
        ttk.Button(
            controls,
            text="Inputs",
            style="CX.Compact.TButton",
            command=on_open_inputs,
        ).pack(side="left", padx=2)
        ttk.Button(
            controls,
            text="Results",
            style="CX.Compact.TButton",
            command=on_open_results,
        ).pack(side="left", padx=2)

        execution = ttk.Frame(self, style="CX.Raised.TFrame", padding=(12, 10))
        execution.pack(fill="x", pady=(0, 8))
        execution.columnconfigure(1, weight=1)
        ttk.Label(execution, text="EXECUTION", style="CX.Section.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 5)
        )
        ttk.Label(
            execution,
            textvariable=self.execution_var,
            style="CX.Secondary.TLabel",
        ).grid(row=0, column=1, sticky="e", pady=(0, 5))
        self.progress = ttk.Progressbar(execution, mode="indeterminate")
        self.progress.grid(row=1, column=0, columnspan=2, sticky="ew")
        ttk.Label(
            execution,
            text=(
                "CleanroomX uses an indeterminate indicator when backend progress "
                "is not measurable; no synthetic percentage is displayed."
            ),
            style="CX.Muted.TLabel",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(5, 0))

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True)

        configuration = ttk.Frame(body, style="CX.Panel.TFrame", padding=(10, 8))
        results = ttk.Frame(body, style="CX.Panel.TFrame", padding=(10, 8))
        body.add(configuration, weight=2)
        body.add(results, weight=3)

        ttk.Label(
            configuration,
            text="ACTIVE CONFIGURATION",
            style="CX.PanelHeader.TLabel",
        ).pack(anchor="w", pady=(0, 8))
        self._kv(configuration, "Backend / kind", self.kind_var)
        self._kv(configuration, "Input summary", self.input_var)
        ttk.Label(
            configuration,
            text=(
                "Detailed parameters remain in the canonical Structured / JSON "
                "input workspace so this control surface does not duplicate edit state."
            ),
            style="CX.Muted.TLabel",
            wraplength=360,
            justify="left",
        ).pack(anchor="w", pady=(10, 0))

        ttk.Label(
            results,
            text="RESULT SUMMARY",
            style="CX.PanelHeader.TLabel",
        ).pack(anchor="w", pady=(0, 8))
        ttk.Label(
            results,
            textvariable=self.result_var,
            style="CX.ViewTitle.TLabel",
            wraplength=560,
            justify="left",
        ).pack(anchor="w")
        ttk.Label(
            results,
            textvariable=self.diagnostics_var,
            style="CX.Secondary.TLabel",
        ).pack(anchor="w", pady=(7, 0))
        ttk.Label(
            results,
            text=(
                "Calculated results, configured requirements, and compliance "
                "verdicts remain separate artifacts in Results, Verification, and Evidence."
            ),
            style="CX.Muted.TLabel",
            wraplength=560,
            justify="left",
        ).pack(anchor="w", pady=(10, 0))

    @staticmethod
    def _kv(master: ttk.Frame, label: str, variable: tk.StringVar) -> None:
        row = ttk.Frame(master)
        row.pack(fill="x", pady=3)
        ttk.Label(row, text=label, style="CX.Muted.TLabel").pack(side="left")
        ttk.Label(row, textvariable=variable).pack(side="right")

    @staticmethod
    def _field_count(value: Any) -> int:
        return len(value) if isinstance(value, dict) else 0

    @staticmethod
    def _diagnostic_count(value: Any) -> int:
        if isinstance(value, dict):
            for key in ("issues", "diagnostics", "findings"):
                candidate = value.get(key)
                if isinstance(candidate, list):
                    return len(candidate)
            return len(value)
        if isinstance(value, list):
            return len(value)
        return 0

    def set_context(
        self,
        *,
        analysis_name: str | None,
        analysis_kind: str | None,
        analysis_input: Any = None,
        running: bool,
        last_run: Any = None,
        error: str | None = None,
    ) -> None:
        if not analysis_name:
            self.analysis_var.set("No active analysis")
            self.kind_var.set("—")
            self.input_var.set("Input fields: —")
            self.state_var.set("NOT CONFIGURED")
            self.state_badge.configure(style="CX.Status.Unknown.TLabel")
            self.execution_var.set("Select or configure an analysis to run.")
            self.result_var.set("No session result")
            self.diagnostics_var.set("Diagnostics: —")
            self.run_button.configure(state="disabled")
            self.cancel_button.configure(state="disabled")
            self.progress.stop()
            return

        self.analysis_var.set(analysis_name)
        self.kind_var.set(analysis_kind or "unknown")
        self.input_var.set(f"Input fields: {self._field_count(analysis_input)}")
        self.run_button.configure(state="disabled" if running else "normal")
        self.cancel_button.configure(state="normal" if running else "disabled")

        if running:
            self.state_var.set("RUNNING")
            self.state_badge.configure(style="CX.Status.Running.TLabel")
            self.execution_var.set("Backend solver is executing…")
            self.progress.start(12)
        else:
            self.progress.stop()
            if error:
                self.state_var.set("FAILED")
                self.state_badge.configure(style="CX.Status.Fail.TLabel")
                self.execution_var.set("Last execution failed")
                self.result_var.set(error)
                self.diagnostics_var.set("Diagnostics: execution error")
                return
            if last_run is None:
                self.state_var.set("READY")
                self.state_badge.configure(style="CX.Status.Unknown.TLabel")
                self.execution_var.set("Ready to run active analysis")
                self.result_var.set("No session result for the active analysis")
                self.diagnostics_var.set("Diagnostics: —")
                return

            status = str(getattr(last_run, "status", "unknown") or "unknown")
            self.state_var.set(status.upper())
            style = (
                "CX.Status.Fail.TLabel"
                if status.casefold() in {"fail", "failed", "error"}
                else "CX.Status.Warning.TLabel"
                if status.casefold() in {"warning", "warn"}
                else "CX.Status.Pass.TLabel"
                if status.casefold() in {"pass", "passed", "ok", "success"}
                else "CX.Status.Verified.TLabel"
            )
            self.state_badge.configure(style=style)
            self.execution_var.set("Last execution completed")
            title = str(getattr(last_run, "title", "") or analysis_name)
            self.result_var.set(f"{title} · status: {status}")
            self.diagnostics_var.set(
                f"Diagnostics: {self._diagnostic_count(getattr(last_run, 'diagnostics', None))}"
            )
