from __future__ import annotations

import argparse
import copy
import json
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
from .spatial import SpatialDesignWorkspace, sync_layout_to_analysis


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
        self.root.geometry("1440x900")
        self.root.minsize(1050, 680)
        self._configure_style()

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
        self.run_state_var = tk.StringVar(value="READY")
        self.wrap_outputs_var = tk.BooleanVar(value=False)

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
        """Apply a compact engineering-workbench theme without external UI dependencies."""
        self._colors = {
            "bg": "#08111f",
            "surface": "#0f1b2d",
            "surface_alt": "#132238",
            "editor": "#0a1424",
            "border": "#23364d",
            "text": "#e6edf7",
            "muted": "#93a4ba",
            "accent": "#16a3d6",
            "accent_active": "#0d8fbd",
            "danger": "#c84b5a",
            "success": "#4fb286",
        }
        style = ttk.Style(self.root)
        try:
            if "clam" in style.theme_names():
                style.theme_use("clam")
        except tk.TclError:
            pass

        self.root.configure(background=self._colors["bg"])
        style.configure(
            ".",
            font=("TkDefaultFont", 10),
            background=self._colors["bg"],
            foreground=self._colors["text"],
        )
        style.configure("App.TFrame", background=self._colors["bg"])
        style.configure("Surface.TFrame", background=self._colors["surface"])
        style.configure("Header.TFrame", background=self._colors["surface_alt"])
        style.configure(
            "Brand.TLabel",
            background=self._colors["surface_alt"],
            foreground="#ffffff",
            font=("TkDefaultFont", 15, "bold"),
        )
        style.configure(
            "Subtitle.TLabel",
            background=self._colors["surface_alt"],
            foreground=self._colors["muted"],
        )
        style.configure(
            "Section.TLabel",
            background=self._colors["surface"],
            foreground="#ffffff",
            font=("TkDefaultFont", 10, "bold"),
        )
        style.configure(
            "Muted.TLabel",
            background=self._colors["surface"],
            foreground=self._colors["muted"],
        )
        style.configure(
            "Status.TLabel",
            background=self._colors["surface_alt"],
            foreground=self._colors["muted"],
            padding=(10, 5),
        )
        style.configure(
            "RunState.TLabel",
            background="#17324a",
            foreground="#9bdcf5",
            font=("TkDefaultFont", 9, "bold"),
            padding=(9, 5),
        )
        style.configure(
            "TButton",
            padding=(9, 5),
            background=self._colors["surface_alt"],
            foreground=self._colors["text"],
            borderwidth=1,
            relief="flat",
        )
        style.map(
            "TButton",
            background=[("active", "#1b3150"), ("pressed", "#1f395c")],
            foreground=[("disabled", "#60738a")],
        )
        style.configure(
            "Accent.TButton",
            background=self._colors["accent"],
            foreground="#ffffff",
            font=("TkDefaultFont", 10, "bold"),
            padding=(12, 6),
        )
        style.map(
            "Accent.TButton",
            background=[
                ("active", self._colors["accent_active"]),
                ("pressed", "#08789f"),
                ("disabled", "#31556a"),
            ],
        )
        style.configure(
            "Danger.TButton",
            background="#5a2631",
            foreground="#ffd9df",
        )
        style.map("Danger.TButton", background=[("active", "#763440")])
        style.configure(
            "TEntry",
            fieldbackground=self._colors["editor"],
            foreground=self._colors["text"],
            insertcolor=self._colors["text"],
            bordercolor=self._colors["border"],
            lightcolor=self._colors["border"],
            darkcolor=self._colors["border"],
            padding=5,
        )
        style.configure(
            "Treeview",
            background=self._colors["editor"],
            fieldbackground=self._colors["editor"],
            foreground=self._colors["text"],
            rowheight=27,
            borderwidth=0,
        )
        style.map(
            "Treeview",
            background=[("selected", "#174d68")],
            foreground=[("selected", "#ffffff")],
        )
        style.configure(
            "Treeview.Heading",
            background=self._colors["surface_alt"],
            foreground=self._colors["muted"],
            relief="flat",
            padding=(6, 5),
        )
        style.map("Treeview.Heading", background=[("active", "#1a2e49")])
        style.configure("Workbench.TNotebook", background=self._colors["bg"], borderwidth=0)
        style.configure(
            "Workbench.TNotebook.Tab",
            background=self._colors["surface"],
            foreground=self._colors["muted"],
            padding=(14, 8),
            borderwidth=0,
        )
        style.map(
            "Workbench.TNotebook.Tab",
            background=[("selected", self._colors["surface_alt"]), ("active", "#152741")],
            foreground=[("selected", "#ffffff"), ("active", "#ffffff")],
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
        view_menu.add_command(label="Refresh Structured Input", command=self.refresh_structure)
        view_menu.add_command(
            label="Refresh Spatial Workspace",
            command=lambda: self.spatial_workspace.refresh(),
        )
        view_menu.add_command(
            label="Fit Spatial Views",
            command=lambda: self.spatial_workspace.fit_views(),
        )
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
        self.root.bind("<F5>", lambda event: self.run_current())

    def _build_layout(self) -> None:
        header = ttk.Frame(self.root, style="Header.TFrame", padding=(16, 10))
        header.pack(fill="x")
        brand = ttk.Frame(header, style="Header.TFrame")
        brand.pack(side="left")
        ttk.Label(brand, text="CleanroomX", style="Brand.TLabel").pack(anchor="w")
        ttk.Label(
            brand,
            text="Design · Simulation · Verification Workbench",
            style="Subtitle.TLabel",
        ).pack(anchor="w")

        actions = ttk.Frame(header, style="Header.TFrame")
        actions.pack(side="right")
        self.run_state_label = ttk.Label(
            actions,
            textvariable=self.run_state_var,
            style="RunState.TLabel",
        )
        self.run_state_label.pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Validate", command=self.validate_current).pack(
            side="left", padx=3
        )
        self.run_button = ttk.Button(
            actions, text="Run Analysis", style="Accent.TButton", command=self.run_current
        )
        self.run_button.pack(side="left", padx=3)
        self.cancel_button = ttk.Button(
            actions,
            text="Abandon",
            style="Danger.TButton",
            command=self.cancel_run,
            state="disabled",
        )
        self.cancel_button.pack(side="left", padx=(3, 0))

        metadata = ttk.Frame(self.root, style="Surface.TFrame", padding=(14, 9))
        metadata.pack(fill="x", padx=8, pady=(8, 4))
        ttk.Label(metadata, text="PROJECT", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 8)
        )
        ttk.Entry(metadata, textvariable=self.name_var, width=30).grid(
            row=0, column=1, sticky="ew", padx=(0, 14)
        )
        ttk.Label(metadata, text="DESCRIPTION", style="Section.TLabel").grid(
            row=0, column=2, sticky="w", padx=(0, 8)
        )
        ttk.Entry(metadata, textvariable=self.description_var).grid(
            row=0, column=3, sticky="ew"
        )
        metadata.columnconfigure(1, weight=1)
        metadata.columnconfigure(3, weight=2)

        panes = ttk.Panedwindow(self.root, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=8, pady=4)

        sidebar = ttk.Frame(panes, style="Surface.TFrame", padding=8)
        panes.add(sidebar, weight=1)
        sidebar_header = ttk.Frame(sidebar, style="Surface.TFrame")
        sidebar_header.pack(fill="x", pady=(0, 6))
        ttk.Label(sidebar_header, text="ANALYSES", style="Section.TLabel").pack(side="left")
        ttk.Button(sidebar_header, text="+", width=3, command=self.add_analysis).pack(
            side="right", padx=(3, 0)
        )
        ttk.Button(sidebar_header, text="Rename", command=self.rename_analysis).pack(
            side="right", padx=3
        )
        ttk.Button(sidebar_header, text="Remove", command=self.remove_analysis).pack(
            side="right", padx=3
        )
        self.analysis_tree = ttk.Treeview(
            sidebar, columns=("kind",), show="tree headings", selectmode="browse"
        )
        self.analysis_tree.heading("#0", text="Name")
        self.analysis_tree.heading("kind", text="Kind")
        self.analysis_tree.column("#0", width=210)
        self.analysis_tree.column("kind", width=155)
        scroll = ttk.Scrollbar(sidebar, orient="vertical", command=self.analysis_tree.yview)
        self.analysis_tree.configure(yscrollcommand=scroll.set)
        self.analysis_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.analysis_tree.bind("<<TreeviewSelect>>", self._on_analysis_selected)

        content = ttk.Frame(panes)
        panes.add(content, weight=4)
        self.notebook = ttk.Notebook(content, style="Workbench.TNotebook")
        self.notebook.pack(fill="both", expand=True)

        self.spatial_workspace = SpatialDesignWorkspace(
            self.notebook,
            project_getter=lambda: self.project,
            analysis_getter=self._editor_analysis,
            on_change=self._on_spatial_changed,
            on_sync_requested=self._sync_spatial_to_current_analysis,
            status_setter=self.status_var.set,
        )
        self.notebook.add(self.spatial_workspace, text="Spatial Studio · 2D / 3D")

        input_tab = ttk.Frame(self.notebook)
        self.notebook.add(input_tab, text="Input")
        input_notebook = ttk.Notebook(input_tab)
        input_notebook.pack(fill="both", expand=True)

        structured_tab = ttk.Frame(input_notebook)
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

        json_tab = ttk.Frame(input_notebook)
        input_notebook.add(json_tab, text="JSON editor")
        self.input_text = tk.Text(
            json_tab,
            wrap="none",
            undo=True,
            background=self._colors["editor"],
            foreground=self._colors["text"],
            insertbackground=self._colors["text"],
            selectbackground="#174d68",
            relief="flat",
            padx=10,
            pady=8,
        )
        input_scroll_y = ttk.Scrollbar(json_tab, orient="vertical", command=self.input_text.yview)
        input_scroll_x = ttk.Scrollbar(json_tab, orient="horizontal", command=self.input_text.xview)
        self.input_text.configure(
            yscrollcommand=input_scroll_y.set, xscrollcommand=input_scroll_x.set
        )
        self.input_text.grid(row=0, column=0, sticky="nsew")
        input_scroll_y.grid(row=0, column=1, sticky="ns")
        input_scroll_x.grid(row=1, column=0, sticky="ew")
        json_tab.rowconfigure(0, weight=1)
        json_tab.columnconfigure(0, weight=1)
        self.input_text.bind("<FocusOut>", lambda event: self.refresh_structure(silent=True))
        self.input_text.bind("<<Modified>>", self._on_input_modified)
        self.input_text.edit_modified(False)

        self.result_text = self._add_text_tab("Results")
        self.report_text = self._add_text_tab("Report")
        self.diagnostics_text = self._add_text_tab("Diagnostics")

        plot_tab = ttk.Frame(self.notebook)
        self.notebook.add(plot_tab, text="Plot")
        self.plot_canvas = tk.Canvas(
            plot_tab,
            highlightthickness=0,
            background=self._colors["editor"],
        )
        self.plot_canvas.pack(fill="both", expand=True)
        self.plot_canvas.bind("<Configure>", lambda event: self._draw_plot())

        status = ttk.Label(
            self.root,
            textvariable=self.status_var,
            anchor="w",
            style="Status.TLabel",
        )
        status.pack(fill="x", side="bottom")

    def _add_text_tab(self, title: str) -> tk.Text:
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=title)
        text = tk.Text(
            frame,
            wrap="none",
            state="disabled",
            background=self._colors["editor"],
            foreground=self._colors["text"],
            insertbackground=self._colors["text"],
            selectbackground="#174d68",
            relief="flat",
            padx=10,
            pady=8,
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
        if hasattr(self, "notebook") and hasattr(self, "result_text"):
            try:
                self.notebook.tab(self.result_text.master, text="Results")
            except (tk.TclError, AttributeError):
                pass
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
        if hasattr(self, "spatial_workspace"):
            self.spatial_workspace.refresh()

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
        if hasattr(self, "spatial_workspace"):
            self.spatial_workspace.refresh()

    def _on_spatial_changed(self) -> None:
        self._update_title()

    def _sync_spatial_to_current_analysis(self) -> None:
        if self._running:
            messagebox.showwarning(
                "Analysis running",
                "Abandon the current run before synchronizing spatial geometry.",
                parent=self.root,
            )
            return
        analysis = self._editor_analysis() or self._current_analysis()
        if analysis is None:
            messagebox.showinfo(
                "No active analysis",
                "Select a room-verification or multi-room verification analysis first.",
                parent=self.root,
            )
            return
        try:
            self._commit_editor(analysis)
        except Exception as exc:
            messagebox.showerror(
                "Cannot synchronize geometry",
                f"Fix the current analysis input before synchronizing.\n\n{exc}",
                parent=self.root,
            )
            return
        if analysis.kind not in {"room_verification", "project_verification"}:
            messagebox.showinfo(
                "Spatial synchronization",
                "Geometry synchronization currently targets room-verification and "
                "multi-room project-verification inputs. The spatial layout remains "
                "available for all projects.",
                parent=self.root,
            )
            return
        changed = sync_layout_to_analysis(self.spatial_workspace.layout, analysis)
        if not changed:
            self.status_var.set("Spatial geometry already matches the active analysis")
            return
        self._invalidate_last_run_for(analysis.id)
        self._load_analysis_into_editor(analysis)
        self._update_title()
        self.status_var.set(
            f"Synchronized spatial room dimensions to {analysis.name}; validate before running."
        )

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
        if hasattr(self, "run_state_var"):
            self.run_state_var.set("RUNNING" if running else "READY")

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
                    if hasattr(self, "run_state_var"):
                        self.run_state_var.set("FAILED")
                    self.status_var.set("Analysis failed")
                    messagebox.showerror("Analysis failed", str(payload), parent=self.root)
                else:
                    self._runs_by_analysis[analysis_id] = payload
                    self.last_run = payload
                    self.last_run_analysis_id = analysis_id
                    self._render_run(payload)
                    if hasattr(self, "run_state_var"):
                        self.run_state_var.set(str(payload.status).upper())
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
        try:
            self.notebook.tab(self.result_text.master, text=f"Results · {run.status}")
        except (tk.TclError, AttributeError):
            pass
        if select_results:
            # Select the actual Results frame rather than a fragile numeric tab index.
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
                fill=self._colors.get("muted", "#93a4ba"),
                font=("TkDefaultFont", 10),
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
