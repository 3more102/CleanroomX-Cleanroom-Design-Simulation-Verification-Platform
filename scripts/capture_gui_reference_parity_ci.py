"""Capture a genuine Linux/Xvfb CleanroomX window for reference-parity review.

Requires a working Tk display (e.g. xvfb-run -s '-screen 0 1920x1080x24'),
the installed CleanroomX package and the external `scrot` executable.
This does not generate or paint an artificial representation of the GUI.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile
import tkinter as tk

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if shutil.which("scrot") is None:
        parser.error("scrot is required to photograph the real X11 display")

    root = tk.Tk()
    with tempfile.TemporaryDirectory(prefix="cleanroomx-parity-ui-") as temp_dir:
        app = CleanroomXApp(
            root,
            autosave_interval_seconds=0,
            ui_state_path=Path(temp_dir) / "layout-state.json",
        )
        app.load_project_path(bundled_demo_project_path())
        root.geometry("1920x1080+0+0")
        app.activate_reference_demo_studio()
        work = app.spatial_workspace
        root.update_idletasks()
        root.update()
        work.fit_3d()
        root.update_idletasks()
        root.update()

        # Strict guard: a completed X11 screenshot is meaningless without
        # actual model data rendered by the real canvas widgets.
        if not work.canvas_3d.find_withtag("room3d"):
            raise RuntimeError("Room geometry is not present on the live 3D canvas")
        if not work.room_navigator_canvas.find_withtag("navigator_room"):
            raise RuntimeError("Embedded Room Navigator did not draw any rooms")
        if work._studio_summary_vars["rooms"].get() != "3":
            raise RuntimeError("Demo room count did not update from project model")
        if not work.inspector_visible() or work.selected is None:
            raise RuntimeError("Live selected-room inspector is missing")

        args.output.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["scrot", "-q", "100", str(args.output.resolve())],
            check=True,
        )
        if args.output.stat().st_size < 10000:
            raise RuntimeError("Screen capture is unexpectedly small")
        root.destroy()
        print(f"Captured real Tk/X11 GUI: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
