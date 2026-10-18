"""Interactive solver-result explorer; all file parsing/export runs off the Tk thread."""
from __future__ import annotations

import json
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .cfd_analysis_export import draw_analysis_graph, export_analysis_bundle
from .cfd_result_analysis import analyze_selected_result_store, build_analysis_graph, digest
from .gui_windowing import fit_window_to_display

VIEWS = {
    "Field history (mean and range)": "field_history",
    "Compare cases / runs at selected time": "comparison",
    "2D cell slab": "cell_slab",
    "3D cell samples": "cell_3d",
    "Solver residual history": "residual_history",
    "Two-room probe pressure history": "pressure_history",
    "Boundary airflow balance": "flow_balance",
    "Whole-domain inlet supply ACH": "air_change_rate",
}


class CFDAnalysisExplorer(tk.Toplevel):
    def __init__(self, master, loader, *, on_proofgraph_loaded=None):
        super().__init__(master)
        self.title("CleanroomX · Solver result analysis")
        self.geometry("1180x820")
        self.minsize(780, 560)
        self._events = queue.Queue()
        self._alive = True
        self._busy = False
        self._loader = loader
        self.sessions = []
        self.current_graph = None
        self.pinned_graphs = []
        self._on_proofgraph_loaded = on_proofgraph_loaded
        self.view_var = tk.StringVar(value=next(iter(VIEWS)))
        self.case_var = tk.StringVar(value="All cases")
        self.field_var = tk.StringVar(value="speed")
        self.time_var = tk.StringVar()
        self.axis_var = tk.StringVar(value="z")
        self.position_var = tk.StringVar(value="1.5")
        self.thickness_var = tk.StringVar(value="0.25")
        self.status_var = tk.StringVar(value="Verifying solver result assets…")
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._after_id = self.after(100, self._drain)
        self._start("loaded", loader)

    def _build(self):
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

        ttk.Label(self, text="SOLVER RESULT ANALYSIS", style="CX.Section.TLabel", padding=8).pack(anchor="w")
        ttk.Label(self, text="Recorded solver outputs · diagnostic calculations · physical validation BLOCKED",
                  padding=(8, 0, 8, 6)).pack(anchor="w")
        controls = ttk.Frame(self, padding=(8, 2))
        controls.pack(fill="x")
        self.view_combo = self._combo(controls, "Graph", self.view_var, list(VIEWS), 0, 0, 39)
        self.case_combo = self._combo(controls, "Case / region", self.case_var, ["All cases"], 0, 2, 22)
        self.field_combo = self._combo(controls, "Field", self.field_var, ["speed"], 1, 0, 39)
        self.time_combo = self._combo(controls, "Solver time", self.time_var, [], 1, 2, 22)
        self._combos = [self.view_combo, self.case_combo, self.field_combo, self.time_combo]
        self.view_combo.bind("<<ComboboxSelected>>", self._view_changed)
        slab = ttk.Frame(self, padding=(8, 2))
        slab.pack(fill="x")
        ttk.Label(slab, text="Slab axis").pack(side="left")
        self.axis_combo = ttk.Combobox(slab, textvariable=self.axis_var, values=list("xyz"), state="readonly", width=3)
        self.axis_combo.pack(side="left", padx=5)
        self._combos.append(self.axis_combo)
        self._entries = []
        for label, variable in (("Position (m)", self.position_var), ("Thickness (m)", self.thickness_var)):
            ttk.Label(slab, text=label).pack(side="left", padx=(10, 4))
            entry = ttk.Entry(slab, textvariable=variable, width=9)
            entry.pack(side="left")
            self._entries.append(entry)
        ttk.Label(slab, text="Spatial plots use verified cell centers; max 5,000 samples").pack(side="left", padx=12)

        navigation = ttk.Frame(self, padding=(8, 2))
        navigation.pack(fill="x")
        self.previous_time_button = ttk.Button(navigation, text="◀ Previous time", command=lambda: self._step_time(-1))
        self.previous_time_button.pack(side="left")
        self.next_time_button = ttk.Button(navigation, text="Next time ▶", command=lambda: self._step_time(1))
        self.next_time_button.pack(side="left", padx=(4, 14))
        self.azimuth_var = tk.DoubleVar(value=-60.0)
        self.elevation_var = tk.DoubleVar(value=25.0)
        ttk.Label(navigation, text="3D azimuth").pack(side="left")
        ttk.Scale(navigation, from_=-180, to=180, variable=self.azimuth_var, command=self._rotate_3d).pack(side="left", padx=(5, 14))
        ttk.Label(navigation, text="Elevation").pack(side="left")
        ttk.Scale(navigation, from_=-90, to=90, variable=self.elevation_var, command=self._rotate_3d).pack(side="left", padx=5)

        toolbar = ttk.Frame(self, padding=(8, 4))
        toolbar.pack(fill="x")
        self.draw_button = ttk.Button(toolbar, text="Draw graph", command=self.draw_graph)
        self.draw_button.pack(side="left")
        self.compare_button = ttk.Button(toolbar, text="Add comparison run...", command=self._add_comparison)
        self.compare_button.pack(side="left", padx=5)
        self.refresh_button = ttk.Button(toolbar, text="Refresh solver data", command=self.refresh_solver_data)
        self.refresh_button.pack(side="left", padx=5)
        self.pin_button = ttk.Button(toolbar, text="Add graph to report", command=self._pin)
        self.pin_button.pack(side="left", padx=5)
        self.export_button = ttk.Button(toolbar, text="Export figures + data + report...", command=self._export)
        self.export_button.pack(side="left", padx=5)
        self._buttons = [self.draw_button, self.compare_button, self.refresh_button, self.pin_button, self.export_button]

        # Reserve the status/provenance area before letting the canvas expand.
        ttk.Label(self, textvariable=self.status_var, padding=8).pack(side="bottom", fill="x")
        self.provenance = ttk.Label(self, text="", padding=(8, 2), wraplength=1100, justify="left")
        self.provenance.pack(side="bottom", fill="x")

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=8, pady=4)
        plot_frame = ttk.Frame(notebook)
        notebook.add(plot_frame, text="Interactive graph")
        self.figure = Figure(figsize=(10, 6), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.figure, master=plot_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        NavigationToolbar2Tk(self.canvas, plot_frame).update()
        detail_frame = ttk.Frame(notebook)
        notebook.add(detail_frame, text="Sources, statistics, mesh and warnings")
        self.details = tk.Text(detail_frame, wrap="word", state="disabled", font=("TkFixedFont", 9))
        scroll = ttk.Scrollbar(detail_frame, orient="vertical", command=self.details.yview)
        self.details.configure(yscrollcommand=scroll.set)
        self.details.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    @staticmethod
    def _combo(parent, label, variable, values, row, column, width):
        ttk.Label(parent, text=label).grid(row=row, column=column, sticky="w", padx=(0, 6), pady=3)
        combo = ttk.Combobox(parent, textvariable=variable, values=values, state="readonly", width=width)
        combo.grid(row=row, column=column + 1, sticky="ew", padx=(0, 14), pady=3)
        parent.columnconfigure(column + 1, weight=1)
        return combo

    def _start(self, event, function):
        if self._busy:
            return
        self._busy = True
        for button in self._buttons:
            button.configure(state="disabled")
        for widget in self._combos + self._entries:
            widget.configure(state="disabled")

        def work():
            try:
                value = function()
            except Exception as exc:
                self._events.put(("error", str(exc)))
            else:
                self._events.put((event, value))

        threading.Thread(target=work, name="cleanroomx-cfd-analysis", daemon=True).start()

    def _step_time(self, direction: int) -> None:
        """Navigate recorded solver times without inventing intermediate steps."""
        if self._busy or direction not in (-1, 1):
            return
        times = list(self.time_combo["values"])
        if not times:
            return
        from decimal import Decimal
        times.sort(key=Decimal)
        current = self.time_var.get()
        if current not in times:
            target = 0 if direction > 0 else len(times) - 1
        else:
            target = min(len(times) - 1, max(0, times.index(current) + direction))
        if times[target] == current:
            return
        self.time_var.set(times[target])
        self.draw_graph()

    def _rotate_3d(self, _value=None):
        """Orbit existing 3D solver samples without modifying their source data."""
        if self.current_graph is None or self.current_graph.get("kind") != "cell_3d":
            return
        if not self.figure.axes:
            return
        axes = self.figure.axes[0]
        if not hasattr(axes, "view_init"):
            return
        axes.view_init(elev=self.elevation_var.get(), azim=self.azimuth_var.get())
        self.canvas.draw_idle()

    def _view_changed(self, _event=None):
        if VIEWS[self.view_var.get()] == "residual_history":
            self.field_var.set("all")
        elif self.field_var.get() == "all":
            self.field_var.set("speed")

    def _refresh_choices(self):
        cases = sorted({s["case_id"] for session in self.sessions for s in session.report["snapshots"]})
        cases += sorted({d["case_id"] for session in self.sessions for d in session.report["diagnostics"]} - set(cases))
        self.case_combo.configure(values=["All cases"] + cases)
        fields = sorted({name for session in self.sessions for s in session.report["snapshots"] for name in s["statistics"]})
        residual_fields = {p["field"] for session in self.sessions for d in session.report["diagnostics"]
                           if d["residuals"] for p in d["residuals"]["samples"]}
        self.field_combo.configure(values=fields + sorted(residual_fields - set(fields)) + ["all"])
        from decimal import Decimal
        times = sorted({s["time_name"] for session in self.sessions for s in session.report["snapshots"]}, key=Decimal)
        self.time_combo.configure(values=times)
        if times and not self.time_var.get():
            self.time_var.set(times[-1])
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("end", json.dumps([session.report for session in self.sessions], indent=2, sort_keys=True))
        self.details.configure(state="disabled")

    def draw_graph(self):
        if not self.sessions or self._busy:
            return
        try:
            kind = VIEWS[self.view_var.get()]
            selected_case = self.case_var.get()
            filters = dict(kind=kind, field_name=self.field_var.get(),
                           case_id=None if selected_case == "All cases" else selected_case,
                           time_name=self.time_var.get() or None, axis=self.axis_var.get(),
                           position_m=float(self.position_var.get()) if kind in ("cell_slab", "cell_3d") else 1.5,
                           thickness_m=float(self.thickness_var.get()) if kind in ("cell_slab", "cell_3d") else 0.25)
            sessions = self.sessions[:1] if kind in ("cell_slab", "cell_3d") else list(self.sessions)
        except (ValueError, KeyError) as exc:
            messagebox.showerror("Analysis filters", str(exc), parent=self)
            return
        self.status_var.set("Reading selected solver data…")
        self._start("graph", lambda: build_analysis_graph(sessions, **filters))

    def refresh_solver_data(self):
        """Reverify native solver sources in a worker, without blocking Tk."""
        if self._busy:
            return
        self.status_var.set("Rechecking solver manifests and source hashes…")
        self._start("refreshed", self._loader)

    def _add_comparison(self):
        folder = filedialog.askdirectory(parent=self, title="Select a simulation folder or standalone sync-case result store")
        if not folder:
            return
        self.status_var.set("Verifying comparison run…")
        self._start("comparison", lambda: analyze_selected_result_store(folder))

    def _pin(self):
        if self.current_graph is None:
            return
        if len(self.pinned_graphs) >= 16:
            messagebox.showerror("Analysis report", "Export the current set before adding more than 16 figures.", parent=self)
            return
        if digest(self.current_graph) not in {digest(g) for g in self.pinned_graphs}:
            self.pinned_graphs.append(self.current_graph)
        self.status_var.set(f"{len(self.pinned_graphs)} graph(s) added to report")

    def _export(self):
        if self.current_graph is None:
            return
        destination = filedialog.asksaveasfilename(parent=self, title="Name a NEW export folder (outside the source results)",
                                                   initialfile="CleanroomX-analysis", confirmoverwrite=False)
        if not destination:
            return
        graphs = list(self.pinned_graphs)
        if digest(self.current_graph) not in {digest(g) for g in graphs}:
            graphs.append(self.current_graph)
        sessions = list(self.sessions)
        self.status_var.set("Rechecking sources and exporting PNG, SVG, CSV, JSON, report and ProofGraph…")
        self._start("export", lambda: export_analysis_bundle(sessions, graphs, destination))

    def _drain(self):
        if not self._alive:
            return
        try:
            event, value = self._events.get_nowait()
        except queue.Empty:
            pass
        else:
            self._busy = False
            for button in self._buttons:
                button.configure(state="normal")
            for widget in self._combos:
                widget.configure(state="readonly")
            for widget in self._entries:
                widget.configure(state="normal")
            if event in ("loaded", "comparison"):
                if any(s.report["simulation_id"] == value.report["simulation_id"] for s in self.sessions):
                    self.status_var.set("This run is already loaded")
                else:
                    self.sessions.append(value)
                    self._refresh_choices()
                    if value.report["mode"] == "two_room_receipt" and event == "loaded":
                        self.view_var.set("Two-room probe pressure history")
                    self.status_var.set(f"{len(self.sessions)} run(s) loaded; select a graph and draw")
                    self.draw_graph()
            elif event == "refreshed":
                if not self.sessions:
                    self.sessions = [value]
                else:
                    self.sessions[0] = value
                # Previously rendered figures may refer to old source hashes.
                self.current_graph = None
                self.pinned_graphs.clear()
                self.figure.clear()
                self.canvas.draw_idle()
                self.provenance.configure(text="Source data refreshed; old plots and report selections cleared.")
                self._refresh_choices()
                self.status_var.set("Solver sources reverified; redraw graphs to inspect updated data")
            elif event == "graph":
                self.current_graph = value
                draw_analysis_graph(self.figure, value)
                self._rotate_3d()
                self.canvas.draw_idle()
                source_names = "; ".join(Path(source["path"]).name + " #" + source["sha256"][:12]
                                         for source in value["sources"][:3])
                self.provenance.configure(text=value["method"] + "\n" + (source_names or value.get("reason", "")))
                self.status_var.set(value.get("reason", f"{sum(len(s['points']) for s in value['series'])} plotted points; full sources in details"))
            elif event == "export":
                self.status_var.set(f"Exported {value}")
                if self._on_proofgraph_loaded:
                    try:
                        document = json.loads((value / "proofgraph-01.json").read_text(encoding="utf-8"))
                        self._on_proofgraph_loaded(document)
                    except Exception as exc:
                        messagebox.showerror("Exported ProofGraph", "Files were saved; viewer could not load: " + str(exc), parent=self)
            else:
                self.status_var.set("Analysis failed: " + value)
                messagebox.showerror("Solver result analysis", value, parent=self)
        self._after_id = self.after(100, self._drain)

    def _close(self):
        self._alive = False
        self.after_cancel(self._after_id)
        self.figure.clear()
        self.destroy()


def open_analysis_explorer(master, loader, *, on_proofgraph_loaded=None):
    try:
        explorer = CFDAnalysisExplorer(master, loader, on_proofgraph_loaded=on_proofgraph_loaded)
        fit_window_to_display(explorer, preferred_width=1180, preferred_height=820,
                              minimum_width=780, minimum_height=560)
        return explorer
    except ImportError as exc:
        messagebox.showerror("Solver result analysis", "Analysis graphs require the cfd extras: pip install 'cleanroomx[cfd]'\n" + str(exc), parent=master)
        return None
