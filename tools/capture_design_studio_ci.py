"""Capture an ACTUAL Tk Desktop screenshot under a display (not a mock)."""
from __future__ import annotations

import argparse
from pathlib import Path
import tkinter as tk

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    from PIL import ImageGrab

    root = tk.Tk()
    root.geometry("1480x920+0+0")
    app = CleanroomXApp(root, autosave_interval_seconds=0)
    try:
        app.load_project_path(bundled_demo_project_path())
        app.notebook.select(app.spatial_workspace)
        app.set_theme("dark", persist=False)
        app.spatial_workspace.set_workspace_mode("3d")
        app.set_focus_workspace(True)
        root.update_idletasks()
        root.update()
        app.spatial_workspace.fit_3d()
        root.update_idletasks()
        root.update()
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        x, y = root.winfo_rootx(), root.winfo_rooty()
        width, height = root.winfo_width(), root.winfo_height()
        assert width >= 1050 and height >= 680, (width, height)
        assert app.spatial_workspace.canvas_3d.find_withtag("room3d")
        ImageGrab.grab(bbox=(x, y, x + width, y + height)).save(output)
        print(f"REAL TK SCREENSHOT: {output} ({width}x{height})")
        return 0
    finally:
        app._autosave_manager.shutdown(wait=False)
        root.destroy()


if __name__ == "__main__":
    raise SystemExit(main())
