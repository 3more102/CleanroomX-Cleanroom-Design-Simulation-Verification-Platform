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
from .autosave import (
    DEFAULT_AUTOSAVE_INTERVAL_SECONDS,
    AutosaveManager,
    discard_recovery_artifact,
    restore_recovery_artifact,
    scan_recovery_artifacts,
)
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
    ProjectWriteConflictError,
    capture_project_file_revision,
    load_project_document,
    load_project_document_with_revision,
    new_project,
    save_project_document,
    save_project_document_guarded,
)
from .persistence import PersistenceDurabilityError, atomic_write_text
from .recovery_ui import RecoveryCenter
from .spatial import SpatialDesignWorkspace, sync_layout_to_analysis


RECOVERY_CHECKPOINT_DEBOUNCE_MS = 1500


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
    def __init__(
        self,
        root: tk.Tk,
        *,
        autosave_interval_seconds: float = DEFAULT_AUTOSAVE_INTERVAL_SECONDS,
        autosave_manager: AutosaveManager | None = None,
    ):
        self.root = root
        self.root.title(f"CleanroomX {__version__}")
        self.root.geometry("1440x900")
        self.root.minsize(1050, 680)

        self.project: ProjectDocument = new_project()
        self.project_path: Path | None = None
        self._project_file_revision = None
        self._recovery_source_path: Path | None = None
        self._restored_recovery_artifact: Path | None = None
        self.last_run: AnalysisRun | None = None
        self.last_run_analysis_id: str | None = None
        self._runs_by_analysis: dict[str, AnalysisRun] = {}
        self._editor_analysis_id: str | None = None
        self._selection_guard = False
        self._baseline_state: str | None = None
        self._autosave_interval_seconds = max(0.0, float(autosave_interval_seconds))
        self._autosave_interval_ms = (
            max(1000, int(self._autosave_interval_seconds * 1000))
            if self._autosave_interval_seconds > 0
            else 0
        )
        self._autosave_manager = autosave_manager or AutosaveManager()
        self._autosave_manager.begin_project(None)
        self._autosave_status_sequence = -1
        self._recovery_checkpoint_after_id = None

        self._queue: queue.Queue = queue.Queue()
        self._run_generation = 0
        self._running = False
        self._abandon_requested = False

        self.name_var = tk.StringVar(value=self.project.name)
        self.description_var = tk.StringVar(value=self.project.description)
        self.status_var = tk.StringVar(value="Ready")
        self.autosave_status_var = tk.StringVar(
            value=(
                "Autosave: ready"
                if self._autosave_interval_ms
                else "Autosave: disabled"
            )
        )
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
        if self._autosave_interval_ms:
            self.root.after(self._autosave_interval_ms, self._autosave_tick)
            self.root.after(500, self._poll_autosave_status)

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="New Project", accelerator="Ctrl+N", command=self.new_project)
        file_menu.add_command(label="Open Project...", accelerator="Ctrl+O", command=self.open_project)
        file_menu.add_command(label="Save Project", accelerator="Ctrl+S", command=self.save_project)
        file_menu.add_command(label="Save Project As...", command=self.save_project_as)
        file_menu.add_command(label="Recovery Center...", command=self.show_recovery_center)
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
        metadata = ttk.Frame(self.root, padding=(8, 8, 8, 4))
        metadata.pack(fill="x")
        ttk.Label(metadata, text="Project").grid(row=0, column=0, sticky="w")
        ttk.Entry(metadata, textvariable=self.name_var, width=32).grid(
            row=0, column=1, sticky="ew", padx=(6, 12)
        )
        ttk.Label(metadata, text="Description").grid(row=0, column=2, sticky="w")
        ttk.Entry(metadata, textvariable=self.description_var).grid(
            row=0, column=3, sticky="ew", padx=(6, 12)
        )
        ttk.Button(metadata, text="Validate", command=self.validate_current).grid(
            row=0, column=4, padx=3
        )
        self.run_button = ttk.Button(metadata, text="Run", command=self.run_current)
        self.run_button.grid(row=0, column=5, padx=3)
        self.cancel_button = ttk.Button(
            metadata, text="Abandon", command=self.cancel_run, state="disabled"
        )
        self.cancel_button.grid(row=0, column=6, padx=3)
        metadata.columnconfigure(1, weight=1)
        metadata.columnconfigure(3, weight=2)

        panes = ttk.Panedwindow(self.root, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=8, pady=4)

        sidebar = ttk.Frame(panes, padding=4)
        panes.add(sidebar, weight=1)
        ttk.Label(sidebar, text="Analyses", font=("TkDefaultFont", 10, "bold")).pack(
            anchor="w", pady=(0, 4)
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
        self.notebook = ttk.Notebook(content)
        self.notebook.pack(fill="both", expand=True)

        self.spatial_workspace = SpatialDesignWorkspace(
            self.notebook,
            project_getter=lambda: self.project,
            analysis_getter=self._editor_analysis,
            on_change=self._on_spatial_changed,
            on_sync_requested=self._sync_spatial_to_current_analysis,
            status_setter=self.status_var.set,
        )
        self.notebook.add(self.spatial_workspace, text="Design 2D + 3D")

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
        self.input_text = tk.Text(json_tab, wrap="none", undo=True)
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

        status_bar = ttk.Frame(self.root)
        status_bar.pack(fill="x", side="bottom")
        status = ttk.Label(
            status_bar,
            textvariable=self.status_var,
            anchor="w",
            relief="sunken",
            padding=(6, 3),
        )
        status.pack(fill="x", side="left", expand=True)
        autosave_status = ttk.Label(
            status_bar,
            textvariable=self.autosave_status_var,
            anchor="e",
            relief="sunken",
            padding=(8, 3),
        )
        autosave_status.pack(side="right")

    def _add_text_tab(self, title: str) -> tk.Text:
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=title)
        text = tk.Text(frame, wrap="none", state="disabled")
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
        if self.project_path is not None:
            return self.project_path.parent
        recovery_source = getattr(self, "_recovery_source_path", None)
        if recovery_source is not None:
            return recovery_source.parent
        return None

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

    def _build_recovery_snapshot(self) -> dict:
        project_data = copy.deepcopy(self.project.to_dict())
        name_text = self.name_var.get()
        description_text = self.description_var.get()
        editor_text = ""
        editor_json_valid = True

        if name_text.strip():
            project_data["project"]["name"] = name_text.strip()
        project_data["project"]["description"] = description_text

        if self._editor_analysis_id is not None:
            editor_text = self.input_text.get("1.0", "end-1c")
            try:
                payload = _strict_json_loads(editor_text)
                if not isinstance(payload, dict):
                    editor_json_valid = False
                else:
                    for analysis in project_data["analyses"]:
                        if analysis["id"] == self._editor_analysis_id:
                            analysis["input"] = payload
                            break
            except (json.JSONDecodeError, ValueError):
                editor_json_valid = False

        return {
            "project": project_data,
            "ui_state": {
                "name_text": name_text,
                "description_text": description_text,
                "editor_analysis_id": self._editor_analysis_id,
                "editor_text": editor_text,
                "editor_json_valid": editor_json_valid,
            },
        }

    def _begin_autosave_project(self, path: str | Path | None) -> None:
        self._cancel_recovery_checkpoint()
        manager = getattr(self, "_autosave_manager", None)
        if manager is not None:
            manager.begin_project(path)

    def _notify_explicit_save(self, path: str | Path) -> None:
        self._cancel_recovery_checkpoint()
        manager = getattr(self, "_autosave_manager", None)
        cleanup_failed = False
        if manager is not None:
            manager.notify_explicit_save(path)
            cleanup_failed = manager.status().state == "failed"
        autosave_var = getattr(self, "autosave_status_var", None)
        if autosave_var is not None:
            autosave_var.set(
                "Autosave: recovery cleanup failed"
                if cleanup_failed
                else "Autosave: clean"
            )

    def _discard_current_autosave(self) -> None:
        self._cancel_recovery_checkpoint()
        manager = getattr(self, "_autosave_manager", None)
        if manager is not None:
            manager.discard_current_recoveries()

    def _discard_restored_recovery(self) -> None:
        artifact = getattr(self, "_restored_recovery_artifact", None)
        if artifact is None:
            return
        if not artifact.exists():
            self._restored_recovery_artifact = None
            return
        try:
            discard_recovery_artifact(artifact, recovery_dir=artifact.parent)
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as exc:
            self.status_var.set(f"Recovery cleanup failed: {exc}")
            return
        self._restored_recovery_artifact = None

    def _autosave_source_path(self) -> Path | None:
        if self.project_path is not None:
            return self.project_path
        return getattr(self, "_recovery_source_path", None)

    def _cancel_recovery_checkpoint(self) -> None:
        token = getattr(self, "_recovery_checkpoint_after_id", None)
        if token is None:
            return
        cancel = getattr(self.root, "after_cancel", None)
        if callable(cancel):
            try:
                cancel(token)
            except tk.TclError:
                pass
        self._recovery_checkpoint_after_id = None

    def _schedule_recovery_checkpoint(self) -> None:
        if not getattr(self, "_autosave_interval_ms", 0):
            return
        schedule = getattr(self.root, "after", None)
        if not callable(schedule):
            return
        self._cancel_recovery_checkpoint()
        self._recovery_checkpoint_after_id = schedule(
            RECOVERY_CHECKPOINT_DEBOUNCE_MS,
            self._run_debounced_recovery_checkpoint,
        )

    def _checkpoint_recovery(self) -> None:
        try:
            if self._has_unsaved_changes():
                snapshot = self._build_recovery_snapshot()
                if self._autosave_manager.request_autosave(
                    snapshot,
                    source_path=self._autosave_source_path(),
                ):
                    self.autosave_status_var.set("Autosave: saving…")
            elif self._autosave_manager.status().state == "saved":
                self._discard_current_autosave()
                cleanup_status = self._autosave_manager.status()
                if cleanup_status.state == "failed":
                    self.autosave_status_var.set("Autosave: recovery cleanup failed")
                    self.status_var.set(cleanup_status.message)
                else:
                    self.autosave_status_var.set("Autosave: clean")
        except (OSError, TypeError, ValueError) as exc:
            self.autosave_status_var.set("Autosave: failed")
            self.status_var.set(f"Autosave failed: {exc}")

    def _run_debounced_recovery_checkpoint(self) -> None:
        self._recovery_checkpoint_after_id = None
        if not getattr(self, "_autosave_interval_ms", 0):
            return
        self._checkpoint_recovery()

    def _autosave_tick(self) -> None:
        if not self._autosave_interval_ms:
            return
        try:
            self._checkpoint_recovery()
        finally:
            self.root.after(self._autosave_interval_ms, self._autosave_tick)

    def _poll_autosave_status(self) -> None:
        status = self._autosave_manager.status()
        if status.sequence != self._autosave_status_sequence:
            self._autosave_status_sequence = status.sequence
            if status.state == "saving":
                self.autosave_status_var.set("Autosave: saving…")
            elif status.state == "saved":
                self.autosave_status_var.set("Autosave: recovery saved")
            elif status.state == "failed":
                self.autosave_status_var.set("Autosave: failed")
                self.status_var.set(status.message)
            elif status.state == "idle":
                self.autosave_status_var.set("Autosave: ready")
        self.root.after(500, self._poll_autosave_status)

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
        self._discard_current_autosave()
        self._discard_restored_recovery()
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

    def restore_recovery_path(self, path: str | Path) -> None:
        recovered = restore_recovery_artifact(path)
        self._discard_current_autosave()
        self.project = recovered.project
        self.project_path = None
        self._project_file_revision = None
        self._recovery_source_path = recovered.source_path
        self._restored_recovery_artifact = recovered.artifact_path
        self._begin_autosave_project(recovered.source_path)

        ui_state = recovered.ui_state
        name_text = ui_state.get("name_text")
        description_text = ui_state.get("description_text")
        self.name_var.set(
            name_text if isinstance(name_text, str) else self.project.name
        )
        self.description_var.set(
            description_text
            if isinstance(description_text, str)
            else self.project.description
        )
        self._clear_run_cache()
        self._refresh_analysis_list()

        editor_id = ui_state.get("editor_analysis_id")
        editor_text = ui_state.get("editor_text")
        if (
            isinstance(editor_id, str)
            and isinstance(editor_text, str)
            and self.analysis_tree.exists(editor_id)
        ):
            self.project.active_analysis_id = editor_id
            self.analysis_tree.selection_set(editor_id)
            self.analysis_tree.focus(editor_id)
            self.analysis_tree.see(editor_id)
            self._editor_analysis_id = editor_id
            self.input_text.delete("1.0", "end")
            self.input_text.insert("1.0", editor_text)
            self.input_text.edit_modified(False)
            self.refresh_structure(silent=True)

        # A recovered copy must require an explicit Save As even when its recovered
        # model happens to equal the source project byte-for-byte.
        self._baseline_state = "__cleanroomx_recovered_copy_requires_save_as__"
        self.status_var.set(
            "Recovered unsaved work — use Save Project As to preserve it separately."
        )
        self.autosave_status_var.set("Autosave: recovered copy")
        self._update_title()

    def show_recovery_center(self, *, announce_empty: bool = True) -> bool:
        try:
            scan = scan_recovery_artifacts(self._autosave_manager.recovery_dir)
        except OSError as exc:
            messagebox.showerror(
                "Recovery scan failed",
                str(exc),
                parent=self.root,
            )
            return False
        if not scan.candidates and not scan.issues:
            if announce_empty:
                self.status_var.set("No recoverable sessions found.")
            return False

        dialog = RecoveryCenter(self.root, scan)
        self.root.wait_window(dialog)
        if dialog.result is None:
            return False
        if not self._confirm_project_replacement():
            return False
        try:
            self.restore_recovery_path(dialog.result)
        except (OSError, ValueError) as exc:
            messagebox.showerror(
                "Recovery restore failed",
                (
                    f"{exc}\n\n"
                    "The recovery artifact was preserved and the original project "
                    "was not changed."
                ),
                parent=self.root,
            )
            return False
        return True

    def offer_startup_recovery(self) -> bool:
        return self.show_recovery_center(announce_empty=False)

    def new_project(self) -> None:
        if self._running:
            messagebox.showwarning("Analysis running", "Abandon the current run first.")
            return
        if not self._confirm_project_replacement():
            return
        self._discard_current_autosave()
        self.project = new_project()
        self.project_path = None
        self._project_file_revision = None
        self._recovery_source_path = None
        self._restored_recovery_artifact = None
        self._begin_autosave_project(None)
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
        project, project_revision = load_project_document_with_revision(project_path)
        self._discard_current_autosave()
        self.project = project
        self.project_path = project_path
        self._project_file_revision = project_revision
        self._recovery_source_path = None
        self._restored_recovery_artifact = None
        self._begin_autosave_project(project_path)
        self.name_var.set(project.name)
        self.description_var.set(project.description)
        self._clear_run_cache()
        self._refresh_analysis_list()
        self._capture_saved_state()
        self.status_var.set(f"Opened {project_path.name}")
        self._update_title()

    def _update_title(self) -> None:
        has_unsaved_changes = self._has_unsaved_changes()
        if has_unsaved_changes:
            self._schedule_recovery_checkpoint()

        title_method = getattr(self.root, "title", None)
        if not callable(title_method):
            return
        if self.project_path is not None:
            suffix = f" — {self.project_path.name}"
        elif getattr(self, "_restored_recovery_artifact", None) is not None:
            suffix = " — Recovered copy"
        else:
            suffix = ""
        dirty = " *" if has_unsaved_changes else ""
        title_method(f"CleanroomX {__version__}{suffix}{dirty}")

    def _report_persistence_durability_failure(
        self,
        path: Path,
        exc: PersistenceDurabilityError,
    ) -> None:
        self.status_var.set(
            f"Write completed for {path.name}, but storage durability was not confirmed."
        )
        messagebox.showwarning(
            "Storage durability not confirmed",
            (
                f"CleanroomX replaced {path.name}, but the operating system reported "
                "a failure while making the directory update durable. Recovery "
                "artifacts were retained. Do not assume the write will survive a "
                "power loss; use Save Project As to another location or reopen and "
                f"verify the file.\n\n{exc}"
            ),
            parent=self.root,
        )

    def _report_external_save_conflict(self, path: Path) -> None:
        self.status_var.set(
            f"Save blocked: {path.name} changed on disk. Use Save Project As or reopen."
        )
        messagebox.showwarning(
            "Project changed on disk",
            (
                f"{path.name} was changed by another process or CleanroomX session "
                "after this window opened it.\n\n"
                "CleanroomX did not overwrite that newer file. Use Save Project As "
                "to preserve this window's work under another name, or reopen the "
                "project to use the on-disk version."
            ),
            parent=self.root,
        )

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

        expected_revision = getattr(self, "_project_file_revision", None)
        try:
            if expected_revision is None:
                expected_revision = capture_project_file_revision(self.project_path)
            saved_path, saved_revision = save_project_document_guarded(
                self.project_path,
                self.project,
                expected_revision=expected_revision,
            )
        except PersistenceDurabilityError as exc:
            self._report_persistence_durability_failure(self.project_path, exc)
            return
        except ProjectWriteConflictError:
            self._report_external_save_conflict(self.project_path)
            return
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc), parent=self.root)
            return

        self.project_path = saved_path
        self._project_file_revision = saved_revision
        self._capture_saved_state()
        self._notify_explicit_save(self.project_path)
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
        recovery_source = getattr(self, "_recovery_source_path", None)
        restored_artifact = getattr(self, "_restored_recovery_artifact", None)
        if (
            restored_artifact is not None
            and recovery_source is not None
            and destination.resolve(strict=False)
            == recovery_source.resolve(strict=False)
        ):
            messagebox.showwarning(
                "Choose a different recovery file",
                (
                    "Recovered work must be saved to a different file first. "
                    "The original project is preserved so both versions remain "
                    "available for comparison."
                ),
                parent=self.root,
            )
            return

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
            same_as_open_project = (
                self.project_path is not None
                and destination.resolve(strict=False)
                == self.project_path.resolve(strict=False)
            )
            expected_revision = (
                getattr(self, "_project_file_revision", None)
                if same_as_open_project
                else capture_project_file_revision(destination)
            )
            if expected_revision is None:
                expected_revision = capture_project_file_revision(destination)
            saved_path, saved_revision = save_project_document_guarded(
                destination,
                candidate,
                expected_revision=expected_revision,
            )
        except PersistenceDurabilityError as exc:
            self._report_persistence_durability_failure(destination, exc)
            return
        except ProjectWriteConflictError:
            self._report_external_save_conflict(destination)
            return
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc), parent=self.root)
            return

        self.project = candidate
        self.project_path = saved_path
        self._project_file_revision = saved_revision
        self._recovery_source_path = None
        if previous_base is not None and self._base_dir() != previous_base:
            self._clear_run_cache()
        if editor_id is not None:
            try:
                self._load_analysis_into_editor(self.project.analysis_by_id(editor_id))
            except KeyError:
                self._refresh_analysis_list()
        self._capture_saved_state()
        self._notify_explicit_save(self.project_path)
        self._discard_restored_recovery()
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
        except PersistenceDurabilityError as exc:
            self.status_var.set(f"{label} written; durability not confirmed")
            messagebox.showwarning(
                f"{label} durability not confirmed",
                str(exc),
                parent=self.root,
            )
            return False
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
            self.notebook.select(1)

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
        self._discard_current_autosave()
        manager = getattr(self, "_autosave_manager", None)
        if manager is not None:
            manager.shutdown(wait=False)
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
    parser.add_argument(
        "--autosave-interval-seconds",
        type=float,
        default=DEFAULT_AUTOSAVE_INTERVAL_SECONDS,
        help=(
            "Recovery autosave interval in seconds; use 0 to disable "
            f"(default: {DEFAULT_AUTOSAVE_INTERVAL_SECONDS:g})"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.demo and args.project:
        parser.error("project path and --demo cannot be used together")
    if args.autosave_interval_seconds < 0:
        parser.error("--autosave-interval-seconds must be zero or greater")
    if args.check:
        print(json.dumps(application_info(), indent=2, ensure_ascii=False))
        return 0

    validate_application_registry()
    project_path = bundled_demo_project_path() if args.demo else args.project

    root = tk.Tk()
    app = CleanroomXApp(
        root,
        autosave_interval_seconds=args.autosave_interval_seconds,
    )
    recovered_at_startup = False
    if not args.smoke:
        recovered_at_startup = app.offer_startup_recovery()

    if project_path and not recovered_at_startup:
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
