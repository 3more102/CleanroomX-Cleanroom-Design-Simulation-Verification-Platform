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

_UI = {
    "bg": "#0b1220",
    "surface": "#111827",
    "surface_alt": "#182235",
    "panel": "#0f172a",
    "border": "#2a3a52",
    "text": "#e5eefc",
    "muted": "#93a4bd",
    "accent": "#22d3ee",
    "accent_hover": "#67e8f9",
    "success": "#34d399",
    "danger": "#fb7185",
    "grid": "#223047",
}


def _engineering_number(value) -> float | None:
    """Return a finite positive engineering value, accepting uncertainty {"value": ...} shapes."""
    if isinstance(value, dict) and "value" in value:
        value = value["value"]
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if number > 0 and number == number and number not in (float("inf"), float("-inf")):
            return number
    return None


def extract_room_geometries(value, path: str = "$") -> list[dict[str, float | str]]:
    """Find rectangular room-like geometry in analysis JSON for dependency-free 2D/3D previews."""
    found: list[dict[str, float | str]] = []
    if isinstance(value, dict):
        length = _engineering_number(value.get("length_m"))
        width = _engineering_number(value.get("width_m"))
        height = _engineering_number(value.get("height_m"))
        if length is not None and width is not None and height is not None:
            name = str(value.get("name") or path.rsplit(".", 1)[-1].replace("[", " ").replace("]", ""))
            found.append(
                {
                    "name": name,
                    "path": path,
                    "length_m": length,
                    "width_m": width,
                    "height_m": height,
                }
            )
        for key, item in value.items():
            found.extend(extract_room_geometries(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(extract_room_geometries(item, f"{path}[{index}]"))
    return found


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
        self.root.geometry("1400x900")
        self.root.minsize(1080, 680)
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
        self.root.configure(background=_UI["bg"])
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", background=_UI["bg"], foreground=_UI["text"])
        style.configure("TFrame", background=_UI["bg"])
        style.configure("Surface.TFrame", background=_UI["surface"])
        style.configure("Panel.TFrame", background=_UI["panel"])
        style.configure("TLabel", background=_UI["bg"], foreground=_UI["text"])
        style.configure("Surface.TLabel", background=_UI["surface"], foreground=_UI["text"])
        style.configure(
            "Title.TLabel",
            background=_UI["surface"],
            foreground=_UI["text"],
            font=("TkDefaultFont", 18, "bold"),
        )
        style.configure(
            "Subtitle.TLabel",
            background=_UI["surface"],
            foreground=_UI["muted"],
            font=("TkDefaultFont", 9),
        )
        style.configure(
            "Section.TLabel",
            background=_UI["bg"],
            foreground=_UI["muted"],
            font=("TkDefaultFont", 9, "bold"),
        )
        style.configure(
            "Accent.TButton",
            background=_UI["accent"],
            foreground="#06212a",
            padding=(14, 8),
            font=("TkDefaultFont", 9, "bold"),
        )
        style.map("Accent.TButton", background=[("active", _UI["accent_hover"])])
        style.configure("Tool.TButton", padding=(10, 7))
        style.configure(
            "Treeview",
            background=_UI["panel"],
            fieldbackground=_UI["panel"],
            foreground=_UI["text"],
            rowheight=28,
            borderwidth=0,
        )
        style.configure(
            "Treeview.Heading",
            background=_UI["surface_alt"],
            foreground=_UI["text"],
            relief="flat",
            padding=(8, 7),
        )
        style.map(
            "Treeview",
            background=[("selected", _UI["accent"])],
            foreground=[("selected", "#06212a")],
        )
        style.configure("TNotebook", background=_UI["bg"], borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=_UI["surface"],
            foreground=_UI["muted"],
            padding=(14, 9),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", _UI["surface_alt"])],
            foreground=[("selected", _UI["text"])],
        )
        style.configure(
            "TEntry",
            fieldbackground=_UI["panel"],
            foreground=_UI["text"],
            insertcolor=_UI["text"],
            padding=6,
        )
        style.configure(
            "Status.TLabel",
            background=_UI["surface"],
            foreground=_UI["muted"],
            padding=(10, 6),
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
        view_menu.add_separator()
        view_menu.add_command(label="2D Layout", accelerator="F6", command=lambda: self.notebook.select(self.preview_2d_tab))
        view_menu.add_command(label="3D View", accelerator="F7", command=lambda: self.notebook.select(self.preview_3d_tab))
        view_menu.add_separator()
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
        self.root.bind("<F6>", lambda event: self.notebook.select(self.preview_2d_tab))
        self.root.bind("<F7>", lambda event: self.notebook.select(self.preview_3d_tab))

    def _build_layout(self) -> None:
        header = ttk.Frame(self.root, style="Surface.TFrame", padding=(18, 14))
        header.pack(fill="x")
        brand = ttk.Frame(header, style="Surface.TFrame")
        brand.grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 22))
        ttk.Label(brand, text="CleanroomX", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            brand,
            text="Cleanroom Design • Simulation • Verification",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        fields = ttk.Frame(header, style="Surface.TFrame")
        fields.grid(row=0, column=1, rowspan=2, sticky="ew")
        ttk.Label(fields, text="PROJECT", style="Subtitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(fields, text="DESCRIPTION", style="Subtitle.TLabel").grid(row=0, column=1, sticky="w", padx=(12, 0))
        ttk.Entry(fields, textvariable=self.name_var, width=28).grid(row=1, column=0, sticky="ew", pady=(3, 0))
        ttk.Entry(fields, textvariable=self.description_var).grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=(3, 0))
        fields.columnconfigure(0, weight=1)
        fields.columnconfigure(1, weight=2)

        actions = ttk.Frame(header, style="Surface.TFrame")
        actions.grid(row=0, column=2, rowspan=2, sticky="e", padx=(18, 0))
        ttk.Button(actions, text="Validate", style="Tool.TButton", command=self.validate_current).pack(side="left", padx=(0, 6))
        self.run_button = ttk.Button(actions, text="Run  F5", style="Accent.TButton", command=self.run_current)
        self.run_button.pack(side="left", padx=(0, 6))
        self.cancel_button = ttk.Button(actions, text="Abandon", style="Tool.TButton", command=self.cancel_run, state="disabled")
        self.cancel_button.pack(side="left")
        header.columnconfigure(1, weight=1)

        workspace = ttk.Frame(self.root, padding=(10, 10, 10, 0))
        workspace.pack(fill="both", expand=True)
        panes = ttk.Panedwindow(workspace, orient="horizontal")
        panes.pack(fill="both", expand=True)

        sidebar = ttk.Frame(panes, style="Panel.TFrame", padding=10)
        panes.add(sidebar, weight=1)
        ttk.Label(sidebar, text="PROJECT ANALYSES", style="Section.TLabel").pack(anchor="w", pady=(0, 8))

        sidebar_actions = ttk.Frame(sidebar, style="Panel.TFrame")
        sidebar_actions.pack(fill="x", pady=(0, 8))
        ttk.Button(sidebar_actions, text="+ Add", style="Tool.TButton", command=self.add_analysis).pack(side="left")
        ttk.Button(sidebar_actions, text="Rename", style="Tool.TButton", command=self.rename_analysis).pack(side="left", padx=5)
        ttk.Button(sidebar_actions, text="Remove", style="Tool.TButton", command=self.remove_analysis).pack(side="left")

        tree_wrap = ttk.Frame(sidebar, style="Panel.TFrame")
        tree_wrap.pack(fill="both", expand=True)
        self.analysis_tree = ttk.Treeview(
            tree_wrap, columns=("kind",), show="tree headings", selectmode="browse"
        )
        self.analysis_tree.heading("#0", text="Name")
        self.analysis_tree.heading("kind", text="Workflow")
        self.analysis_tree.column("#0", width=205, minwidth=150)
        self.analysis_tree.column("kind", width=150, minwidth=110)
        scroll = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.analysis_tree.yview)
        self.analysis_tree.configure(yscrollcommand=scroll.set)
        self.analysis_tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        tree_wrap.rowconfigure(0, weight=1)
        tree_wrap.columnconfigure(0, weight=1)
        self.analysis_tree.bind("<<TreeviewSelect>>", self._on_analysis_selected)

        content = ttk.Frame(panes)
        panes.add(content, weight=4)
        self.notebook = ttk.Notebook(content)
        self.notebook.pack(fill="both", expand=True)

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
            background=_UI["panel"],
            foreground=_UI["text"],
            insertbackground=_UI["text"],
            selectbackground=_UI["accent"],
            selectforeground="#06212a",
            relief="flat",
            borderwidth=0,
            padx=12,
            pady=12,
            font=("TkFixedFont", 10),
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

        self.preview_2d_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.preview_2d_tab, text="2D Layout  F6")
        self.preview_2d_canvas = tk.Canvas(
            self.preview_2d_tab,
            background=_UI["panel"],
            highlightthickness=0,
        )
        self.preview_2d_canvas.pack(fill="both", expand=True)
        self.preview_2d_canvas.bind("<Configure>", lambda event: self._draw_2d_preview())

        self.preview_3d_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.preview_3d_tab, text="3D View  F7")
        self.preview_3d_canvas = tk.Canvas(
            self.preview_3d_tab,
            background=_UI["panel"],
            highlightthickness=0,
        )
        self.preview_3d_canvas.pack(fill="both", expand=True)
        self.preview_3d_canvas.bind("<Configure>", lambda event: self._draw_3d_preview())

        self.result_text = self._add_text_tab("Results")
        self.report_text = self._add_text_tab("Report")
        self.diagnostics_text = self._add_text_tab("Diagnostics")

        plot_tab = ttk.Frame(self.notebook)
        self.notebook.add(plot_tab, text="Plot")
        self.plot_canvas = tk.Canvas(plot_tab, background=_UI["panel"], highlightthickness=0)
        self.plot_canvas.pack(fill="both", expand=True)
        self.plot_canvas.bind("<Configure>", lambda event: self._draw_plot())

        status = ttk.Frame(self.root, style="Surface.TFrame")
        status.pack(fill="x", side="bottom")
        ttk.Label(
            status,
            textvariable=self.status_var,
            anchor="w",
            style="Status.TLabel",
        ).pack(side="left", fill="x", expand=True)
        ttk.Label(
            status,
            text=f"v{__version__}   •   F5 Run   •   F6 2D   •   F7 3D",
            anchor="e",
            style="Status.TLabel",
        ).pack(side="right")

        self._refresh_room_previews()

    def _add_text_tab(self, title: str) -> tk.Text:
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=title)
        text = tk.Text(
            frame,
            wrap="none",
            state="disabled",
            background=_UI["panel"],
            foreground=_UI["text"],
            insertbackground=_UI["text"],
            selectbackground=_UI["accent"],
            selectforeground="#06212a",
            relief="flat",
            borderwidth=0,
            padx=12,
            pady=12,
            font=("TkFixedFont", 10),
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
        self._refresh_room_previews()
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
        self._refresh_room_previews()
        self._restore_run_for(analysis.id)

    def refresh_structure(self, silent: bool = False) -> None:
        for item in self.structure_tree.get_children():
            self.structure_tree.delete(item)
        text = self.input_text.get("1.0", "end-1c").strip()
        if not text:
            self._refresh_room_previews({})
            return
        try:
            payload = _strict_json_loads(text)
        except (json.JSONDecodeError, ValueError) as exc:
            self._refresh_room_previews({})
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
        self._refresh_room_previews(payload)

    def _preview_payload(self) -> dict | None:
        if not hasattr(self, "input_text"):
            return None
        text = self.input_text.get("1.0", "end-1c").strip()
        if not text:
            return None
        try:
            payload = _strict_json_loads(text)
        except (json.JSONDecodeError, ValueError):
            return None
        return payload if isinstance(payload, dict) else None

    def _refresh_room_previews(self, payload: dict | None = None) -> None:
        if not hasattr(self, "preview_2d_canvas") or not hasattr(self, "preview_3d_canvas"):
            return
        payload = payload if payload is not None else self._preview_payload()
        self._preview_geometries = extract_room_geometries(payload or {})
        self._draw_2d_preview()
        self._draw_3d_preview()

    def _draw_preview_empty(self, canvas: tk.Canvas, title: str) -> None:
        canvas.delete("all")
        width = max(canvas.winfo_width(), 500)
        height = max(canvas.winfo_height(), 320)
        canvas.create_text(
            28,
            24,
            anchor="nw",
            text=title,
            fill=_UI["text"],
            font=("TkDefaultFont", 13, "bold"),
        )
        canvas.create_text(
            width / 2,
            height / 2,
            text="No rectangular room geometry found in the current input.\n"
                 "Add length_m, width_m and height_m fields to enable this view.",
            fill=_UI["muted"],
            justify="center",
            font=("TkDefaultFont", 10),
        )

    def _draw_2d_preview(self) -> None:
        canvas = self.preview_2d_canvas
        geometries = getattr(self, "_preview_geometries", [])
        if not geometries:
            self._draw_preview_empty(canvas, "2D Layout")
            return
        canvas.delete("all")
        width = max(canvas.winfo_width(), 560)
        height = max(canvas.winfo_height(), 360)
        margin = 70
        for x in range(0, width, 40):
            canvas.create_line(x, 0, x, height, fill=_UI["grid"])
        for y in range(0, height, 40):
            canvas.create_line(0, y, width, y, fill=_UI["grid"])
        canvas.create_text(28, 24, anchor="nw", text="2D Layout", fill=_UI["text"], font=("TkDefaultFont", 13, "bold"))
        canvas.create_text(28, 48, anchor="nw", text="Geometry extracted from active analysis input", fill=_UI["muted"])

        max_l = max(float(g["length_m"]) for g in geometries)
        max_w = max(float(g["width_m"]) for g in geometries)
        scale = min((width - margin * 2) / max_l, (height - margin * 2) / max_w) * 0.82
        offset_step = min(26, max(8, int(90 / max(len(geometries), 1))))

        for index, geometry in enumerate(geometries[:12]):
            rw = float(geometry["length_m"]) * scale
            rh = float(geometry["width_m"]) * scale
            x0 = margin + index * offset_step
            y0 = margin + index * offset_step
            x1 = min(x0 + rw, width - 24)
            y1 = min(y0 + rh, height - 24)
            canvas.create_rectangle(x0, y0, x1, y1, outline=_UI["accent"], width=2)
            label = (
                f'{geometry["name"]}  •  '
                f'{float(geometry["length_m"]):.3g} × {float(geometry["width_m"]):.3g} m'
            )
            canvas.create_text(x0 + 8, y0 + 8, anchor="nw", text=label, fill=_UI["text"], font=("TkDefaultFont", 9, "bold"))

    def _draw_3d_preview(self) -> None:
        canvas = self.preview_3d_canvas
        geometries = getattr(self, "_preview_geometries", [])
        if not geometries:
            self._draw_preview_empty(canvas, "3D View")
            return
        canvas.delete("all")
        width = max(canvas.winfo_width(), 560)
        height = max(canvas.winfo_height(), 360)
        canvas.create_text(28, 24, anchor="nw", text="3D View", fill=_UI["text"], font=("TkDefaultFont", 13, "bold"))
        canvas.create_text(28, 48, anchor="nw", text="Dependency-free isometric engineering preview", fill=_UI["muted"])

        max_dim = max(
            max(float(g["length_m"]), float(g["width_m"]), float(g["height_m"]))
            for g in geometries
        )
        scale = min(width, height) * 0.34 / max_dim
        base_x = width * 0.28
        base_y = height * 0.72

        for index, geometry in enumerate(geometries[:8]):
            l = float(geometry["length_m"]) * scale
            w = float(geometry["width_m"]) * scale
            h = float(geometry["height_m"]) * scale
            ox = base_x + index * 28
            oy = base_y - index * 18
            dx, dy = w * 0.55, w * 0.32
            a = (ox, oy)
            b = (ox + l, oy)
            c = (ox + l + dx, oy - dy)
            d = (ox + dx, oy - dy)
            ah, bh, ch, dh = (
                (a[0], a[1] - h),
                (b[0], b[1] - h),
                (c[0], c[1] - h),
                (d[0], d[1] - h),
            )
            for p1, p2 in ((a, b), (b, c), (c, d), (d, a), (ah, bh), (bh, ch), (ch, dh), (dh, ah), (a, ah), (b, bh), (c, ch), (d, dh)):
                canvas.create_line(*p1, *p2, fill=_UI["accent"], width=2)
            canvas.create_text(
                ah[0] + 8,
                ah[1] - 8,
                anchor="sw",
                text=f'{geometry["name"]}  {float(geometry["height_m"]):.3g} m high',
                fill=_UI["text"],
                font=("TkDefaultFont", 9, "bold"),
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
                fill=_UI["muted"],
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

        canvas.create_line(left, height - bottom, width - right, height - bottom, fill=_UI["muted"])
        canvas.create_line(left, top, left, height - bottom, fill=_UI["muted"])
        canvas.create_text(width / 2, 18, text=plot["title"], fill=_UI["text"], font=("TkDefaultFont", 11, "bold"))
        canvas.create_text(width / 2, height - 20, text=plot["x_label"], fill=_UI["muted"])
        canvas.create_text(18, height / 2, text=plot["y_label"], angle=90, fill=_UI["muted"])
        canvas.create_text(left, height - bottom + 18, text=f"{xmin:.3g}", anchor="n", fill=_UI["muted"])
        canvas.create_text(width - right, height - bottom + 18, text=f"{xmax:.3g}", anchor="n", fill=_UI["muted"])
        canvas.create_text(left - 8, height - bottom, text=f"{ymin:.3g}", anchor="e", fill=_UI["muted"])
        canvas.create_text(left - 8, top, text=f"{ymax:.3g}", anchor="e", fill=_UI["muted"])

        for index, series in enumerate(plot["series"]):
            coords = []
            for x, y in zip(series["x"], series["y"]):
                coords.extend(point(x, y))
            line_options = {"width": 2}
            if index % 2:
                line_options["dash"] = (6, 4)
            if len(coords) >= 4:
                canvas.create_line(*coords, fill=_UI["accent"], **line_options)
            for x, y in zip(series["x"], series["y"]):
                px, py = point(x, y)
                canvas.create_oval(px - 2, py - 2, px + 2, py + 2, fill=_UI["accent"], outline=_UI["accent"])

            legend_x = max(left + 20, width - right - 170)
            legend_y = top + index * 18
            canvas.create_line(
                legend_x,
                legend_y,
                legend_x + 28,
                legend_y,
                fill=_UI["accent"],
                **line_options,
            )
            canvas.create_text(
                legend_x + 34,
                legend_y,
                text=series.get("name", f"Series {index + 1}"),
                anchor="w",
                fill=_UI["text"],
            )

        for marker in plot.get("markers", []):
            px, py = point(marker["x"], marker["y"])
            canvas.create_oval(px - 6, py - 6, px + 6, py + 6, width=2, outline=_UI["success"])
            canvas.create_text(px + 8, py - 8, text=marker["name"], anchor="sw", fill=_UI["success"])

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
