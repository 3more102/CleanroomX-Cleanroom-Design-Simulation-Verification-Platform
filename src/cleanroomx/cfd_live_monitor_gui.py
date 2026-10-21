"""Live numerical preview, kept separate from canonical CFD field imports."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import ttk

from .cfd_live_monitor import LiveLogFollower
from .cfd_residual_plot import RecordedResidualPlot
from .gui_scrollable import create_scrollable_content


class LiveSolverPanel(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        body = create_scrollable_content(self, padding=8)
        self.follower = None
        self.phase = tk.StringVar(self, value="No solver run monitored.")
        self.summary = tk.StringVar(self, value="Start a fresh native or WSL run to monitor its log.")
        self.continuity = tk.StringVar(self, value="No complete continuity record observed.")
        ttk.Label(body, text="LIVE SOLVER LOG PREVIEW", font=("TkDefaultFont", 12, "bold")).pack(anchor="w")
        ttk.Label(body, textvariable=self.phase, wraplength=1050).pack(anchor="w", pady=3)
        ttk.Label(body, textvariable=self.summary, wraplength=1050).pack(anchor="w")
        self.latest = ttk.Treeview(body, columns=("field", "iteration", "initial", "final"),
                                   show="headings", height=4)
        for name, label in (("field", "Latest observed field"), ("iteration", "SIMPLE iteration"),
                            ("initial", "Initial residual"), ("final", "Final linear residual")):
            self.latest.heading(name, text=label)
            self.latest.column(name, width=160)
        self.latest.pack(fill="x", pady=5)
        ttk.Label(body, textvariable=self.continuity, wraplength=1050).pack(anchor="w")
        self.plot = RecordedResidualPlot(body)
        self.plot.pack(fill="both", expand=True, pady=4)
        self.plot.window.set("Last 100")
        ttk.Label(body, wraplength=1050, text=(
            "Preview only: logs and partial runs have not passed receipt and field checks. "
            "No convergence or engineering verdict is issued here. Import computed fields "
            "after execution to verify results. Continuity values are raw solver diagnostics, "
            "not independently computed face-flux balances."
        )).pack(anchor="w")

    def reset(self):
        self.follower = None
        self.phase.set("No solver run monitored.")
        self.summary.set("Start a fresh native or WSL run to monitor its log.")
        self.latest.delete(*self.latest.get_children())
        self.continuity.set("No complete continuity record observed.")
        self.plot.set_report(None)

    def begin(self, directory, *, source="Native run", allow_existing=False):
        self.reset()
        self.follower = LiveLogFollower(
            Path(directory) / "simpleFoam.log", allow_existing=allow_existing)
        self.phase.set(source + " | waiting for the simpleFoam log.")
        self.summary.set("UNVERIFIED preview | no complete residual records observed.")

    def poll(self):
        if self.follower is None or not self.follower.poll():
            return
        monitor = self.follower.monitor
        self.latest.delete(*self.latest.get_children())
        error = self.follower.error or monitor.error
        if error is not None:
            self.summary.set("Preview stopped: " + error + ". Solver execution and verified import are separate.")
            self.plot.set_report(None)
            self.continuity.set("Preview records unavailable after log error.")
            return
        iteration = "—" if monitor.iteration is None else f"{monitor.iteration:g}"
        self.summary.set(
            f"UNVERIFIED preview | observed SIMPLE iteration {iteration} | "
            f"{monitor.total_samples} linear solves observed; {len(monitor.history)} retained | "
            f"{len(monitor.pending)} bytes in a pending trailing line. " + self.follower.notice)
        for name, row in monitor.latest.items():
            self.latest.insert("", "end", iid=name, values=(
                name, f"{row['iteration']:g}", f"{row['initial']:.8g}", f"{row['final']:.8g}"))
        if monitor.continuity is not None:
            row = monitor.continuity
            self.continuity.set(
                f"Last log continuity record at iteration {row['iteration']:g}: "
                f"sum local = {row['sum_local']:.8g}; global = {row['global']:.8g}; "
                f"cumulative = {row['cumulative']:.8g} (raw solver log values).")
        else:
            self.continuity.set("No complete continuity record observed.")
        self.plot.set_report(monitor.plot_snapshot())
        if not monitor.history:
            self.plot.detail.set("Waiting for complete residual log lines.")
