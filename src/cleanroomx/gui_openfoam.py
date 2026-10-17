"""Desktop OpenFOAM Foundation v10 workflow and evidence browser."""
from __future__ import annotations

import hashlib
import json
import math
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import Any, Callable

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .cfd_project_handoff import project_room_openfoam_spec
from .cli_output import atomic_write_cli_output, dumps_strict_json
from .cfd_openfoam_timeseries import (
    export_openfoam_time_series_csv,
    read_openfoam_sync_time_series,
)
from .gui_theme import theme_palette
from .proofgraph_io import proofgraph_from_dict
from .strict_json import load_strict_json_snapshot


_MAX_PREVIEW_BYTES = 2_000_000
_MAX_OUTPUT_CHARS = 250_000
_MAX_OUTPUT_EVENTS = 2_048
_MAX_EVENTS_PER_POLL = 256
_OUTPUT_TRIM_NOTICE = (
    "Earlier command output trimmed; showing the most recent "
    f"{_MAX_OUTPUT_CHARS:,} characters.\n"
)
_SIMULATION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_SYNC_SIMULATION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
_EVIDENCE_NAMES = ("manifest.json", "sync-state.json", "sync_manifest.json")
_MAX_PROOFGRAPH_BYTES = 64 * 1024 * 1024


def _enqueue_process_event(
    events: queue.Queue[tuple[str, Any]],
    event: tuple[str, Any],
    *,
    on_output_dropped: Callable[[], None] | None = None,
) -> None:
    """Enqueue reader events without letting a slow Tk loop grow memory forever."""
    while True:
        try:
            events.put_nowait(event)
            return
        except queue.Full:
            try:
                removed = events.get_nowait()
            except queue.Empty:
                continue
            if removed[0] == "output":
                if on_output_dropped is not None:
                    on_output_dropped()
                continue

            # The reader is the only producer. A terminal event is queued after all
            # output, so keep it if a consumer races with the bounded queue.
            events.put_nowait(removed)
            return


def _output_trim_plan(
    current_chars: int,
    *,
    already_trimmed: bool,
    max_chars: int = _MAX_OUTPUT_CHARS,
    notice_chars: int = len(_OUTPUT_TRIM_NOTICE),
) -> tuple[int, bool]:
    """Return the oldest body length to delete and whether to add a notice."""
    if current_chars <= max_chars:
        return 0, False
    add_notice = not already_trimmed
    over_limit = current_chars + (notice_chars if add_notice else 0) - max_chars
    return max(0, over_limit), add_notice


def _process_group_launch_options(*, windows: bool | None = None) -> dict[str, Any]:
    """Start the CLI in a process group that includes solver children."""
    use_windows = os.name == "nt" if windows is None else windows
    if use_windows:
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _kill_windows_process_tree(process: subprocess.Popen[str]) -> None:
    """Use the Windows taskkill tree option for the CLI and its descendants."""
    try:
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        if process.poll() is None:
            process.kill()


def _signal_process_tree(
    process: subprocess.Popen[str],
    *,
    force: bool = False,
    windows: bool | None = None,
) -> None:
    """Stop the OpenFOAM CLI and solver processes it started."""
    use_windows = os.name == "nt" if windows is None else windows
    if use_windows:
        if force:
            _kill_windows_process_tree(process)
            return
        try:
            process.send_signal(signal.CTRL_BREAK_EVENT)
        except (AttributeError, OSError, ValueError):
            _kill_windows_process_tree(process)
        return

    try:
        os.killpg(
            process.pid,
            signal.SIGKILL if force else signal.SIGTERM,
        )
    except ProcessLookupError:
        return
    except OSError:
        if process.poll() is None:
            (process.kill if force else process.terminate)()


def build_openfoam_generate_command(
    specification: str,
    case_directory: str,
    *,
    python_executable: str = sys.executable,
) -> list[str]:
    """Build an argv-only case-generation command."""
    if not specification.strip() or not case_directory.strip():
        raise ValueError("Choose a specification file and a new case directory")
    return [
        python_executable,
        "-m",
        "cleanroomx.cfd_pipeline_cli",
        "generate",
        specification,
        case_directory,
    ]


def build_openfoam_run_command(
    case_directory: str,
    *,
    result_directory: str = "",
    simulation_id: str = "",
    timeout_seconds: int = 3600,
    python_executable: str = sys.executable,
) -> list[str]:
    """Build an argv-only Foundation v10 run command."""
    if not case_directory.strip():
        raise ValueError("Choose a generated case directory")
    command = [
        python_executable,
        "-m",
        "cleanroomx.cfd_pipeline_cli",
        "run",
        case_directory,
        "--timeout-seconds",
        str(timeout_seconds),
    ]
    if result_directory.strip():
        if not simulation_id.strip() or _SIMULATION_ID.fullmatch(simulation_id) is None:
            raise ValueError("Enter a safe simulation ID when synchronizing results")
        command.extend(
            ("--sync-results", result_directory, "--simulation-id", simulation_id)
        )
    elif simulation_id.strip():
        raise ValueError("A simulation ID requires a result directory")
    return command


def build_openfoam_sync_vtk_command(
    source_directory: str,
    result_directory: str,
    configuration_file: str,
    simulation_id: str,
    *,
    field_map_file: str = "",
    once: bool = True,
    interval_seconds: float = 1.0,
    python_executable: str = sys.executable,
) -> list[str]:
    """Build a one-pass or continuous foamToVTK import command."""
    if not all(
        value.strip()
        for value in (
            source_directory,
            result_directory,
            configuration_file,
            simulation_id,
        )
    ):
        raise ValueError(
            "Choose the VTK source, result directory, case manifest, and simulation ID"
        )
    if _SYNC_SIMULATION_ID.fullmatch(simulation_id) is None:
        raise ValueError("Simulation ID must be 1-64 safe ASCII filename characters")
    if type(once) is not bool:
        raise ValueError("once must be a boolean")
    if (
        type(interval_seconds) not in (int, float)
        or not math.isfinite(interval_seconds)
        or not 0.1 <= interval_seconds <= 3600
    ):
        raise ValueError("Scan interval must be finite and in [0.1,3600] seconds")
    command = [
        python_executable,
        "-m",
        "cleanroomx.cfd_pipeline_cli",
        "sync-vtk",
        source_directory,
        result_directory,
        "--simulation-id",
        simulation_id,
        "--configuration-file",
        configuration_file,
    ]
    if field_map_file.strip():
        command.extend(("--field-map-file", field_map_file))
    if once:
        command.append("--once")
    else:
        command.extend(
            (
                "--interval-seconds",
                format(interval_seconds, ".6g"),
                "--stable-seconds",
                "0.5",
                "--quiet-unchanged",
            )
        )
    return command


