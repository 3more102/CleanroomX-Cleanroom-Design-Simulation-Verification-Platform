"""Capture the actual Tk Design Studio under a graphical display.

This is a real OS screen capture. It does not synthesize or redraw the GUI.
Run with a 1920x1080 desktop (for Linux CI, xvfb-run -s).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import tempfile
import tkinter as tk

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path
from cleanroomx.spatial import layout_metrics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", action="store_true")
    args = parser.parse_args()

    # Pillow is a screenshot-only dependency, deliberately not in production.
    from PIL import ImageGrab

    root = tk.Tk()
    root.geometry("1920x1080+0+0")
    with tempfile.TemporaryDirectory(prefix="cleanroomx-studio-capture-") as tmp:
        app = CleanroomXApp(
            root,
            autosave_interval_seconds=0,
            ui_state_path=Path(tmp) / "layout.json",
        )
        app.load_project_path(bundled_demo_project_path())
        app.notebook.select(app.spatial_workspace)
        app.set_theme("dark", persist=False)
        # First flush the original saved-layout restoration. Studio View then
        # hides external navigator/output panels and keeps room Inspector open.
        root.update_idletasks()
        root.update()
        if not args.baseline:
            app.spatial_workspace.studio_view()
        app.spatial_workspace.select_item("room", "process", notify=True)
        root.geometry("1920x1080+0+0")
        root.update_idletasks()
        root.update()
        dims = (root.winfo_width(), root.winfo_height())
        if dims != (1920, 1080):
            raise RuntimeError(f"Expected 1920x1080 Tk window, got {dims!r}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        image = ImageGrab.grab(bbox=(0, 0, 1920, 1080))
        if image.size != (1920, 1080):
            raise RuntimeError(f"Unexpected screenshot dimensions: {image.size!r}")
        image.save(args.output, format="PNG")
        snapshot = layout_metrics(app.spatial_workspace.layout)
        manifest = {
            "capture_type": "real_desktop_screenshot",
            "baseline": args.baseline,
            "platform": platform.platform(),
            "git_commit": os.environ.get(
                "CLEANROOMX_CAPTURE_SOURCE_SHA", os.environ.get("GITHUB_SHA")
            ),
            "resolution": [1920, 1080],
            "image_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
            "room_count": snapshot["room_count"],
            "floor_area_m2": snapshot["total_floor_area_m2"],
            "volume_m3": snapshot["total_volume_m3"],
            "placed_devices": sum(snapshot["device_counts"].values()),
            "canvas_3d_pixels": [
                app.spatial_workspace.canvas_3d.winfo_width(),
                app.spatial_workspace.canvas_3d.winfo_height(),
            ],
            "camera_zoom_3d": app.spatial_workspace.layout["view"]["zoom_3d"],
            "visual_reference_comparison": "NOT PERFORMED",
            "openfoam_execution": "NOT PERFORMED",
        }
        args.output.with_suffix(".json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        root.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
