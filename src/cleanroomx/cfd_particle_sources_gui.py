"""Tk source editor and numerical population review for recorded CFD particles."""
from __future__ import annotations

import copy
import queue
import threading
import tkinter as tk
from tkinter import filedialog, ttk

from .cfd_particle_sources import (
    export_particle_source_configuration, export_particle_source_csv,
    export_particle_source_run, load_particle_source_configuration,
    particle_source_population, run_particle_sources, validate_particle_sources,
)
from .cfd_particles import ParticleRunCancelled
from .cfd_streamlines import ComputedVelocityGrid


class ParticleSourcesWindow(tk.Toplevel):
    """Source edits are atomic; numerical work never calls Tk from its worker."""

    def __init__(self, parent, report, *, on_run, on_sources=None, scene_state=None):
        super().__init__(parent)
        self.title("CleanroomX | Recorded CFD particle sources")
        self.geometry("1160x830")
        self.minsize(960, 720)
        self.report, self.on_run, self.on_sources = report, on_run, on_sources
        self.scene_state = scene_state
        self._scene_at_start = None
        self.sources = []
        self.last_run = None
        self.population = []
        self.revision = 0
        self.busy = False
        self._poll_id = None
        self._cancel = threading.Event()
        self._events = queue.Queue()
        self._editing = None
        self.status = tk.StringVar(value="Add a fluid source or pick a solved fluid cell in 3D.")
        self.end_var = tk.StringVar(value="2")
        self.enabled_var = tk.BooleanVar(value=True)
        self.vars = {name: tk.StringVar() for name in (
            "source_id", "x", "y", "z", "particle_count", "start_time_s", "duration_s",
            "diameter_um", "particle_density_kg_m3", "vx", "vy", "vz")}
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="PARTICLE SOURCES  /  RECORDED VELOCITY FIELD",
                  font=("TkDefaultFont", 13, "bold")).pack(anchor="w")
        ttk.Label(body, text=(
            f"OpenFOAM SIMPLE iteration {report['time_name']} | frozen U | engineering HOLD\n"
            "Numerical counts and release times; no calibrated concentration, deposition or escape."
        ), wraplength=1080).pack(anchor="w", pady=(4, 10))
        toolbar = ttk.Frame(body)
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Label(toolbar, text="Observation end (s)").pack(side="left")
        ttk.Entry(toolbar, textvariable=self.end_var, width=8).pack(side="left", padx=5)
        self.end_var.trace_add("write", lambda *_: self._changed())
        self.run_button = ttk.Button(toolbar, text="Run sources / replace particle paths", command=self.start_run)
        self.run_button.pack(side="left", padx=8)
        self.cancel_button = ttk.Button(toolbar, text="Cancel", command=self.cancel, state="disabled")
        self.cancel_button.pack(side="left")
        ttk.Button(toolbar, text="Load sources", command=self._choose_load).pack(side="right", padx=4)
        ttk.Button(toolbar, text="Save sources", command=self._choose_save).pack(side="right", padx=4)
        self.notebook = ttk.Notebook(body)
        self.notebook.pack(fill="both", expand=True)
        editor, analysis = ttk.Frame(self.notebook, padding=10), ttk.Frame(self.notebook, padding=10)
        self.notebook.add(editor, text="Injection sources")
        self.notebook.add(analysis, text="Numerical population")
        cols = ("enabled", "xyz", "count", "start", "duration", "diameter", "density")
        self.table = ttk.Treeview(editor, columns=cols, show="tree headings", height=6)
        self.table.heading("#0", text="Source ID")
        self.table.column("#0", width=140)
        for key, label, width in zip(cols, (
            "Enabled", "Position (m)", "Count", "Start (s)", "Duration (s)", "Size (µm)", "Density kg/m³"
        ), (70, 215, 65, 80, 90, 80, 105)):
            self.table.heading(key, text=label)
            self.table.column(key, width=width, minwidth=50)
        self.table.pack(fill="both", expand=True)
        self.table.bind("<<TreeviewSelect>>", self._select_source)
        actions = ttk.Frame(editor)
        actions.pack(fill="x", pady=8)
        for text, command in (("New source", self.new_source), ("Save source", self.save_source),
                              ("Enable / disable", self.toggle_source), ("Delete source", self.delete_source)):
            ttk.Button(actions, text=text, command=command).pack(side="left", padx=(0, 6))
        form = ttk.LabelFrame(editor, text="Source properties — metres, seconds, µm, kg/m³", padding=10)
        form.pack(fill="x")
        fields = (("source_id", "Source ID"), ("particle_count", "Numerical particles"),
                  ("diameter_um", "Diameter (µm)"), ("x", "X (m)"), ("y", "Y (m)"), ("z", "Z (m)"),
                  ("start_time_s", "Release start (s)"), ("duration_s", "Release duration (s)"),
                  ("particle_density_kg_m3", "Density (kg/m³)"),
                  ("vx", "Initial Vx (m/s)"), ("vy", "Initial Vy (m/s)"), ("vz", "Initial Vz (m/s)"))
        for index, (key, label) in enumerate(fields):
            row, col = divmod(index, 3)
            ttk.Label(form, text=label).grid(row=row, column=col*2, sticky="w", padx=(0, 5), pady=5)
            ttk.Entry(form, textvariable=self.vars[key], width=17).grid(
                row=row, column=col*2+1, sticky="ew", padx=(0, 14), pady=5)
            form.columnconfigure(col*2+1, weight=1)
        ttk.Checkbutton(form, text="Enabled", variable=self.enabled_var).grid(row=4, column=0, sticky="w")
        ttk.Label(form, text="Leave all initial velocity fields blank to use recorded gas U.",
                  wraplength=700).grid(row=4, column=1, columnspan=5, sticky="w", pady=6)
        ttk.Label(editor, text=(
            "Release duration spans first to last release; zero gives simultaneous releases. "
            "One particle requires zero duration. All releases must precede observation end.\n"
            "Use 'Pick source in 3D' in the viewer, then click a computed fluid point to prefill a new source."
        ), wraplength=1070).pack(anchor="w", pady=(10, 0))
        self.chart = tk.Canvas(analysis, height=250, background="#101c30", highlightthickness=0)
        self.chart.pack(fill="both", expand=True)
        self.chart.bind("<Configure>", lambda *_: self._draw_population())
        pcols = ("time", "unreleased", "tracked", "boundary", "limited", "complete", "rooms")
        self.population_table = ttk.Treeview(analysis, columns=pcols, show="headings", height=8)
        for key, label in zip(pcols, ("Time (s)", "Not released", "Tracked", "Boundary unresolved",
                                     "Step limited", "Observation end", "Last-sample room counts")):
            self.population_table.heading(key, text=label)
            self.population_table.column(key, width=115, minwidth=65)
        self.population_table.column("rooms", width=230)
        scroll = ttk.Scrollbar(analysis, orient="vertical", command=self.population_table.yview)
        self.population_table.configure(yscrollcommand=scroll.set)
        self.population_table.pack(side="left", fill="both", expand=True, pady=8)
        scroll.pack(side="right", fill="y", pady=8)
        export_bar = ttk.Frame(body)
        export_bar.pack(fill="x", pady=(8, 0))
        ttk.Button(export_bar, text="Export run JSON", command=lambda: self._choose_export(False)).pack(side="left")
        ttk.Button(export_bar, text="Export trajectory CSV", command=lambda: self._choose_export(True)).pack(side="left", padx=6)
        ttk.Label(export_bar, text="Terminal samples are held; boundary contact is not deposition.",
                  wraplength=650).pack(side="right")
        ttk.Label(body, textvariable=self.status, wraplength=1080).pack(fill="x", pady=(8, 0))
        self.protocol("WM_DELETE_WINDOW", self.withdraw)
        self.bind("<Destroy>", self._destroyed, add="+")
        self.new_source()

    def _changed(self):
        self.revision += 1
        self._cancel.set()
        self.last_run, self.population = None, []
        if hasattr(self, "population_table"):
            self.population_table.delete(*self.population_table.get_children())
            self._draw_population()
        self.status.set("Inputs changed; previous 3D paths retained. Run saved sources to apply edits.")

    def _update_sources(self, sources):
        validated = validate_particle_sources(self.report, sources, float(self.end_var.get())) if sources else []
        self.sources = validated
        self._changed()
        self.table.delete(*self.table.get_children())
        for source in self.sources:
            self.table.insert("", "end", iid=source["source_id"], text=source["source_id"], values=(
                "yes" if source["enabled"] else "no", ", ".join(f"{v:.5g}" for v in source["position_m"]),
                source["particle_count"], source["start_time_s"], source["duration_s"],
                source["diameter_um"], source["particle_density_kg_m3"]))
        if self.on_sources:
            self.on_sources(copy.deepcopy(self.sources))

    def new_source(self, seed=None):
        self._editing = None
        self.table.selection_remove(*self.table.selection())
        existing = {s["source_id"] for s in self.sources}
        sid = next(f"Source_{i}" for i in range(1, 22) if f"Source_{i}" not in existing)
        point = self.report["cells"][0]["center_m"] if seed is None else seed
        if ComputedVelocityGrid(self.report).cell_at(point) is None:
            raise ValueError("Pick a recorded fluid point for the source")
        values = dict(source_id=sid, particle_count="4", start_time_s="0", duration_s="0",
                      diameter_um="5", particle_density_kg_m3="1000", vx="", vy="", vz="",
                      **dict(zip("xyz", map(str, point))))
        for key, value in values.items():
            self.vars[key].set(value)
        self.enabled_var.set(True)
        self.notebook.select(0)
        self.deiconify()
        self.lift()
        self.status.set("New fluid source prefilled. Save source before running.")

    def _select_source(self, _event=None):
        selection = self.table.selection()
        if not selection:
            return
        sid = selection[0]
        source = next((s for s in self.sources if s["source_id"] == sid), None)
        if source is None:
            return
        self._editing = sid
        for key in ("source_id", "particle_count", "start_time_s", "duration_s", "diameter_um", "particle_density_kg_m3"):
            self.vars[key].set(str(source[key]))
        for axis, value in zip("xyz", source["position_m"]):
            self.vars[axis].set(str(value))
        for axis, value in zip(("vx", "vy", "vz"), source["initial_velocity_m_s"] or ("", "", "")):
            self.vars[axis].set(str(value))
        self.enabled_var.set(source["enabled"])

    def save_source(self):
        try:
            velocity = [self.vars[key].get().strip() for key in ("vx", "vy", "vz")]
            initial = None if not any(velocity) else [float(v) for v in velocity]
            source = {
                "source_id": self.vars["source_id"].get().strip(), "enabled": self.enabled_var.get(),
                "position_m": [float(self.vars[k].get()) for k in "xyz"],
                "particle_count": int(self.vars["particle_count"].get()),
                **{key: float(self.vars[key].get()) for key in (
                    "start_time_s", "duration_s", "diameter_um", "particle_density_kg_m3")},
                "initial_velocity_m_s": initial,
            }
            candidate = [s for s in self.sources if s["source_id"] != self._editing]
            candidate.append(source)
            self._update_sources(candidate)
            self._editing = source["source_id"]
            self.table.selection_set(self._editing)
            self.status.set("Source saved. Run sources to compute trajectories from recorded U.")
            return True
        except (ValueError, TypeError, KeyError) as exc:
            self.status.set(f"Source rejected: {exc}")
            return False

    def toggle_source(self):
        selected = self.table.selection()
        if not selected:
            self.status.set("Select a saved source first")
            return False
        candidate = copy.deepcopy(self.sources)
        for source in candidate:
            if source["source_id"] == selected[0]:
                source["enabled"] = not source["enabled"]
        try:
            self._update_sources(candidate)
            return True
        except ValueError as exc:
            self.status.set(f"Source change rejected: {exc}")
            return False

    def delete_source(self):
        selected = self.table.selection()
        if selected:
            self._update_sources([s for s in self.sources if s["source_id"] != selected[0]])
            self.new_source()

    def cancel(self):
        self._cancel.set()
        self.status.set("Cancellation requested; no partial source run will replace paths.")

    def _start_task(self, operation, work):
        if self.busy:
            self.status.set("A particle task is already running")
            return False
        self.busy = True
        self._cancel = threading.Event()
        revision = self.revision
        self._scene_at_start = self.scene_state() if self.scene_state else None
        self.run_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.status.set(f"{operation} | worker running on recorded CFD U")
        def worker():
            try:
                result = work(self._cancel.is_set)
                self._events.put(("result", operation, revision, result))
            except Exception as exc:
                self._events.put(("error", operation, revision, exc))
        threading.Thread(target=worker, daemon=True).start()
        self._poll_id = self.after(40, self._poll)
        return True

    def _poll(self):
        self._poll_id = None
        try:
            kind, operation, revision, result = self._events.get_nowait()
        except queue.Empty:
            self._poll_id = self.after(40, self._poll)
            return
        self.busy = False
        self.run_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        if self._cancel.is_set() or revision != self.revision:
            self.status.set("Task cancelled or saved sources changed; stale result discarded.")
            return
        if kind == "error":
            self.status.set(f"{operation} rejected: {result}")
            return
        if operation == "Integrating sources":
            if self.scene_state and self.scene_state() != self._scene_at_start:
                self.status.set("3D particle paths changed during integration; stale source run discarded.")
                return
            try:
                self.on_run(result)
                self.last_run = result
                end = result["configuration"]["observation_end_s"]
                self.population = particle_source_population(self.report, result, [end*i/40 for i in range(41)])
                self.population_table.delete(*self.population_table.get_children())
                for row in self.population:
                    self.population_table.insert("", "end", values=(
                        f"{row['observation_time_s']:.4g}", row["not_yet_released"], row["tracked"],
                        row["boundary_unresolved"], row["step_limited"], row["observation_complete"],
                        ", ".join(f"{room}: {n}" for room, n in row["last_sample_room_counts"].items())))
                self._draw_population()
                self.notebook.select(1)
                self.status.set(f"Computed {len(result['tracks'])} scheduled numerical paths; accounting complete. Engineering HOLD.")
            except (ValueError, TypeError, KeyError) as exc:
                self.last_run = None
                self.status.set(f"Source result rejected: {exc}")
        else:
            self.status.set(f"Saved: {result}")

    def start_run(self):
        try:
            end = float(self.end_var.get())
            sources = validate_particle_sources(self.report, copy.deepcopy(self.sources), end)
        except (ValueError, TypeError, KeyError) as exc:
            self.status.set(f"Source run rejected: {exc}")
            return False
        return self._start_task("Integrating sources", lambda cancelled: run_particle_sources(
            self.report, sources, observation_end_s=end, cancel_check=cancelled))

    def _draw_population(self):
        self.chart.delete("all")
        width, height = max(400, self.chart.winfo_width()), max(180, self.chart.winfo_height())
        self.chart.create_text(16, 17, anchor="w", fill="#e5efff",
                               text="Numerical particle population — representative samples, not concentration")
        if not self.population:
            self.chart.create_text(width/2, height/2, fill="#a0b8cf", text="Run saved sources to compute population counts.")
            return
        left, right, top, bottom = 48, width-20, 65, height-35
        self.chart.create_line(left, top, left, bottom, right, bottom, fill="#68819d")
        end = self.population[-1]["observation_time_s"]
        maximum = max(1, self.population[0]["scheduled_particles"])
        series = (("not_yet_released", "Not released", "#b48ef0"), ("tracked", "Tracked", "#61dfbb"),
                  ("boundary_unresolved", "Boundary unresolved", "#ffb759"),
                  ("observation_complete", "Observation end", "#78b4ff"), ("step_limited", "Step limit", "#ff788b"))
        for index, (key, label, color) in enumerate(series):
            self.chart.create_text(left+index*195, 41, anchor="w", fill=color, text=label)
            previous = None
            for row in self.population:
                x = left+(right-left)*row["observation_time_s"]/end
                y = bottom-(bottom-top)*row[key]/maximum
                if previous is not None:
                    # Hold plotted observations between recorded ledger queries.
                    self.chart.create_line(previous[0], previous[1], x, previous[1], x, y, fill=color, width=2)
                previous = x, y
        for number, x, y in ((0, left, bottom+14), (end, right, bottom+14), (maximum, left-15, top)):
            self.chart.create_text(x, y, fill="#c5d7ed", text=f"{number:g}")
        self.chart.create_text(width/2, height-10, fill="#c5d7ed", text="Modeled observation time (s); room labels use last recorded samples")

    def save_configuration(self, path):
        return export_particle_source_configuration(self.report, self.sources, float(self.end_var.get()), path)

    def load_configuration(self, path):
        config = load_particle_source_configuration(self.report, path)
        self.end_var.set(str(config["observation_end_s"]))
        self._update_sources(config["sources"])
        return config

    def export_run(self, path, *, csv_output=False):
        if self.last_run is None:
            self.status.set("Compute saved sources before exporting a run")
            return False
        result = copy.deepcopy(self.last_run)
        exporter = export_particle_source_csv if csv_output else export_particle_source_run
        return self._start_task("Exporting trajectories", lambda cancelled:
                                exporter(self.report, result, path, cancel_check=cancelled))

    def _choose_load(self):
        path = filedialog.askopenfilename(parent=self, filetypes=(("Source JSON", "*.json"),))
        if path:
            try:
                self.load_configuration(path)
            except (OSError, ValueError, TypeError, KeyError) as exc:
                self.status.set(f"Source import rejected: {exc}")

    def _choose_save(self):
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".json")
        if path:
            try:
                self.save_configuration(path)
                self.status.set(f"Saved source configuration: {path}")
            except (OSError, ValueError) as exc:
                self.status.set(f"Source export rejected: {exc}")

    def _choose_export(self, csv_output):
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".csv" if csv_output else ".json")
        if path:
            self.export_run(path, csv_output=csv_output)

    def _destroyed(self, event):
        if event.widget is self:
            self._cancel.set()
            if self._poll_id is not None:
                self.after_cancel(self._poll_id)
                self._poll_id = None