def build_openfoam_proofgraph_command(
    result_directory: str,
    output_file: str,
    *,
    python_executable: str = sys.executable,
) -> list[str]:
    """Build an argv-only command for the hash-verified sync-to-ProofGraph bridge."""
    if not result_directory.strip() or not output_file.strip():
        raise ValueError("Choose the OpenFOAM result store and a ProofGraph output file")
    return [
        python_executable,
        "-m",
        "cleanroomx.cfd_pipeline_cli",
        "proofgraph-export",
        result_directory,
        "--output",
        output_file,
    ]


def read_openfoam_evidence_preview(
    directory: str | Path,
    *,
    simulation_id: str = "",
) -> list[dict[str, Any]]:
    """Read a small set of known evidence JSON files without treating them as validated."""
    root = Path(directory).expanduser()
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Evidence directory must be a regular directory")
    root = root.resolve(strict=True)
    candidates = [root / name for name in _EVIDENCE_NAMES]
    if simulation_id:
        if _SIMULATION_ID.fullmatch(simulation_id) is None:
            raise ValueError("Simulation ID contains unsupported characters")
        candidates.extend(
            root / simulation_id / f"configuration_{number}" / "sync_manifest.json"
            for number in (1, 2, 3)
        )

    previews: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for candidate in candidates:
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.is_symlink() or not candidate.is_file() or info.st_nlink != 1:
            continue
        if info.st_size > _MAX_PREVIEW_BYTES:
            previews.append(
                {
                    "path": candidate.relative_to(root).as_posix(),
                    "error": "file exceeds the 2 MB preview limit",
                }
            )
            continue
        try:
            snapshot = load_strict_json_snapshot(
                candidate, max_bytes=_MAX_PREVIEW_BYTES
            )
        except (OSError, ValueError, UnicodeError) as exc:
            previews.append(
                {
                    "path": candidate.relative_to(root).as_posix(),
                    "error": f"JSON preview unavailable: {type(exc).__name__}",
                }
            )
            continue
        value = snapshot.value
        if type(value) is not dict:
            previews.append(
                {
                    "path": candidate.relative_to(root).as_posix(),
                    "error": "top-level JSON value is not an object",
                }
            )
            continue
        summary = {
            key: value[key]
            for key in (
                "schema_version",
                "status",
                "simulation_id",
                "configuration_hash",
                "solver_build",
                "record_count",
                "error_count",
                "times",
                "failed_times",
            )
            if key in value
        }
        if isinstance(value.get("records"), dict):
            summary["record_count"] = len(value["records"])
            summary["record_times"] = sorted(value["records"])[:40]
        if isinstance(value.get("cases"), dict):
            summary["case_statuses"] = {
                str(key): item.get("status")
                for key, item in sorted(value["cases"].items())
                if isinstance(item, dict)
            }
        previews.append(
            {
                "path": candidate.relative_to(root).as_posix(),
                "bytes": snapshot.size,
                "sha256": hashlib.sha256(snapshot.raw_bytes).hexdigest(),
                "summary": summary,
            }
        )
    return previews


