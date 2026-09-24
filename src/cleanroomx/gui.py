from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
import queue
import threading
import uuid

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import __version__
from .application import (
    ANALYSIS_SPECS,
    AnalysisRun,
    analysis_catalog,
    application_info,
    rebase_analysis_file_references,
    run_analysis,
    validate_analysis_input,
    validate_application_registry,
)
from .project import (
    AnalysisDocument,
    ProjectDocument,
    atomic_write_text,
    load_project_document,
    new_project,
    save_project_document,
)


_UNIT_SUFFIXES = (
    ("_m3_h", "m³/h"),
    ("_m3_s", "m³/s"),
    ("_kg_m3", "kg/m³"),
    ("_m2_s", "m²/s"),
    ("_m2", "m²"),
    ("_m3", "m³"),
    ("_pa", "Pa"),
    ("_kw", "kW"),
    ("_w", "W"),
    ("_c", "°C"),
    ("_percent", "%"),
    ("_minutes", "min"),
    ("_um", "µm"),
    ("_m", "m"),
)


def _reject_json_constant(value: str):
    raise ValueError(f"non-finite JSON constant is not allowed: {value}")


def _strict_json_loads(text: str):
    return json.loads(text, parse_constant=_reject_json_constant)


def unit_hint(path: str) -> str:
    key = path.rsplit(".", 1)[-1].split("[", 1)[0].lower()
    for suffix, unit in _UNIT_SUFFIXES:
        if key.endswith(suffix):
            return unit
    if key.endswith("_1_h") or key == "ach":
        return "1/h"
    return ""


def flatten_json(value, path: str = "$") -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    if isinstance(value, dict):
        if not value:
            rows.append((path, "{}", ""))
        for key, item in value.items():
            child = f"{path}.{key}"
            rows.extend(flatten_json(item, child))
    elif isinstance(value, list):
        if not value:
            rows.append((path, "[]", ""))
        for index, item in enumerate(value):
            rows.extend(flatten_json(item, f"{path}[{index}]"))
    else:
        text = json.dumps(value, ensure_ascii=False)
        rows.append((path, text, unit_hint(path)))
    return rows



def _positive_number(mapping: dict, *keys: str) -> float | None:
    """Return the first finite, positive numeric value present in *mapping*."""
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        value = float(value)
        if math.isfinite(value) and value > 0.0:
            return value
    return None


def design_rooms(payload: dict) -> list[dict]:
    """Extract lightweight room geometry for the GUI's schematic design views.

    Explicit width/length values are preferred. When only floor area (or volume
    plus height) is supplied, a square footprint is generated *for display
    only* and labelled as derived so it cannot be mistaken for design geometry.
    """
    rooms: list[dict] = []

    def visit(value, path: str) -> None:
        if isinstance(value, dict):
            geometry = value.get("geometry")
            sources = [value]
            if isinstance(geometry, dict):
                sources.append(geometry)

            width = length = height = area = volume = None
            for source in sources:
                width = width or _positive_number(
                    source, "width_m", "room_width_m", "x_length_m"
                )
                length = length or _positive_number(
                    source, "length_m", "room_length_m", "depth_m", "y_length_m"
                )
                height = height or _positive_number(
                    source, "height_m", "room_height_m", "ceiling_height_m"
                )
                area = area or _positive_number(
                    source, "floor_area_m2", "area_m2", "room_area_m2"
                )
                volume = volume or _positive_number(
                    source, "volume_m3", "room_volume_m3"
                )

            source_label = "explicit dimensions"
            if width is not None and length is not None:
                area = area or width * length
            else:
                if area is None and volume is not None and height is not None:
                    area = volume / height
                    source_label = "volume/height-derived schematic"
                elif area is not None:
                    source_label = "area-derived schematic"

                if area is not None:
                    if width is not None and length is None:
                        length = area / width
                    elif length is not None and width is None:
                        width = area / length
                    elif width is None and length is None:
                        width = math.sqrt(area)
                        length = area / width

            if width is not None and length is not None:
                name = (
                    value.get("name")
                    or value.get("room_name")
                    or value.get("id")
                    or path.rsplit(".", 1)[-1]
                )
                supply = _positive_number(
                    value, "supply_airflow_m3_h", "supply_m3_h", "airflow_m3_h"
                )
                exhaust = _positive_number(
                    value, "exhaust_airflow_m3_h", "return_airflow_m3_h"
                )
                pressure = None
                for key in (
                    "pressure_pa",
                    "differential_pressure_pa",
                    "pressure_difference_pa",
                ):
                    raw = value.get(key)
                    if (
                        not isinstance(raw, bool)
                        and isinstance(raw, (int, float))
                        and math.isfinite(float(raw))
                    ):
                        pressure = float(raw)
                        break
                rooms.append(
                    {
                        "name": str(name),
                        "width_m": float(width),
                        "length_m": float(length),
                        "height_m": None if height is None else float(height),
                        "area_m2": None if area is None else float(area),
                        "supply_airflow_m3_h": supply,
                        "exhaust_airflow_m3_h": exhaust,
                        "pressure_pa": pressure,
                        "geometry_source": source_label,
                        "path": path,
                    }
                )

            for key, item in value.items():
                if key == "geometry" and isinstance(item, dict):
                    continue
                visit(item, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]")

    visit(payload, "$")

    # Prefer named room-like records over incidental geometry nested below them.
    unique: list[dict] = []
    seen: set[tuple[str, float, float]] = set()
    for room in rooms:
        key = (
            room["name"],
            round(room["width_m"], 9),
            round(room["length_m"], 9),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(room)
    return unique[:24]


class AnalysisPicker(tk.Toplevel):
    def __init__(self, parent: tk.Misc):
        super().__init__(parent)
        self.title("Add analysis")
        self.resizable(True, True)
        self.result: str | None = None
        self.transient(parent)
        self.grab_set()

        ttk.Label(
            self,
            text="Choose a CleanroomX backend workflow",
            font=("TkDefaultFont", 11, "bold"),
        ).pack(anchor="w", padx=12, pady=(12, 6))

        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=12, pady=6)
        self.tree = ttk.Treeview(
            frame,
            columns=("category", "description"),
            show="tree headings",
            height=14,
        )
        self.tree.heading("#0", text="Analysis")
        self.tree.heading("category", text="Category")
        self.tree.heading("description", text="Description")
        self.tree.column("#0", width=230, stretch=False)
        self.tree.column("category", width=110, stretch=False)
        self.tree.column("description", width=460, stretch=True)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        for item in analysis_catalog():
            self.tree.insert(
                "",
                "end",
                iid=item["key"],
                text=item["title"],
                values=(item["category"], item["description"]),
            )

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=12, pady=(6, 12))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Add", command=self._accept).pack(
            side="right", padx=(0, 6)
        )
        self.tree.bind("<Double-1>", lambda event: self._accept())
        first = self.tree.get_children()
        if first:
            self.tree.selection_set(first[0])
            self.tree.focus(first[0])

        self.geometry("850x470")

    def _accept(self) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        self.result = selection[0]
        self.destroy()


class CleanroomXApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"CleanroomX {__version__}")
        self.root.geometry("1380x860")
        self.root.minsize(1080, 680)

        self.project: ProjectDocument = new_project()
        self.project_path: Path | None = None
        self.last_run: AnalysisRun | None = None
        self.last_run_analysis_id: str | None = None
        self._runs_by_analysis: dict[str, AnalysisRun] = {}
        self._editor_analysis_id: str | None = None
        self._selection_guard = False
        self._baseline_state: str | None = None

        self._queue: queue.Queue = queue.Queue()
        self._run_generation = 0
        self._running = False
        self._abandon_requested = False

        self.name_var = tk.StringVar(value=self.project.name)
        self.description_var = tk.StringVar(value=self.project.description)
        self.status_var = tk.StringVar(value="Ready")
        self.wrap_outputs_var = tk.BooleanVar(value=False)

        self._configure_style()
        self._build_menu()
        self._build_layout()
        self._refresh_analysis_list()
        self._capture_saved_state()
        self.name_var.trace_add("write", lambda *_: self._update_title())
        self.description_var.trace_add("write", lambda *_: self._update_title())
        self._update_title()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._poll_worker)

    def _configure_style(self) -> None:
        self.colors = {
            "bg": "#08111f",
            "panel": "#0f1b2d",
            "panel_alt": "#132238",
            "panel_soft": "#172a43",
            "border": "#263b57",
            "text": "#eef6ff",
            "muted": "#9db0c5",
            "accent": "#32b8ff",
            "accent_soft": "#173f5b",
            "success": "#32d583",
            "warning": "#f4b740",
            "danger": "#ff6b6b",
        }
        self.root.configure(background=self.colors["bg"])
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("App.TFrame", background=self.colors["bg"])
        style.configure("Panel.TFrame", background=self.colors["panel"])
        style.configure("Header.TFrame", background=self.colors["panel_alt"])
        style.configure(
            "Title.TLabel",
            background=self.colors["panel_alt"],
            foreground=self.colors["text"],
            font=("TkDefaultFont", 15, "bold"),
        )
        style.configure(
            "Subtitle.TLabel",
            background=self.colors["panel_alt"],
            foreground=self.colors["muted"],
        )
        style.configure(
            "PanelTitle.TLabel",
            background=self.colors["panel"],
            foreground=self.colors["text"],
            font=("TkDefaultFont", 10, "bold"),
        )
        style.configure(
            "Muted.TLabel",
            background=self.colors["panel"],
            foreground=self.colors["muted"],
        )
        style.configure(
            "Accent.TButton",
            padding=(12, 7),
            background=self.colors["accent"],
            foreground="#06101b",
            font=("TkDefaultFont", 9, "bold"),
        )
        style.map(
            "Accent.TButton",
            background=[("active", "#6fd0ff"), ("disabled", self.colors["border"])],
        )
        style.configure("Tool.TButton", padding=(9, 6))
        style.configure("Danger.TButton", padding=(9, 6))
        style.configure(
            "Treeview",
            rowheight=27,
            background=self.colors["panel"],
            fieldbackground=self.colors["panel"],
            foreground=self.colors["text"],
            bordercolor=self.colors["border"],
        )
        style.map(
            "Treeview",
            background=[("selected", self.colors["accent_soft"])],
            foreground=[("selected", self.colors["text"])],
        )
        style.configure(
            "Treeview.Heading",
            background=self.colors["panel_alt"],
            foreground=self.colors["text"],
            relief="flat",
        )
        style.configure(
            "TNotebook",
            background=self.colors["bg"],
            borderwidth=0,
        )
        style.configure(
            "TNotebook.Tab",
            padding=(12, 7),
            background=self.colors["panel_alt"],
            foreground=self.colors["muted"],
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", self.colors["panel_soft"])],
            foreground=[("selected", self.colors["text"])],
        )

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="New Project", accelerator="Ctrl+N", command=self.new_project)
        file_menu.add_command(label="Open Project...", accelerator="Ctrl+O", command=self.open_project)
        file_menu.add_command(label="Save Project", accelerator="Ctrl+S", command=self.save_project)
        file_menu.add_command(label="Save Project As...", command=self.save_project_as)
        file_menu.add_separator()
        file_menu.add_command(label="Import Analysis Input JSON...", command=self.import_input_json)
        file_menu.add_command(label="Export Analysis Input JSON...", command=self.export_input_json)
        file_menu.add_separator()
        file_menu.add_command(label="Export Result JSON...", command=self.export_result_json)
        file_menu.add_command(label="Export Run Bundle JSON...", command=self.export_run_bundle_json)
        file_menu.add_command(label="Export Report Markdown...", command=self.export_report_markdown)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        analysis_menu = tk.Menu(menubar, tearoff=False)
        analysis_menu.add_command(label="Add Analysis...", command=self.add_analysis)
        analysis_menu.add_command(label="Rename Analysis...", command=self.rename_analysis)
        analysis_menu.add_command(label="Remove Analysis", command=self.remove_analysis)
        analysis_menu.add_separator()
        analysis_menu.add_command(label="Validate Input", command=self.validate_current)
        analysis_menu.add_command(label="Run Analysis", accelerator="F5", command=self.run_current)
        analysis_menu.add_command(label="Abandon Current Run", command=self.cancel_run)
        menubar.add_cascade(label="Analysis", menu=analysis_menu)

        view_menu = tk.Menu(menubar, tearoff=False)
        view_menu.add_command(
            label="2D Design View",
            accelerator="Ctrl+1",
            command=lambda: self.notebook.select(self.design_2d_tab),
        )
        view_menu.add_command(
            label="3D Design View",
            accelerator="Ctrl+2",
            command=lambda: self.notebook.select(self.design_3d_tab),
        )
        view_menu.add_separator()
        view_menu.add_command(label="Refresh Structured Input", command=self.refresh_structure)
        view_menu.add_checkbutton(
            label="Wrap output text",
            variable=self.wrap_outputs_var,
            command=self._apply_wrap_setting,
        )
        menubar.add_cascade(label="View", menu=view_menu)

        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="About CleanroomX", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menubar)
        self.root.bind("<Control-n>", lambda event: self.new_project())
        self.root.bind("<Control-o>", lambda event: self.open_project())
        self.root.bind("<Control-s>", lambda event: self.save_project())
        self.root.bind("<Control-Key-1>", lambda event: self.notebook.select(self.design_2d_tab))
        self.root.bind("<Control-Key-2>", lambda event: self.notebook.select(self.design_3d_tab))
        self.root.bind("<F5>", lambda event: self.run_current())

    def _build_layout(self) -> None:
        header = ttk.Frame(self.root, style="Header.TFrame", padding=(14, 10))
        header.pack(fill="x")

        brand = ttk.Frame(header, style="Header.TFrame")
        brand.grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 18))
        ttk.Label(brand, text="CleanroomX", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            brand,
            text="Design • Simulation • Verification",
            style="Subtitle.TLabel",
        ).pack(anchor="w")

        ttk.Label(
            header,
            text="Project",
            background=self.colors["panel_alt"],
            foreground=self.colors["muted"],
        ).grid(row=0, column=1, sticky="w")
        ttk.Entry(header, textvariable=self.name_var, width=28).grid(
            row=1, column=1, sticky="ew", padx=(0, 10)
        )
        ttk.Label(
            header,
            text="Description",
            background=self.colors["panel_alt"],
            foreground=self.colors["muted"],
        ).grid(row=0, column=2, sticky="w")
        ttk.Entry(header, textvariable=self.description_var).grid(
            row=1, column=2, sticky="ew", padx=(0, 12)
        )

        action_bar = ttk.Frame(header, style="Header.TFrame")
        action_bar.grid(row=0, column=3, rowspan=2, sticky="e")
        ttk.Button(
            action_bar,
            text="Validate",
            style="Tool.TButton",
            command=self.validate_current,
        ).pack(side="left", padx=3)
        self.run_button = ttk.Button(
            action_bar,
            text="▶  Run Analysis",
            style="Accent.TButton",
            command=self.run_current,
        )
        self.run_button.pack(side="left", padx=3)
        self.cancel_button = ttk.Button(
            action_bar,
            text="Abandon",
            style="Danger.TButton",
            command=self.cancel_run,
            state="disabled",
        )
        self.cancel_button.pack(side="left", padx=3)

        header.columnconfigure(1, weight=1)
        header.columnconfigure(2, weight=2)

        panes = ttk.Panedwindow(self.root, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=10, pady=(8, 6))

        sidebar = ttk.Frame(panes, style="Panel.TFrame", padding=10)
        panes.add(sidebar, weight=1)

        ttk.Label(sidebar, text="PROJECT EXPLORER", style="PanelTitle.TLabel").pack(
            anchor="w", pady=(0, 2)
        )
        ttk.Label(
            sidebar,
            text="Analyses and engineering workflows",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(0, 8))

        tree_frame = ttk.Frame(sidebar, style="Panel.TFrame")
        tree_frame.pack(fill="both", expand=True)
        self.analysis_tree = ttk.Treeview(
            tree_frame,
            columns=("kind",),
            show="tree headings",
            selectmode="browse",
        )
        self.analysis_tree.heading("#0", text="Analysis")
        self.analysis_tree.heading("kind", text="Workflow")
        self.analysis_tree.column("#0", width=205)
        self.analysis_tree.column("kind", width=150)
        scroll = ttk.Scrollbar(
            tree_frame, orient="vertical", command=self.analysis_tree.yview
        )
        self.analysis_tree.configure(yscrollcommand=scroll.set)
        self.analysis_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.analysis_tree.bind("<<TreeviewSelect>>", self._on_analysis_selected)

        side_actions = ttk.Frame(sidebar, style="Panel.TFrame")
        side_actions.pack(fill="x", pady=(8, 0))
        ttk.Button(
            side_actions, text="+ Add", style="Tool.TButton", command=self.add_analysis
        ).pack(side="left")
        ttk.Button(
            side_actions, text="Rename", style="Tool.TButton", command=self.rename_analysis
        ).pack(side="left", padx=4)
        ttk.Button(
            side_actions, text="Remove", style="Tool.TButton", command=self.remove_analysis
        ).pack(side="left")

        content = ttk.Frame(panes, style="App.TFrame")
        panes.add(content, weight=5)
        self.notebook = ttk.Notebook(content)
        self.notebook.pack(fill="both", expand=True)

        self.design_2d_tab = ttk.Frame(self.notebook, style="Panel.TFrame")
        self.notebook.add(self.design_2d_tab, text="2D Plan")
        view2d_header = ttk.Frame(
            self.design_2d_tab, style="Panel.TFrame", padding=(12, 9)
        )
        view2d_header.pack(fill="x")
        ttk.Label(
            view2d_header,
            text="2D CLEANROOM PLAN",
            style="PanelTitle.TLabel",
        ).pack(side="left")
        ttk.Label(
            view2d_header,
            text="Schematic from project input geometry",
            style="Muted.TLabel",
        ).pack(side="left", padx=(12, 0))
        ttk.Button(
            view2d_header,
            text="Refresh",
            style="Tool.TButton",
            command=self.refresh_structure,
        ).pack(side="right")
        self.design_2d_canvas = tk.Canvas(
            self.design_2d_tab,
            background=self.colors["bg"],
            highlightthickness=0,
        )
        self.design_2d_canvas.pack(fill="both", expand=True)
        self.design_2d_canvas.bind(
            "<Configure>", lambda event: self._refresh_design_views()
        )

        self.design_3d_tab = ttk.Frame(self.notebook, style="Panel.TFrame")
        self.notebook.add(self.design_3d_tab, text="3D Model")
        view3d_header = ttk.Frame(
            self.design_3d_tab, style="Panel.TFrame", padding=(12, 9)
        )
        view3d_header.pack(fill="x")
        ttk.Label(
            view3d_header,
            text="3D CLEANROOM MODEL",
            style="PanelTitle.TLabel",
        ).pack(side="left")
        ttk.Label(
            view3d_header,
            text="Pseudo-3D engineering schematic — not CFD",
            style="Muted.TLabel",
        ).pack(side="left", padx=(12, 0))
        ttk.Button(
            view3d_header,
            text="Refresh",
            style="Tool.TButton",
            command=self.refresh_structure,
        ).pack(side="right")
        self.design_3d_canvas = tk.Canvas(
            self.design_3d_tab,
            background=self.colors["bg"],
            highlightthickness=0,
        )
        self.design_3d_canvas.pack(fill="both", expand=True)
        self.design_3d_canvas.bind(
            "<Configure>", lambda event: self._refresh_design_views()
        )

        input_tab = ttk.Frame(self.notebook, style="Panel.TFrame")
        self.notebook.add(input_tab, text="Input")
        input_notebook = ttk.Notebook(input_tab)
        input_notebook.pack(fill="both", expand=True, padx=2, pady=2)

        structured_tab = ttk.Frame(input_notebook, style="Panel.TFrame")
        input_notebook.add(structured_tab, text="Structured")
        self.structure_tree = ttk.Treeview(
            structured_tab,
            columns=("value", "unit"),
            show="tree headings",
        )
        self.structure_tree.heading("#0", text="Field path")
        self.structure_tree.heading("value", text="Value")
        self.structure_tree.heading("unit", text="Unit")
        self.structure_tree.column("#0", width=430)
        self.structure_tree.column("value", width=310)
        self.structure_tree.column("unit", width=90, stretch=False)
        struct_scroll = ttk.Scrollbar(
            structured_tab, orient="vertical", command=self.structure_tree.yview
        )
        self.structure_tree.configure(yscrollcommand=struct_scroll.set)
        self.structure_tree.pack(side="left", fill="both", expand=True)
        struct_scroll.pack(side="right", fill="y")

        json_tab = ttk.Frame(input_notebook, style="Panel.TFrame")
        input_notebook.add(json_tab, text="JSON Editor")
        self.input_text = tk.Text(
            json_tab,
            wrap="none",
            undo=True,
            background="#0b1524",
            foreground=self.colors["text"],
            insertbackground=self.colors["accent"],
            selectbackground=self.colors["accent_soft"],
            relief="flat",
            padx=10,
            pady=10,
        )
        input_scroll_y = ttk.Scrollbar(
            json_tab, orient="vertical", command=self.input_text.yview
        )
        input_scroll_x = ttk.Scrollbar(
            json_tab, orient="horizontal", command=self.input_text.xview
        )
        self.input_text.configure(
            yscrollcommand=input_scroll_y.set, xscrollcommand=input_scroll_x.set
        )
        self.input_text.grid(row=0, column=0, sticky="nsew")
        input_scroll_y.grid(row=0, column=1, sticky="ns")
        input_scroll_x.grid(row=1, column=0, sticky="ew")
        json_tab.rowconfigure(0, weight=1)
        json_tab.columnconfigure(0, weight=1)
        self.input_text.bind(
            "<FocusOut>", lambda event: self.refresh_structure(silent=True)
        )
        self.input_text.bind("<<Modified>>", self._on_input_modified)
        self.input_text.edit_modified(False)

        self.result_text = self._add_text_tab("Results")
        self.report_text = self._add_text_tab("Report")
        self.diagnostics_text = self._add_text_tab("Diagnostics")

        plot_tab = ttk.Frame(self.notebook, style="Panel.TFrame")
        self.notebook.add(plot_tab, text="Plot")
        self.plot_canvas = tk.Canvas(
            plot_tab,
            background="#f7fafc",
            highlightthickness=0,
        )
        self.plot_canvas.pack(fill="both", expand=True)
        self.plot_canvas.bind("<Configure>", lambda event: self._draw_plot())

        status_frame = ttk.Frame(self.root, style="Header.TFrame", padding=(10, 4))
        status_frame.pack(fill="x", side="bottom")
        ttk.Label(
            status_frame,
            textvariable=self.status_var,
            style="Subtitle.TLabel",
            anchor="w",
        ).pack(side="left", fill="x", expand=True)
        ttk.Label(
            status_frame,
            text=f"v{__version__}  •  F5 Run  •  Ctrl+1 2D  •  Ctrl+2 3D",
            style="Subtitle.TLabel",
        ).pack(side="right")

        self._refresh_design_views()

    def _refresh_design_views(self, payload: dict | None = None) -> None:
        if not hasattr(self, "design_2d_canvas") or not hasattr(self, "design_3d_canvas"):
            return
        if payload is None:
            if not hasattr(self, "input_text"):
                payload = {}
            else:
                text = self.input_text.get("1.0", "end-1c").strip()
                if not text:
                    payload = {}
                else:
                    try:
                        payload = _strict_json_loads(text)
                    except (json.JSONDecodeError, ValueError):
                        payload = {}
        rooms = design_rooms(payload if isinstance(payload, dict) else {})
        self._draw_design_2d(rooms)
        self._draw_design_3d(rooms)

    def _draw_design_empty(self, canvas: tk.Canvas, title: str) -> None:
        width = max(canvas.winfo_width(), 640)
        height = max(canvas.winfo_height(), 420)
        canvas.delete("all")
        canvas.create_text(
            width / 2,
            height / 2 - 24,
            text=title,
            fill=self.colors["text"],
            font=("TkDefaultFont", 13, "bold"),
        )
        canvas.create_text(
            width / 2,
            height / 2 + 14,
            text=(
                "No room geometry found in the active analysis.\n"
                "Provide width_m + length_m, floor_area_m2, or volume_m3 + height_m."
            ),
            fill=self.colors["muted"],
            justify="center",
        )

    def _draw_design_2d(self, rooms: list[dict]) -> None:
        canvas = self.design_2d_canvas
        canvas.delete("all")
        if not rooms:
            self._draw_design_empty(canvas, "2D plan is ready")
            return

        width = max(canvas.winfo_width(), 720)
        height = max(canvas.winfo_height(), 480)
        margin_x, margin_y = 42, 46
        n = len(rooms)
        cols = min(3, max(1, math.ceil(math.sqrt(n))))
        rows = math.ceil(n / cols)
        gap = 20
        cell_w = (width - 2 * margin_x - gap * (cols - 1)) / cols
        cell_h = (height - 2 * margin_y - gap * (rows - 1)) / rows

        canvas.create_text(
            margin_x,
            20,
            text=f"{n} room{'s' if n != 1 else ''} • schematic footprint",
            fill=self.colors["muted"],
            anchor="w",
        )

        for index, room in enumerate(rooms):
            row, col = divmod(index, cols)
            x0 = margin_x + col * (cell_w + gap)
            y0 = margin_y + row * (cell_h + gap)
            available_w = max(80.0, cell_w - 36)
            available_h = max(70.0, cell_h - 78)
            scale = min(
                available_w / room["width_m"],
                available_h / room["length_m"],
            )
            rw = room["width_m"] * scale
            rh = room["length_m"] * scale
            rx0 = x0 + (cell_w - rw) / 2
            ry0 = y0 + 28 + (available_h - rh) / 2
            rx1, ry1 = rx0 + rw, ry0 + rh

            canvas.create_rectangle(
                x0,
                y0,
                x0 + cell_w,
                y0 + cell_h,
                fill=self.colors["panel"],
                outline=self.colors["border"],
                width=1,
            )
            canvas.create_rectangle(
                rx0,
                ry0,
                rx1,
                ry1,
                fill=self.colors["panel_soft"],
                outline=self.colors["accent"],
                width=2,
            )
            canvas.create_text(
                x0 + 12,
                y0 + 10,
                text=room["name"],
                fill=self.colors["text"],
                anchor="nw",
                font=("TkDefaultFont", 10, "bold"),
            )
            canvas.create_text(
                (rx0 + rx1) / 2,
                ry0 - 8,
                text=f'{room["width_m"]:.2f} m',
                fill=self.colors["muted"],
                anchor="s",
            )
            canvas.create_text(
                rx0 - 8,
                (ry0 + ry1) / 2,
                text=f'{room["length_m"]:.2f} m',
                fill=self.colors["muted"],
                anchor="e",
                angle=90,
            )

            details = []
            if room["area_m2"] is not None:
                details.append(f'Area {room["area_m2"]:.1f} m²')
            if room["supply_airflow_m3_h"] is not None:
                details.append(f'Supply {room["supply_airflow_m3_h"]:.0f} m³/h')
            if room["pressure_pa"] is not None:
                details.append(f'ΔP {room["pressure_pa"]:.1f} Pa')
            canvas.create_text(
                x0 + 12,
                y0 + cell_h - 12,
                text="  •  ".join(details) if details else room["geometry_source"],
                fill=self.colors["muted"],
                anchor="sw",
            )
            if room["geometry_source"] != "explicit dimensions":
                canvas.create_text(
                    x0 + cell_w - 12,
                    y0 + 10,
                    text="DERIVED",
                    fill=self.colors["warning"],
                    anchor="ne",
                    font=("TkDefaultFont", 8, "bold"),
                )

    def _draw_design_3d(self, rooms: list[dict]) -> None:
        canvas = self.design_3d_canvas
        canvas.delete("all")
        if not rooms:
            self._draw_design_empty(canvas, "3D model is ready")
            return

        width = max(canvas.winfo_width(), 720)
        height = max(canvas.winfo_height(), 480)
        n = len(rooms)
        cols = min(3, max(1, math.ceil(math.sqrt(n))))
        rows = math.ceil(n / cols)
        margin_x, margin_y, gap = 46, 54, 22
        cell_w = (width - 2 * margin_x - gap * (cols - 1)) / cols
        cell_h = (height - 2 * margin_y - gap * (rows - 1)) / rows

        canvas.create_text(
            margin_x,
            22,
            text="Pseudo-3D schematic • dimensions come from the active analysis input",
            fill=self.colors["muted"],
            anchor="w",
        )

        for index, room in enumerate(rooms):
            row, col = divmod(index, cols)
            x0 = margin_x + col * (cell_w + gap)
            y0 = margin_y + row * (cell_h + gap)
            canvas.create_rectangle(
                x0,
                y0,
                x0 + cell_w,
                y0 + cell_h,
                fill=self.colors["panel"],
                outline=self.colors["border"],
            )

            ratio = room["width_m"] / max(room["length_m"], 1e-9)
            base_w = min(cell_w * 0.58, 210.0)
            base_w = max(95.0, min(base_w * math.sqrt(max(ratio, 0.25)), cell_w * 0.68))
            depth = min(cell_h * 0.22, 62.0)
            depth = max(28.0, depth / math.sqrt(max(ratio, 0.25)))
            if room["height_m"] is None:
                prism_h = min(72.0, cell_h * 0.34)
            else:
                prism_h = min(105.0, max(42.0, room["height_m"] * 18.0))

            cx = x0 + cell_w / 2
            floor_y = y0 + cell_h * 0.70
            skew = depth * 0.78
            p0 = (cx - base_w / 2, floor_y)
            p1 = (cx + base_w / 2, floor_y)
            p2 = (cx + base_w / 2 + skew, floor_y - depth)
            p3 = (cx - base_w / 2 + skew, floor_y - depth)
            t0 = (p0[0], p0[1] - prism_h)
            t1 = (p1[0], p1[1] - prism_h)
            t2 = (p2[0], p2[1] - prism_h)
            t3 = (p3[0], p3[1] - prism_h)

            canvas.create_polygon(
                *p0, *p1, *t1, *t0,
                fill="#112b40",
                outline=self.colors["accent"],
                width=1,
            )
            canvas.create_polygon(
                *p1, *p2, *t2, *t1,
                fill="#173a52",
                outline=self.colors["accent"],
                width=1,
            )
            canvas.create_polygon(
                *t0, *t1, *t2, *t3,
                fill="#1c4b69",
                outline=self.colors["accent"],
                width=2,
            )
            canvas.create_polygon(
                *p0, *p1, *p2, *p3,
                fill="",
                outline=self.colors["border"],
            )

            top_center_x = sum(point[0] for point in (t0, t1, t2, t3)) / 4
            top_center_y = sum(point[1] for point in (t0, t1, t2, t3)) / 4
            canvas.create_line(
                top_center_x,
                top_center_y - 22,
                top_center_x,
                top_center_y + 22,
                fill=self.colors["success"],
                width=3,
                arrow=tk.LAST,
            )
            canvas.create_text(
                x0 + 12,
                y0 + 10,
                text=room["name"],
                fill=self.colors["text"],
                anchor="nw",
                font=("TkDefaultFont", 10, "bold"),
            )
            height_text = (
                f'{room["height_m"]:.2f} m high'
                if room["height_m"] is not None
                else "height not supplied"
            )
            canvas.create_text(
                x0 + 12,
                y0 + cell_h - 28,
                text=f'{room["width_m"]:.2f} × {room["length_m"]:.2f} m • {height_text}',
                fill=self.colors["muted"],
                anchor="sw",
            )
            canvas.create_text(
                x0 + 12,
                y0 + cell_h - 10,
                text=room["geometry_source"],
                fill=(
                    self.colors["muted"]
                    if room["geometry_source"] == "explicit dimensions"
                    else self.colors["warning"]
                ),
                anchor="sw",
            )

    def _add_text_tab(self, title: str) -> tk.Text:
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=title)
        text = tk.Text(
            frame,
            wrap="none",
            state="disabled",
            background="#0b1524",
            foreground=self.colors["text"],
            insertbackground=self.colors["accent"],
            selectbackground=self.colors["accent_soft"],
            relief="flat",
            padx=10,
            pady=10,
        )
        yscroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        xscroll = ttk.Scrollbar(frame, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        return text

    def _apply_wrap_setting(self) -> None:
        wrap = "word" if self.wrap_outputs_var.get() else "none"
        for widget in (self.result_text, self.report_text, self.diagnostics_text):
            widget.configure(wrap=wrap)

    def _set_text(self, widget: tk.Text, value: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def _clear_rendered_run(self) -> None:
        self.last_run = None
        self.last_run_analysis_id = None
        self._set_text(self.result_text, "")
        self._set_text(self.report_text, "")
        self._set_text(self.diagnostics_text, "")
        self._draw_plot()

    def _clear_run_cache(self) -> None:
        self._runs_by_analysis.clear()
        self._clear_rendered_run()

    def _invalidate_last_run_for(self, analysis_id: str | None) -> None:
        if analysis_id is None:
            return
        self._runs_by_analysis.pop(analysis_id, None)
        if self.last_run_analysis_id == analysis_id:
            self._clear_rendered_run()

    def _restore_run_for(self, analysis_id: str) -> bool:
        run = self._runs_by_analysis.get(analysis_id)
        if run is None:
            self._clear_rendered_run()
            return False
        self.last_run = run
        self.last_run_analysis_id = analysis_id
        self._render_run(run, select_results=False)
        return True

    def _on_input_modified(self, event=None) -> None:
        if not self.input_text.edit_modified():
            return
        self.input_text.edit_modified(False)
        self._invalidate_last_run_for(self._editor_analysis_id)
        self._update_title()

    def _current_analysis(self) -> AnalysisDocument | None:
        selection = self.analysis_tree.selection()
        if not selection:
            return None
        try:
            return self.project.analysis_by_id(selection[0])
        except KeyError:
            return None

    def _editor_analysis(self) -> AnalysisDocument | None:
        if self._editor_analysis_id is None:
            return None
        try:
            return self.project.analysis_by_id(self._editor_analysis_id)
        except KeyError:
            return None

    def _commit_editor(self, analysis: AnalysisDocument | None = None) -> AnalysisDocument:
        analysis = analysis or self._editor_analysis() or self._current_analysis()
        if analysis is None:
            raise ValueError("select or add an analysis first")
        try:
            payload = _strict_json_loads(self.input_text.get("1.0", "end-1c"))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"input JSON is invalid at line {exc.lineno}, column {exc.colno}: {exc.msg}"
            ) from exc
        if not isinstance(payload, dict):
            raise ValueError("analysis input must be a JSON object")
        analysis.input = payload
        self._sync_metadata()
        return analysis

    def _sync_metadata(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            raise ValueError("project name cannot be empty")
        self.project.name = name
        self.project.description = self.description_var.get()

    def _base_dir(self) -> Path | None:
        return None if self.project_path is None else self.project_path.parent

    def _project_state_signature(self) -> str:
        data = copy.deepcopy(self.project.to_dict())
        name = self.name_var.get().strip()
        if not name:
            raise ValueError("project name cannot be empty")
        data["project"]["name"] = name
        data["project"]["description"] = self.description_var.get()

        if self._editor_analysis_id is not None:
            text = self.input_text.get("1.0", "end-1c")
            try:
                payload = _strict_json_loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"input JSON is invalid at line {exc.lineno}, column {exc.colno}: {exc.msg}"
                ) from exc
            if not isinstance(payload, dict):
                raise ValueError("analysis input must be a JSON object")
            for analysis in data["analyses"]:
                if analysis["id"] == self._editor_analysis_id:
                    analysis["input"] = payload
                    break

        return json.dumps(
            data, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        )

    def _has_unsaved_changes(self) -> bool:
        baseline = getattr(self, "_baseline_state", None)
        if baseline is None:
            return False
        try:
            return self._project_state_signature() != baseline
        except Exception:
            return True

    def _capture_saved_state(self) -> None:
        self._baseline_state = self._project_state_signature()
        self._update_title()

    def _confirm_project_replacement(self) -> bool:
        if not self._has_unsaved_changes():
            return True
        choice = messagebox.askyesnocancel(
            "Unsaved changes",
            "Save changes to the current project before continuing?",
            parent=self.root,
        )
        if choice is None:
            return False
        if choice:
            self.save_project()
            return not self._has_unsaved_changes()
        return True

    def _refresh_analysis_list(self, select_id: str | None = None) -> None:
        for item in self.analysis_tree.get_children():
            self.analysis_tree.delete(item)
        for analysis in self.project.analyses:
            self.analysis_tree.insert(
                "",
                "end",
                iid=analysis.id,
                text=analysis.name,
                values=(analysis.kind,),
            )
        target = select_id or self.project.active_analysis_id
        if target and self.analysis_tree.exists(target):
            self.analysis_tree.selection_set(target)
            self.analysis_tree.focus(target)
            self.analysis_tree.see(target)
            self._load_analysis_into_editor(self.project.analysis_by_id(target))
        elif self.project.analyses:
            first = self.project.analyses[0].id
            self.project.active_analysis_id = first
            self.analysis_tree.selection_set(first)
            self.analysis_tree.focus(first)
            self._load_analysis_into_editor(self.project.analyses[0])
        else:
            self._editor_analysis_id = None
            self.input_text.delete("1.0", "end")
            self.input_text.edit_modified(False)
            self.refresh_structure(silent=True)

    def _on_analysis_selected(self, event=None) -> None:
        if self._selection_guard:
            return
        analysis = self._current_analysis()
        if analysis is None:
            return
        previous = self._editor_analysis()
        if self._running and previous is not None and previous.id != analysis.id:
            self._selection_guard = True
            try:
                if self.analysis_tree.exists(previous.id):
                    self.analysis_tree.selection_set(previous.id)
                    self.analysis_tree.focus(previous.id)
                    self.analysis_tree.see(previous.id)
            finally:
                self._selection_guard = False
            self.status_var.set(
                f"Running {previous.name} — abandon the current run before switching analyses."
            )
            return
        if previous is not None and previous.id != analysis.id:
            try:
                self._commit_editor(previous)
            except Exception as exc:
                self._selection_guard = True
                try:
                    if self.analysis_tree.exists(previous.id):
                        self.analysis_tree.selection_set(previous.id)
                        self.analysis_tree.focus(previous.id)
                        self.analysis_tree.see(previous.id)
                finally:
                    self._selection_guard = False
                messagebox.showerror(
                    "Cannot switch analysis",
                    f"Fix the current analysis input before switching.\n\n{exc}",
                    parent=self.root,
                )
                return
        self.project.active_analysis_id = analysis.id
        self._load_analysis_into_editor(analysis)
        self._update_title()

    def _load_analysis_into_editor(self, analysis: AnalysisDocument) -> None:
        self._editor_analysis_id = analysis.id
        self.input_text.delete("1.0", "end")
        self.input_text.insert(
            "1.0",
            json.dumps(analysis.input, indent=2, ensure_ascii=False, sort_keys=False),
        )
        self.input_text.edit_modified(False)
        self.status_var.set(f"{analysis.name} — {ANALYSIS_SPECS[analysis.kind].title}")
        self.refresh_structure(silent=True)
        self._restore_run_for(analysis.id)

    def refresh_structure(self, silent: bool = False) -> None:
        for item in self.structure_tree.get_children():
            self.structure_tree.delete(item)
        text = self.input_text.get("1.0", "end-1c").strip()
        if not text:
            return
        try:
            payload = _strict_json_loads(text)
        except (json.JSONDecodeError, ValueError) as exc:
            if not silent:
                detail = (
                    f"Line {exc.lineno}, column {exc.colno}: {exc.msg}"
                    if isinstance(exc, json.JSONDecodeError)
                    else str(exc)
                )
                messagebox.showerror("Invalid JSON", detail, parent=self.root)
            return
        self._refresh_design_views(payload)
        for index, (path, value, unit) in enumerate(flatten_json(payload)):
            display = value if len(value) <= 160 else value[:157] + "..."
            self.structure_tree.insert(
                "", "end", iid=f"row-{index}", text=path, values=(display, unit)
            )

    def new_project(self) -> None:
        if self._running:
            messagebox.showwarning("Analysis running", "Abandon the current run first.")
            return
        if not self._confirm_project_replacement():
            return
        self.project = new_project()
        self.project_path = None
        self.name_var.set(self.project.name)
        self.description_var.set("")
        self._clear_run_cache()
        self._refresh_analysis_list()
        self._capture_saved_state()
        self.status_var.set("New project")
        self._update_title()

    def open_project(self) -> None:
        if self._running:
            messagebox.showwarning("Analysis running", "Abandon the current run first.")
            return
        path = filedialog.askopenfilename(
            parent=self.root,
            title="Open CleanroomX project",
            filetypes=[
                ("CleanroomX project", "*.cleanroomx.json"),
                ("JSON files", "*.json"),
                ("All files", "*.*"),
            ],
        )
        if path:
            if not self._confirm_project_replacement():
                return
            try:
                self.load_project_path(path)
            except Exception as exc:
                messagebox.showerror("Open failed", str(exc), parent=self.root)

    def load_project_path(self, path: str | Path) -> None:
        project_path = Path(path)
        project = load_project_document(project_path)
        self.project = project
        self.project_path = project_path
        self.name_var.set(project.name)
        self.description_var.set(project.description)
        self._clear_run_cache()
        self._refresh_analysis_list()
        self._capture_saved_state()
        self.status_var.set(f"Opened {project_path.name}")
        self._update_title()

    def _update_title(self) -> None:
        title_method = getattr(self.root, "title", None)
        if not callable(title_method):
            return
        suffix = "" if self.project_path is None else f" — {self.project_path.name}"
        dirty = " *" if self._has_unsaved_changes() else ""
        title_method(f"CleanroomX {__version__}{suffix}{dirty}")

    def save_project(self) -> None:
        try:
            if self._editor_analysis() is not None:
                self._commit_editor()
            else:
                self._sync_metadata()
        except Exception as exc:
            messagebox.showerror("Cannot save", str(exc), parent=self.root)
            return
        if self.project_path is None:
            self.save_project_as()
            return
        try:
            save_project_document(self.project_path, self.project)
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc), parent=self.root)
            return
        self._capture_saved_state()
        self.status_var.set(f"Saved {self.project_path.name}")

    def save_project_as(self) -> None:
        try:
            if self._editor_analysis() is not None:
                self._commit_editor()
            else:
                self._sync_metadata()
        except Exception as exc:
            messagebox.showerror("Cannot save", str(exc), parent=self.root)
            return
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Save CleanroomX project",
            defaultextension=".cleanroomx.json",
            filetypes=[("CleanroomX project", "*.cleanroomx.json"), ("JSON files", "*.json")],
        )
        if not path:
            return

        destination = Path(path)
        previous_base = self._base_dir()
        editor_id = self._editor_analysis_id
        candidate = copy.deepcopy(self.project)
        if (
            previous_base is not None
            and previous_base.resolve() != destination.parent.resolve()
        ):
            for analysis in candidate.analyses:
                analysis.input = rebase_analysis_file_references(
                    analysis.kind,
                    analysis.input,
                    source_base=previous_base,
                    target_base=destination.parent,
                )

        try:
            saved_path = save_project_document(destination, candidate)
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc), parent=self.root)
            return

        self.project = candidate
        self.project_path = saved_path
        if previous_base is not None and self._base_dir() != previous_base:
            self._clear_run_cache()
        if editor_id is not None:
            try:
                self._load_analysis_into_editor(self.project.analysis_by_id(editor_id))
            except KeyError:
                self._refresh_analysis_list()
        self._capture_saved_state()
        self.status_var.set(f"Saved {self.project_path.name}")
        self._update_title()

    def add_analysis(self) -> None:
        if self._running:
            messagebox.showwarning("Analysis running", "Abandon the current run first.")
            return
        previous = self._editor_analysis()
        if previous is not None:
            try:
                self._commit_editor(previous)
            except Exception as exc:
                messagebox.showerror(
                    "Cannot add analysis",
                    f"Fix the current analysis input before adding another analysis.\n\n{exc}",
                    parent=self.root,
                )
                return
        picker = AnalysisPicker(self.root)
        self.root.wait_window(picker)
        if picker.result is None:
            return
        kind = picker.result
        spec = ANALYSIS_SPECS[kind]
        analysis_id = f"{kind}-{uuid.uuid4().hex[:8]}"
        payload = {"name": "New Dossier"} if kind == "dossier" else {}
        analysis = AnalysisDocument(
            id=analysis_id,
            name=spec.title,
            kind=kind,
            input=payload,
        )
        self.project.analyses.append(analysis)
        self.project.active_analysis_id = analysis_id
        self._refresh_analysis_list(select_id=analysis_id)
        self._update_title()

    def rename_analysis(self) -> None:
        if self._running:
            messagebox.showwarning("Analysis running", "Abandon the current run first.")
            return
        analysis = self._current_analysis()
        if analysis is None:
            return
        value = simpledialog.askstring(
            "Rename analysis", "Analysis name", initialvalue=analysis.name, parent=self.root
        )
        if value and value.strip():
            analysis.name = value.strip()
            self.analysis_tree.item(analysis.id, text=analysis.name)
            self._update_title()

    def remove_analysis(self) -> None:
        if self._running:
            messagebox.showwarning("Analysis running", "Abandon the current run first.")
            return
        analysis = self._current_analysis()
        if analysis is None:
            return
        if not messagebox.askyesno(
            "Remove analysis",
            f"Remove {analysis.name!r} from this project?",
            parent=self.root,
        ):
            return
        self._invalidate_last_run_for(analysis.id)
        self.project.analyses = [item for item in self.project.analyses if item.id != analysis.id]
        self.project.active_analysis_id = (
            self.project.analyses[0].id if self.project.analyses else None
        )
        self._refresh_analysis_list()
        self._update_title()

    def import_input_json(self) -> None:
        if self._running:
            messagebox.showwarning("Analysis running", "Abandon the current run first.")
            return
        analysis = self._current_analysis()
        if analysis is None:
            messagebox.showinfo("No analysis", "Add or select an analysis first.")
            return
        path = filedialog.askopenfilename(
            parent=self.root,
            title="Import analysis input JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        source_path = Path(path)
        try:
            payload = _strict_json_loads(source_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("input file must contain a JSON object")
            payload = rebase_analysis_file_references(
                analysis.kind,
                payload,
                source_base=source_path.parent,
                target_base=self._base_dir(),
            )
        except Exception as exc:
            messagebox.showerror("Import failed", str(exc), parent=self.root)
            return
        analysis.input = payload
        self._invalidate_last_run_for(analysis.id)
        self._load_analysis_into_editor(analysis)
        self.status_var.set(f"Imported {source_path.name}")
        self._update_title()

    def _write_export_file(self, path: str, content: str, *, label: str) -> bool:
        target = Path(path)
        try:
            atomic_write_text(target, content)
        except Exception as exc:
            self.status_var.set(f"{label} export failed")
            messagebox.showerror(
                f"{label} export failed",
                str(exc),
                parent=self.root,
            )
            return False
        self.status_var.set(f"Exported {label.lower()} — {target.name}")
        return True

    def export_input_json(self) -> None:
        try:
            analysis = self._commit_editor()
        except Exception as exc:
            messagebox.showerror("Cannot export", str(exc), parent=self.root)
            return
        path = filedialog.asksaveasfilename(
            parent=self.root, defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
        )
        if path:
            self._write_export_file(
                path,
                json.dumps(
                    analysis.input, indent=2, ensure_ascii=False, allow_nan=False
                ) + "\n",
                label="Input",
            )

    def validate_current(self) -> None:
        try:
            analysis = self._commit_editor()
            validate_analysis_input(analysis.kind, analysis.input, base_dir=self._base_dir())
        except Exception as exc:
            self.status_var.set("Validation failed")
            messagebox.showerror("Validation failed", str(exc), parent=self.root)
            return
        self.refresh_structure(silent=True)
        self.status_var.set(f"Input valid — {analysis.name}")
        messagebox.showinfo("Validation", "Input is valid for the selected backend workflow.")

    def run_current(self) -> None:
        if self._running:
            return
        try:
            analysis = self._commit_editor()
            validate_analysis_input(analysis.kind, analysis.input, base_dir=self._base_dir())
        except Exception as exc:
            self.status_var.set("Cannot run — invalid input")
            messagebox.showerror("Cannot run analysis", str(exc), parent=self.root)
            return

        self._run_generation += 1
        generation = self._run_generation
        analysis_id = analysis.id
        kind = analysis.kind
        payload = copy.deepcopy(analysis.input)
        base_dir = self._base_dir()
        self._abandon_requested = False
        self._set_running(True)
        self.status_var.set(f"Running {analysis.name}...")

        def worker() -> None:
            try:
                result = run_analysis(kind, payload, base_dir=base_dir)
                self._queue.put(("success", generation, analysis_id, result))
            except Exception as exc:
                self._queue.put(("error", generation, analysis_id, str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def cancel_run(self) -> None:
        if not self._running or self._abandon_requested:
            return
        self._abandon_requested = True
        self.cancel_button.configure(state="disabled")
        self.status_var.set(
            "Run abandoned in the UI; waiting for the backend worker to finish before another run."
        )

    def _set_running(self, running: bool) -> None:
        self._running = running
        self.run_button.configure(state="disabled" if running else "normal")
        self.cancel_button.configure(state="normal" if running else "disabled")
        self.input_text.configure(state="disabled" if running else "normal")

    def _poll_worker(self) -> None:
        try:
            while True:
                kind, generation, analysis_id, payload = self._queue.get_nowait()
                if generation != self._run_generation:
                    continue
                if self._abandon_requested:
                    self._abandon_requested = False
                    self._set_running(False)
                    self.status_var.set("Run abandoned; backend worker finished. Ready.")
                    continue
                self._set_running(False)
                if kind == "error":
                    self.status_var.set("Analysis failed")
                    messagebox.showerror("Analysis failed", str(payload), parent=self.root)
                else:
                    self._runs_by_analysis[analysis_id] = payload
                    self.last_run = payload
                    self.last_run_analysis_id = analysis_id
                    self._render_run(payload)
                    self.status_var.set(
                        f"Completed — {payload.title} — status: {payload.status}"
                    )
        except queue.Empty:
            pass
        self.root.after(100, self._poll_worker)

    def _render_run(self, run: AnalysisRun, *, select_results: bool = True) -> None:
        self._set_text(
            self.result_text,
            json.dumps(run.result, indent=2, ensure_ascii=False, allow_nan=False),
        )
        self._set_text(self.report_text, run.markdown)
        self._set_text(
            self.diagnostics_text,
            json.dumps(run.diagnostics, indent=2, ensure_ascii=False, allow_nan=False),
        )
        self._draw_plot()
        if select_results:
            self.notebook.select(self.result_text.master)

    def _draw_plot(self) -> None:
        canvas = self.plot_canvas
        canvas.delete("all")
        run = self.last_run
        if run is None or run.plot is None:
            canvas.create_text(
                max(canvas.winfo_width() / 2, 150),
                max(canvas.winfo_height() / 2, 100),
                text="No plot is available for the selected result.",
            )
            return
        plot = run.plot
        width = max(canvas.winfo_width(), 500)
        height = max(canvas.winfo_height(), 350)
        left, right, top, bottom = 70, 30, 45, 60
        xs = [x for series in plot["series"] for x in series["x"]]
        ys = [y for series in plot["series"] for y in series["y"]]
        xs += [m["x"] for m in plot.get("markers", [])]
        ys += [m["y"] for m in plot.get("markers", [])]
        if not xs or not ys:
            return
        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(ys), max(ys)
        if xmax == xmin:
            xmax = xmin + 1.0
        if ymax == ymin:
            ymax = ymin + 1.0
        xpad = (xmax - xmin) * 0.05
        ypad = (ymax - ymin) * 0.08
        xmin, xmax = xmin - xpad, xmax + xpad
        ymin, ymax = ymin - ypad, ymax + ypad

        def point(x, y):
            px = left + (x - xmin) / (xmax - xmin) * (width - left - right)
            py = height - bottom - (y - ymin) / (ymax - ymin) * (height - top - bottom)
            return px, py

        canvas.create_line(left, height - bottom, width - right, height - bottom)
        canvas.create_line(left, top, left, height - bottom)
        canvas.create_text(width / 2, 18, text=plot["title"], font=("TkDefaultFont", 11, "bold"))
        canvas.create_text(width / 2, height - 20, text=plot["x_label"])
        canvas.create_text(18, height / 2, text=plot["y_label"], angle=90)
        canvas.create_text(left, height - bottom + 18, text=f"{xmin:.3g}", anchor="n")
        canvas.create_text(width - right, height - bottom + 18, text=f"{xmax:.3g}", anchor="n")
        canvas.create_text(left - 8, height - bottom, text=f"{ymin:.3g}", anchor="e")
        canvas.create_text(left - 8, top, text=f"{ymax:.3g}", anchor="e")

        for index, series in enumerate(plot["series"]):
            coords = []
            for x, y in zip(series["x"], series["y"]):
                coords.extend(point(x, y))
            line_options = {"width": 2}
            if index % 2:
                line_options["dash"] = (6, 4)
            if len(coords) >= 4:
                canvas.create_line(*coords, **line_options)
            for x, y in zip(series["x"], series["y"]):
                px, py = point(x, y)
                canvas.create_oval(px - 2, py - 2, px + 2, py + 2, fill="black")

            legend_x = max(left + 20, width - right - 170)
            legend_y = top + index * 18
            canvas.create_line(
                legend_x,
                legend_y,
                legend_x + 28,
                legend_y,
                **line_options,
            )
            canvas.create_text(
                legend_x + 34,
                legend_y,
                text=series.get("name", f"Series {index + 1}"),
                anchor="w",
            )

        for marker in plot.get("markers", []):
            px, py = point(marker["x"], marker["y"])
            canvas.create_oval(px - 6, py - 6, px + 6, py + 6, width=2)
            canvas.create_text(px + 8, py - 8, text=marker["name"], anchor="sw")

    def export_result_json(self) -> None:
        if self.last_run is None:
            messagebox.showinfo("No result", "Run an analysis first.")
            return
        path = filedialog.asksaveasfilename(
            parent=self.root, defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
        )
        if path:
            self._write_export_file(
                path,
                json.dumps(
                    self.last_run.result, indent=2, ensure_ascii=False, allow_nan=False
                ) + "\n",
                label="Result",
            )

    def export_run_bundle_json(self) -> None:
        if self.last_run is None:
            messagebox.showinfo("No result", "Run an analysis first.")
            return
        path = filedialog.asksaveasfilename(
            parent=self.root, defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
        )
        if path:
            self._write_export_file(
                path,
                json.dumps(
                    self.last_run.to_dict(),
                    indent=2,
                    ensure_ascii=False,
                    allow_nan=False,
                ) + "\n",
                label="Run bundle",
            )

    def export_report_markdown(self) -> None:
        if self.last_run is None:
            messagebox.showinfo("No report", "Run an analysis first.")
            return
        path = filedialog.asksaveasfilename(
            parent=self.root, defaultextension=".md",
            filetypes=[("Markdown files", "*.md"), ("Text files", "*.txt")],
        )
        if path:
            self._write_export_file(path, self.last_run.markdown, label="Report")

    def show_about(self) -> None:
        messagebox.showinfo(
            "About CleanroomX",
            (
                f"CleanroomX {__version__}\n\n"
                f"{len(ANALYSIS_SPECS)} backend workflows are available through the application layer.\n\n"
                "CleanroomX provides engineering screening and numerical/provenance evidence. "
                "It does not by itself establish cleanroom certification, CFD validation, "
                "commissioning/TAB acceptance, manufacturer approval, or regulatory compliance."
            ),
            parent=self.root,
        )

    def smoke_run_active(self) -> AnalysisRun:
        analysis = self._current_analysis()
        if analysis is None:
            raise ValueError("smoke project has no active analysis")
        run = run_analysis(analysis.kind, analysis.input, base_dir=self._base_dir())
        self._runs_by_analysis[analysis.id] = run
        self.last_run = run
        self.last_run_analysis_id = analysis.id
        self._render_run(run)
        return run

    def _on_close(self) -> None:
        if self._running and not messagebox.askyesno(
            "Analysis running",
            "A backend analysis is still running. Close CleanroomX anyway?",
            parent=self.root,
        ):
            return
        if not self._confirm_project_replacement():
            return
        self.root.destroy()


def bundled_demo_project_path() -> Path:
    """Return the self-contained demonstration project shipped in the package."""
    path = Path(__file__).resolve().parent / "demo" / "gui_demo.cleanroomx.json"
    if not path.is_file():
        raise FileNotFoundError(f"bundled CleanroomX demo is missing: {path}")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-gui",
        description="CleanroomX desktop engineering application",
    )
    parser.add_argument("project", nargs="?", help="Optional CleanroomX project file to open")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Open the self-contained demonstration project bundled with CleanroomX",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate GUI/application imports and print capability information without opening a window",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Open the real Tk GUI, optionally load a project, run its active analysis, then exit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.demo and args.project:
        parser.error("project path and --demo cannot be used together")
    if args.check:
        print(json.dumps(application_info(), indent=2, ensure_ascii=False))
        return 0

    validate_application_registry()
    project_path = bundled_demo_project_path() if args.demo else args.project

    root = tk.Tk()
    app = CleanroomXApp(root)
    if project_path:
        try:
            app.load_project_path(project_path)
        except Exception as exc:
            if args.smoke:
                root.destroy()
                print(f"CleanroomX GUI smoke: FAIL — {exc}")
                return 2
            messagebox.showerror("Open failed", str(exc), parent=root)

    if args.smoke:
        if project_path and app.project.analyses:
            run = app.smoke_run_active()
            json.dumps(run.to_dict(), allow_nan=False)
        root.update_idletasks()
        root.update()
        root.destroy()
        print("CleanroomX GUI smoke: PASS")
        return 0

    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
