"""Capture an ACTUAL Tk Desktop screenshot under a display (not a mock)."""
from __future__ import annotations

import argparse
from pathlib import Path
import tkinter as tk

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--width", type=int, default=1536)
    parser.add_argument("--height", type=int, default=960)
    args = parser.parse_args()
    if args.width < 1050 or args.height < 680:
        parser.error("Studio screenshot requires at least 1050 x 680 pixels")
    from PIL import ImageGrab

    root = tk.Tk()
    root.geometry(f"{args.width}x{args.height}+0+0")
    app = CleanroomXApp(root, autosave_interval_seconds=0)
    # Restore the requested size after the application's saved-layout setup.
    root.geometry(f"{args.width}x{args.height}+0+0")
    try:
        app.load_project_path(bundled_demo_project_path())
        # Complete pending saved-layout restoration before enabling focus.
        root.update_idletasks()
        root.update()
        app.notebook.select(app.spatial_workspace)
        app.set_theme("dark", persist=False)
        app.spatial_workspace._studio.studio_view()
        root.update_idletasks()
        root.update()
        app.spatial_workspace.fit_studio_3d()
        root.update_idletasks()
        root.update()
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        x, y = root.winfo_rootx(), root.winfo_rooty()
        width, height = root.winfo_width(), root.winfo_height()
        assert (width, height) == (args.width, args.height), (
            "Screenshot window was resized by the host display", width, height,
        )
        assert app.spatial_workspace.canvas_3d.find_withtag("room3d")
        ImageGrab.grab(bbox=(x, y, x + width, y + height)).save(output)
        print(f"REAL TK SCREENSHOT: {output} ({width}x{height})")
        return 0
    finally:
        app._autosave_manager.shutdown(wait=False)
        root.destroy()


if __name__ == "__main__":
    raise SystemExit(main())