class OpenFOAMWorkspace(ttk.Frame):
    """GUI for case generation, opt-in v10 runs, VTK sync, and evidence review."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_proofgraph_loaded: Callable[[dict[str, Any]], None] | None = None,
        status_setter: Callable[[str], None] | None = None,
        project_context_getter: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(master)
        self._on_proofgraph_loaded = on_proofgraph_loaded
        self._status_setter = status_setter or (lambda _message: None)
        self._project_context_getter = project_context_getter
        self._events: queue.Queue[tuple[str, Any]] = queue.Queue(
            maxsize=_MAX_OUTPUT_EVENTS
        )
        self._analysis_events: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)
        self._timeseries_busy = False
        self._output_drop_lock = threading.Lock()
        self._dropped_output_lines = 0
        self._output_chars = 0
        self._output_truncated = False
        self._process: subprocess.Popen[str] | None = None
        self._command_success_action: Callable[[], None] | None = None
        self._busy = False
        self._destroyed = False
        self._stop_requested = False
        self._theme_palette = theme_palette("light")

        self.specification_var = tk.StringVar()
        self.case_directory_var = tk.StringVar()
        self.result_directory_var = tk.StringVar()
        self.simulation_id_var = tk.StringVar(value=f"cleanroomx-openfoam-{uuid.uuid4().hex[:10]}")
        self.vtk_source_var = tk.StringVar()
        self.manifest_var = tk.StringVar()
        self.field_map_var = tk.StringVar()
        self.vtk_simulation_id_var = tk.StringVar(value=f"cleanroomx-vtk-{uuid.uuid4().hex[:10]}")
        self.sync_interval_var = tk.StringVar(value="0.5")
        self._active_command_label = "OpenFOAM command"
        self._stop_prompt = (
            "Stop OpenFOAM command",
            "Terminate the running command? The case may be left incomplete.",
        )
        self._stopping_status = "Stopping OpenFOAM command and child solvers"
        self._stopped_message = "OpenFOAM command and child solvers stopped."
        self._build()
        self.bind("<Destroy>", self._on_destroy, add="+")
        self.after(120, self._drain_events)

    def _build(self) -> None:
        header = ttk.Frame(self, padding=(10, 8, 10, 4))
        header.pack(fill="x")
        ttk.Label(
            header,
            text="OPENFOAM FOUNDATION v10",
            style="CX.Section.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            header,
            text=(
                "Generate the supported three-case bundle, opt in to a solver run, "
                "or synchronize an existing foamToVTK export."
            ),
            wraplength=980,
        ).pack(anchor="w", pady=(3, 0))
        ttk.Label(
            self,
            text=(
                "Execution, mesh checks, and field import are diagnostic evidence. "
                "Scientific validation remains BLOCKED until independent cleanroom "
                "measurements and review are supplied."
            ),
            wraplength=980,
            style="CX.Section.TLabel",
        ).pack(fill="x", padx=10, pady=(2, 7))

        output_frame = ttk.LabelFrame(
            self,
            text="Command output and evidence preview",
            padding=5,
            height=100,
        )
        self._output_frame = output_frame
        output_frame.pack_propagate(False)
        output_frame.pack(
            side="bottom", fill="both", expand=False, padx=10, pady=(2, 10)
        )
        self.output = tk.Text(
            output_frame,
            wrap="word",
            height=5,
            state="disabled",
            font=("TkFixedFont", 9),
        )
        output_controls = ttk.Frame(output_frame)
        self.copy_output_button = ttk.Button(
            output_controls,
            text="Copy",
            width=7,
            command=self.copy_output,
        )
        self.copy_output_button.pack(fill="x", pady=(0, 3))
        self.clear_output_button = ttk.Button(
            output_controls,
            text="Clear",
            width=7,
            command=self.clear_output,
        )
        self.clear_output_button.pack(fill="x")
        scroll = ttk.Scrollbar(
            output_frame, orient="vertical", command=self.output.yview
        )
        self.output.configure(yscrollcommand=scroll.set)
        self.output.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        output_controls.pack(side="right", fill="y", padx=(4, 0))

        workflow_view = ttk.Frame(self)
        workflow_view.pack(fill="both", expand=True, padx=10, pady=(0, 2))
        self._workflow_canvas = tk.Canvas(
            workflow_view,
            background=self._theme_palette["background"],
            highlightthickness=0,
            borderwidth=0,
        )
        self._workflow_canvas.pack(side="left", fill="both", expand=True)
        self._workflow_scrollbar = ttk.Scrollbar(
            workflow_view,
            orient="vertical",
            command=self._workflow_canvas.yview,
        )
        self._workflow_scrollbar.pack(side="right", fill="y")
        self._workflow_canvas.configure(
            yscrollcommand=self._workflow_scrollbar.set
        )
        self._workflow_content = ttk.Frame(self._workflow_canvas)
        self._workflow_window = self._workflow_canvas.create_window(
            (0, 0),
            window=self._workflow_content,
            anchor="nw",
        )
        self._workflow_content.bind(
            "<Configure>", self._update_workflow_scrollregion, add="+"
        )
        self._workflow_canvas.bind(
            "<Configure>", self._resize_workflow_content, add="+"
        )

        settings = ttk.LabelFrame(self._workflow_content, text="Case bundle", padding=8)
        settings.pack(fill="x", pady=4)
        self._path_row(
            settings,
            0,
            "Specification JSON",
            self.specification_var,
            lambda: self._browse_file(
                self.specification_var,
                (("JSON files", "*.json"), ("All files", "*")),
            ),
        )
        self._path_row(
            settings,
            1,
            "New case directory",
            self.case_directory_var,
            lambda: self._browse_directory(self.case_directory_var),
        )
        self._path_row(
            settings,
            2,
            "Optional native result store",
            self.result_directory_var,
            lambda: self._browse_directory(self.result_directory_var),
        )
        ttk.Label(settings, text="Simulation ID").grid(
            row=3, column=0, sticky="w", padx=(0, 8), pady=3
        )
        ttk.Entry(settings, textvariable=self.simulation_id_var).grid(
            row=3, column=1, sticky="ew", pady=3
        )
        settings.columnconfigure(1, weight=1)

        actions = ttk.Frame(settings)
        actions.grid(row=4, column=0, columnspan=3, sticky="w", pady=(5, 0))
        self.generate_button = ttk.Button(
            actions,
            text="Generate cases",
            command=self._generate,
        )
        self.generate_button.pack(side="left", padx=(0, 4))
        self.run_button = ttk.Button(
            actions,
            text="Run Foundation v10…",
            style="CX.Primary.TButton",
            command=self._run,
        )
        self.run_button.pack(side="left", padx=4)
        self.project_spec_button = ttk.Button(
            actions,
            text="Create spec from selected room…",
            command=self._make_project_room_spec,
            state="normal" if self._project_context_getter is not None else "disabled",
        )
        self.project_spec_button.pack(side="left", padx=4)
        self.stop_button = ttk.Button(
            actions,
            text="Stop",
            command=self._stop,
            state="disabled",
        )
        self.stop_button.pack(side="left", padx=4)
        ttk.Label(
            settings,
            text=(
                "Room handoff copies length, width, and height only; devices, "
                "boundary placement, and flow remain template inputs."
            ),
            wraplength=900,
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(4, 0))

        vtk = ttk.LabelFrame(
            self._workflow_content, text="Existing foamToVTK output", padding=8
        )
        vtk.pack(fill="x", pady=4)
        self._path_row(
            vtk,
            0,
            "VTK output directory",
            self.vtk_source_var,
            lambda: self._browse_directory(self.vtk_source_var),
        )
        self._path_row(
            vtk,
            1,
            "Case bundle manifest",
            self.manifest_var,
            lambda: self._browse_file(
                self.manifest_var,
                (("JSON files", "*.json"), ("All files", "*")),
            ),
        )
        ttk.Label(vtk, text="Import result store").grid(
            row=2, column=0, sticky="w", padx=(0, 8), pady=3
        )
        ttk.Entry(vtk, textvariable=self.result_directory_var).grid(
            row=2, column=1, sticky="ew", pady=3
        )
        ttk.Label(vtk, text="Simulation ID").grid(
            row=3, column=0, sticky="w", padx=(0, 8), pady=3
        )
        ttk.Entry(vtk, textvariable=self.vtk_simulation_id_var).grid(
            row=3, column=1, sticky="ew", pady=3
        )
        self._path_row(
            vtk,
            4,
            "Optional field map JSON",
            self.field_map_var,
            lambda: self._browse_file(
                self.field_map_var,
                (("JSON files", "*.json"), ("All files", "*")),
            ),
        )
        ttk.Label(vtk, text="Live scan interval (seconds)").grid(
            row=5, column=0, sticky="w", padx=(0, 8), pady=3
        )
        ttk.Entry(vtk, textvariable=self.sync_interval_var, width=8).grid(
            row=5, column=1, sticky="w", pady=3
        )
        vtk.columnconfigure(1, weight=1)
        self.sync_vtk_button = ttk.Button(
            vtk,
            text="Sync VTK once",
            command=self._sync_vtk,
        )
        self.sync_vtk_button.grid(row=6, column=0, sticky="w", pady=(5, 0))
        self.watch_vtk_button = ttk.Button(
            vtk,
            text="Start live sync",
            command=self._watch_vtk,
        )
        self.watch_vtk_button.grid(row=6, column=1, sticky="w", pady=(5, 0))

        evidence = ttk.Frame(self._workflow_content, padding=(0, 5, 0, 3))
        evidence.pack(fill="x")
        self.preview_button = ttk.Button(
            evidence,
            text="Preview result evidence",
            command=self._preview_evidence,
        )
        self.preview_button.pack(side="left", padx=(0, 5))
        self.graph_button = ttk.Button(
            evidence,
            text="Load ProofGraph JSON…",
            command=self._load_proofgraph,
            state="normal" if self._on_proofgraph_loaded is not None else "disabled",
        )
        self.graph_button.pack(side="left", padx=5)
        self.build_graph_button = ttk.Button(
            evidence,
            text="Build ProofGraph from results…",
            command=self._build_proofgraph,
            state="normal" if self._on_proofgraph_loaded is not None else "disabled",
        )
        self.build_graph_button.pack(side="left", padx=5)
        self.time_series_button = ttk.Button(
            evidence,
            text="View mapped-field time series…",
            command=self._analyze_time_series,
        )
        self.time_series_button.pack(side="left", padx=5)
        ttk.Label(
            evidence,
            text="Generated graphs audit retained hashes; scientific validation remains BLOCKED.",
        ).pack(side="left", padx=(10, 0))



        self._action_buttons = (
            self.generate_button,
            self.run_button,
            self.project_spec_button,
            self.sync_vtk_button,
            self.watch_vtk_button,
            self.preview_button,
            self.graph_button,
            self.build_graph_button,
            self.time_series_button,
        )
        self._bind_workflow_scroll(self._workflow_canvas)

    def apply_theme(self, value: str) -> None:
        """Retheme native workbench surfaces without changing workflow state."""
        self._theme_palette = theme_palette(value)
        palette = self._theme_palette
        self._workflow_canvas.configure(background=palette["background"])
        self.output.configure(
            background=palette["field"],
            foreground=palette["field_text"],
            insertbackground=palette["text"],
            selectbackground=palette["selection"],
            selectforeground=palette["selection_text"],
        )

    def _update_workflow_scrollregion(self, _event=None) -> None:
        self._workflow_canvas.configure(
            scrollregion=self._workflow_canvas.bbox("all")
        )

    def _resize_workflow_content(self, event: tk.Event) -> None:
        self._workflow_canvas.itemconfigure(
            self._workflow_window, width=max(1, int(event.width))
        )

    def _bind_workflow_scroll(self, widget: tk.Misc) -> None:
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            widget.bind(sequence, self._on_workflow_mousewheel, add="+")
        for child in widget.winfo_children():
            self._bind_workflow_scroll(child)

    def _on_workflow_mousewheel(self, event: tk.Event) -> str | None:
        delta = int(getattr(event, "delta", 0) or 0)
        if delta:
            steps = max(1, abs(delta) // 120)
            direction = -1 if delta > 0 else 1
        else:
            button = getattr(event, "num", None)
            if button not in (4, 5):
                return None
            steps = 1
            direction = -1 if button == 4 else 1
        self._workflow_canvas.yview_scroll(direction * steps, "units")
        return "break"

    def _path_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        browse: Callable[[], None],
    ) -> None:
        ttk.Label(parent, text=label).grid(
            row=row, column=0, sticky="w", padx=(0, 8), pady=3
        )
        ttk.Entry(parent, textvariable=variable).grid(
            row=row, column=1, sticky="ew", pady=3
        )
        ttk.Button(parent, text="Browse…", command=browse).grid(
            row=row, column=2, padx=(6, 0), pady=3
        )

    @staticmethod
    def _browse_file(
        variable: tk.StringVar,
        filetypes: tuple[tuple[str, str], ...],
    ) -> None:
        selected = filedialog.askopenfilename(filetypes=filetypes)
        if selected:
            variable.set(selected)

    @staticmethod
    def _browse_directory(variable: tk.StringVar) -> None:
        selected = filedialog.askdirectory(mustexist=False)
        if selected:
            variable.set(selected)

    def _generate(self) -> None:
        try:
            command = build_openfoam_generate_command(
                self.specification_var.get().strip(),
                self.case_directory_var.get().strip(),
            )
        except ValueError as exc:
            messagebox.showerror("OpenFOAM case generation", str(exc), parent=self)
            return
        self._start_command("Generate OpenFOAM cases", command)

    def _run(self) -> None:
        result_directory = self.result_directory_var.get().strip()
        simulation_id = self.simulation_id_var.get().strip()
        try:
            command = build_openfoam_run_command(
                self.case_directory_var.get().strip(),
                result_directory=result_directory,
                simulation_id=simulation_id if result_directory else "",
            )
        except ValueError as exc:
            messagebox.showerror("OpenFOAM run", str(exc), parent=self)
            return
        prompt = (
            "Run blockMesh, checkMesh, and simpleFoam for all three cases "
            "using the current environment?\n\n"
            "The command requires OpenFOAM Foundation v10. A successful process "
            "exit is diagnostic evidence and does not establish convergence or "
            "physical validation."
        )
        if not messagebox.askyesno("Run OpenFOAM Foundation v10", prompt, parent=self):
            return
        self._start_command("OpenFOAM Foundation v10 run", command)

    def _sync_vtk(self) -> None:
        result_directory = self.result_directory_var.get().strip()
        manifest = self.manifest_var.get().strip()
        if not manifest and self.case_directory_var.get().strip():
            manifest = str(Path(self.case_directory_var.get().strip()) / "manifest.json")
        try:
            command = build_openfoam_sync_vtk_command(
                self.vtk_source_var.get().strip(),
                result_directory,
                manifest,
                self.vtk_simulation_id_var.get().strip(),
                field_map_file=self.field_map_var.get().strip(),
            )
        except ValueError as exc:
            messagebox.showerror("OpenFOAM VTK synchronization", str(exc), parent=self)
            return
        self._start_command("Synchronize OpenFOAM VTK output", command)

    def _watch_vtk(self) -> None:
        result_directory = self.result_directory_var.get().strip()
        manifest = self.manifest_var.get().strip()
        if not manifest and self.case_directory_var.get().strip():
            manifest = str(Path(self.case_directory_var.get().strip()) / "manifest.json")
        try:
            interval_seconds = float(self.sync_interval_var.get().strip())
            command = build_openfoam_sync_vtk_command(
                self.vtk_source_var.get().strip(),
                result_directory,
                manifest,
                self.vtk_simulation_id_var.get().strip(),
                field_map_file=self.field_map_var.get().strip(),
                once=False,
                interval_seconds=interval_seconds,
            )
        except ValueError as exc:
            messagebox.showerror("OpenFOAM live synchronization", str(exc), parent=self)
            return
        self._start_command(
            "Live OpenFOAM VTK synchronization",
            command,
            stop_prompt=(
                "Stop live synchronization",
                "Stop watching for new VTK snapshots? Imported CleanroomX results will remain saved.",
            ),
            stopping_status="Stopping live OpenFOAM result synchronization",
            stopped_message="Live result synchronization stopped; imported snapshots remain saved.",
        )

    def _build_proofgraph(self) -> None:
        result_directory = self.result_directory_var.get().strip()
        if not result_directory:
            messagebox.showerror(
                "OpenFOAM ProofGraph",
                "Choose the CleanroomX OpenFOAM result store first.",
                parent=self,
            )
            return
        output_file = filedialog.asksaveasfilename(
            title="Save OpenFOAM synchronization ProofGraph",
            initialfile="openfoam-sync-proofgraph.json",
            defaultextension=".json",
            filetypes=(("JSON files", "*.json"), ("All files", "*")),
            confirmoverwrite=True,
        )
        if not output_file:
            return
        try:
            command = build_openfoam_proofgraph_command(result_directory, output_file)
        except ValueError as exc:
            messagebox.showerror("OpenFOAM ProofGraph", str(exc), parent=self)
            return
        self._start_command(
            "Verify OpenFOAM snapshots and build ProofGraph",
            command,
            on_success=lambda: self._open_built_proofgraph(output_file),
        )

    def _start_command(
        self,
        label: str,
        command: list[str],
        *,
        stop_prompt: tuple[str, str] | None = None,
        stopping_status: str | None = None,
        stopped_message: str | None = None,
        on_success: Callable[[], None] | None = None,
    ) -> None:
        if self._busy or self._timeseries_busy:
            return
        self._active_command_label = label
        self._stop_prompt = stop_prompt or (
            "Stop OpenFOAM command",
            "Terminate the running command? The case may be left incomplete.",
        )
        self._stopping_status = stopping_status or "Stopping OpenFOAM command and child solvers"
        self._stopped_message = stopped_message or "OpenFOAM command and child solvers stopped."
        self._command_success_action = on_success
        self._append(f"{label}\n$ argv = {json.dumps(command, ensure_ascii=False)}\n")
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                shell=False,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                **_process_group_launch_options(),
            )
        except OSError as exc:
            self._command_success_action = None
            messagebox.showerror(label, f"Could not start command: {exc}", parent=self)
            self._status_setter(f"{label} could not start")
            return

        self._process = process
        self._stop_requested = False
        self._set_busy(True)
        threading.Thread(
            target=self._read_process,
            args=(process,),
            name="cleanroomx-openfoam-command",
            daemon=True,
        ).start()
        self._status_setter(f"{label} started")

    def _read_process(self, process: subprocess.Popen[str]) -> None:
        stream = process.stdout
        if stream is not None:
            for line in stream:
                self._enqueue_output(line)
        self._enqueue_finished(process.wait())

    def _record_dropped_output(self) -> None:
        with self._output_drop_lock:
            self._dropped_output_lines += 1

    def _enqueue_event(self, event: tuple[str, Any]) -> None:
        _enqueue_process_event(
            self._events,
            event,
            on_output_dropped=self._record_dropped_output,
        )

    def _enqueue_output(self, value: str) -> None:
        self._enqueue_event(("output", value))

    def _enqueue_finished(self, return_code: int) -> None:
        self._enqueue_event(("finished", return_code))

    def _drain_events(self) -> None:
        if self._destroyed:
            return
        try:
            analysis_kind, analysis_value = self._analysis_events.get_nowait()
        except queue.Empty:
            pass
        else:
            self._timeseries_busy = False
            self._set_busy(self._busy)
            if analysis_kind == "time_series_ready":
                try:
                    self._show_time_series(analysis_value)
                except (OSError, ValueError, tk.TclError) as exc:
                    messagebox.showerror(
                        "OpenFOAM time-series analysis", str(exc), parent=self
                    )
                    self._status_setter("OpenFOAM time-series view could not be opened")
            else:
                messagebox.showerror(
                    "OpenFOAM time-series analysis", str(analysis_value), parent=self
                )
                self._status_setter("OpenFOAM time-series analysis failed")
        visible_output: list[str] = []
        for _ in range(_MAX_EVENTS_PER_POLL):
            try:
                kind, value = self._events.get_nowait()
            except queue.Empty:
                break
            if kind == "output":
                visible_output.append(value)
            elif kind == "finished":
                self._process = None
                self._set_busy(False)
                success_action = self._command_success_action
                self._command_success_action = None
                if self._stop_requested:
                    self._stop_requested = False
                    visible_output.append(f"\n{self._stopped_message}\n")
                    self._status_setter(f"{self._active_command_label} stopped")
                elif value == 0:
                    visible_output.append(
                        "\nProcess exited successfully. Review the command evidence; "
                        "this does not establish CFD convergence or validation.\n"
                    )
                    self._status_setter("OpenFOAM command finished; scientific validation remains blocked")
                    if success_action is not None:
                        try:
                            success_action()
                        except (OSError, ValueError, UnicodeError) as exc:
                            visible_output.append(f"\nCould not open generated ProofGraph: {exc}\n")
                            self._status_setter("ProofGraph export completed but could not be loaded")
                else:
                    visible_output.append(f"\nProcess exited with status {value}.\n")
                    self._status_setter(f"OpenFOAM command failed with status {value}")
        if visible_output:
            self._append("".join(visible_output))
        with self._output_drop_lock:
            dropped_lines = self._dropped_output_lines
            self._dropped_output_lines = 0
        if dropped_lines:
            self._append(
                f"\n[{dropped_lines:,} older command output lines were skipped "
                "to keep the workbench responsive.]\n"
            )
        self.after(120, self._drain_events)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        unavailable = {
            button
            for button, enabled in (
                (self.project_spec_button, self._project_context_getter is not None),
                (self.graph_button, self._on_proofgraph_loaded is not None),
                (self.build_graph_button, self._on_proofgraph_loaded is not None),
            )
            if not enabled
        }
        for button in self._action_buttons:
            button.configure(
                state="disabled"
                if busy or self._timeseries_busy or button in unavailable
                else "normal"
            )
        self.stop_button.configure(state="normal" if busy else "disabled")

    def _make_project_room_spec(self) -> None:
        if self._project_context_getter is None:
            messagebox.showerror(
                "OpenFOAM project handoff",
                "The active CleanroomX project is unavailable.",
                parent=self,
            )
            return
        template_value = self.specification_var.get().strip()
        if not template_value:
            messagebox.showerror(
                "OpenFOAM project handoff",
                "Choose an OpenFOAM specification template first.",
                parent=self,
            )
            return
        template_path = Path(template_value).expanduser()
        try:
            if template_path.is_symlink() or not template_path.is_file():
                raise ValueError("specification template must be a regular file")
            template_snapshot = load_strict_json_snapshot(
                template_path, max_bytes=_MAX_PREVIEW_BYTES
            )
            context = self._project_context_getter()
            spec = project_room_openfoam_spec(
                template_snapshot.value,
                project_name=context.get("project_name"),
                spatial_layout=context.get("spatial_layout"),
                selection_kind=context.get("selection_kind"),
                selected_room_id=context.get("selected_room_id"),
            )
            project_path_value = context.get("project_path")
            room_id = spec["project_geometry"]["room_id"]
            safe_room_id = re.sub(r"[^A-Za-z0-9._-]+", "-", room_id).strip(".-")
            initial_file = (
                f"{template_path.stem}-{safe_room_id or 'room'}-spec.json"
            )
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            messagebox.showerror(
                "OpenFOAM project handoff",
                str(exc),
                parent=self,
            )
            return

        output_name = filedialog.asksaveasfilename(
            title="Save reviewable OpenFOAM room specification",
            initialdir=str(template_path.parent),
            initialfile=initial_file,
            defaultextension=".json",
            filetypes=(("JSON files", "*.json"), ("All files", "*")),
            confirmoverwrite=True,
        )
        if not output_name:
            return
        try:
            output_path = Path(output_name).expanduser()
            protected_paths = [template_path]
            if project_path_value:
                protected_paths.append(Path(project_path_value).expanduser())
            atomic_write_cli_output(
                output_path,
                dumps_strict_json(spec, sort_keys=True) + "\n",
                protected_inputs=protected_paths,
            )
        except (OSError, ValueError) as exc:
            messagebox.showerror(
                "OpenFOAM project handoff",
                f"Could not save the room specification: {exc}",
                parent=self,
            )
            return
        self.specification_var.set(str(output_path))
        dimensions = " × ".join(f"{value:g} m" for value in spec["room_m"])
        self._append(
            "CleanroomX room-spec draft saved: "
            f"{spec['project_geometry']['room_name']} ({dimensions}). "
            "Only the rectangular room envelope was copied; other geometry and "
            "boundary conditions remain unverified template inputs.\n"
        )
        self._status_setter(
            "OpenFOAM spec draft created from room dimensions; scientific validation remains BLOCKED."
        )

    def _stop(self) -> None:
        process = self._process
        if process is None or process.poll() is not None:
            return
        title, prompt = self._stop_prompt
        if not messagebox.askyesno(title, prompt, parent=self):
            return
        self._stop_requested = True
        _signal_process_tree(process)
        self.stop_button.configure(state="disabled")
        self._status_setter(self._stopping_status)
        self.after(5000, lambda: self._kill_if_running(process))

    @staticmethod
    def _kill_if_running(process: subprocess.Popen[str]) -> None:
        if process.poll() is None:
            _signal_process_tree(process, force=True)

    def _preview_evidence(self) -> None:
        directory = self.result_directory_var.get().strip()
        if not directory:
            directory = self.case_directory_var.get().strip()
        if not directory:
            messagebox.showerror(
                "OpenFOAM evidence",
                "Choose a case directory or result store first.",
                parent=self,
            )
            return
        try:
            previews = read_openfoam_evidence_preview(
                directory,
                simulation_id=self.simulation_id_var.get().strip(),
            )
        except (OSError, ValueError) as exc:
            messagebox.showerror("OpenFOAM evidence", str(exc), parent=self)
            return
        if not previews:
            self._append("No recognized OpenFOAM evidence JSON was found.\n")
            return
        self._append(
            "Read-only evidence preview (hashes are displayed, not independently verified):\n"
            + json.dumps(previews, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        )

    def _analyze_time_series(self) -> None:
        if self._timeseries_busy or self._busy:
            return
        directory = self.result_directory_var.get().strip()
        if not directory:
            directory = filedialog.askdirectory(
                title="Choose a CleanroomX OpenFOAM result store",
                mustexist=True,
            )
            if not directory:
                return
            self.result_directory_var.set(directory)
        self._timeseries_busy = True
        self._set_busy(self._busy)
        self._status_setter("Checking synchronized OpenFOAM snapshots and field summaries…")
        self._append("Checking OpenFOAM result integrity before plotting mapped fields…\n")

        def analyze() -> None:
            try:
                result = read_openfoam_sync_time_series(directory)
            except (OSError, ValueError, UnicodeError) as exc:
                event = ("time_series_error", str(exc))
            else:
                event = ("time_series_ready", result)
            try:
                self._analysis_events.put_nowait(event)
            except queue.Full:
                # A single analysis can be in flight, so this indicates the
                # workbench is already closing or has not drained its prior result.
                pass

        threading.Thread(
            target=analyze,
            name="cleanroomx-openfoam-time-series",
            daemon=True,
        ).start()

    def _show_time_series(self, series: dict[str, Any]) -> tk.Toplevel:
        rows = series["rows"]
        cases = series["cases"]
        if not cases or not rows:
            raise ValueError("No mapped OpenFOAM field samples are available")

        window = tk.Toplevel(self)
        window.title(f"OpenFOAM time series — {series['simulation_id']}")
        window_width = min(920, max(640, window.winfo_screenwidth() - 60))
        window_height = min(680, max(480, window.winfo_screenheight() - 100))
        window.geometry(f"{window_width}x{window_height}")
        window.minsize(min(720, window_width), min(520, window_height))
        window.transient(self.winfo_toplevel())

        ttk.Label(
            window,
            text=(
                f"Snapshot integrity: {str(series['integrity_status']).upper()}  ·  "
                "Scientific validation: BLOCKED"
            ),
            style="CX.Section.TLabel",
        ).pack(anchor="w", padx=12, pady=(10, 2))
        ttk.Label(
            window,
            text=(
                "Volume-weighted means from imported, mapped VTK fields. The plot is "
                "descriptive; OpenFOAM time labels are not assumed to be seconds."
            ),
            wraplength=880,
        ).pack(anchor="w", padx=12, pady=(0, 8))

        controls = ttk.Frame(window, padding=(12, 0, 12, 8))
        controls.pack(fill="x")
        case_var = tk.StringVar(value=cases[0])
        field_var = tk.StringVar()
        ttk.Label(controls, text="Case").pack(side="left")
        case_box = ttk.Combobox(
            controls, textvariable=case_var, values=cases, state="readonly", width=22
        )
        case_box.pack(side="left", padx=(5, 18))
        ttk.Label(controls, text="Mapped field").pack(side="left")
        field_box = ttk.Combobox(
            controls, textvariable=field_var, state="readonly", width=28
        )
        field_box.pack(side="left", padx=5)
        export_button = ttk.Button(controls, text="Export CSV…")
        export_button.pack(side="right")

        chart = tk.Canvas(
            window,
            background=self._theme_palette["plot"],
            highlightthickness=1,
            highlightbackground=self._theme_palette["border"],
            height=320,
        )
        chart.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        table_frame = ttk.LabelFrame(window, text="Imported samples", padding=5)
        table_frame.pack(fill="x", padx=12, pady=(0, 8))
        columns = ("time", "mean1", "mean2", "mean3", "units", "snapshot")
        table = ttk.Treeview(
            table_frame, columns=columns, show="headings", height=7,
        )
        headings = {
            "time": "Solver time label",
            "mean1": "Mean 1",
            "mean2": "Mean 2",
            "mean3": "Mean 3",
            "units": "Units",
            "snapshot": "Snapshot SHA-256",
        }
        widths = {"time": 140, "mean1": 110, "mean2": 110,
                  "mean3": 110, "units": 100, "snapshot": 145}
        for column in columns:
            table.heading(column, text=headings[column])
            table.column(column, width=widths[column], anchor="w", stretch=True)
        table_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=table.yview)
        table.configure(yscrollcommand=table_scroll.set)
        table.pack(side="left", fill="x", expand=True)
        table_scroll.pack(side="right", fill="y")

        detail_var = tk.StringVar()
        ttk.Label(window, textvariable=detail_var, wraplength=880).pack(
            fill="x", padx=12, pady=(0, 10), anchor="w"
        )

        def selected_rows() -> list[dict[str, Any]]:
            case = case_var.get()
            field = field_var.get()
            return [row for row in rows
                    if row["case_id"] == case and row["field"] == field]

        def selection_summary(selected: list[dict[str, Any]]) -> str:
            if not selected:
                return "No imported field samples are available for this selection."
            first = selected[0]
            sample_count = first.get("field_sample_count", len(selected))
            case_count = first.get("case_snapshot_count", len(selected))
            coverage = first.get("coverage_status", "unspecified")
            return (
                f"{sample_count} field sample(s) · {coverage} coverage "
                f"({sample_count}/{case_count} case snapshots) · {first['array_name']} · "
                "hover over a sample to inspect its exact label, mean, minimum, and maximum."
            )

        def fields_for_case(case: str) -> list[str]:
            return sorted({row["field"] for row in rows if row["case_id"] == case})

        def redraw(_event=None) -> None:
            chart.delete("all")
            hover_rows.clear()
            selected = selected_rows()
            if not selected:
                chart.create_text(
                    max(1, chart.winfo_width() // 2),
                    max(1, chart.winfo_height() // 2),
                    text="No imported samples for this case and field.",
                    fill=self._theme_palette["text"],
                )
                table.delete(*table.get_children())
                return

            chart.update_idletasks()
            width = max(360, chart.winfo_width())
            height = max(220, chart.winfo_height())
            left, right, top, bottom = 78, width - 24, 28, height - 58
            x_values = [row["solver_time_value"] for row in selected]
            y_values = [number for row in selected for number in row["mean"]]
            x_low, x_high = min(x_values), max(x_values)
            if x_low == x_high:
                x_low -= 0.5
                x_high += 0.5
            y_low, y_high = min(y_values), max(y_values)
            if y_low == y_high:
                padding = max(abs(y_low) * 0.05, 0.5)
                y_low -= padding
                y_high += padding
            else:
                padding = (y_high - y_low) * 0.08
                y_low -= padding
                y_high += padding

            def x_pixel(value: float) -> float:
                return left + (value - x_low) / (x_high - x_low) * (right - left)

            def y_pixel(value: float) -> float:
                return bottom - (value - y_low) / (y_high - y_low) * (bottom - top)

            for tick in range(5):
                ratio = tick / 4
                y = top + ratio * (bottom - top)
                value = y_high - ratio * (y_high - y_low)
                chart.create_line(left, y, right, y, fill=self._theme_palette["grid"])
                chart.create_text(
                    left - 8, y, text=f"{value:.4g}", anchor="e",
                    fill=self._theme_palette["muted"],
                )
                x = left + ratio * (right - left)
                time_label = x_low + ratio * (x_high - x_low)
                chart.create_line(x, top, x, bottom, fill=self._theme_palette["grid"])
                chart.create_text(
                    x, bottom + 15, text=f"{time_label:.4g}", anchor="n",
                    fill=self._theme_palette["muted"],
                )
            chart.create_line(left, top, left, bottom, fill=self._theme_palette["text"])
            chart.create_line(left, bottom, right, bottom, fill=self._theme_palette["text"])
            units = selected[0]["units"]
            chart.create_text(
                left, 10, text=f"Volume-weighted mean ({units})", anchor="nw",
                fill=self._theme_palette["text"],
            )
            chart.create_text(
                (left + right) / 2, height - 10,
                text="OpenFOAM time label (not assumed seconds)", anchor="s",
                fill=self._theme_palette["text"],
            )

            colors = ("#2878b5", "#dc7042", "#39875e")
            component_count = selected[0]["components"]
            for row in selected:
                hover_rows.append((x_pixel(row["solver_time_value"]), row))
            for component in range(component_count):
                color = colors[component]
                points = []
                for row in selected:
                    points.extend((x_pixel(row["solver_time_value"]),
                                   y_pixel(row["mean"][component])))
                if len(selected) > 1:
                    chart.create_line(*points, fill=color, width=2)
                for index in range(0, len(points), 2):
                    x, y = points[index], points[index + 1]
                    chart.create_oval(x - 3, y - 3, x + 3, y + 3,
                                      fill=color, outline=color)
                label = "mean" if component_count == 1 else f"component {component + 1}"
                chart.create_line(right - 142, top + component * 20,
                                  right - 122, top + component * 20,
                                  fill=color, width=2)
                chart.create_text(right - 116, top + component * 20,
                                  text=label, anchor="w", fill=self._theme_palette["text"])

            table.delete(*table.get_children())
            for row in selected:
                means = [f"{number:.8g}" for number in row["mean"]]
                means.extend([""] * (3 - len(means)))
                table.insert("", "end", values=(
                    row["solver_time_label"], *means, row["units"],
                    row["snapshot_sha256"][:12],
                ))
            detail_var.set(selection_summary(selected))

        hover_rows: list[tuple[float, dict[str, Any]]] = []

        def show_hover(event: tk.Event) -> None:
            if not hover_rows:
                return
            x, row = min(hover_rows, key=lambda item: abs(item[0] - event.x))
            if abs(x - event.x) > 18:
                return
            values = lambda key: ", ".join(f"{value:.12g}" for value in row[key])
            detail_var.set(
                f"Solver time label {row['solver_time_label']} · "
                f"mean [{values('mean')}] · min [{values('minimum')}] · "
                f"max [{values('maximum')}] {row['units']} · "
                f"snapshot SHA-256 {row['snapshot_sha256']} · "
                f"{row.get('coverage_status', 'unspecified')} field coverage"
            )

        def clear_hover(_event=None) -> None:
            detail_var.set(selection_summary(selected_rows()))

        def change_case(_event=None) -> None:
            available = fields_for_case(case_var.get())
            field_box.configure(values=available)
            field_var.set(available[0] if available else "")
            redraw()

        def export_csv() -> None:
            selected = selected_rows()
            if not selected:
                messagebox.showerror(
                    "Export OpenFOAM time series",
                    "There are no samples to export for this selection.",
                    parent=window,
                )
                return
            initial = re.sub(
                r"[^A-Za-z0-9_.-]+",
                "_",
                f"{case_var.get()}-{field_var.get()}-timeseries",
            ) + ".csv"
            destination = filedialog.asksaveasfilename(
                title="Export mapped-field time series",
                initialfile=initial,
                defaultextension=".csv",
                filetypes=(("CSV files", "*.csv"), ("All files", "*")),
                confirmoverwrite=True,
            )
            if not destination:
                return
            try:
                path = export_openfoam_time_series_csv(
                    series, destination,
                    case_id=case_var.get(), field=field_var.get(),
                )
            except (OSError, ValueError) as exc:
                messagebox.showerror("Export OpenFOAM time series", str(exc), parent=window)
                return
            detail_var.set(f"CSV exported: {path}")

        export_button.configure(command=export_csv)
        case_box.bind("<<ComboboxSelected>>", change_case, add="+")
        field_box.bind("<<ComboboxSelected>>", redraw, add="+")
        chart.bind("<Configure>", redraw, add="+")
        chart.bind("<Motion>", show_hover, add="+")
        chart.bind("<Leave>", clear_hover, add="+")
        available = fields_for_case(case_var.get())
        field_box.configure(values=available)
        if available:
            field_var.set(available[0])
        redraw()
        return window

    def _load_proofgraph(self) -> None:
        if self._on_proofgraph_loaded is None:
            return
        selected = filedialog.askopenfilename(
            title="Open persisted ProofGraph",
            filetypes=(("JSON files", "*.json"), ("All files", "*")),
        )
        if not selected:
            return
        try:
            path = Path(selected)
            snapshot = load_strict_json_snapshot(path, max_bytes=_MAX_PREVIEW_BYTES)
            if type(snapshot.value) is not dict:
                raise ValueError("ProofGraph JSON must contain an object")
            self._on_proofgraph_loaded(snapshot.value)
        except (OSError, ValueError, UnicodeError) as exc:
            messagebox.showerror("Open ProofGraph", str(exc), parent=self)
            return
        self._append(f"Loaded persisted ProofGraph from {selected}\n")
        self._status_setter(
            "ProofGraph loaded; confirm its evidence and validation statuses in the viewer"
        )

    def _open_built_proofgraph(self, output_file: str) -> None:
        if self._on_proofgraph_loaded is None:
            return
        snapshot = load_strict_json_snapshot(
            output_file, max_bytes=_MAX_PROOFGRAPH_BYTES
        )
        graph = proofgraph_from_dict(snapshot.value)
        self._on_proofgraph_loaded(graph.to_dict())
        integrity = next(
            item["status"]
            for item in graph.to_dict()["verdicts"]
            if item["requirement_id"] == "OPENFOAM-SYNC-INTEGRITY"
        )
        self._append(
            f"Verified OpenFOAM sync ProofGraph saved to {output_file}; "
            f"snapshot integrity: {integrity}; scientific validation: BLOCKED.\n"
        )
        self._status_setter(
            f"OpenFOAM ProofGraph loaded; snapshot integrity is {integrity}, scientific validation remains blocked"
        )

    def _append(self, value: str) -> None:
        if self._destroyed:
            return
        self.output.configure(state="normal")
        self.output.insert("end", value)
        self._output_chars += len(value)
        remove_chars, add_notice = _output_trim_plan(
            self._output_chars,
            already_trimmed=self._output_truncated,
            max_chars=_MAX_OUTPUT_CHARS,
        )
        if remove_chars:
            if add_notice:
                self.output.insert("1.0", _OUTPUT_TRIM_NOTICE)
                self._output_chars += len(_OUTPUT_TRIM_NOTICE)
                self._output_truncated = True
            marker_length = len(_OUTPUT_TRIM_NOTICE) if self._output_truncated else 0
            delete_start = f"1.0+{marker_length}c"
            delete_end = f"1.0+{marker_length + remove_chars}c"
            self.output.delete(delete_start, delete_end)
            self._output_chars -= remove_chars
        self.output.see("end")
        self.output.configure(state="disabled")

    def clear_output(self) -> None:
        """Clear the visible command log without interrupting a running process."""
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.configure(state="disabled")
        self._output_chars = 0
        self._output_truncated = False
        self._status_setter("OpenFOAM output cleared; any running command continues")

    def copy_output(self) -> None:
        """Copy the currently retained command output to the system clipboard."""
        if self._destroyed:
            return
        try:
            text = self.output.get("1.0", "end-1c")
            self.clipboard_clear()
            self.clipboard_append(text)
        except tk.TclError as exc:
            self._status_setter(f"Could not copy OpenFOAM output: {exc}")
            return
        self._status_setter(
            f"Copied {len(text):,} characters of retained OpenFOAM output"
        )

    def _on_destroy(self, event: tk.Event) -> None:
        if event.widget is not self:
            return
        self._destroyed = True
        process = self._process
        if process is not None and process.poll() is None:
            _signal_process_tree(process, force=True)


