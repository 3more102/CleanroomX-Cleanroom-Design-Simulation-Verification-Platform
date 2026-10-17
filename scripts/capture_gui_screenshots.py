#!/usr/bin/env python3
"""Capture the real CleanroomX demo GUI on an interactive desktop."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from tkinter import ttk
from typing import Callable


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))


def _git_commit() -> str | None:
    result = subprocess.run(
        ["git", "-C", str(REPOSITORY_ROOT), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _capture(root: tk.Tk, destination: Path, image_grab) -> tuple[int, int]:
    root.update_idletasks()
    root.update()
    left, top = root.winfo_rootx(), root.winfo_rooty()
    width, height = root.winfo_width(), root.winfo_height()
    if width < 700 or height < 500:
        raise RuntimeError(
            f"The CleanroomX window is too small to capture ({width}x{height})."
        )
    image = image_grab.grab(bbox=(left, top, left + width, top + height))
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG", optimize=True)
    return image.size


def _descendants(widget: tk.Misc):
    for child in widget.winfo_children():
        yield child
        yield from _descendants(child)


def _notebook_with_tabs(root: tk.Misc, expected: set[str]) -> ttk.Notebook:
    for widget in _descendants(root):
        if not isinstance(widget, ttk.Notebook):
            continue
        labels = {widget.tab(tab, "text") for tab in widget.tabs()}
        if expected.issubset(labels):
            return widget
    raise RuntimeError(f"Could not find a notebook with tabs: {sorted(expected)}")


def _select_tab(notebook: ttk.Notebook, label: str) -> None:
    for tab in notebook.tabs():
        if notebook.tab(tab, "text") == label:
            notebook.select(tab)
            return
    raise RuntimeError(f"Notebook tab not found: {label}")


def _select_main_tab(app, label: str) -> None:
    _select_tab(app.notebook, label)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Capture all main CleanroomX workspaces and output panels as PNGs. "
            "This must run in a logged-in desktop session."
        )
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPOSITORY_ROOT / "docs" / "gui_screenshots",
        help="Destination directory (default: docs/gui_screenshots)",
    )
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=1000)
    parser.add_argument("--delay-seconds", type=float, default=1.5)
    parser.add_argument(
        "--timeseries-result-directory",
        type=Path,
        help=(
            "Optionally capture the mapped-field time-series dialog using an "
            "existing CleanroomX OpenFOAM result store. The store is read only."
        ),
    )
    args = parser.parse_args()
    if args.width < 700 or args.height < 500:
        parser.error("--width must be at least 700 and --height at least 500")
    if args.delay_seconds < 0:
        parser.error("--delay-seconds must be zero or greater")

    try:
        from PIL import ImageGrab
    except ImportError as exc:
        raise SystemExit(
            "Screenshot capture requires Pillow. Install it with: python -m pip install Pillow"
        ) from exc

    from cleanroomx.gui import (
        CleanroomXApp,
        bundled_demo_project_path,
        validate_application_registry,
    )
    from cleanroomx.cfd_openfoam_timeseries import read_openfoam_sync_time_series
    from cleanroomx import __version__

    validate_application_registry()
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise SystemExit(
            "A desktop display is required to capture the real GUI. "
            f"Tk could not open a window: {exc}"
        ) from exc

    app = None
    state_directory = tempfile.TemporaryDirectory(
        prefix="cleanroomx-screenshot-capture-"
    )
    try:
        root.title("CleanroomX — documentation screenshot capture")
        screen_width = max(700, root.winfo_screenwidth() - 40)
        screen_height = max(500, root.winfo_screenheight() - 80)
        width, height = min(args.width, screen_width), min(args.height, screen_height)
        app = CleanroomXApp(
            root,
            autosave_interval_seconds=0,
            ui_state_path=Path(state_directory.name) / "gui-layout.json",
        )
        root.geometry(f"{width}x{height}+20+20")
        root.minsize(min(700, width), min(500, height))
        root.lift()
        root.focus_force()
        app.load_project_path(bundled_demo_project_path())

        # Preserve the normal navigational chrome and ensure the output pane is
        # visible so its engineering details can be documented as well.
        app.set_focus_workspace(False)
        app.navigator_panel_visible_var.set(True)
        app._sync_navigator_panel_visibility()
        app.output_panel_visible_var.set(True)
        app._sync_output_panel_visibility()
        app._activate_spatial_workspace("split")
        root.update_idletasks()

        input_notebook = _notebook_with_tabs(app.input_tab, {"Structured", "JSON editor"})
        output_notebook = app.output_notebook
        capture_targets: dict[str, tk.Misc] = {}

        def open_time_series() -> None:
            if args.timeseries_result_directory is None:
                return
            series = read_openfoam_sync_time_series(args.timeseries_result_directory)
            app.notebook.select(app.openfoam_workspace)
            capture_targets["openfoam-timeseries.png"] = app.openfoam_workspace._show_time_series(series)

        steps: list[tuple[str, str, Callable[[], None]]] = [
            ("start-center.png", "Start Center", app._activate_start_workspace),
            ("design-2d.png", "Design · 2D", lambda: app._activate_spatial_workspace("2d")),
            ("design-3d.png", "Design · 3D", lambda: app._activate_spatial_workspace("3d")),
            ("design-split.png", "Design · synchronized 2D + 3D", lambda: app._activate_spatial_workspace("split")),
            ("input-structured.png", "Input · Structured", lambda: (app.notebook.select(app.input_tab), _select_tab(input_notebook, "Structured"))),
            ("input-json-editor.png", "Input · JSON editor", lambda: (app.notebook.select(app.input_tab), _select_tab(input_notebook, "JSON editor"))),
            ("plot.png", "Plot", lambda: _select_main_tab(app, "Plot")),
            ("proofgraph.png", "ProofGraph", lambda: _select_main_tab(app, "ProofGraph")),
            ("openfoam.png", "OpenFOAM", lambda: _select_main_tab(app, "OpenFOAM")),
            ("output-problems.png", "Output · Problems", lambda: _select_tab(output_notebook, "Problems")),
            ("output-diagnostics.png", "Output · Diagnostics", lambda: _select_tab(output_notebook, "Diagnostics")),
            ("output-verification.png", "Output · Verification", lambda: _select_tab(output_notebook, "Verification")),
            ("output-console.png", "Output · Console", lambda: _select_tab(output_notebook, "Console")),
            ("output-evidence.png", "Output · Evidence", lambda: _select_tab(output_notebook, "Evidence")),
            ("output-results.png", "Output · Results", lambda: _select_tab(output_notebook, "Results")),
            ("output-report.png", "Output · Report", lambda: _select_tab(output_notebook, "Report")),
        ]
        if args.timeseries_result_directory is not None:
            steps.append((
                "openfoam-timeseries.png",
                "OpenFOAM · Mapped-field time series",
                open_time_series,
            ))
        output_dir = args.output_dir.resolve()
        captures: list[dict[str, object]] = []
        errors: list[dict[str, str]] = []
        delay_ms = round(args.delay_seconds * 1000)

        def capture_step(index: int = 0) -> None:
            if index >= len(steps):
                manifest = {
                    "captured_at_utc": datetime.now(timezone.utc).isoformat(),
                    "source_commit": _git_commit(),
                    "application_version": __version__,
                    "capture_method": "Pillow ImageGrab of the running CleanroomX Tk window",
                    "window_size_px": [width, height],
                    "captures": captures,
                    "errors": errors,
                    "not_captured": [
                        filename
                        for filename, _, _ in steps
                        if filename not in {item["file"] for item in captures}
                    ],
                }
                output_dir.mkdir(parents=True, exist_ok=True)
                (output_dir / "capture-manifest.json").write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                manager = getattr(app, "_autosave_manager", None)
                if manager is not None:
                    manager.shutdown(wait=False)
                root.destroy()
                return

            filename, label, select = steps[index]
            try:
                # Keep the output panel visible for all captures, and use the
                # design workspace as context for each output-panel screenshot.
                app.output_panel_visible_var.set(True)
                app._sync_output_panel_visibility()
                if filename.startswith("output-"):
                    app._activate_spatial_workspace("split")
                select()
                root.after(delay_ms, lambda: finish_step(index, filename, label))
            except Exception as exc:  # Keep collecting the other real views.
                errors.append({"file": filename, "workspace": label, "error": str(exc)})
                root.after(delay_ms, lambda: capture_step(index + 1))

        def finish_step(index: int, filename: str, label: str) -> None:
            try:
                target = capture_targets.get(filename, root)
                size = _capture(target, output_dir / filename, ImageGrab)
                captures.append({
                    "file": filename,
                    "workspace": label,
                    "dimensions_px": list(size),
                })
            except Exception as exc:  # Continue so one bad panel won't hide the rest.
                errors.append({"file": filename, "workspace": label, "error": str(exc)})
            capture_step(index + 1)

        root.after(delay_ms, capture_step)
        root.mainloop()
    finally:
        if app is not None:
            manager = getattr(app, "_autosave_manager", None)
            if manager is not None:
                manager.shutdown(wait=False)
        try:
            if root.winfo_exists():
                root.destroy()
        except tk.TclError:
            pass
        state_directory.cleanup()

    manifest_path = args.output_dir.resolve() / "capture-manifest.json"
    if not manifest_path.exists():
        raise SystemExit("Screenshot capture ended before writing its manifest.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in manifest["captures"]:
        print(f"Captured {item['workspace']}: {manifest_path.parent / item['file']}")
    print(f"Capture manifest: {manifest_path}")
    if manifest["errors"]:
        for item in manifest["errors"]:
            print(f"Could not capture {item['workspace']}: {item['error']}", file=sys.stderr)
    if len(manifest["captures"]) != len(steps):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
