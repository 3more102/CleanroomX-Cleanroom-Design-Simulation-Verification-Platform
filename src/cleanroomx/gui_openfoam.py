"""Desktop OpenFOAM Foundation v10 workflow and evidence browser."""
from __future__ import annotations

from collections import deque
import hashlib
import json
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any, Callable

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .cfd_openfoam import verify_openfoam_case_bundle
from .gui_theme import theme_palette
from .strict_json import load_strict_json_snapshot


_MAX_PREVIEW_BYTES = 2_000_000
_MAX_QUEUED_EVENTS_PER_TICK = 256
_BUSY_QUEUE_POLL_MS = 15
_IDLE_QUEUE_POLL_MS = 120
_SIMULATION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_SYNC_SIMULATION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
_EVIDENCE_NAMES = ("manifest.json", "sync-state.json", "sync_manifest.json")


class OpenFOAMConsoleLog:
    """Retain the full session transcript while bounding the live Text view."""

    def __init__(
        self,
        *,
        max_display_chars: int = 500_000,
        max_display_lines: int = 4_000,
        spool_max_bytes: int = 1_000_000,
    ) -> None:
        self._max_display_chars = max(1, int(max_display_chars))
        self._max_display_lines = max(1, int(max_display_lines))
        self._stream = tempfile.SpooledTemporaryFile(
            max_size=max(1, int(spool_max_bytes)),
            mode="w+t",
            encoding="utf-8",
            newline="",
        )
        self._display_chunks: deque[str] = deque()
        self._display_chars = 0
        self._display_newlines = 0
        self.total_chars = 0
        self.truncated = False
        self.error: str | None = None
        self._closed = False

    @property
    def display_text(self) -> str:
        return "".join(self._display_chunks)

    @property
    def full_log_available(self) -> bool:
        return not self._closed and self.error is None

    @property
    def has_output(self) -> bool:
        return self.total_chars > 0

    def _remove_prefix(self, count: int) -> int:
        remaining = max(0, int(count))
        removed = 0
        while remaining and self._display_chunks:
            chunk = self._display_chunks[0]
            take = min(remaining, len(chunk))
            prefix = chunk[:take]
            if take == len(chunk):
                self._display_chunks.popleft()
            else:
                self._display_chunks[0] = chunk[take:]
            self._display_chars -= take
            self._display_newlines -= prefix.count("\n")
            removed += take
            remaining -= take
        return removed

    def _remove_first_line(self) -> int:
        prefix_chars = 0
        for chunk in self._display_chunks:
            newline = chunk.find("\n")
            if newline >= 0:
                prefix_chars += newline + 1
                self.truncated = True
                return self._remove_prefix(prefix_chars)
            prefix_chars += len(chunk)
        return 0

    def append(self, value: str) -> int:
        """Append output and return the number of leading display characters trimmed."""
        text = str(value)
        if not text:
            return 0
        self.total_chars += len(text)
        if self.full_log_available:
            try:
                self._stream.write(text)
                self._stream.flush()
            except (OSError, ValueError) as exc:
                self.error = str(exc)

        self._display_chunks.append(text)
        self._display_chars += len(text)
        self._display_newlines += text.count("\n")
        removed = 0

        def line_count() -> int:
            tail = self._display_chunks[-1] if self._display_chunks else ""
            return self._display_newlines + (
                1 if self._display_chars and not tail.endswith("\n") else 0
            )

        while line_count() > self._max_display_lines:
            line_removed = self._remove_first_line()
            if not line_removed:
                break
            removed += line_removed

        if self._display_chars > self._max_display_chars:
            excess = self._display_chars - self._max_display_chars
            removed_chars = self._remove_prefix(excess)
            self.truncated = self.truncated or removed_chars > 0
            removed += removed_chars
        return removed

    def save_to(self, destination: str | Path) -> Path:
        """Atomically save the complete session log to a user-selected path."""
        if not self.full_log_available:
            detail = self.error or "the session log is closed"
            raise OSError(f"full session console log is unavailable: {detail}")
        target = Path(destination)
        self._stream.flush()
        position = self._stream.tell()
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                prefix=".cleanroomx-console-",
                suffix=".tmp",
                dir=target.parent,
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                self._stream.seek(0)
                shutil.copyfileobj(self._stream, handle, length=64 * 1024)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, target)
            return target
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink()
                except FileNotFoundError:
                    pass
            if not self._closed:
                self._stream.seek(position)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._stream.close()


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
    python_executable: str = sys.executable,
) -> list[str]:
    """Build a one-pass foamToVTK import command."""
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
    return [
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
        "--once",
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
    ) -> None:
        super().__init__(master)
        self._on_proofgraph_loaded = on_proofgraph_loaded
        self._status_setter = status_setter or (lambda _message: None)
        self._events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._process: subprocess.Popen[str] | None = None
        self._busy = False
        self._destroyed = False
        self._stop_requested = False
        self._theme_palette = theme_palette("light")
        self._console_log = OpenFOAMConsoleLog()

        self.specification_var = tk.StringVar()
        self.case_directory_var = tk.StringVar()
        self.result_directory_var = tk.StringVar()
        self.simulation_id_var = tk.StringVar(value=f"cleanroomx-openfoam-{uuid.uuid4().hex[:10]}")
        self.vtk_source_var = tk.StringVar()
        self.manifest_var = tk.StringVar()
        self.vtk_simulation_id_var = tk.StringVar(value=f"cleanroomx-vtk-{uuid.uuid4().hex[:10]}")
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
            height=122,
        )
        self._output_frame = output_frame
        output_frame.pack_propagate(False)
        output_frame.pack(
            side="bottom", fill="both", expand=False, padx=10, pady=(2, 10)
        )
        output_toolbar = ttk.Frame(output_frame)
        output_toolbar.pack(fill="x", pady=(0, 2))
        self.output_log_status_var = tk.StringVar(
            value="Complete session output is retained; save it before closing."
        )
        ttk.Label(
            output_toolbar,
            textvariable=self.output_log_status_var,
            anchor="w",
        ).pack(side="left", fill="x", expand=True)
        self.save_log_button = ttk.Button(
            output_toolbar,
            text="Save full log…",
            command=self.save_full_console_log,
            state="disabled",
        )
        self.save_log_button.pack(side="right", padx=(6, 0))

        self.output = tk.Text(
            output_frame,
            wrap="word",
            height=3,
            state="disabled",
            font=("TkFixedFont", 9),
        )
        scroll = ttk.Scrollbar(
            output_frame, orient="vertical", command=self.output.yview
        )
        self.output.configure(yscrollcommand=scroll.set)
        self.output.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

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
        self.verify_button = ttk.Button(
            actions,
            text="Verify case inputs",
            command=self._verify_case_bundle,
        )
        self.verify_button.pack(side="left", padx=4)
        self.run_button = ttk.Button(
            actions,
            text="Run Foundation v10…",
            style="CX.Primary.TButton",
            command=self._run,
        )
        self.run_button.pack(side="left", padx=4)
        self.stop_button = ttk.Button(
            actions,
            text="Stop",
            command=self._stop,
            state="disabled",
        )
        self.stop_button.pack(side="left", padx=4)

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
        vtk.columnconfigure(1, weight=1)
        self.sync_vtk_button = ttk.Button(
            vtk,
            text="Sync VTK once",
            command=self._sync_vtk,
        )
        self.sync_vtk_button.grid(row=4, column=0, sticky="w", pady=(5, 0))

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
        ttk.Label(
            evidence,
            text="JSON preview is read-only and does not independently verify hashes.",
        ).pack(side="left", padx=(10, 0))



        self._action_buttons = (
            self.generate_button,
            self.verify_button,
            self.run_button,
            self.sync_vtk_button,
            self.preview_button,
            self.graph_button,
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

    def _verify_case_bundle(self) -> None:
        directory = self.case_directory_var.get().strip()
        if not directory:
            messagebox.showerror(
                "Verify OpenFOAM case inputs",
                "Choose a generated case directory first.",
                parent=self,
            )
            return
        if self._busy:
            return
        self._append(f"Verify generated case inputs\nDirectory: {directory}\n")
        self._set_busy(True)
        self._status_setter("Verifying OpenFOAM case inputs")
        threading.Thread(
            target=self._verify_case_bundle_worker,
            args=(directory,),
            name="cleanroomx-openfoam-case-preflight",
            daemon=True,
        ).start()

    def _verify_case_bundle_worker(self, directory: str) -> None:
        try:
            report = verify_openfoam_case_bundle(directory)
        except Exception as exc:
            self._events.put(("case_verification_failed", str(exc)))
        else:
            self._events.put(("case_verification_finished", report))

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
            )
        except ValueError as exc:
            messagebox.showerror("OpenFOAM VTK synchronization", str(exc), parent=self)
            return
        self._start_command("Synchronize OpenFOAM VTK output", command)

    def _start_command(self, label: str, command: list[str]) -> None:
        if self._busy:
            return
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
                self._events.put(("output", line))
        self._events.put(("finished", process.wait()))

    def _drain_events(self) -> None:
        if self._destroyed:
            return
        processed = 0
        output_parts: list[str] = []
        while processed < _MAX_QUEUED_EVENTS_PER_TICK:
            try:
                kind, value = self._events.get_nowait()
            except queue.Empty:
                break
            processed += 1
            if kind == "output":
                output_parts.append(str(value))
                continue
            if output_parts:
                self._append("".join(output_parts))
                output_parts.clear()
            if kind == "finished":
                self._process = None
                self._set_busy(False)
                if self._stop_requested:
                    self._stop_requested = False
                    self._append("\nOpenFOAM command and child solvers stopped.\n")
                    self._status_setter("OpenFOAM command stopped")
                elif value == 0:
                    self._append(
                        "\nProcess exited successfully. Review the command evidence; "
                        "this does not establish CFD convergence or validation.\n"
                    )
                    self._status_setter("OpenFOAM command finished; scientific validation remains blocked")
                else:
                    self._append(f"\nProcess exited with status {value}.\n")
                    self._status_setter(f"OpenFOAM command failed with status {value}")
            elif kind == "case_verification_finished":
                self._set_busy(False)
                self._append(self._format_case_verification(value))
                self._status_setter(
                    "Case inputs verified; scientific validation remains blocked"
                )
            elif kind == "case_verification_failed":
                self._set_busy(False)
                self._append(f"\nCase input verification failed: {value}\n")
                self._status_setter("OpenFOAM case input verification failed")
        if output_parts:
            self._append("".join(output_parts))
        delay_ms = (
            _BUSY_QUEUE_POLL_MS
            if not self._events.empty()
            else _IDLE_QUEUE_POLL_MS
        )
        self.after(delay_ms, self._drain_events)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        for button in self._action_buttons:
            button.configure(state="disabled" if busy else "normal")
        self.stop_button.configure(
            state="normal" if busy and self._process is not None else "disabled"
        )

    @staticmethod
    def _format_case_verification(report: dict[str, Any]) -> str:
        return (
            "\nCase-input hashes: MATCH local manifest\n"
            f"Generated inputs: {report['files_checked']}/{report['files_expected']}\n"
            "Boundary-input consistency: "
            f"{report['boundary_audits_passed']}/3 configurations passed\n"
            f"Bytes checked: {report['total_bytes_checked']}\n"
            f"Manifest SHA-256: {report['manifest_sha256']}\n"
            "Manifest trust: local file; not digitally signed\n"
            "Scientific validation: BLOCKED "
            "(solver convergence and measured-data validation were not assessed)\n"
        )

    def _stop(self) -> None:
        process = self._process
        if process is None or process.poll() is not None:
            return
        if not messagebox.askyesno(
            "Stop OpenFOAM command",
            "Terminate the running command? The case may be left incomplete.",
            parent=self,
        ):
            return
        self._stop_requested = True
        _signal_process_tree(process)
        self.stop_button.configure(state="disabled")
        self._status_setter("Stopping OpenFOAM command and child solvers")
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

    def _append(self, value: str) -> None:
        if self._destroyed:
            return
        removed_chars = self._console_log.append(value)
        self.output.configure(state="normal")
        self.output.insert("end", value)
        if removed_chars:
            self.output.delete("1.0", f"1.0 + {removed_chars} chars")
        self.output.see("end")
        self.output.configure(state="disabled")

        if self._console_log.error is not None:
            self.output_log_status_var.set(
                "Full log capture failed; only the visible tail remains."
            )
            self.save_log_button.configure(state="disabled")
        elif self._console_log.truncated:
            self.output_log_status_var.set(
                "Showing the latest output; save the full session log before closing."
            )
            self.save_log_button.configure(
                state="normal" if self._console_log.has_output else "disabled"
            )
        else:
            self.output_log_status_var.set(
                "Complete session output is retained; save it before closing."
            )
            self.save_log_button.configure(
                state="normal" if self._console_log.has_output else "disabled"
            )

    def save_full_console_log(self) -> None:
        if not self._console_log.full_log_available:
            self._status_setter("Full OpenFOAM console log is unavailable")
            return
        selected = filedialog.asksaveasfilename(
            title="Save full OpenFOAM console log",
            defaultextension=".log",
            initialfile="cleanroomx-openfoam-console.log",
            filetypes=(("Log files", "*.log"), ("Text files", "*.txt"), ("All files", "*")),
        )
        if not selected:
            return
        try:
            self._console_log.save_to(selected)
        except (OSError, ValueError) as exc:
            messagebox.showerror(
                "Save OpenFOAM console log",
                f"Could not save the complete session output: {exc}",
                parent=self,
            )
            return
        self.output_log_status_var.set(
            f"Full session log saved to {Path(selected).name}."
        )
        self._status_setter("Full OpenFOAM console log saved")

    def _on_destroy(self, event: tk.Event) -> None:
        if event.widget is not self:
            return
        self._destroyed = True
        process = self._process
        if process is not None and process.poll() is None:
            _signal_process_tree(process, force=True)
        self._console_log.close()
