"""Desktop workspace for recorded, genuinely computed multiroom CFD fields."""
from __future__ import annotations

import json
import math
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .cfd_multizone import run_multizone_open_door_case, verify_multizone_inputs
from .cfd_multizone_results import analyze_multizone_case, export_multizone_report
from .cfd_streamlines import trace_computed_streamline, export_computed_streamlines
from .cfd_multizone_review import review_recorded_multizone, export_engineering_review
from .cfd_closed_door_comparison import (
    load_closed_door_network_scenario, compare_closed_network_with_open_cfd,
    export_closed_door_comparison, write_closed_door_scenario_template,
)
from .cfd_closed_door_sensitivity import (
    sweep_closed_door_leakage, export_closed_door_sensitivity,
)
from .cfd_multizone_stability import (
    SCHEMA as HISTORY_SCHEMA, analyze_recorded_iteration_history,
    export_recorded_iteration_history,
)


def slice_samples(report: dict, axis: str, position_m: float, room: str = "all") -> list:
    """Select one actual cell layer; never interpolate or fill missing cells."""
    if axis not in ("x","y","z") or not math.isfinite(position_m):
        raise ValueError("Choose a finite x/y/z section coordinate")
    a = "xyz".index(axis)
    half = report["voxel_pitch_m"][a]/2
    return [c for c in report["cells"] if (room=="all" or c["room_id"]==room)
            and abs(c["center_m"][a]-position_m) < half-1e-8]


