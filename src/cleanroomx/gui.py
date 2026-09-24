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
    run_analysis,
    validate_analysis_input,
)
from .project import (
    AnalysisDocument,
    ProjectDocument,
    load_project_document,
    new_project,
    save_project_document,
)


_UNIT_SUFFIXES = (
    ("_m3_h", "m³/h"),
    ("_m3_s", "m³/s"),
    ("_m2", "m²"),
    ("_m3", "m³"),
    ("_pa", "Pa"),
    ("_kw", "kW"),
    ("_w", "W"),
    ("_c", "°C"),
    ("_percent", "%"),
    ("_minutes", "min"),
    ("_um", "µm"),
    ("_kg_m3", "kg/m³"),
    ("_m2_s", "m²/s"),
    ("_m", "m"),
)


def unit_hint(path: str) -> str:
    key = path.rsplit(".", 1)[-1].split("[", 1)[0].lower()
    for suffix, unit in _UNIT_SUFFIXES:
        if key.endswith(suffix):
            return unit
    if key.endswith("_1_h") or key == "ach":
        return "1/h"
    return ""


def parse_analysis_input_text(text: str) -> dict:
    def reject_constant(value: str):
        raise ValueError(f"non-finite JSON value is not allowed: {value}")

    try:
        payload = json.loads(text, parse_constant=reject_constant)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"input JSON is invalid at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError("analysis input must be a JSON object")
    return payload


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
        self.root.geometry("1180x760")
        self.root.minsize(900, 600)

        self.project: ProjectDocument = new_project()
        self.project_path: Path | None = None
        self.last_run: AnalysisRun | None = None
        self.last_run_analysis_id: str | None = None

        self._queue: queue.Queue = queue.Queue()
        self._run_generation = 0
        self._running = False
        self._loaded_analysis_id: str | None = None
        self._selection_guard = False
        self._saved_signature: str | None = None

        self.name_var = tk.StringVar(value=self.project.name)
        self.description_var = tk.StringVar(value=self.project.description)
        self.status_var = tk.StringVar(value="Ready")
        self.wrap_outputs_var = tk.BooleanVar(value=False)

        self._build_menu()
        self._build_layout()
        self._refresh_analysis_list()
        self._saved_signature = self._state_signature()
        self._update_title()
        self.name_var.trace_add("write", lambda *_: self._update_title())
        self.description_var.trace_add("write", lambda *_: self._update_title())
        self.input_text.bind("<<Modified>>", self._on_editor_modified, add="+")
        self.input_text.edit_modified(False)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._poll_worker)

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

        self.result_text = self._add_text_tab("Results")
        self.report_text = self._add_text_tab("Report")
        self.diagnostics_text = self._add_text_tab("Diagnostics")

        plot_tab = ttk.Frame(self.notebook)
        self.notebook.add(plot_tab, text="Plot")
        self.plot_canvas = tk.Canvas(plot_tab, highlightthickness=0)
        self.plot_canvas.pack(fill="both", expand=True)
        self.plot_canvas.bind("<Configure>", lambda event: self._draw_plot())

        status = ttk.Label(
            self.root,
            textvariable=self.status_var,
            anchor="w",
            relief="sunken",
            padding=(6, 3),
        )
        status.pack(fill="x", side="bottom")

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

    def _current_analysis(self) -> AnalysisDocument | None:
        selection = self.analysis_tree.selection()
        if not selection:
            return None
        try:
            return self.project.analysis_by_id(selection[0])
        except KeyError:
            return None

    def _loaded_analysis(self) -> AnalysisDocument | None:
        if self._loaded_analysis_id is None:
            return None
        try:
            return self.project.analysis_by_id(self._loaded_analysis_id)
        except KeyError:
            return None

    def _commit_loaded_editor(self, *, sync_metadata: bool = True) -> AnalysisDocument:
        analysis = self._loaded_analysis()
        if analysis is None:
            raise ValueError("select or add an analysis first")
        payload = parse_analysis_input_text(self.input_text.get("1.0", "end-1c"))
        analysis.input = payload
        if sync_metadata:
            self._sync_metadata()
        return analysis

    def _commit_editor(self) -> AnalysisDocument:
        analysis = self._current_analysis()
        if analysis is None:
            raise ValueError("select or add an analysis first")
        if self._loaded_analysis_id != analysis.id:
            raise RuntimeError("selected analysis is not loaded in the editor")
        return self._commit_loaded_editor(sync_metadata=True)

    def _state_signature(self) -> str:
        data = copy.deepcopy(self.project.to_dict())
        data["active_analysis_id"] = None
        project_data = data["project"]
        project_data["name"] = self.name_var.get()
        project_data["description"] = self.description_var.get()

        if self._loaded_analysis_id is not None:
            raw = self.input_text.get("1.0", "end-1c")
            try:
                live_payload = parse_analysis_input_text(raw)
            except ValueError:
                data["_gui_invalid_editor"] = {
                    "analysis_id": self._loaded_analysis_id,
                    "text": raw,
                }
            else:
                for item in data["analyses"]:
                    if item["id"] == self._loaded_analysis_id:
                        item["input"] = live_payload
                        break
        return json.dumps(data, sort_keys=True, ensure_ascii=False, allow_nan=True)

    def _has_unsaved_changes(self) -> bool:
        return (
            self._saved_signature is not None
            and self._state_signature() != self._saved_signature
        )

    def _mark_saved_state(self) -> None:
        self._saved_signature = self._state_signature()
        self._update_title()

    def _on_editor_modified(self, event=None) -> None:
        if self.input_text.edit_modified():
            self.input_text.edit_modified(False)
            self._update_title()

    def _confirm_unsaved_changes(self, action: str) -> bool:
        if not self._has_unsaved_changes():
            return True
        choice = messagebox.askyesnocancel(
            "Unsaved changes",
            f"Save changes before {action}?",
            parent=self.root,
        )
        if choice is None:
            return False
        if choice:
            return self.save_project()
        return True

    def _sync_metadata(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            raise ValueError("project name cannot be empty")
        self.project.name = name
        self.project.description = self.description_var.get()

    def _base_dir(self) -> Path | None:
        return None if self.project_path is None else self.project_path.parent

    def _refresh_analysis_list(self, select_id: str | None = None) -> None:
        self._selection_guard = True
        self._loaded_analysis_id = None
        try:
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
                self.analysis_tree.selection_set(first)
                self.analysis_tree.focus(first)
                self.project.active_analysis_id = first
                self._load_analysis_into_editor(self.project.analyses[0])
            else:
                self.input_text.delete("1.0", "end")
                self.input_text.edit_modified(False)
                self.refresh_structure(silent=True)
        finally:
            self._selection_guard = False

    def _restore_analysis_selection(self, analysis_id: str) -> None:
        self._selection_guard = True
        try:
            if self.analysis_tree.exists(analysis_id):
                self.analysis_tree.selection_set(analysis_id)
                self.analysis_tree.focus(analysis_id)
                self.analysis_tree.see(analysis_id)
        finally:
            self._selection_guard = False

    def _on_analysis_selected(self, event=None) -> None:
        if self._selection_guard:
            return
        analysis = self._current_analysis()
        if analysis is None:
            return
        if (
            self._loaded_analysis_id is not None
            and analysis.id != self._loaded_analysis_id
        ):
            previous_id = self._loaded_analysis_id
            try:
                self._commit_loaded_editor(sync_metadata=False)
            except Exception as exc:
                self.status_var.set("Cannot switch analysis — fix the current input JSON")
                messagebox.showerror(
                    "Cannot switch analysis",
                    f"{exc}\n\nThe current editor contents were preserved.",
                    parent=self.root,
                )
                self._restore_analysis_selection(previous_id)
                return
        self.project.active_analysis_id = analysis.id
        self._load_analysis_into_editor(analysis)
        self._update_title()

    def _load_analysis_into_editor(self, analysis: AnalysisDocument) -> None:
        self._loaded_analysis_id = analysis.id
        self.input_text.delete("1.0", "end")
        self.input_text.insert(
            "1.0",
            json.dumps(analysis.input, indent=2, ensure_ascii=False, sort_keys=False),
        )
        self.input_text.edit_modified(False)
        self.status_var.set(f"{analysis.name} — {ANALYSIS_SPECS[analysis.kind].title}")
        self.refresh_structure(silent=True)
        if self.last_run_analysis_id != analysis.id:
            self._set_text(self.result_text, "")
            self._set_text(self.report_text, "")
            self._set_text(self.diagnostics_text, "")
            self.last_run = None
            self._draw_plot()

    def refresh_structure(self, silent: bool = False) -> None:
        for item in self.structure_tree.get_children():
            self.structure_tree.delete(item)
        text = self.input_text.get("1.0", "end-1c").strip()
        if not text:
            return
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            if not silent:
                messagebox.showerror(
                    "Invalid JSON",
                    f"Line {exc.lineno}, column {exc.colno}: {exc.msg}",
                    parent=self.root,
                )
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
        if not self._confirm_unsaved_changes("creating a new project"):
            return
        self.project = new_project()
        self.project_path = None
        self.name_var.set(self.project.name)
        self.description_var.set("")
        self.last_run = None
        self.last_run_analysis_id = None
        self._refresh_analysis_list()
        self.status_var.set("New project")
        self._mark_saved_state()

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
        if not path:
            return
        if not self._confirm_unsaved_changes("opening another project"):
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
        self.last_run = None
        self.last_run_analysis_id = None
        self._refresh_analysis_list()
        self.status_var.set(f"Opened {project_path.name}")
        self._mark_saved_state()

    def _update_title(self) -> None:
        suffix = "" if self.project_path is None else f" — {self.project_path.name}"
        dirty = " *" if self._has_unsaved_changes() else ""
        self.root.title(f"CleanroomX {__version__}{suffix}{dirty}")

    def save_project(self) -> bool:
        try:
            if self.project.analyses and self._loaded_analysis() is not None:
                self._commit_loaded_editor(sync_metadata=True)
            else:
                self._sync_metadata()
        except Exception as exc:
            messagebox.showerror("Cannot save", str(exc), parent=self.root)
            return False
        if self.project_path is None:
            return self.save_project_as()
        try:
            save_project_document(self.project_path, self.project)
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc), parent=self.root)
            return False
        self.status_var.set(f"Saved {self.project_path.name}")
        self._mark_saved_state()
        return True

    def save_project_as(self) -> bool:
        try:
            if self.project.analyses and self._loaded_analysis() is not None:
                self._commit_loaded_editor(sync_metadata=True)
            else:
                self._sync_metadata()
        except Exception as exc:
            messagebox.showerror("Cannot save", str(exc), parent=self.root)
            return False
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Save CleanroomX project",
            defaultextension=".cleanroomx.json",
            filetypes=[("CleanroomX project", "*.cleanroomx.json"), ("JSON files", "*.json")],
        )
        if not path:
            return False
        try:
            self.project_path = save_project_document(path, self.project)
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc), parent=self.root)
            return False
        self.status_var.set(f"Saved {self.project_path.name}")
        self._mark_saved_state()
        return True

    def add_analysis(self) -> None:
        if self._loaded_analysis() is not None:
            try:
                self._commit_loaded_editor(sync_metadata=False)
            except Exception as exc:
                messagebox.showerror(
                    "Cannot add analysis",
                    f"Fix the current input JSON first.\n\n{exc}",
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
        analysis = self._current_analysis()
        if analysis is None:
            return
        if not messagebox.askyesno(
            "Remove analysis",
            f"Remove {analysis.name!r} from this project?",
            parent=self.root,
        ):
            return
        self.project.analyses = [item for item in self.project.analyses if item.id != analysis.id]
        self.project.active_analysis_id = (
            self.project.analyses[0].id if self.project.analyses else None
        )
        self._refresh_analysis_list()
        self._update_title()

    def import_input_json(self) -> None:
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
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("input file must contain a JSON object")
        except Exception as exc:
            messagebox.showerror("Import failed", str(exc), parent=self.root)
            return
        analysis.input = payload
        self._load_analysis_into_editor(analysis)
        self.status_var.set(f"Imported {Path(path).name}")
        self._update_title()

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
            Path(path).write_text(
                json.dumps(analysis.input, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                encoding="utf-8",
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
        if not self._running:
            return
        self._run_generation += 1
        self._set_running(False)
        self.status_var.set(
            "Run abandoned in the UI; backend computation may finish in its worker thread."
        )

    def _set_running(self, running: bool) -> None:
        self._running = running
        self.run_button.configure(state="disabled" if running else "normal")
        self.cancel_button.configure(state="normal" if running else "disabled")

    def _poll_worker(self) -> None:
        try:
            while True:
                kind, generation, analysis_id, payload = self._queue.get_nowait()
                if generation != self._run_generation:
                    continue
                self._set_running(False)
                if kind == "error":
                    self.status_var.set("Analysis failed")
                    messagebox.showerror("Analysis failed", str(payload), parent=self.root)
                else:
                    self.last_run = payload
                    self.last_run_analysis_id = analysis_id
                    self._render_run(payload)
                    self.status_var.set(
                        f"Completed — {payload.title} — status: {payload.status}"
                    )
        except queue.Empty:
            pass
        self.root.after(100, self._poll_worker)

    def _render_run(self, run: AnalysisRun) -> None:
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

        for series in plot["series"]:
            coords = []
            for x, y in zip(series["x"], series["y"]):
                coords.extend(point(x, y))
            if len(coords) >= 4:
                canvas.create_line(*coords, width=2)
            for x, y in zip(series["x"], series["y"]):
                px, py = point(x, y)
                canvas.create_oval(px - 2, py - 2, px + 2, py + 2, fill="black")

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
            Path(path).write_text(
                json.dumps(
                    self.last_run.result, indent=2, ensure_ascii=False, allow_nan=False
                ) + "\n",
                encoding="utf-8",
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
            Path(path).write_text(self.last_run.markdown, encoding="utf-8")

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

    def smoke_check_editor_transition(self) -> None:
        if len(self.project.analyses) < 2:
            return
        source = self._current_analysis()
        if source is None:
            raise ValueError("smoke project has no active analysis")
        target = next(item for item in self.project.analyses if item.id != source.id)
        original = copy.deepcopy(source.input)
        probe = copy.deepcopy(original)
        probe["__cleanroomx_gui_smoke_probe__"] = "preserve-on-switch"
        self.input_text.delete("1.0", "end")
        self.input_text.insert("1.0", json.dumps(probe, indent=2, ensure_ascii=False))
        self.input_text.edit_modified(False)

        self.analysis_tree.selection_set(target.id)
        self.analysis_tree.focus(target.id)
        self.root.update_idletasks()
        self.root.update()
        committed = self.project.analysis_by_id(source.id).input
        if committed.get("__cleanroomx_gui_smoke_probe__") != "preserve-on-switch":
            raise RuntimeError("GUI editor transition lost unsaved analysis input")

        self.project.analysis_by_id(source.id).input = original
        self.analysis_tree.selection_set(source.id)
        self.analysis_tree.focus(source.id)
        self.root.update_idletasks()
        self.root.update()

    def smoke_run_active(self) -> AnalysisRun:
        analysis = self._current_analysis()
        if analysis is None:
            raise ValueError("smoke project has no active analysis")
        run = run_analysis(analysis.kind, analysis.input, base_dir=self._base_dir())
        self.last_run = run
        self.last_run_analysis_id = analysis.id
        self._render_run(run)
        return run

    def _on_close(self) -> None:
        if self._running:
            if not messagebox.askyesno(
                "Analysis running",
                "An analysis is still running. Abandon it and exit?",
                parent=self.root,
            ):
                return
            self._run_generation += 1
            self._set_running(False)
        if not self._confirm_unsaved_changes("exiting"):
            return
        self.root.destroy()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-gui",
        description="CleanroomX desktop engineering application",
    )
    parser.add_argument("project", nargs="?", help="Optional CleanroomX project file to open")
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
    args = build_parser().parse_args(argv)
    if args.check:
        print(json.dumps(application_info(), indent=2, ensure_ascii=False))
        return 0

    root = tk.Tk()
    app = CleanroomXApp(root)
    if args.project:
        app.load_project_path(args.project)

    if args.smoke:
        if args.project and app.project.analyses:
            app.smoke_check_editor_transition()
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
