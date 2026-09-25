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


def _optional_finite_float(value, *, positive: bool = False) -> float | None:
    """Return a finite numeric value, or None when visualization data is unusable."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    if positive and number <= 0:
        return None
    return number


def analysis_matches_filter(analysis: AnalysisDocument, query: str) -> bool:
    """Case-insensitive sidebar filtering across analysis name, kind, and catalog title."""
    needle = query.strip().casefold()
    if not needle:
        return True
    spec = ANALYSIS_SPECS.get(analysis.kind)
    title = "" if spec is None else spec.title
    haystack = " ".join((analysis.name, analysis.kind, title)).casefold()
    return needle in haystack


def extract_pressure_cascade(payload: dict) -> list[dict]:
    """Extract declared high-to-low room pressure relationships from an analysis input."""
    if not isinstance(payload, dict):
        return []

    candidates: list[list] = []

    def visit(value) -> None:
        if isinstance(value, dict):
            cascade = value.get("pressure_cascade")
            if isinstance(cascade, list):
                candidates.append(cascade)
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(payload)
    if not candidates:
        return []

    links: list[dict] = []
    for item in candidates[0]:
        if not isinstance(item, dict):
            continue
        higher = item.get("higher_pressure_room")
        lower = item.get("lower_pressure_room")
        if not isinstance(higher, str) or not higher.strip():
            continue
        if not isinstance(lower, str) or not lower.strip():
            continue
        minimum_value = _optional_finite_float(item.get("min_delta_pa"), positive=True)
        links.append({
            "higher_pressure_room": higher.strip(),
            "lower_pressure_room": lower.strip(),
            "min_delta_pa": minimum_value,
        })
    return links


def extract_room_visuals(payload: dict) -> list[dict]:
    """Extract room-like records for the lightweight 2D/3D engineering workspace."""
    if not isinstance(payload, dict):
        return []

    room_lists: list[list] = []

    def visit(value) -> None:
        if isinstance(value, dict):
            rooms = value.get("rooms")
            if isinstance(rooms, list) and any(isinstance(item, dict) for item in rooms):
                room_lists.append(rooms)
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(payload)
    if not room_lists:
        return []

    rooms: list[dict] = []
    seen: set[str] = set()
    for item in room_lists[0]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("id") or f"Room {len(rooms) + 1}")
        if name in seen:
            continue
        seen.add(name)

        def positive_number(key: str, fallback: float) -> tuple[float, bool]:
            number = _optional_finite_float(item.get(key), positive=True)
            return (fallback, False) if number is None else (number, True)

        def finite_number(key: str) -> tuple[float | None, bool]:
            number = _optional_finite_float(item.get(key))
            return number, number is not None

        length_m, length_real = positive_number("length_m", 4.0)
        width_m, width_real = positive_number("width_m", 4.0)
        height_m, height_real = positive_number("height_m", 3.0)
        x_m, x_real = finite_number("x_m")
        y_m, y_real = finite_number("y_m")
        airflow = _optional_finite_float(
            item.get("supply_airflow_m3_h", item.get("cleanroom_airflow_m3_h")),
            positive=True,
        )
        pressure = _optional_finite_float(
            item.get("observed_pressure_pa", item.get("pressure_pa"))
        )
        min_ach = _optional_finite_float(item.get("min_ach"), positive=True)
        min_pressure = _optional_finite_float(item.get("min_pressure_pa"))
        rooms.append({
            "name": name,
            "length_m": length_m,
            "width_m": width_m,
            "height_m": height_m,
            "dimensions_real": length_real and width_real,
            "height_real": height_real,
            "position_real": x_real and y_real,
            "x_m": x_m,
            "y_m": y_m,
            "airflow_m3_h": airflow,
            "pressure_pa": pressure,
            "min_ach": min_ach,
            "min_pressure_pa": min_pressure,
        })
    return rooms


def room_visual_engineering_metrics(room: dict) -> dict:
    """Calculate visualization-only room requirement metrics without using display defaults."""
    airflow = _optional_finite_float(room.get("airflow_m3_h"), positive=True)
    min_ach = _optional_finite_float(room.get("min_ach"), positive=True)
    pressure = _optional_finite_float(room.get("pressure_pa"))
    min_pressure = _optional_finite_float(room.get("min_pressure_pa"))

    ach = None
    if (
        room.get("dimensions_real")
        and room.get("height_real")
        and airflow is not None
    ):
        length = _optional_finite_float(room.get("length_m"), positive=True)
        width = _optional_finite_float(room.get("width_m"), positive=True)
        height = _optional_finite_float(room.get("height_m"), positive=True)
        if length is not None and width is not None and height is not None:
            volume = length * width * height
            if volume > 0:
                ach = airflow / volume

    ach_status = "not_required"
    if min_ach is not None:
        ach_status = "unknown" if ach is None else ("pass" if ach >= min_ach else "fail")

    pressure_status = "not_required"
    if min_pressure is not None:
        pressure_status = (
            "unknown"
            if pressure is None
            else ("pass" if pressure >= min_pressure else "fail")
        )

    required_statuses = [
        status
        for status in (ach_status, pressure_status)
        if status != "not_required"
    ]
    if any(status == "fail" for status in required_statuses):
        status = "fail"
    elif required_statuses and all(status == "pass" for status in required_statuses):
        status = "pass"
    else:
        status = "unknown"

    return {
        "ach": ach,
        "min_ach": min_ach,
        "ach_status": ach_status,
        "pressure_pa": pressure,
        "min_pressure_pa": min_pressure,
        "pressure_status": pressure_status,
        "status": status,
    }


def evaluate_pressure_cascade_visuals(rooms: list[dict], links: list[dict]) -> list[dict]:
    """Attach observed differential pressure and requirement state to cascade links."""
    pressure_by_room = {
        room["name"]: _optional_finite_float(room.get("pressure_pa"))
        for room in rooms
        if isinstance(room.get("name"), str)
    }
    evaluated: list[dict] = []
    for link in links:
        higher = link.get("higher_pressure_room")
        lower = link.get("lower_pressure_room")
        minimum = _optional_finite_float(link.get("min_delta_pa"), positive=True)
        higher_pressure = pressure_by_room.get(higher)
        lower_pressure = pressure_by_room.get(lower)
        observed_delta = None
        if higher_pressure is not None and lower_pressure is not None:
            observed_delta = higher_pressure - lower_pressure

        status = "unknown"
        if observed_delta is not None and minimum is not None:
            status = "pass" if observed_delta >= minimum else "fail"

        evaluated.append({
            **link,
            "min_delta_pa": minimum,
            "observed_delta_pa": observed_delta,
            "status": status,
        })
    return evaluated


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
        self.root.geometry("1360x860")
        self.root.minsize(1024, 680)
        self._configure_styles()

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
        self.analysis_filter_var = tk.StringVar(value="")
        self.dashboard_project_var = tk.StringVar(value="")
        self.dashboard_analysis_var = tk.StringVar(value="")
        self.dashboard_runs_var = tk.StringVar(value="")
        self.dashboard_rooms_var = tk.StringVar(value="")
        self.dashboard_active_var = tk.StringVar(value="")
        self.dashboard_result_var = tk.StringVar(value="")
        self._visual_zoom = 1.0
        self._visual3d_yaw_deg = 0.0
        self._selected_room_name: str | None = None

        self._build_menu()
        self._build_layout()
        self._refresh_analysis_list()
        self._capture_saved_state()
        self.name_var.trace_add(
            "write", lambda *_: (self._update_title(), self._refresh_dashboard())
        )
        self.description_var.trace_add(
            "write", lambda *_: (self._update_title(), self._refresh_dashboard())
        )
        self.analysis_filter_var.trace_add("write", lambda *_: self._refresh_analysis_list())
        self._update_title()
        self._refresh_dashboard()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._poll_worker)

    def _configure_styles(self) -> None:
        """Apply a restrained engineering-oriented visual system using stock ttk only."""
        self.root.configure(background="#0b1220")
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure(".", font=("Segoe UI", 10))
        style.configure("TFrame", background="#0f172a")
        style.configure("Header.TFrame", background="#111c31")
        style.configure("Sidebar.TFrame", background="#101827")
        style.configure("TLabel", background="#0f172a", foreground="#dbeafe")
        style.configure("Header.TLabel", background="#111c31", foreground="#e2e8f0")
        style.configure("Brand.TLabel", background="#111c31", foreground="#f8fafc", font=("Segoe UI", 16, "bold"))
        style.configure("Muted.TLabel", background="#0f172a", foreground="#94a3b8")
        style.configure("SidebarTitle.TLabel", background="#101827", foreground="#f8fafc", font=("Segoe UI", 11, "bold"))
        style.configure("TButton", padding=(10, 6))
        style.configure("Primary.TButton", padding=(12, 7), font=("Segoe UI", 10, "bold"))
        style.configure("Tool.TButton", padding=(8, 5))
        style.configure("TEntry", fieldbackground="#172033", foreground="#f8fafc", insertcolor="#f8fafc", padding=5)
        style.configure("Treeview", background="#111827", fieldbackground="#111827", foreground="#e5e7eb", rowheight=27, borderwidth=0)
        style.configure("Treeview.Heading", background="#1e293b", foreground="#e2e8f0", font=("Segoe UI", 9, "bold"), relief="flat")
        style.map("Treeview", background=[("selected", "#1d4ed8")], foreground=[("selected", "#ffffff")])
        style.configure("TNotebook", background="#0f172a", borderwidth=0)
        style.configure("TNotebook.Tab", background="#172033", foreground="#cbd5e1", padding=(14, 8))
        style.map("TNotebook.Tab", background=[("selected", "#1e293b")], foreground=[("selected", "#ffffff")])
        style.configure("Status.TLabel", background="#111827", foreground="#cbd5e1", padding=(8, 5))

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
        view_menu.add_command(label="Overview", accelerator="Ctrl+1", command=lambda: self.notebook.select(self.overview_tab))
        view_menu.add_command(label="2D Workspace", accelerator="Ctrl+2", command=lambda: self.notebook.select(self.visual2d_tab))
        view_menu.add_command(label="3D Preview", accelerator="Ctrl+3", command=lambda: self.notebook.select(self.visual3d_tab))
        view_menu.add_command(label="Fit Visual Workspace", accelerator="Ctrl+0", command=self._reset_visual_view)
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
        self.root.bind("<Control-Key-1>", lambda event: self.notebook.select(self.overview_tab))
        self.root.bind("<Control-Key-2>", lambda event: self.notebook.select(self.visual2d_tab))
        self.root.bind("<Control-Key-3>", lambda event: self.notebook.select(self.visual3d_tab))
        self.root.bind("<Control-Key-0>", lambda event: self._reset_visual_view())
        self.root.bind("<Control-f>", lambda event: self.analysis_filter_entry.focus_set())

    def _build_layout(self) -> None:
        metadata = ttk.Frame(self.root, style="Header.TFrame", padding=(14, 10, 14, 10))
        metadata.pack(fill="x")
        ttk.Label(metadata, text="CleanroomX", style="Brand.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 16))
        ttk.Label(metadata, text="Project", style="Header.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Entry(metadata, textvariable=self.name_var, width=30).grid(row=0, column=2, sticky="ew", padx=(6, 12))
        ttk.Label(metadata, text="Description", style="Header.TLabel").grid(row=0, column=3, sticky="w")
        ttk.Entry(metadata, textvariable=self.description_var).grid(row=0, column=4, sticky="ew", padx=(6, 12))
        ttk.Button(metadata, text="Validate", style="Tool.TButton", command=self.validate_current).grid(row=0, column=5, padx=3)
        self.run_button = ttk.Button(metadata, text="Run Analysis", style="Primary.TButton", command=self.run_current)
        self.run_button.grid(row=0, column=6, padx=3)
        self.cancel_button = ttk.Button(metadata, text="Abandon", style="Tool.TButton", command=self.cancel_run, state="disabled")
        self.cancel_button.grid(row=0, column=7, padx=3)
        metadata.columnconfigure(2, weight=1)
        metadata.columnconfigure(4, weight=2)

        panes = ttk.Panedwindow(self.root, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=10, pady=(8, 6))

        sidebar = ttk.Frame(panes, style="Sidebar.TFrame", padding=8)
        panes.add(sidebar, weight=1)
        ttk.Label(sidebar, text="ANALYSES", style="SidebarTitle.TLabel").pack(
            anchor="w", pady=(0, 7)
        )
        search_row = ttk.Frame(sidebar, style="Sidebar.TFrame")
        search_row.pack(fill="x", pady=(0, 7))
        ttk.Label(search_row, text="Filter", style="Muted.TLabel").pack(side="left")
        self.analysis_filter_entry = ttk.Entry(
            search_row, textvariable=self.analysis_filter_var, width=22
        )
        self.analysis_filter_entry.pack(side="left", fill="x", expand=True, padx=(6, 4))
        ttk.Button(
            search_row,
            text="×",
            style="Tool.TButton",
            width=3,
            command=lambda: self.analysis_filter_var.set(""),
        ).pack(side="right")

        tree_host = ttk.Frame(sidebar, style="Sidebar.TFrame")
        tree_host.pack(fill="both", expand=True)
        self.analysis_tree = ttk.Treeview(
            tree_host, columns=("kind",), show="tree headings", selectmode="browse"
        )
        self.analysis_tree.heading("#0", text="Name")
        self.analysis_tree.heading("kind", text="Kind")
        self.analysis_tree.column("#0", width=210)
        self.analysis_tree.column("kind", width=155)
        scroll = ttk.Scrollbar(
            tree_host, orient="vertical", command=self.analysis_tree.yview
        )
        self.analysis_tree.configure(yscrollcommand=scroll.set)
        self.analysis_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.analysis_tree.bind("<<TreeviewSelect>>", self._on_analysis_selected)

        sidebar_actions = ttk.Frame(sidebar, style="Sidebar.TFrame")
        sidebar_actions.pack(fill="x", pady=(8, 0))
        ttk.Button(sidebar_actions, text="+ Add", style="Tool.TButton", command=self.add_analysis).pack(side="left")
        ttk.Button(sidebar_actions, text="Rename", style="Tool.TButton", command=self.rename_analysis).pack(side="left", padx=4)
        ttk.Button(sidebar_actions, text="Remove", style="Tool.TButton", command=self.remove_analysis).pack(side="left")

        content = ttk.Frame(panes)
        panes.add(content, weight=4)
        self.notebook = ttk.Notebook(content)
        self.notebook.pack(fill="both", expand=True)

        self.overview_tab = ttk.Frame(self.notebook, padding=16)
        self.notebook.add(self.overview_tab, text="Overview")
        overview_header = ttk.Frame(self.overview_tab)
        overview_header.pack(fill="x", pady=(0, 14))
        ttk.Label(
            overview_header,
            text="Project Overview",
            font=("Segoe UI", 18, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            overview_header,
            textvariable=self.dashboard_project_var,
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        cards = ttk.Frame(self.overview_tab)
        cards.pack(fill="x")
        for column in range(4):
            cards.columnconfigure(column, weight=1)
        card_specs = (
            ("Analyses", self.dashboard_analysis_var),
            ("Session runs", self.dashboard_runs_var),
            ("Detected rooms", self.dashboard_rooms_var),
            ("Active workflow", self.dashboard_active_var),
        )
        for column, (title, variable) in enumerate(card_specs):
            card = ttk.Frame(cards, padding=14)
            card.grid(
                row=0,
                column=column,
                sticky="nsew",
                padx=(0 if column == 0 else 6, 6 if column < 3 else 0),
            )
            ttk.Label(card, text=title, style="Muted.TLabel").pack(anchor="w")
            ttk.Label(
                card,
                textvariable=variable,
                font=("Segoe UI", 16, "bold"),
            ).pack(anchor="w", pady=(8, 0))

        overview_body = ttk.Frame(self.overview_tab)
        overview_body.pack(fill="both", expand=True, pady=(16, 0))
        overview_body.columnconfigure(0, weight=3)
        overview_body.columnconfigure(1, weight=2)
        overview_body.rowconfigure(0, weight=1)

        active_card = ttk.Frame(overview_body, padding=16)
        active_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ttk.Label(
            active_card,
            text="Active analysis",
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            active_card,
            textvariable=self.dashboard_result_var,
            justify="left",
            wraplength=620,
        ).pack(anchor="w", pady=(10, 0))

        actions_card = ttk.Frame(overview_body, padding=16)
        actions_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        ttk.Label(
            actions_card,
            text="Quick actions",
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w")
        ttk.Button(
            actions_card,
            text="Run active analysis",
            style="Primary.TButton",
            command=self.run_current,
        ).pack(fill="x", pady=(12, 6))
        ttk.Button(
            actions_card,
            text="Validate input",
            command=self.validate_current,
        ).pack(fill="x", pady=6)
        ttk.Button(
            actions_card,
            text="Open 2D workspace",
            command=lambda: self.notebook.select(self.visual2d_tab),
        ).pack(fill="x", pady=6)
        ttk.Button(
            actions_card,
            text="Open 3D preview",
            command=lambda: self.notebook.select(self.visual3d_tab),
        ).pack(fill="x", pady=6)

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
            background="#08111f",
            foreground="#e2e8f0",
            insertbackground="#f8fafc",
            selectbackground="#1d4ed8",
            selectforeground="#ffffff",
            relief="flat",
            borderwidth=0,
            padx=10,
            pady=10,
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
        self.plot_canvas = tk.Canvas(plot_tab, highlightthickness=0)
        self.plot_canvas.pack(fill="both", expand=True)
        self.plot_canvas.bind("<Configure>", lambda event: self._draw_plot())

        self.visual2d_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.visual2d_tab, text="2D Workspace")
        visual2d_toolbar = ttk.Frame(self.visual2d_tab, padding=(10, 8))
        visual2d_toolbar.pack(fill="x")
        ttk.Label(visual2d_toolbar, text="Room layout / pressure cascade", font=("Segoe UI", 10, "bold")).pack(side="left")
        ttk.Label(
            visual2d_toolbar,
            text="Click a room to inspect • mouse wheel zoom • Ctrl+0 fit",
            style="Muted.TLabel",
        ).pack(side="left", padx=12)
        ttk.Button(
            visual2d_toolbar,
            text="+",
            style="Tool.TButton",
            width=3,
            command=lambda: self._change_visual_zoom(1.2),
        ).pack(side="right")
        ttk.Button(
            visual2d_toolbar,
            text="Fit",
            style="Tool.TButton",
            command=self._reset_visual_view,
        ).pack(side="right", padx=4)
        ttk.Button(
            visual2d_toolbar,
            text="−",
            style="Tool.TButton",
            width=3,
            command=lambda: self._change_visual_zoom(1 / 1.2),
        ).pack(side="right")
        ttk.Button(
            visual2d_toolbar,
            text="Refresh",
            style="Tool.TButton",
            command=self._refresh_visuals,
        ).pack(side="right", padx=(0, 8))
        self.visual2d_canvas = tk.Canvas(self.visual2d_tab, background="#0b1220", highlightthickness=0)
        self.visual2d_canvas.pack(fill="both", expand=True)
        self.visual2d_canvas.bind("<Configure>", lambda event: self._draw_2d_workspace())
        self.visual2d_canvas.bind("<MouseWheel>", self._on_visual_mousewheel)
        self.visual2d_canvas.bind("<Button-4>", lambda event: self._change_visual_zoom(1.12))
        self.visual2d_canvas.bind("<Button-5>", lambda event: self._change_visual_zoom(1 / 1.12))
        self.visual2d_canvas.bind("<Double-Button-1>", lambda event: self._reset_visual_view())

        self.visual3d_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.visual3d_tab, text="3D Preview")
        visual3d_toolbar = ttk.Frame(self.visual3d_tab, padding=(10, 8))
        visual3d_toolbar.pack(fill="x")
        ttk.Label(visual3d_toolbar, text="Conceptual 3D room massing", font=("Segoe UI", 10, "bold")).pack(side="left")
        ttk.Label(
            visual3d_toolbar,
            text="Click a room to inspect • mouse wheel zoom • visualization only",
            style="Muted.TLabel",
        ).pack(side="left", padx=12)
        ttk.Button(
            visual3d_toolbar,
            text="Rotate ↻",
            style="Tool.TButton",
            command=lambda: self._rotate_3d(30.0),
        ).pack(side="right")
        ttk.Button(
            visual3d_toolbar,
            text="↺ Rotate",
            style="Tool.TButton",
            command=lambda: self._rotate_3d(-30.0),
        ).pack(side="right", padx=(0, 4))
        ttk.Button(
            visual3d_toolbar,
            text="+",
            style="Tool.TButton",
            width=3,
            command=lambda: self._change_visual_zoom(1.2),
        ).pack(side="right", padx=(4, 0))
        ttk.Button(
            visual3d_toolbar,
            text="Fit",
            style="Tool.TButton",
            command=self._reset_visual_view,
        ).pack(side="right", padx=4)
        ttk.Button(
            visual3d_toolbar,
            text="−",
            style="Tool.TButton",
            width=3,
            command=lambda: self._change_visual_zoom(1 / 1.2),
        ).pack(side="right")
        ttk.Button(
            visual3d_toolbar,
            text="Refresh",
            style="Tool.TButton",
            command=self._refresh_visuals,
        ).pack(side="right", padx=(0, 8))
        self.visual3d_canvas = tk.Canvas(self.visual3d_tab, background="#08111f", highlightthickness=0)
        self.visual3d_canvas.pack(fill="both", expand=True)
        self.visual3d_canvas.bind("<Configure>", lambda event: self._draw_3d_workspace())
        self.visual3d_canvas.bind("<MouseWheel>", self._on_visual_mousewheel)
        self.visual3d_canvas.bind("<Button-4>", lambda event: self._change_visual_zoom(1.12))
        self.visual3d_canvas.bind("<Button-5>", lambda event: self._change_visual_zoom(1 / 1.12))
        self.visual3d_canvas.bind("<Double-Button-1>", lambda event: self._reset_visual_view())

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
            background="#08111f",
            foreground="#e2e8f0",
            insertbackground="#f8fafc",
            selectbackground="#1d4ed8",
            selectforeground="#ffffff",
            relief="flat",
            borderwidth=0,
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
        self._refresh_visuals()
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
        query = self.analysis_filter_var.get() if hasattr(self, "analysis_filter_var") else ""
        visible = [
            analysis
            for analysis in self.project.analyses
            if analysis_matches_filter(analysis, query)
        ]
        for analysis in visible:
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
            if self._editor_analysis_id != target:
                self._load_analysis_into_editor(self.project.analysis_by_id(target))
        elif visible and (not query or select_id is not None or self._editor_analysis_id is None):
            first = visible[0].id
            self.project.active_analysis_id = first
            self.analysis_tree.selection_set(first)
            self.analysis_tree.focus(first)
            self._load_analysis_into_editor(visible[0])
        elif not self.project.analyses:
            self._editor_analysis_id = None
            self.input_text.delete("1.0", "end")
            self.input_text.edit_modified(False)
            self.refresh_structure(silent=True)
        self._refresh_dashboard()

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
        self._selected_room_name = None
        self.input_text.delete("1.0", "end")
        self.input_text.insert(
            "1.0",
            json.dumps(analysis.input, indent=2, ensure_ascii=False, sort_keys=False),
        )
        self.input_text.edit_modified(False)
        self.status_var.set(f"{analysis.name} — {ANALYSIS_SPECS[analysis.kind].title}")
        self.refresh_structure(silent=True)
        self._restore_run_for(analysis.id)
        self._refresh_dashboard()
        self._refresh_visuals()

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
        self._refresh_visuals()
        self._refresh_dashboard()
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

    def _refresh_dashboard(self) -> None:
        if not hasattr(self, "dashboard_project_var"):
            return
        project_name = (
            self.name_var.get().strip()
            if hasattr(self, "name_var")
            else self.project.name
        )
        description = (
            self.description_var.get().strip()
            if hasattr(self, "description_var")
            else self.project.description
        )
        path_text = "Unsaved project" if self.project_path is None else str(self.project_path)
        self.dashboard_project_var.set(
            f"{project_name}  •  {path_text}"
            + (f"\n{description}" if description else "")
        )
        self.dashboard_analysis_var.set(str(len(self.project.analyses)))
        self.dashboard_runs_var.set(str(len(self._runs_by_analysis)))

        active = self._editor_analysis() or self._current_analysis()
        payload = self._visual_payload() if hasattr(self, "input_text") else {}
        rooms = extract_room_visuals(payload)
        pressure_links = extract_pressure_cascade(payload)
        self.dashboard_rooms_var.set(str(len(rooms)))
        if active is None:
            self.dashboard_active_var.set("None")
            self.dashboard_result_var.set(
                "Add or select an analysis to inspect inputs, run engineering checks, "
                "and open the visual workspaces."
            )
            return

        spec = ANALYSIS_SPECS.get(active.kind)
        title = active.kind if spec is None else spec.title
        self.dashboard_active_var.set(title)
        run = self._runs_by_analysis.get(active.id)
        run_line = "No session result yet." if run is None else f"Latest status: {run.status}"
        room_line = (
            f"Detected {len(rooms)} room record(s) for 2D/3D visualization."
            if rooms
            else "No room geometry detected in this analysis input."
        )
        cascade_line = (
            f"Declared pressure-cascade links: {len(pressure_links)}."
            if pressure_links
            else "No declared pressure-cascade links in this input."
        )
        self.dashboard_result_var.set(
            f"{active.name}\nWorkflow: {title}\n{run_line}\n{room_line}\n{cascade_line}"
        )

    def _change_visual_zoom(self, factor: float) -> None:
        self._visual_zoom = max(0.45, min(3.0, self._visual_zoom * factor))
        self._refresh_visuals()

    def _on_visual_mousewheel(self, event) -> str:
        delta = getattr(event, "delta", 0)
        if delta:
            self._change_visual_zoom(1.12 if delta > 0 else 1 / 1.12)
        return "break"

    def _select_visual_room(self, room_name: str) -> None:
        self._selected_room_name = room_name
        self._refresh_visuals()
        self.status_var.set(f"Selected room — {room_name}")

    def _draw_room_inspector(
        self,
        canvas: tk.Canvas,
        room: dict | None,
        width: float,
        height: float,
    ) -> None:
        if room is None:
            return
        panel_width = 292
        x1 = width - 18
        x0 = max(18, x1 - panel_width)
        y0 = 54
        area = room["length_m"] * room["width_m"]
        volume = area * room["height_m"]
        metrics = room_visual_engineering_metrics(room)
        lines = [
            room["name"],
            f'{room["length_m"]:.2f} × {room["width_m"]:.2f} × {room["height_m"]:.2f} m',
            f"Area  {area:.2f} m²",
            f"Volume  {volume:.2f} m³",
        ]
        if room.get("position_real"):
            lines.append(f'Origin  ({room["x_m"]:.2f}, {room["y_m"]:.2f}) m')
        if room.get("airflow_m3_h") is not None:
            lines.append(f'Airflow  {room["airflow_m3_h"]:g} m³/h')

        ach = metrics["ach"]
        min_ach = metrics["min_ach"]
        if min_ach is not None:
            if ach is None:
                lines.append(f"ACH  unavailable  • min {min_ach:g}  • UNKNOWN")
            else:
                lines.append(
                    f'ACH  {ach:.1f}  • min {min_ach:g}  • {metrics["ach_status"].upper()}'
                )
        elif ach is not None:
            lines.append(f"ACH  {ach:.1f}")

        pressure = metrics["pressure_pa"]
        min_pressure = metrics["min_pressure_pa"]
        if min_pressure is not None:
            if pressure is None:
                lines.append(f"Pressure  unavailable  • min {min_pressure:g} Pa  • UNKNOWN")
            else:
                lines.append(
                    f'Pressure  {pressure:g} Pa  • min {min_pressure:g}  • '
                    f'{metrics["pressure_status"].upper()}'
                )
        elif pressure is not None:
            lines.append(f"Pressure  {pressure:g} Pa")

        if metrics["status"] in {"pass", "fail"}:
            lines.append(f'Room requirements  {metrics["status"].upper()}')

        y1 = min(height - 18, y0 + 34 + 22 * len(lines))
        canvas.create_rectangle(
            x0,
            y0,
            x1,
            y1,
            fill="#0f172a",
            outline="#334155",
            width=1,
        )
        canvas.create_text(
            x0 + 14,
            y0 + 13,
            anchor="nw",
            text="ROOM INSPECTOR",
            fill="#94a3b8",
            font=("Segoe UI", 8, "bold"),
        )
        for index, line in enumerate(lines):
            fill = "#f8fafc" if index == 0 else "#cbd5e1"
            if line.endswith("PASS"):
                fill = "#86efac"
            elif line.endswith("FAIL"):
                fill = "#fca5a5"
            elif line.endswith("UNKNOWN"):
                fill = "#cbd5e1"
            canvas.create_text(
                x0 + 14,
                y0 + 34 + index * 22,
                anchor="nw",
                text=line,
                fill=fill,
                font=("Segoe UI", 10, "bold" if index == 0 else "normal"),
            )

    def _reset_visual_view(self) -> None:
        self._visual_zoom = 1.0
        self._visual3d_yaw_deg = 0.0
        self._refresh_visuals()

    def _rotate_3d(self, delta_deg: float) -> None:
        self._visual3d_yaw_deg = (self._visual3d_yaw_deg + delta_deg) % 360.0
        self._draw_3d_workspace()

    def _visual_payload(self) -> dict:
        text = self.input_text.get("1.0", "end-1c").strip() if hasattr(self, "input_text") else ""
        if not text:
            return {}
        try:
            payload = _strict_json_loads(text)
        except (json.JSONDecodeError, ValueError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _refresh_visuals(self) -> None:
        if hasattr(self, "visual2d_canvas"):
            self._draw_2d_workspace()
        if hasattr(self, "visual3d_canvas"):
            self._draw_3d_workspace()

    def _room_layout(self, rooms: list[dict]) -> tuple[list[dict], bool]:
        """Use declared plan coordinates when complete, otherwise auto-arrange deterministically."""
        if not rooms:
            return [], False
        if all(room.get("position_real") for room in rooms):
            placed = [
                {
                    **room,
                    "x": float(room["x_m"]),
                    "y": float(room["y_m"]),
                }
                for room in rooms
            ]
            return placed, all(room["dimensions_real"] for room in rooms)

        columns = max(1, min(4, int(len(rooms) ** 0.5 + 0.999)))
        max_length = max(room["length_m"] for room in rooms)
        max_width = max(room["width_m"] for room in rooms)
        gap = max(max_length, max_width) * 0.22 + 0.7
        placed: list[dict] = []
        for index, room in enumerate(rooms):
            col = index % columns
            row = index // columns
            placed.append({
                **room,
                "x": col * (max_length + gap),
                "y": row * (max_width + gap),
            })
        return placed, all(room["dimensions_real"] for room in rooms)

    def _draw_2d_workspace(self) -> None:
        canvas = self.visual2d_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 640)
        height = max(canvas.winfo_height(), 420)
        payload = self._visual_payload()
        rooms = extract_room_visuals(payload)
        if not rooms:
            canvas.create_text(width / 2, height / 2 - 12, text="No room geometry found in the selected analysis.", fill="#e2e8f0", font=("Segoe UI", 13, "bold"))
            canvas.create_text(width / 2, height / 2 + 18, text="Use an analysis containing a rooms[] list to populate the 2D workspace.", fill="#94a3b8", font=("Segoe UI", 10))
            return

        room_metrics = {
            room["name"]: room_visual_engineering_metrics(room)
            for room in rooms
        }
        placed, fully_scaled = self._room_layout(rooms)
        declared_positions = all(room.get("position_real") for room in rooms)
        min_x = min(room["x"] for room in placed)
        min_y = min(room["y"] for room in placed)
        max_x = max(room["x"] + room["length_m"] for room in placed)
        max_y = max(room["y"] + room["width_m"] for room in placed)
        pad = 68
        scale = min((width - 2 * pad) / max(max_x - min_x, 1.0), (height - 2 * pad) / max(max_y - min_y, 1.0))
        scale = max(8.0, min(scale, 95.0)) * self._visual_zoom

        canvas.create_text(
            18,
            18,
            anchor="nw",
            text=(
                (
                    "Coordinates and dimensions to scale."
                    if fully_scaled and declared_positions
                    else (
                        "Dimensions to scale; placement auto-arranged."
                        if fully_scaled
                        else "Schematic view: missing geometry uses display defaults."
                    )
                )
                + f"  •  Zoom {self._visual_zoom:.0%}"
            ),
            fill="#94a3b8",
            font=("Segoe UI", 9),
        )
        canvas.create_text(
            18,
            38,
            anchor="nw",
            text="Requirement status: green PASS  •  red FAIL  •  blue UNKNOWN/not declared",
            fill="#64748b",
            font=("Segoe UI", 8),
        )
        palette = ("#164e63", "#1e3a8a", "#3f3f46", "#14532d", "#581c87", "#7c2d12")
        status_colors = {
            "pass": "#22c55e",
            "fail": "#ef4444",
            "unknown": "#93c5fd",
        }
        for index, room in enumerate(placed):
            metrics = room_metrics[room["name"]]
            x0 = pad + (room["x"] - min_x) * scale
            y0 = pad + (room["y"] - min_y) * scale
            x1 = x0 + room["length_m"] * scale
            y1 = y0 + room["width_m"] * scale
            room_tag = f"room-2d-{index}"
            selected = room["name"] == self._selected_room_name
            outline = "#facc15" if selected else status_colors[metrics["status"]]
            canvas.create_rectangle(
                x0,
                y0,
                x1,
                y1,
                fill=palette[index % len(palette)],
                outline=outline,
                width=4 if selected else 2,
                tags=(room_tag,),
            )
            canvas.create_text(
                (x0 + x1) / 2,
                (y0 + y1) / 2 - 10,
                text=room["name"],
                fill="#f8fafc",
                font=("Segoe UI", 10, "bold"),
                tags=(room_tag,),
            )
            dims = f'{room["length_m"]:.2g} × {room["width_m"]:.2g} m' if room["dimensions_real"] else "size not specified"
            canvas.create_text(
                (x0 + x1) / 2,
                (y0 + y1) / 2 + 9,
                text=dims,
                fill="#dbeafe",
                font=("Segoe UI", 9),
                tags=(room_tag,),
            )
            canvas.tag_bind(
                room_tag,
                "<Button-1>",
                lambda event, room_name=room["name"]: self._select_visual_room(room_name),
            )
            meta = []
            if metrics["ach"] is not None:
                meta.append(f'ACH {metrics["ach"]:.1f}')
            elif room["airflow_m3_h"] is not None:
                meta.append(f'Q {room["airflow_m3_h"]:g} m³/h')
            if room["pressure_pa"] is not None:
                meta.append(f'P {room["pressure_pa"]:g} Pa')
            if metrics["status"] in {"pass", "fail"}:
                meta.append(metrics["status"].upper())
            if meta:
                canvas.create_text(
                    (x0 + x1) / 2,
                    min(y1 - 12, (y0 + y1) / 2 + 28),
                    text="  •  ".join(meta),
                    fill=(
                        "#86efac"
                        if metrics["status"] == "pass"
                        else "#fca5a5"
                        if metrics["status"] == "fail"
                        else "#bfdbfe"
                    ),
                    font=("Segoe UI", 8, "bold" if metrics["status"] != "unknown" else "normal"),
                    tags=(room_tag,),
                )

        centers = {
            room["name"]: (
                pad + (room["x"] - min_x + room["length_m"] / 2) * scale,
                pad + (room["y"] - min_y + room["width_m"] / 2) * scale,
            )
            for room in placed
        }
        pressure_links = evaluate_pressure_cascade_visuals(
            rooms,
            extract_pressure_cascade(payload),
        )
        cascade_colors = {
            "pass": "#22c55e",
            "fail": "#f87171",
            "unknown": "#facc15",
        }
        for link in pressure_links:
            start = centers.get(link["higher_pressure_room"])
            end = centers.get(link["lower_pressure_room"])
            if start is None or end is None:
                continue
            sx, sy = start
            ex, ey = end
            color = cascade_colors[link["status"]]
            canvas.create_line(
                sx,
                sy,
                ex,
                ey,
                fill=color,
                width=3 if link["status"] == "fail" else 2,
                dash=(6, 4),
                arrow="last",
                arrowshape=(10, 12, 4),
            )
            minimum = link["min_delta_pa"]
            observed = link["observed_delta_pa"]
            if observed is not None and minimum is not None:
                label = f'Δ {observed:g} Pa / min {minimum:g} • {link["status"].upper()}'
            elif minimum is not None:
                label = f"Δ unknown / min {minimum:g} Pa"
            elif observed is not None:
                label = f"Δ {observed:g} Pa"
            else:
                label = "pressure cascade"
            canvas.create_text(
                (sx + ex) / 2,
                (sy + ey) / 2 - 10,
                text=label,
                fill=color,
                font=("Segoe UI", 8, "bold"),
            )

        selected_room = next(
            (room for room in rooms if room["name"] == self._selected_room_name),
            None,
        )
        self._draw_room_inspector(canvas, selected_room, width, height)

    def _draw_3d_workspace(self) -> None:
        canvas = self.visual3d_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 640)
        height = max(canvas.winfo_height(), 420)
        rooms = extract_room_visuals(self._visual_payload())
        if not rooms:
            canvas.create_text(width / 2, height / 2 - 12, text="No room geometry found for 3D preview.", fill="#e2e8f0", font=("Segoe UI", 13, "bold"))
            canvas.create_text(width / 2, height / 2 + 18, text="The preview activates when the selected analysis contains rooms[].", fill="#94a3b8", font=("Segoe UI", 10))
            return

        room_metrics = {
            room["name"]: room_visual_engineering_metrics(room)
            for room in rooms
        }
        placed, fully_scaled = self._room_layout(rooms)
        declared_positions = all(room.get("position_real") for room in rooms)
        iso_x = 0.74
        iso_y = 0.38
        z_scale = 0.78
        theta = math.radians(self._visual3d_yaw_deg)
        cos_t, sin_t = math.cos(theta), math.sin(theta)

        def rotate_xy(x: float, y: float) -> tuple[float, float]:
            return x * cos_t - y * sin_t, x * sin_t + y * cos_t

        raw_points: list[tuple[float, float]] = []
        for room in placed:
            x, y = room["x"], room["y"]
            l, w, h = room["length_m"], room["width_m"], room["height_m"]
            for px, py, pz in (
                (x, y, 0),
                (x + l, y, 0),
                (x + l, y + w, 0),
                (x, y + w, 0),
                (x, y, h),
                (x + l, y, h),
                (x + l, y + w, h),
                (x, y + w, h),
            ):
                rx, ry = rotate_xy(px, py)
                raw_points.append(
                    ((rx - ry) * iso_x, (rx + ry) * iso_y - pz * z_scale)
                )

        min_rx = min(point[0] for point in raw_points)
        max_rx = max(point[0] for point in raw_points)
        min_ry = min(point[1] for point in raw_points)
        max_ry = max(point[1] for point in raw_points)
        raw_w = max(max_rx - min_rx, 1.0)
        raw_h = max(max_ry - min_ry, 1.0)
        scale = min((width - 150) / raw_w, (height - 150) / raw_h)
        scale = max(7.0, min(scale, 55.0)) * self._visual_zoom
        origin_x = (width - (min_rx + max_rx) * scale) / 2
        origin_y = (height - (min_ry + max_ry) * scale) / 2

        def project(x: float, y: float, z: float = 0.0) -> tuple[float, float]:
            rx, ry = rotate_xy(x, y)
            return (
                origin_x + (rx - ry) * iso_x * scale,
                origin_y + ((rx + ry) * iso_y - z * z_scale) * scale,
            )

        palette = ("#0e7490", "#1d4ed8", "#52525b", "#15803d", "#7e22ce", "#c2410c")
        status_colors = {
            "pass": "#22c55e",
            "fail": "#ef4444",
            "unknown": "#60a5fa",
        }
        ordered = sorted(
            enumerate(placed),
            key=lambda pair: rotate_xy(
                pair[1]["x"] + pair[1]["length_m"] / 2,
                pair[1]["y"] + pair[1]["width_m"] / 2,
            )[1],
            reverse=True,
        )
        for index, room in ordered:
            metrics = room_metrics[room["name"]]
            x, y = room["x"], room["y"]
            l, w, h = room["length_m"], room["width_m"], room["height_m"]
            p000 = project(x, y, 0)
            p100 = project(x + l, y, 0)
            p110 = project(x + l, y + w, 0)
            p010 = project(x, y + w, 0)
            p001 = project(x, y, h)
            p101 = project(x + l, y, h)
            p111 = project(x + l, y + w, h)
            p011 = project(x, y + w, h)
            base = palette[index % len(palette)]
            room_tag = f"room-3d-{index}"
            selected = room["name"] == self._selected_room_name
            requirement_outline = status_colors[metrics["status"]]
            outline = "#facc15" if selected else requirement_outline
            top_outline = "#fde047" if selected else requirement_outline
            side_width = 3 if selected or metrics["status"] == "fail" else 1
            top_width = 4 if selected else 2
            canvas.create_polygon(
                *p010, *p110, *p111, *p011,
                fill="#123047", outline=outline, width=side_width, tags=(room_tag,)
            )
            canvas.create_polygon(
                *p100, *p110, *p111, *p101,
                fill="#102a43", outline=outline, width=side_width, tags=(room_tag,)
            )
            canvas.create_polygon(
                *p001, *p101, *p111, *p011,
                fill=base, outline=top_outline, width=top_width, tags=(room_tag,)
            )
            cx, cy = project(x + l / 2, y + w / 2, h)
            canvas.create_text(
                cx, cy - 8, text=room["name"], fill="#ffffff",
                font=("Segoe UI", 9, "bold"), tags=(room_tag,)
            )
            canvas.tag_bind(
                room_tag,
                "<Button-1>",
                lambda event, room_name=room["name"]: self._select_visual_room(room_name),
            )
            meta = []
            if room["height_real"]:
                meta.append(f"h={h:.2g} m")
            if metrics["ach"] is not None:
                meta.append(f'ACH={metrics["ach"]:.1f}')
            if metrics["status"] in {"pass", "fail"}:
                meta.append(metrics["status"].upper())
            if meta:
                canvas.create_text(
                    cx,
                    cy + 9,
                    text=" • ".join(meta),
                    fill=(
                        "#86efac"
                        if metrics["status"] == "pass"
                        else "#fca5a5"
                        if metrics["status"] == "fail"
                        else "#dbeafe"
                    ),
                    font=("Segoe UI", 8, "bold" if metrics["status"] != "unknown" else "normal"),
                    tags=(room_tag,),
                )

        note = (
            "Scaled declared coordinates and room dimensions."
            if fully_scaled and declared_positions
            else (
                "Scaled room dimensions; auto-arranged for preview."
                if fully_scaled
                else "Conceptual preview; missing geometry uses display defaults."
            )
        )
        note += (
            f"  View {self._visual3d_yaw_deg:.0f}°"
            f"  •  Zoom {self._visual_zoom:.0%}"
        )
        canvas.create_text(
            18,
            18,
            anchor="nw",
            text=note,
            fill="#94a3b8",
            font=("Segoe UI", 9),
        )
        canvas.create_text(
            18,
            38,
            anchor="nw",
            text="Requirement status: green PASS  •  red FAIL  •  blue UNKNOWN/not declared",
            fill="#64748b",
            font=("Segoe UI", 8),
        )
        selected_room = next(
            (room for room in rooms if room["name"] == self._selected_room_name),
            None,
        )
        self._draw_room_inspector(canvas, selected_room, width, height)

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