class MultizoneCFDWindow(tk.Toplevel):
    """Run in a worker, tail actual logs, and review recorded field samples."""

    def __init__(self, master, *, directory: str | Path | None = None):
        super().__init__(master)
        self.title("CleanroomX • Multiroom CFD")
        self.geometry("1230x830")
        self.minsize(850,600)
        self.report = None
        self.engineering_review = None
        self.iteration_history = None
        self.closed_door_comparison = None
        self.closed_door_model = None
        self.closed_door_evidence = None
        self.closed_door_scenario_sha = None
        self.closed_door_sensitivity = None
        self.running = False
        self.events = queue.Queue()
        self.case_path = tk.StringVar(value=str(directory or ""))
        self.density = tk.StringVar(value="")
        self.reference = tk.StringVar(value="corridor")
        self.time_name = tk.StringVar(value="latest")
        self.field = tk.StringVar(value="Pressure (Pa)")
        self.axis = tk.StringVar(value="z")
        self.position = tk.StringVar(value="1.35")
        self.room = tk.StringVar(value="all")
        self.vectors = tk.BooleanVar(value=True)
        self.trace_paths = []
        self._section_samples = []
        self._section_to_pixel = None
        self.trace_status = tk.StringVar(value="Click a computed fluid cell to trace its steady 3D streamline.")
        self.status = tk.StringVar(value="Select a generated connected case. Enter the actual air density before importing fields.")
        self.active_log = None
        self.log_offset = 0
        self._build()
        self._poll_id = self.after(150,self._poll)
        self.protocol("WM_DELETE_WINDOW",self.close)

    def _build(self):
        top=ttk.Frame(self,padding=12)
        top.pack(fill="x")
        ttk.Label(top,text="MULTIROOM CFD",font=("TkDefaultFont",16,"bold")).pack(anchor="w")
        ttk.Label(top,text="All doors open • computed values stay separate from the design pressure targets").pack(anchor="w",pady=(2,8))
        location=ttk.Frame(top)
        location.pack(fill="x")
        ttk.Label(location,text="Case folder").pack(side="left")
        ttk.Entry(location,textvariable=self.case_path).pack(side="left",fill="x",expand=True,padx=8)
        ttk.Button(location,text="Browse",command=self.browse).pack(side="left")
        commands=ttk.Frame(top)
        commands.pack(fill="x",pady=8)
        ttk.Label(commands,text="Density (kg/m³)").pack(side="left")
        ttk.Entry(commands,textvariable=self.density,width=8).pack(side="left",padx=6)
        ttk.Label(commands,text="Pressure reference room").pack(side="left")
        ttk.Entry(commands,textvariable=self.reference,width=13).pack(side="left",padx=6)
        self.run_button=ttk.Button(commands,text="Run OpenFOAM 10",command=self.run_case)
        self.run_button.pack(side="left",padx=8)
        self.import_button=ttk.Button(commands,text="Import computed fields",command=self.import_case)
        self.import_button.pack(side="left")
        ttk.Button(commands,text="Export report",command=self.export_report).pack(side="right")
        ttk.Label(top,textvariable=self.status,wraplength=1130).pack(anchor="w")
        self.progress=ttk.Progressbar(top,mode="indeterminate")
        self.progress.pack(fill="x",pady=(8,0))
        self.tabs=ttk.Notebook(self)
        self.tabs.pack(fill="both",expand=True,padx=12,pady=(0,12))
        summary=ttk.Frame(self.tabs,padding=10)
        fields=ttk.Frame(self.tabs,padding=8)
        residuals=ttk.Frame(self.tabs,padding=8)
        logs=ttk.Frame(self.tabs,padding=8)
        diagnostics=ttk.Frame(self.tabs,padding=8)
        engineering=ttk.Frame(self.tabs,padding=10)
        history_tab=ttk.Frame(self.tabs,padding=10)
        closed_tab=ttk.Frame(self.tabs,padding=10)
        for tab,label in ((summary,"Room comparison"),(fields,"Computed sections"),(residuals,"Residual histories"),(logs,"Solver logs"),(diagnostics,"Diagnostics / provenance"),(engineering,"Engineering review"),(history_tab,"Iteration stability"),(closed_tab,"Closed-door network")):
            self.tabs.add(tab,text=label)
        columns=("name","target","pressure","speed","supply","returns","imbalance","balance_pct","upward")
        self.room_table=ttk.Treeview(summary,columns=columns,show="headings",height=5)
        for key,label,width in zip(columns,("Room","Target Pa","Computed Pa*","Mean m/s","Supply m³/h","Return m³/h","Imbalance m³/s","Imbalance %†","Upward %"),(140,75,100,85,95,95,120,100,85)):
            self.room_table.heading(key,text=label)
            self.room_table.column(key,width=width,minwidth=60)
        self.room_table.pack(fill="x")
        ttk.Label(summary,text="*Pressure relative to the selected room's computed mean. Targets are design inputs. †Absolute net imbalance / mean incoming and outgoing face flow; no acceptance limit is assumed.",wraplength=1100).pack(anchor="w",pady=6)
        self.engineering_verdict=tk.StringVar(value="Engineering HOLD — import genuine computed fields for a review.")
        ttk.Label(
            engineering,textvariable=self.engineering_verdict,wraplength=1080,
            font=("TkDefaultFont",11,"bold")).pack(anchor="w",pady=6)
        ttk.Label(
            engineering,
            text="Open-door CFD observations only. No numerical tolerance, mesh-independence, leakage scenario or cleanroom acceptance is assumed.",
            wraplength=1080).pack(anchor="w",pady=6)
        self.engineering_table=ttk.Treeview(
            engineering,columns=("door","target","observed","gap","direction","forward","reverse"),
            show="headings",height=5)
        for key,label in (
            ("door","Door"),("target","Design Δp (Pa)"),("observed","Computed Δp (Pa)"),
            ("gap","Computed − target (Pa)"),("direction","Reversed Δp?"),
            ("forward","Forward solved phi (m³/h)"),("reverse","Reverse solved phi (m³/h)")
        ):
            self.engineering_table.heading(key,text=label)
            self.engineering_table.column(key,width=145,minwidth=75)
        self.engineering_table.pack(fill="x",pady=8)
        ttk.Label(engineering,text="Review limitations and next engineering checks:").pack(anchor="w",pady=4)
        self.engineering_text=tk.Text(
            engineering,wrap="word",height=14,font=("TkFixedFont",10))
        self.engineering_text.pack(fill="both",expand=True)
        ttk.Button(
            engineering,text="Export review JSON (HOLD only)",
            command=self.export_engineering_review_file).pack(anchor="e",pady=8)
        history_header=ttk.Frame(history_tab)
        history_header.pack(fill="x")
        self.history_status=tk.StringVar(
            value="Analyze saved OpenFOAM iterations to compare actual numerical drift; not physical time.")
        ttk.Label(history_header,textvariable=self.history_status,wraplength=960).pack(
            side="left",fill="x",expand=True)
        ttk.Button(history_header,text="Analyze saved iterations",
            command=self.analyze_iteration_history).pack(side="right",padx=4)
        ttk.Button(history_header,text="Export iteration history",
            command=self.export_iteration_history).pack(side="right",padx=4)
        self.history_table=ttk.Treeview(
            history_tab,columns=("iteration","converged","door_pa","door_flow","cell_sum","room_p"),
            show="headings",height=6)
        for key,label in (
            ("iteration","SIMPLE iteration"),("converged","Selected converged?"),
            ("door_pa","Max Δ door Δp (Pa)"),("door_flow","Max Δ door transfer (m³/h)"),
            ("cell_sum","Σ absolute cell imbalance (m³/s)"),
            ("room_p","Max Δ room pressure (Pa)"),
        ):
            self.history_table.heading(key,text=label)
            self.history_table.column(key,width=175,minwidth=110)
        self.history_table.pack(fill="x",pady=7)
        self.history_pressure_canvas=tk.Canvas(
            history_tab,background="#101b2b",highlightthickness=0,height=205)
        self.history_pressure_canvas.pack(fill="both",expand=True,pady=4)
        self.history_balance_canvas=tk.Canvas(
            history_tab,background="#101b2b",highlightthickness=0,height=140)
        self.history_balance_canvas.pack(fill="both",expand=True,pady=4)
        self.history_pressure_canvas.bind(
            "<Configure>",lambda _e:self.draw_iteration_history())
        self.history_balance_canvas.bind(
            "<Configure>",lambda _e:self.draw_iteration_history())
        ttk.Label(history_tab,
            text="Every marker is a saved OpenFOAM SIMPLE iteration. Connecting lines are visual guides ONLY; they do not create intermediate CFD results or represent seconds. Engineering decision remains HOLD.",
            wraplength=1050).pack(anchor="w",pady=5)
        closed_head=ttk.Frame(closed_tab)
        closed_head.pack(fill="x",pady=5)
        self.closed_door_status=tk.StringVar(
            value="Engineering HOLD | Import recorded OPEN-door CFD and independently specified CLOSED-door leakage inputs.")
        ttk.Label(closed_head,textvariable=self.closed_door_status,
                  wraplength=760).pack(side="left",fill="x",expand=True)
        ttk.Button(closed_head,text="Load leakage scenario JSON",
                   command=self.import_closed_door_network).pack(side="right",padx=5)
        ttk.Button(closed_head,text="Create missing-input template",
                   command=self.create_closed_door_input_template).pack(side="right",padx=5)
        ttk.Button(closed_head,text="Export comparison JSON",
                   command=self.export_closed_door_comparison_file).pack(side="right",padx=5)
        ttk.Button(closed_head,text="Illustrative leakage sweep",
                   command=self.run_closed_leakage_sensitivity).pack(side="right",padx=5)
        ttk.Button(closed_head,text="Export sweep JSON",
                   command=self.export_closed_leakage_sensitivity_file).pack(side="right",padx=5)
        ttk.Label(closed_tab,text="This comparison uses the existing room-pressure network solver, NOT a second CFD run. Enter measured/manufacturer/explicit engineering-assumption leakage coefficients and independent supply/return values in JSON. It never certifies 5 Pa.",wraplength=1100).pack(anchor="w",pady=8)
        self.closed_door_table=ttk.Treeview(
            closed_tab,columns=("door","target","open_p","network_p","difference",
                                "network_flow","basis","nominal"),
            show="headings",height=5)
        for key,label in (
            ("door","Door"),("target","Target Δp Pa"),
            ("open_p","Open CFD Δp Pa"),("network_p","Closed network Δp Pa"),
            ("difference","Closed − open Pa"),("network_flow","Closed flow m³/h"),
            ("basis","Leakage source"),("nominal","Nominal network target"),
        ):
            self.closed_door_table.heading(key,text=label)
            self.closed_door_table.column(key,width=145,minwidth=75)
        self.closed_door_table.pack(fill="x",pady=8)
        ttk.Label(closed_tab,text="Illustrative sensitivity only: simultaneous 0.5× / 1× / 2× leakage coefficients; NOT a confidence interval.",
                  wraplength=1080).pack(anchor="w")
        self.closed_sweep_table=ttk.Treeview(
            closed_tab,columns=("factor","door","delta","nominal"),
            show="headings",height=4)
        for key,label in (
            ("factor","Hypothetical scale"),("door","Door"),
            ("delta","Network Δp (Pa)"),("nominal","Nominal target"),
        ):
            self.closed_sweep_table.heading(key,text=label)
            self.closed_sweep_table.column(key,width=180,minwidth=95)
        self.closed_sweep_table.pack(fill="x",pady=(4,8))
        self.closed_sweep_canvas=tk.Canvas(
            closed_tab,height=175,background="#101b2b",highlightthickness=0)
        self.closed_sweep_canvas.pack(fill="x",pady=4)
        self.closed_sweep_canvas.bind(
            "<Configure>",lambda _event:self.draw_closed_leakage_sensitivity())
        self.closed_door_details=tk.Text(
            closed_tab,wrap="word",font=("TkFixedFont",10),height=14)
        self.closed_door_details.pack(fill="both",expand=True)
        self.pressure_canvas=tk.Canvas(summary,background="#101b2b",highlightthickness=0,height=220)
        self.pressure_canvas.pack(fill="both",expand=True,pady=8)
        self.pressure_canvas.bind("<Configure>",lambda e:self.draw_pressure())
        self.door_table=ttk.Treeview(summary,columns=("door","dp","target","flow","reverse"),show="headings",height=4)
        for key,label in (("door","Open door"),("dp","Computed Δp (Pa)"),("target","Target Δp (Pa)"),("flow","Net transfer (m³/h)"),("reverse","Reverse component (m³/h)")):
            self.door_table.heading(key,text=label)
            self.door_table.column(key,width=190)
        self.door_table.pack(fill="x")
        controls=ttk.Frame(fields)
        controls.pack(fill="x",pady=(0,6))
        for var,values,width in ((self.field,("Pressure (Pa)","Speed (m/s)"),18),(self.axis,("x","y","z"),3),(self.room,("all",),14),(self.time_name,("latest",),8)):
            combo=ttk.Combobox(controls,textvariable=var,values=values,state="readonly",width=width)
            combo.pack(side="left",padx=4)
            combo.bind("<<ComboboxSelected>>",lambda e:self.draw_section())
            if var is self.room:
                self.room_picker=combo
            if var is self.time_name:
                self.time_picker=combo
                combo.bind("<<ComboboxSelected>>",lambda e:self.import_case())
        ttk.Label(controls,text="Plane (m)").pack(side="left")
        ttk.Entry(controls,textvariable=self.position,width=8).pack(side="left",padx=4)
        ttk.Checkbutton(controls,text="Velocity vectors",variable=self.vectors,command=self.draw_section).pack(side="left",padx=4)
        ttk.Button(controls,text="Apply section",command=self.draw_section).pack(side="left",padx=6)
        traces=ttk.Frame(fields)
        traces.pack(fill="x",pady=(0,5))
        ttk.Label(traces,textvariable=self.trace_status,wraplength=750).pack(side="left",fill="x",expand=True)
        ttk.Button(traces,text="Clear traces",command=self.clear_traces).pack(side="right",padx=4)
        ttk.Button(traces,text="Export 3D traces",command=self.export_traces).pack(side="right",padx=4)
        ttk.Button(traces,text="Open real VTK 3D",command=self.open_vtk_3d).pack(side="right",padx=4)
        self.section_canvas=tk.Canvas(fields,background="#101b2b",highlightthickness=0)
        self.section_canvas.pack(fill="both",expand=True)
        self.section_canvas.bind("<Configure>",lambda e:self.draw_section())
        self.section_canvas.bind("<Button-1>",self.seed_streamline_at_click)
        ttk.Label(fields,text="Cells and arrows: computed layer. Gold paths: projection of 3D steady streamlines, NOT confined to this plane, NOT particle trajectories. Missing fluid voxels stop tracing.",wraplength=1100).pack(anchor="w",pady=5)
        self.numerical_status=tk.StringVar()
        ttk.Label(residuals,textvariable=self.numerical_status,wraplength=1100).pack(anchor="w",pady=(0,6))
        self.residual_table=ttk.Treeview(residuals,columns=("field","initial","final","limit","below"),show="headings",height=4)
        for key,label in (("field","Selected iteration field"),("initial","First initial residual"),("final","Last linear final residual"),("limit","Configured initial limit"),("below","Initial below limit")):
            self.residual_table.heading(key,text=label)
            self.residual_table.column(key,width=210)
        self.residual_table.pack(fill="x",pady=(0,8))
        self.residual_canvas=tk.Canvas(residuals,background="#101b2b",highlightthickness=0)
        self.residual_canvas.pack(fill="both",expand=True)
        self.residual_canvas.bind("<Configure>",lambda e:self.draw_residuals())
        ttk.Label(residuals,text="Full run initial residuals on a log₁₀ scale; the white marker selects the displayed fields. Linear final residuals do not establish SIMPLE convergence.",wraplength=1100).pack(anchor="w",pady=5)
        self.log_text=tk.Text(logs,background="#101b2b",foreground="#d9e7f7",wrap="none",font=("TkFixedFont",10))
        self.log_text.pack(fill="both",expand=True)
        self.diagnostics=tk.Text(diagnostics,wrap="word",font=("TkFixedFont",10))
        self.diagnostics.pack(fill="both",expand=True)

    def browse(self):
        if self.running:
            return
        path=filedialog.askdirectory(parent=self,title="Select generated connected OpenFOAM case")
        if path:
            self.case_path.set(path)
            self.time_name.set("latest")
            self.report=None
            self._clear_results()

    def _worker(self, function):
        if self.running:
            return
        self.running=True
        self.run_button.configure(state="disabled")
        self.import_button.configure(state="disabled")
        self.progress.start(15)
        def work():
            try:
                self.events.put(("result",function()))
            except Exception as exc:
                self.events.put(("error",str(exc)))
        threading.Thread(target=work,daemon=True).start()

    def run_case(self):
        try:
            root,_=verify_multizone_inputs(self.case_path.get())
        except (OSError,ValueError) as exc:
            messagebox.showerror("Invalid CFD case",str(exc),parent=self)
            return
        self.report=None
        self._clear_results()
        self.status.set("Running recorded OpenFOAM stages. Review logs and numerical convergence after execution.")
        self.tabs.select(3)
        self._worker(lambda:run_multizone_open_door_case(root,on_progress=lambda event:self.events.put(("progress",event))))

    def import_case(self):
        try:
            density=float(self.density.get())
            if not math.isfinite(density) or density<=0:
                raise ValueError("Enter a finite positive air density in kg/m³")
            root=Path(self.case_path.get()).resolve(strict=True)
            reference=self.reference.get().strip()
            selected=self.time_name.get()
        except (OSError,ValueError) as exc:
            messagebox.showerror("CFD field import",str(exc),parent=self)
            return
        self.status.set("Verifying recorded inputs, logs, mesh and computed field hashes…")
        self.report=None
        self._clear_results()
        self._worker(lambda:analyze_multizone_case(root,density_kg_m3=density,reference_room_id=reference,
                                                  time_name=None if selected=="latest" else selected))

    def _poll(self):
        try:
            while True:
                kind,payload=self.events.get_nowait()
                if kind=="progress":
                    self.status.set(f"{payload['stage']}: {payload['event']}")
                    if payload["event"]=="started":
                        self.active_log=Path(payload["log"])
                        self.log_offset=0
                        self.log_text.insert("end",f"\n--- {payload['stage']} ---\n")
                    else:
                        self._tail_log()
                else:
                    self._tail_log()
                    self.running=False
                    self.progress.stop()
                    self.run_button.configure(state="normal")
                    self.import_button.configure(state="normal")
                    if kind=="error":
                        self.status.set("CFD operation failed: "+payload)
                        messagebox.showerror("CFD operation failed",payload,parent=self)
                    elif payload.get("schema")=="cleanroomx.multizone-results.v1":
                        self.load_report(payload)
                    elif payload.get("schema")==HISTORY_SCHEMA:
                        self.load_iteration_history(payload)
                    else:
                        self.status.set(payload["status"].replace("_"," ")+". Enter density and import computed fields to review.")
        except queue.Empty:
            pass
        self._tail_log()
        self._poll_id=self.after(150,self._poll)

    def _tail_log(self):
        if self.active_log and self.active_log.is_file():
            with self.active_log.open("rb") as stream:
                stream.seek(self.log_offset)
                data=stream.read(128*1024)
                self.log_offset=stream.tell()
            if data:
                self.log_text.insert("end",data.decode("utf-8",errors="replace"))
                if int(self.log_text.index("end-1c").split(".")[0])>6000:
                    self.log_text.delete("1.0","2000.0")
                self.log_text.see("end")

    def _clear_results(self):
        self.trace_paths.clear()
        self._section_samples = []
        self._section_to_pixel = None
        self.trace_status.set("Click a computed fluid cell to trace its steady 3D streamline.")
        self.engineering_review = None
        self.iteration_history = None
        self.closed_door_comparison = None
        self.closed_door_model = None
        self.closed_door_evidence = None
        self.closed_door_scenario_sha = None
        self.closed_door_sensitivity = None
        self.closed_sweep_table.delete(*self.closed_sweep_table.get_children())
        self.closed_sweep_canvas.delete("all")
        self.closed_door_status.set("Engineering HOLD | Closed leakage scenario not loaded")
        self.closed_door_table.delete(*self.closed_door_table.get_children())
        self.closed_door_details.delete("1.0","end")
        self.history_status.set("Analyze saved OpenFOAM iterations; not physical time.")
        self.history_table.delete(*self.history_table.get_children())
        self.history_pressure_canvas.delete("all")
        self.history_balance_canvas.delete("all")
        self.engineering_verdict.set("Engineering HOLD — import genuine computed fields for a review.")
        self.engineering_text.delete("1.0","end")
        for table in (self.room_table,self.door_table,self.residual_table,self.engineering_table):
            table.delete(*table.get_children())
        self.numerical_status.set("")
        self.diagnostics.delete("1.0","end")
        for canvas in (self.section_canvas,self.residual_canvas,self.pressure_canvas):
            canvas.delete("all")

    def load_report(self, report):
        self.report=report
        self.density.set(f"{report['density_kg_m3']:g}")
        self.reference.set(report["pressure_reference"]["room_id"])
        self._clear_results()
        self.engineering_review=review_recorded_multizone(report)
        review=self.engineering_review
        self.engineering_verdict.set(
            f"ENGINEERING HOLD | {len(review['doors'])} computed open-door pressure deltas | "
            +("solver-reported convergence" if review["numerical_convergence_at_selected_iteration"] else "NOT CONVERGED")
            +" | 5 Pa CLOSED-DOOR PERFORMANCE NOT DEMONSTRATED")
        for item in review["door_review_by_absolute_mismatch"]:
            gap=item["delta_minus_target_pa"]
            target=item["target_delta_pa"]
            reversed_flag=item["target_direction_reversed"]
            self.engineering_table.insert("","end",values=(
                item["door"],"—" if target is None else f"{target:.6g}",
                f"{item['observed_delta_pa']:.6g}",
                "—" if gap is None else f"{gap:+.6g}",
                "unknown" if reversed_flag is None else ("YES" if reversed_flag else "no"),
                f"{item['computed_forward_m3_s']*3600:.6g}",
                f"{item['computed_reverse_m3_s']*3600:.6g}"))
        lines=["Reasons for HOLD:",*(
            "• "+reason["code"]+": "+reason["message"]
            for reason in review["reasons"]),
            "", "Non-prescriptive next engineering checks:",
            *("• "+action for action in review["non_prescriptive_checks"])]
        self.engineering_text.insert("1.0","\n".join(lines))
        for rid,r in report["rooms"].items():
            target=r["design_pressure_relative_to_reference_pa"]
            self.room_table.insert("","end",iid=rid,values=(r["name"],"—" if target is None else f"{target:g}",
                f"{r['mean_pressure_pa_relative_to_reference']:.5g}",f"{r['mean_speed_m_s']:.4g}",
                f"{r['supply_inflow_m3_s']*3600:.4g}",f"{r['return_outflow_m3_s']*3600:.4g}",
                f"{r['net_outward_imbalance_m3_s']:.3g}",
                "—" if r['net_imbalance_fraction_of_throughflow'] is None else f"{r['net_imbalance_fraction_of_throughflow']*100:.3g}",
                f"{r['upward_volume_fraction']*100:.1f}"))
        for name,d in report["doors"].items():
            self.door_table.insert("","end",values=(name,f"{d['computed_delta_pressure_pa']:.5g}",
                d["design_delta_pressure_target_pa"],f"{d['computed_net_transfer_m3_s']*3600:.5g}",
                f"{d['computed_reverse_m3_s']*3600:.5g}"))
        self.room_picker.configure(values=("all",*report["rooms"]))
        self.time_picker.configure(values=("latest",*report["available_times"]))
        self.time_name.set(report["time_name"])
        reference=report["pressure_reference"]["room_id"]
        self.status.set(f"COMPUTED • {report['mesh']['cells']:.0f} cells • iteration {report['time_name']} • "
                        +("solver reported convergence" if report["solver_reported_convergence"] else "NOT CONVERGED")
                        +f" • pressure relative to computed mean in {reference}. Engineering review required.")
        numerics=report["numerics"]
        final_verdict=(f"converged at iteration {numerics['solver_convergence_iteration']:g}"
                       if numerics["run_reported_convergence"] else "did not report convergence")
        balance=report["flow_balance"]
        self.numerical_status.set(
            f"Selected fields: iteration {report['time_name']}. Full run {final_verdict}. "
            f"Sum of absolute cell flow imbalances: {balance['sum_absolute_cell_imbalance_m3_s']:.5g} m³/s; "
            f"largest cell: {balance['max_absolute_cell_imbalance_m3_s']:.5g} m³/s.")
        for field,data in numerics["fields"].items():
            limit=data["configured_initial_residual_limit"]
            below=data["initial_residual_below_limit"]
            self.residual_table.insert("","end",iid=field,values=(field,
                f"{data['first_initial_residual']:.5g}",f"{data['last_final_linear_residual']:.5g}",
                "—" if limit is None else f"{limit:.5g}","unknown" if below is None else ("yes" if below else "no")))
        summary={k:v for k,v in report.items() if k not in ("cells","residual_history")}
        self.diagnostics.delete("1.0","end")
        self.diagnostics.insert("1.0",json.dumps(summary,indent=2,sort_keys=True,allow_nan=False))
        self.draw_pressure()
        self.draw_section()
        self.draw_residuals()
        self.tabs.select(0)

    def analyze_iteration_history(self):
        """Compute across all saved iterations in worker, no synthetic snapshots."""
        if not self.report or self.running:
            self.history_status.set("Import real OpenFOAM fields before comparing iterations.")
            return
        root=self.case_path.get()
        density=self.report["density_kg_m3"]
        reference=self.report["pressure_reference"]["room_id"]
        self.history_status.set("Validating each saved p/U/C/phi snapshot and calculating evolution…")
        self._worker(lambda:analyze_recorded_iteration_history(
            root,density_kg_m3=density,reference_room_id=reference))

    def load_iteration_history(self, history):
        """Render actual saved SIMPLE iteration samples; always noncertifying."""
        if history.get("schema")!=HISTORY_SCHEMA or history.get("engineering_release")!="HOLD":
            raise ValueError("Iteration stability requires an unqualified recorded-CFD comparison")
        if self.report and (
            history["source_run_receipt_sha256"]!=
                self.report["provenance"]["run_receipt_sha256"] or
            history["source_manifest_sha256"]!=
                self.report["provenance"]["manifest_sha256"]):
            raise ValueError("Saved snapshot history belongs to a different OpenFOAM run")
        self.iteration_history=history
        self.history_table.delete(*self.history_table.get_children())
        for snap in history["snapshots"]:
            change=snap["change_from_previous_recorded_iteration"]
            self.history_table.insert("","end",values=(
                snap["iteration"],
                "yes" if snap["solver_reported_convergence"] else "no",
                "—" if change is None else
                    f"{change['max_absolute_door_delta_change_pa']:.5g}",
                "—" if change is None else
                    f"{3600*change['max_absolute_door_transfer_change_m3_s']:.5g}",
                f"{snap['sum_absolute_cell_imbalance_m3_s']:.5g}",
                "—" if change is None else
                    f"{change['max_absolute_room_pressure_change_pa']:.5g}"))
        final=history["last_saved_snapshot_change"]
        self.history_status.set(
            f"ENGINEERING HOLD | {len(history['snapshots'])} real saved SIMPLE iterations | "
            f"last maximum door Δp drift {final['max_absolute_door_delta_change_pa']:.5g} Pa | "
            +("latest solver reported convergence" if history["latest_solver_reported_convergence"]
              else "latest NOT CONVERGED")
            +" | does NOT prove a 5 Pa closed-door cascade")
        self.draw_iteration_history()
        self.tabs.select(self.tabs.index("end")-1)

    def draw_iteration_history(self):
        """Chart only genuine saved iteration points, never estimated CFD values."""
        history=self.iteration_history
        for canvas in (self.history_pressure_canvas,self.history_balance_canvas):
            canvas.delete("all")
        if history is None:
            return
        snapshots=history["snapshots"]
        if not snapshots:
            return
        def axes(canvas,title,series,unit):
            w=max(canvas.winfo_width(),650)
            h=max(canvas.winfo_height(),120)
            left,right,top,bottom=72,w-18,40,h-26
            lows=[float(snapshot["iteration"]) for snapshot in snapshots]
            if not all(math.isfinite(v) for v in lows) or lows[0]==lows[-1]:
                raise ValueError("Invalid recorded SIMPLE iteration indices")
            vals=[v for _,points in series for v in points]
            low=min(vals)
            high=max(vals)
            span=max(high-low,abs(high)*1e-6,1e-10)
            low-=span*.08
            high+=span*.08
            canvas.create_text(15,14,anchor="w",fill="#e6eef7",
                text=f"{title} ({unit}) — saved SIMPLE iterations only",tags="history-chart-title")
            canvas.create_line(left,top,left,bottom,fill="#718096")
            canvas.create_line(left,bottom,right,bottom,fill="#718096")
            canvas.create_text(7,top,anchor="w",fill="#acbfd4",text=f"{high:.4g}")
            canvas.create_text(7,bottom,anchor="w",fill="#acbfd4",text=f"{low:.4g}")
            def xp(i):
                return left+(float(snapshots[i]["iteration"])-lows[0])/(lows[-1]-lows[0])*(right-left)
            def yp(v):
                return bottom-(v-low)/(high-low)*(bottom-top)
            for i,snap in enumerate(snapshots):
                canvas.create_text(xp(i),bottom+13,fill="#acbfd4",
                    text=snap["iteration"],tags="computed-iteration-label")
            colors=("#22c5d6","#ffca65","#c5a4ff","#8de0a7","#e89eb0","#a8c2d4")
            for n,(name,values) in enumerate(series):
                coords=[(xp(i),yp(value)) for i,value in enumerate(values)]
                color=colors[n%len(colors)]
                for a,b in zip(coords,coords[1:]):
                    canvas.create_line(a[0],a[1],b[0],b[1],
                        fill=color,width=2,tags="snapshot-visual-guide")
                for x,y in coords:
                    canvas.create_oval(x-3.5,y-3.5,x+3.5,y+3.5,
                        fill=color,outline="#101b2b",tags="computed-iteration-point")
                canvas.create_text(right-8,top+n*15,anchor="ne",fill=color,
                    text=str(name),tags="computed-series-label")
        doors=tuple(sorted(snapshots[0]["doors"]))
        axes(self.history_pressure_canvas,"Open-door computed Δp",
            [(name,[snap["doors"][name]["delta_pa"] for snap in snapshots])
             for name in doors],"Pa")
        axes(self.history_balance_canvas,"Σ absolute cell flow imbalance",
            [("All cells",[snap["sum_absolute_cell_imbalance_m3_s"]
                          for snap in snapshots])],"m³/s")

    def export_iteration_history(self):
        if not self.iteration_history or self.running:
            self.history_status.set("Analyze recorded iterations before exporting history.")
            return
        root=filedialog.askdirectory(
            parent=self,title="Choose NEW directory for solver iteration history")
        if not root:
            return
        # Exporter creates the destination itself. Prevent accidental
        # rewriting by using a nonexisting child inside the selected parent.
        dest=Path(root)/("iteration-history-"+
                         self.iteration_history["source_run_receipt_sha256"][:12])
        try:
            saved=export_recorded_iteration_history(self.iteration_history,dest)
        except (OSError,ValueError) as exc:
            messagebox.showerror("Iteration history export failed",str(exc),parent=self)
            return
        self.history_status.set(f"ENGINEERING HOLD | Saved recorded evolution: {saved}")

    def draw_pressure(self):
        c=self.pressure_canvas
        c.delete("all")
        if not self.report:
            return
        width=max(c.winfo_width(),600)
        values=list(self.report["rooms"].values())
        peak=max(1e-9,*(abs(r["mean_pressure_pa_relative_to_reference"]) for r in values))
        c.create_text(12,15,anchor="w",fill="#d9e7f7",text="Computed room pressures (Pa) • chart uses computed values only")
        center=width*.48
        for i,r in enumerate(values):
            y=48+i*37
            value=r["mean_pressure_pa_relative_to_reference"]
            end=center+value/peak*width*.26
            c.create_text(12,y,anchor="w",fill="#d9e7f7",text=r["name"])
            c.create_rectangle(min(center,end),y-9,max(center+1,end),y+9,fill="#22c5d6",outline="",tags="computed-pressure")
            c.create_text(width-20,y,anchor="e",fill="#d9e7f7",text=f"{value:.6g} Pa")

    def create_closed_door_input_template(self):
        """Produce explicit model layout while retaining unknown leakage data."""
        if not self.report or self.running:
            self.closed_door_status.set("Import actual open-door CFD fields before creating a template.")
            return
        path=filedialog.asksaveasfilename(
            parent=self,title="Save INCOMPLETE closed-door network input template",
            defaultextension=".json",filetypes=(("JSON","*.json"),))
        if not path:
            return
        try:
            saved=write_closed_door_scenario_template(self.report,path)
        except (OSError,ValueError) as exc:
            self.closed_door_status.set(f"Closed-door input template rejected: {exc}")
            return
        self.closed_door_status.set(
            f"ENGINEERING HOLD | Incomplete source-linked room/door template: {saved} | "
            "Fill ALL mechanical flows, leakage coefficients and evidence references.")

    def import_closed_door_network(self):
        """Read explicit leakage source JSON; never infer closed leakage from open CFD."""
        if not self.report or self.running:
            self.closed_door_status.set("Import verified open-door OpenFOAM results first.")
            return
        path=filedialog.askopenfilename(
            parent=self,title="Select independently sourced closed-door leakage scenario",
            filetypes=(("JSON","*.json"),))
        if not path:
            return
        try:
            model,evidence,sha=load_closed_door_network_scenario(path)
            comparison=compare_closed_network_with_open_cfd(
                self.report,model,evidence,scenario_sha256=sha)
            self.load_closed_door_comparison(comparison)
            self.closed_door_model=model
            self.closed_door_evidence=evidence
            self.closed_door_scenario_sha=sha
        except (ValueError,RuntimeError,OSError) as exc:
            self.closed_door_status.set(f"Closed-door comparison rejected: {exc}")
            messagebox.showerror("Closed-door leakage scenario rejected",str(exc),parent=self)

    def load_closed_door_comparison(self,comparison):
        if (comparison.get("schema")!="cleanroomx.open-cfd-vs-closed-network.v1"
            or comparison.get("engineering_release")!="HOLD"
            or comparison.get("closed_door_5pa_cfd_demonstrated") is not False
            or (self.report and (
                comparison["open_cfd_provenance"]["run_receipt_sha256"]!=
                    self.report["provenance"]["run_receipt_sha256"]
                or comparison["open_cfd_provenance"]["manifest_sha256"]!=
                    self.report["provenance"]["manifest_sha256"]
                or comparison["open_cfd_provenance"]["selected_iteration"]!=
                    self.report["time_name"]))):
            raise ValueError("Closed-door comparison is invalid or from another CFD run/iteration")
        self.closed_door_comparison=comparison
        self.closed_door_sensitivity=None
        self.closed_sweep_table.delete(*self.closed_sweep_table.get_children())
        self.closed_sweep_canvas.delete("all")
        self.closed_door_table.delete(*self.closed_door_table.get_children())
        for d in comparison["door_comparison"]:
            self.closed_door_table.insert("","end",values=(
                d["door"],f"{d['design_target_pa']:.5g}",
                f"{d['open_door_cfd_delta_pa']:.5g}",
                f"{d['closed_door_network_delta_pa']:.5g}",
                f"{d['closed_network_minus_open_cfd_delta_pa']:+.5g}",
                f"{d['closed_door_network_flow_m3_h']:.5g}",
                d["leakage_source_basis"],
                "model yes" if d["closed_network_meets_nominal_target"] else "model no"))
        note="\n".join([
            "ENGINEERING HOLD — TWO DIFFERENT MODELS; NO CLOSED-DOOR CFD",
            "Open-field source iteration: "+
            comparison["open_cfd_provenance"]["selected_iteration"],
            "Network result: "+comparison["network_solver_result"]["status"],
            "Network nominal targets: "+
            ("all met" if comparison["network_nominal_targets_met"] else "at least one missed"),
            "Leakage path evidence:",
            *(" - "+p+": "+v["basis"]+" — "+v["reference"]
              for p,v in sorted(comparison["path_evidence"].items())),
            "Open CFD phi versus CLOSED network independent mechanical airflow inputs:",
            *(
                f" - {row['room']}: supply CFD={row['open_cfd_supply_m3_h']:.4g}, "
                f"network={row['closed_network_supply_input_m3_h']:.4g} m³/h; "
                f"return CFD={row['open_cfd_return_m3_h']:.4g}, "
                f"network={row['closed_network_return_input_m3_h']:.4g} m³/h; "
                f"network exhaust={row['closed_network_exhaust_input_m3_h']:.4g} m³/h"
                for row in comparison["mechanical_airflow_boundary_comparison"]
            ),
            "Warning: "+comparison["boundary_comparison_note"],
            "Engineering limitations:",*(
                " - "+x for x in comparison["limitations"])
        ])
        self.closed_door_details.delete("1.0","end")
        self.closed_door_details.insert("1.0",note)
        self.closed_door_status.set(
            "ENGINEERING HOLD | compared recorded OPEN-door CFD with independently "
            "specified CLOSED-door leakage NETWORK; NOT closed-door CFD")
        self.tabs.select(self.tabs.index("end")-1)

    def run_closed_leakage_sensitivity(self):
        """Parametric NETWORK-only scenario, never a statistical uncertainty bound."""
        if (not self.report or not self.closed_door_model or
            not self.closed_door_evidence or self.running):
            self.closed_door_status.set(
                "Load a complete independently sourced closed-door leakage scenario first.")
            return
        try:
            sweep=sweep_closed_door_leakage(
                self.report,self.closed_door_model,self.closed_door_evidence,
                factors=(0.5,1.,2.),scenario_sha256=self.closed_door_scenario_sha)
        except (ValueError,RuntimeError) as exc:
            self.closed_door_sensitivity=None
            self.closed_door_status.set(f"Leakage sweep rejected: {exc}")
            return
        self.closed_door_sensitivity=sweep
        self.closed_sweep_table.delete(*self.closed_sweep_table.get_children())
        for scenario in sweep["factor_results"]:
            for door in scenario["door_results"]:
                self.closed_sweep_table.insert("","end",values=(
                    f"{scenario['leakage_multiplier']:g}×",
                    door["door"],
                    f"{door['computed_closed_network_delta_pa']:.5g}",
                    "model yes" if door["nominal_target_met"] else "model no"))
        self.draw_closed_leakage_sensitivity()
        self.closed_door_status.set(
            "ENGINEERING HOLD | Hypothetical leakage sensitivity 0.5×/1×/2×. "
            "Not measured uncertainty, CFD or proof of 5 Pa.")

    def draw_closed_leakage_sensitivity(self):
        """Plot ONLY actually solved network factors; joining lines are guides."""
        canvas=self.closed_sweep_canvas
        canvas.delete("all")
        sweep=self.closed_door_sensitivity
        if not sweep:
            return
        series=sweep["factor_results"]
        width=max(canvas.winfo_width(),700)
        height=max(canvas.winfo_height(),175)
        left,right,top,bottom=70,width-22,36,height-28
        factors=[float(item["leakage_multiplier"]) for item in series]
        names=sorted({d["door"] for d in series[0]["door_results"]})
        all_values=[
            d["computed_closed_network_delta_pa"]
            for item in series for d in item["door_results"]]
        all_values.extend(
            d["nominal_design_delta_pa"] for d in series[0]["door_results"])
        low,high=min(all_values),max(all_values)
        stretch=max(high-low,max(abs(low),abs(high),1.)*.04)
        low-=stretch*.08
        high+=stretch*.08
        canvas.create_text(12,15,anchor="w",fill="#e4f0fa",
            text="Closed NETWORK Δp vs illustrative leakage multiplier — NOT CFD")
        canvas.create_line(left,top,left,bottom,fill="#72829e")
        canvas.create_line(left,bottom,right,bottom,fill="#72829e")
        canvas.create_text(8,top,anchor="w",fill="#9cb5ce",text=f"{high:.4g} Pa")
        canvas.create_text(8,bottom,anchor="w",fill="#9cb5ce",text=f"{low:.4g} Pa")
        def xp(factor):
            return left+(factor-factors[0])/(factors[-1]-factors[0])*(right-left)
        def yp(value):
            return bottom-(value-low)/(high-low)*(bottom-top)
        for factor in factors:
            canvas.create_text(xp(factor),bottom+13,fill="#a8bcd4",
                text=f"{factor:g}×",tags="leakage-factor-marker")
        palette=("#22c5d6","#f6bb69","#9ade9f","#bc9aff","#f99aba")
        for i,name in enumerate(names):
            color=palette[i%len(palette)]
            per_factor=[
                next(d for d in item["door_results"] if d["door"]==name)
                for item in series]
            target=per_factor[0]["nominal_design_delta_pa"]
            ytarget=yp(target)
            canvas.create_line(left,ytarget,right,ytarget,fill=color,
                dash=(3,5),tags="leakage-design-target")
            points=[(xp(f),yp(d["computed_closed_network_delta_pa"]))
                    for f,d in zip(factors,per_factor)]
            for a,b in zip(points,points[1:]):
                canvas.create_line(*a,*b,fill=color,width=2,
                    tags="leakage-snapshot-guide")
            for x,y in points:
                canvas.create_oval(x-4,y-4,x+4,y+4,fill=color,
                    outline="#101b2b",tags="leakage-solved-point")
            canvas.create_text(right-5,top+15*i,anchor="ne",fill=color,
                text=name+" (dashed=design target)",tags="leakage-legend")

    def export_closed_leakage_sensitivity_file(self):
        if self.closed_door_sensitivity is None or self.running:
            self.closed_door_status.set("Run illustrative sensitivity before export.")
            return
        path=filedialog.asksaveasfilename(
            parent=self,title="Export hypothetical closed-door leakage sensitivity",
            defaultextension=".json",filetypes=(("JSON","*.json"),))
        if not path:
            return
        try:
            saved=export_closed_door_sensitivity(self.closed_door_sensitivity,path)
        except (ValueError,OSError) as exc:
            self.closed_door_status.set(f"Sensitivity export rejected: {exc}")
            return
        self.closed_door_status.set(f"ENGINEERING HOLD | Hypothetical scenarios saved: {saved}")

    def export_closed_door_comparison_file(self):
        if not self.closed_door_comparison or self.running:
            return
        filename=filedialog.asksaveasfilename(
            parent=self,title="Export source-linked two-model comparison (HOLD only)",
            defaultextension=".json",filetypes=(("JSON","*.json"),))
        if not filename:
            return
        try:
            saved=export_closed_door_comparison(self.closed_door_comparison,filename)
        except (ValueError,OSError) as exc:
            messagebox.showerror("Closed-door comparison export rejected",str(exc),parent=self)
            return
        self.closed_door_status.set(f"ENGINEERING HOLD | Saved: {saved}")

    def export_engineering_review_file(self):
        if not self.engineering_review or self.running:
            return
        destination=filedialog.asksaveasfilename(
            parent=self,title="Export computed CFD engineering review (HOLD)",
            defaultextension=".json",filetypes=(("JSON","*.json"),))
        if not destination:
            return
        try:
            saved=export_engineering_review(self.engineering_review,destination)
        except (OSError,ValueError) as exc:
            messagebox.showerror("Engineering review export failed",str(exc),parent=self)
            return
        self.engineering_verdict.set(f"ENGINEERING HOLD | Evidence saved: {saved}")

    def open_vtk_3d(self):
        """Open real 3D computed-cell geometry and recorded steady flow paths."""
        if not self.report or self.running:
            self.trace_status.set("Import recorded CFD fields before opening real VTK 3D.")
            return
        try:
            from .cfd_multizone_vtk import open_multizone_vtk_window
            window=open_multizone_vtk_window(self,self.report,list(self.trace_paths))
        except (RuntimeError,ImportError,ValueError,tk.TclError) as exc:
            messagebox.showerror("3D VTK viewer unavailable",str(exc),parent=self)
            return
        self.trace_status.set(
            "Native interactive VTK 3D opened. Colors are computed velocity, "
            "gold paths are recorded-field steady streamlines; NOT particle motion.")
        window.lift()

    def export_traces(self):
        if not self.trace_paths or self.running:
            self.trace_status.set("No recorded traces to export.")
            return
        destination=filedialog.asksaveasfilename(
            parent=self,title="Export computed 3D steady streamlines",
            defaultextension=".json",filetypes=(("JSON","*.json"),))
        if not destination:
            return
        try:
            path=export_computed_streamlines(self.trace_paths,destination)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Streamline export failed",str(exc),parent=self)
            return
        self.trace_status.set(f"Provenance-tagged 3D streamline data exported: {path}")

    def clear_traces(self):
        self.trace_paths.clear()
        self.trace_status.set("Traces cleared. Click a computed fluid cell to seed another.")
        self.draw_section()

    def seed_streamline_at_click(self, event):
        if self.report is None or self._section_to_pixel is None or self.running:
            return
        if len(self.trace_paths) >= 20:
            self.trace_status.set("Maximum 20 displayed traces; clear traces to seed again.")
            return
        a,b = self._section_plane_axes
        ha,hb = self._section_half_size
        for sample in self._section_samples:
            px,py = self._section_to_pixel(sample["center_m"][a], sample["center_m"][b])
            if abs(event.x-px) <= ha*self._section_scale and abs(event.y-py) <= hb*self._section_scale:
                try:
                    trace = trace_computed_streamline(self.report,sample["center_m"])
                except ValueError as exc:
                    self.trace_status.set(f"Trace rejected: {exc}")
                    return
                self.trace_paths.append(trace)
                self.trace_status.set(
                    f"3D streamline from {sample['room_id']} at {sample['center_m']} m: "
                    f"{len(trace['points'])} computed-field points; stop: {trace['termination']}. "
                    "Projection only; not transient particle motion.")
                self.draw_section()
                return
        self.trace_status.set("Click inside a colored recorded fluid cell to select a valid seed.")

    def draw_section(self):
        c=self.section_canvas
        c.delete("all")
        self._section_samples = []
        self._section_to_pixel = None
        if not self.report:
            return
        try:
            samples=slice_samples(self.report,self.axis.get(),float(self.position.get()),self.room.get())
        except ValueError:
            return
        if not samples:
            c.create_text(30,30,anchor="w",fill="white",text="No computed cell layer at this coordinate. Choose a cell-centre coordinate.")
            return
        axes=[i for i in range(3) if i!="xyz".index(self.axis.get())]
        a,b=axes
        ha,hb=(self.report["voxel_pitch_m"][i]/2 for i in axes)
        lo=[min(s["center_m"][i] for s in samples)-self.report["voxel_pitch_m"][i]/2 for i in axes]
        hi=[max(s["center_m"][i] for s in samples)+self.report["voxel_pitch_m"][i]/2 for i in axes]
        width,height=max(c.winfo_width(),600),max(c.winfo_height(),350)
        scale=min((width-100)/(hi[0]-lo[0]),(height-95)/(hi[1]-lo[1]))
        def point(x,y):
            return 45+(x-lo[0])*scale,height-45-(y-lo[1])*scale
        self._section_samples = samples
        self._section_plane_axes = (a,b)
        self._section_half_size = (ha,hb)
        self._section_scale = scale
        self._section_to_pixel = point
        values=[s["pressure_pa_relative_to_reference"] if self.field.get().startswith("Pressure") else math.sqrt(sum(v*v for v in s["velocity_m_s"])) for s in samples]
        low,high=min(values),max(values)
        for s,value in zip(samples,values):
            x,y=s["center_m"][a],s["center_m"][b]
            t=(value-low)/(high-low) if high>low else .5
            color=f"#{int(30+220*t):02x}{int(130+70*(1-abs(2*t-1))):02x}{int(240-210*t):02x}"
            c.create_rectangle(*point(x-ha,y-hb),*point(x+ha,y+hb),fill=color,outline="",tags="computed-cell")
        if self.vectors.get():
            vmax=max(math.hypot(s["velocity_m_s"][a],s["velocity_m_s"][b]) for s in samples)
            vector_scale=30/max(vmax,1e-12)
            for s in samples[::max(1,len(samples)//150)]:
                x,y=point(s["center_m"][a],s["center_m"][b])
                u,v=s["velocity_m_s"][a],s["velocity_m_s"][b]
                c.create_line(x,y,x+u*vector_scale,y-v*vector_scale,fill="#102030",arrow="last",tags="computed-vector")
        for trace in self.trace_paths:
            xy = []
            for item in trace["points"]:
                xy.extend(point(item["xyz_m"][a],item["xyz_m"][b]))
            if len(xy) >= 4:
                c.create_line(*xy,fill="#ffe59a",width=2,tags="computed-3d-streamline-projection")
            elif len(xy) == 2:
                c.create_oval(xy[0]-3,xy[1]-3,xy[0]+3,xy[1]+3,
                              fill="#ffe59a",outline="",tags="computed-3d-streamline-projection")
        c.create_text(12,16,anchor="w",fill="white",text=f"{self.field.get()} • {low:.5g} to {high:.5g} • axes {'xyz'[a]}/{'xyz'[b]} (m) • {len(samples)} actual cells")
        c.create_text(12,36,anchor="w",fill="#b6cddd",text="" if self.report["solver_reported_convergence"] else "NOT CONVERGED • provisional numerical fields")

    def draw_residuals(self):
        c=self.residual_canvas
        c.delete("all")
        if not self.report:
            return
        width,height=max(c.winfo_width(),600),max(c.winfo_height(),350)
        histories=self.report["residual_history"]
        times=[h["iteration"] for h in histories if h["iteration"] is not None]
        max_time=max(times,default=1)
        for power in range(0,-11,-1):
            y=35+(-power)/10*(height-80)
            c.create_line(65,y,width-20,y,fill="#24374e")
            c.create_text(50,y,anchor="e",text=f"1e{power}",fill="#b6cddd")
        for field,color in (("p","#ffbf69"),("Ux","#22c5d6"),("Uy","#98d36b"),("Uz","#d990ed")):
            data=[h for h in histories if h["field"]==field and h["iteration"] is not None]
            points=[]
            for h in data:
                x=65+h["iteration"]/max_time*(width-90)
                y=35-min(0,max(-10,math.log10(max(h["initial"],1e-10))))/10*(height-80)
                points.extend((x,y))
            if len(points)>=4:
                c.create_line(*points,fill=color,width=1.5,tags="computed-residual")
            index=("p","Ux","Uy","Uz").index(field)
            c.create_text(90+index*100,height-20,text=field,fill=color)
        selected=float(self.report["time_name"])
        x=65+selected/max_time*(width-90)
        c.create_line(x,35,x,height-45,fill="#ffffff",dash=(4,3),tags="selected-iteration")
        c.create_text(min(x,width-100),18,anchor="w",fill="#ffffff",text=f"Selected: {selected:g}")

    def export_report(self):
        if not self.report or self.running:
            return
        target=filedialog.asksaveasfilename(parent=self,title="New report directory (must not exist)",initialfile="cleanroomx-cfd-report")
        if not target:
            return
        try:
            path=export_multizone_report(self.report,target)
        except (OSError,ValueError) as exc:
            messagebox.showerror("Report export failed",str(exc),parent=self)
            return
        self.status.set(f"Computed report exported: {path}")

    def close(self):
        if self.running:
            self.status.set("An OpenFOAM operation is running. This window remains open until execution finishes.")
            return
        self.after_cancel(self._poll_id)
        self.destroy()
