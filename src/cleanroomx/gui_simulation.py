from __future__ import annotations

from typing import Any, Callable

import tkinter as tk
from tkinter import ttk

from .gui_theme import attach_tooltip, status_style_name


def _diagnostic_count(value: Any) -> int:
    """Count explicit diagnostic records without interpreting their engineering meaning."""
    if isinstance(value, dict):
        for key in ("issues", "diagnostics", "findings"):
            candidate = value.get(key)
            if isinstance(candidate, (list, tuple)):
                return len(candidate)
        return len(value)
    if isinstance(value, (list, tuple)):
        return len(value)
    return 0


def _leaf_count(value: Any, *, limit: int = 5000) -> int:
    """Count scalar result leaves for presentation only, with a defensive cap."""
    count = 0
    stack = [value]
    while stack and count < limit:
        current = stack.pop()
        if isinstance(current, dict):
            stack.extend(current.values())
        elif isinstance(current, (list, tuple)):
            stack.extend(current)
        else:
            count += 1
    return count


def _explicit_convergence(value: Any) -> str:
    """Return only convergence state explicitly emitted by a backend result."""
    wanted = {"converged", "solver_converged", "convergence_status", "convergence"}
    stack: list[Any] = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key, item in current.items():
                if str(key).casefold() in wanted and not isinstance(item, (dict, list, tuple)):
                    if isinstance(item, bool):
                        return "CONVERGED" if item else "NOT CONVERGED"
                    text = str(item).strip()
                    if text:
                        return text.upper()
                if isinstance(item, (dict, list, tuple)):
                    stack.append(item)
        elif isinstance(current, (list, tuple)):
            stack.extend(current)
    return "NOT REPORTED"


class SimulationWorkspace(ttk.Frame):
    """Operator-facing control/status surface over the existing analysis runner."""

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
        self.input_var = tk.StringVar(value="0 top-level fields")
        self.state_var = tk.StringVar(value="NOT CONFIGURED")
        self.stage_var = tk.StringVar(value="Select or configure an analysis.")
        self.elapsed_var = tk.StringVar(value="—")
        self.result_var = tk.StringVar(value="No session result")
        self.result_fields_var = tk.StringVar(value="—")
        self.diagnostics_var = tk.StringVar(value="—")
        self.convergence_var = tk.StringVar(value="NOT REPORTED")
        self.plot_var = tk.StringVar(value="—")
        self.verification_var = tk.StringVar(value="Separate verification workspace")

        header = ttk.Frame(self, style="CX.PanelHeader.TFrame", padding=(10, 7))
        header.pack(fill="x", pady=(0, 8))
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header,
            text="SIMULATION / ANALYSIS",
            style="CX.PanelHeader.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            textvariable=self.analysis_var,
            style="CX.PanelHeader.TLabel",
        ).grid(row=0, column=1, sticky="e", padx=(12, 8))
        self.state_badge = ttk.Label(
            header,
            textvariable=self.state_var,
            style="CX.Status.Neutral.TLabel",
        )
        self.state_badge.grid(row=0, column=2, sticky="e")

        controls = ttk.Frame(self, style="CX.Toolbar.TFrame", padding=(8, 5))
        controls.pack(fill="x", pady=(0, 8))
        ttk.Label(
            controls,
            text="SOLVER",
            style="CX.ToolbarSection.TLabel",
        ).pack(side="left", padx=(0, 8))
        self.run_button = ttk.Button(
            controls,
            text="▶ Run Active",
            style="CX.Primary.TButton",
            command=on_run,
            state="disabled",
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
        ttk.Separator(controls, orient="vertical").pack(side="left", fill="y", padx=7)
        ttk.Button(
            controls,
            text="Validate Inputs",
            style="CX.Compact.TButton",
            command=on_validate,
        ).pack(side="left", padx=2)
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

        execution = ttk.Frame(self, style="CX.SubtlePanel.TFrame", padding=(10, 8))
        execution.pack(fill="x", pady=(0, 8))
        execution.columnconfigure(1, weight=1)
        ttk.Label(
            execution,
            text="EXECUTION STAGE",
            style="CX.SurfaceSection.TLabel",
        ).grid(row=0, column=0, sticky="w", padx=(0, 10))
        ttk.Label(
            execution,
            textvariable=self.stage_var,
            style="CX.SurfaceSecondary.TLabel",
        ).grid(row=0, column=1, sticky="w")
        ttk.Label(
            execution,
            textvariable=self.elapsed_var,
            style="CX.SurfaceMuted.TLabel",
            width=10,
            anchor="e",
        ).grid(row=0, column=2, sticky="e", padx=(8, 0))
        self.progress = ttk.Progressbar(
            execution,
            mode="indeterminate",
            style="CX.Simulation.Horizontal.TProgressbar",
        )
        self.progress.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        note = ttk.Label(
            execution,
            text=(
                "Backend progress is shown as indeterminate when no measurable progress "
                "signal exists; CleanroomX does not synthesize a percentage."
            ),
            style="CX.SurfaceMuted.TLabel",
        )
        note.grid(row=2, column=0, columnspan=3, sticky="w", pady=(5, 0))
        attach_tooltip(
            self.progress,
            "Indeterminate activity means the selected backend does not expose a measurable progress percentage.",
        )

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True)

        configuration = ttk.Frame(body, style="CX.Panel.TFrame", padding=(10, 9))
        execution_summary = ttk.Frame(body, style="CX.Panel.TFrame", padding=(10, 9))
        result = ttk.Frame(body, style="CX.Panel.TFrame", padding=(10, 9))
        body.add(configuration, weight=2)
        body.add(execution_summary, weight=2)
        body.add(result, weight=3)

        ttk.Label(
            configuration,
            text="ACTIVE CONFIGURATION",
            style="CX.PanelSection.TLabel",
        ).pack(anchor="w", pady=(0, 8))
        self._kv(configuration, "Backend / kind", self.kind_var)
        self._kv(configuration, "Input summary", self.input_var)
        ttk.Label(
            configuration,
            text=(
                "Detailed parameters stay in the canonical Input workspace so this "
                "surface never creates a second editable analysis state."
            ),
            style="CX.PanelMuted.TLabel",
            wraplength=300,
            justify="left",
        ).pack(anchor="w", pady=(10, 0))

        ttk.Label(
            execution_summary,
            text="SOLVER TELEMETRY",
            style="CX.PanelSection.TLabel",
        ).pack(anchor="w", pady=(0, 8))
        self._kv(execution_summary, "Convergence", self.convergence_var)
        self._kv(execution_summary, "Plot payload", self.plot_var)
        ttk.Label(
            execution_summary,
            text=(
                "Convergence is displayed only when the backend explicitly emits a "
                "convergence field. Otherwise the state remains NOT REPORTED."
            ),
            style="CX.PanelMuted.TLabel",
            wraplength=300,
            justify="left",
        ).pack(anchor="w", pady=(10, 0))

        ttk.Label(
            result,
            text="RESULT SUMMARY",
            style="CX.PanelSection.TLabel",
        ).pack(anchor="w", pady=(0, 8))
        ttk.Label(
            result,
            textvariable=self.result_var,
            style="CX.PanelTitle.TLabel",
            wraplength=430,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))
        self._kv(result, "Calculated result fields", self.result_fields_var)
        self._kv(result, "Run diagnostics", self.diagnostics_var)
        self._kv(result, "Compliance / verification", self.verification_var)
        ttk.Label(
            result,
            text=(
                "Calculated results, configured requirements, verification verdicts, "
                "and evidence remain distinct artifacts."
            ),
            style="CX.PanelMuted.TLabel",
            wraplength=430,
            justify="left",
        ).pack(anchor="w", pady=(10, 0))

    @staticmethod
    def _kv(master: ttk.Frame, label: str, variable: tk.StringVar) -> None:
        row = ttk.Frame(master, style="CX.Panel.TFrame")
        row.pack(fill="x", pady=3)
        ttk.Label(row, text=label, style="CX.PanelMuted.TLabel").pack(side="left")
        ttk.Label(row, textvariable=variable, style="CX.PanelSecondary.TLabel").pack(
            side="right"
        )

    def set_context(
        self,
        *,
        analysis_name: str | None,
        analysis_kind: str | None,
        analysis_input: Any = None,
        last_run: Any = None,
        running: bool = False,
    ) -> None:
        if not analysis_name:
            self.analysis_var.set("No active analysis")
            self.kind_var.set("—")
            self.input_var.set("0 top-level fields")
            self.state_var.set("NOT CONFIGURED")
            self.state_badge.configure(style="CX.Status.Neutral.TLabel")
            self.stage_var.set("Select or configure an analysis.")
            self.elapsed_var.set("—")
            self.result_var.set("No session result")
            self.result_fields_var.set("—")
            self.diagnostics_var.set("—")
            self.convergence_var.set("NOT REPORTED")
            self.plot_var.set("—")
            self.run_button.configure(state="disabled")
            self.cancel_button.configure(state="disabled")
            self.progress.stop()
            return

        self.analysis_var.set(str(analysis_name))
        self.kind_var.set(str(analysis_kind or "unknown"))
        self.input_var.set(
            f"{len(analysis_input) if isinstance(analysis_input, dict) else 0} top-level fields"
        )
        self.run_button.configure(state="disabled" if running else "normal")
        self.cancel_button.configure(state="normal" if running else "disabled")

        if running:
            self.set_execution(
                state="running",
                stage="Executing backend solver…",
                elapsed="0.0 s",
            )
        elif last_run is not None:
            self.set_completed(last_run)
        else:
            self.state_var.set("READY")
            self.state_badge.configure(style="CX.Status.Neutral.TLabel")
            self.stage_var.set("Ready to run active analysis")
            self.elapsed_var.set("—")
            self.result_var.set("No session result for the active analysis")
            self.result_fields_var.set("—")
            self.diagnostics_var.set("—")
            self.convergence_var.set("NOT REPORTED")
            self.plot_var.set("—")
            self.progress.stop()

    def set_execution(
        self,
        *,
        state: str,
        stage: str,
        elapsed: str | None = None,
    ) -> None:
        token = str(state or "running").strip().lower()
        self.state_var.set(token.upper().replace("_", " "))
        self.state_badge.configure(style=status_style_name(token))
        self.stage_var.set(str(stage))
        if elapsed is not None:
            self.elapsed_var.set(str(elapsed))
        self.run_button.configure(state="disabled")
        self.cancel_button.configure(
            state="disabled" if token in {"abandon_requested"} else "normal"
        )
        if token in {"running", "calculating", "queued", "finalizing"}:
            self.progress.start(12)
        else:
            self.progress.stop()

    def set_elapsed(self, text: str) -> None:
        self.elapsed_var.set(str(text))

    def set_completed(self, run: Any) -> None:
        status = str(getattr(run, "status", None) or "completed").strip().lower()
        result = getattr(run, "result", None)
        diagnostics = getattr(run, "diagnostics", None)
        self.state_var.set(status.upper().replace("_", " "))
        self.state_badge.configure(style=status_style_name(status))
        self.stage_var.set("Execution complete")
        self.run_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self.progress.stop()
        title = str(getattr(run, "title", None) or self.analysis_var.get())
        self.result_var.set(f"{title} · analysis status: {status}")
        self.result_fields_var.set(str(_leaf_count(result)))
        self.diagnostics_var.set(str(_diagnostic_count(diagnostics)))
        self.convergence_var.set(_explicit_convergence(result))
        self.plot_var.set("AVAILABLE" if getattr(run, "plot", None) is not None else "NOT PROVIDED")

    def set_blocked(self, reason: str) -> None:
        self.state_var.set("BLOCKED")
        self.state_badge.configure(style="CX.Status.Fail.TLabel")
        self.stage_var.set(str(reason))
        self.run_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self.progress.stop()

    def set_failed(self, message: str) -> None:
        self.state_var.set("FAILED")
        self.state_badge.configure(style="CX.Status.Fail.TLabel")
        self.stage_var.set("Execution failed")
        self.result_var.set(str(message))
        self.run_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self.progress.stop()

    def set_abandon_requested(self) -> None:
        self.state_var.set("ABANDON REQUESTED")
        self.state_badge.configure(style="CX.Status.Warning.TLabel")
        self.stage_var.set(
            "UI result will be abandoned; waiting for the backend worker to finish safely"
        )
        self.run_button.configure(state="disabled")
        self.cancel_button.configure(state="disabled")
        self.progress.start(12)

    def set_abandoned(self) -> None:
        self.state_var.set("ABANDONED")
        self.state_badge.configure(style="CX.Status.Warning.TLabel")
        self.stage_var.set("UI run abandoned; backend worker has finished")
        self.run_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self.progress.stop()

    def set_discarded(self, reason: str) -> None:
        self.state_var.set("DISCARDED")
        self.state_badge.configure(style="CX.Status.Warning.TLabel")
        self.stage_var.set(str(reason))
        self.run_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self.progress.stop()
