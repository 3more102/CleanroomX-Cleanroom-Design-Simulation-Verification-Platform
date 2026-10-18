"""Capture a genuine CleanroomX Tk screenshot from an isolated checkout.

No mock screens, generated drawings or solver outputs are used. This command
requires a real desktop display (or Xvfb) and Pillow.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    checkout = args.checkout.resolve()
    source = checkout / "src"
    if not source.is_dir() or args.width < 1050 or args.height < 680:
        raise ValueError("valid checkout and a display of at least 1050x680 required")
    # Force imports from the requested checkout: never compare two checkouts
    # using the same installed package.
    sys.path.insert(0, str(source))
    from PIL import ImageGrab
    import tkinter as tk
    from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path

    root = tk.Tk()
    try:
        screen_width, screen_height = root.winfo_screenwidth(), root.winfo_screenheight()
        if screen_width < args.width or screen_height < args.height:
            raise RuntimeError(
                f"Actual display {screen_width}x{screen_height} is smaller "
                f"than requested capture {args.width}x{args.height}"
            )
        # CleanroomXApp loads persisted GUI dimensions in its constructor.
        # Set the requested capture size AFTER that initialization.
        app = CleanroomXApp(
            root,
            autosave_interval_seconds=0,
            ui_state_path=args.output.parent / "parity-capture-layout.json",
        )
        app.set_theme("dark", persist=False)
        app.load_project_path(bundled_demo_project_path())
        app.notebook.select(app.spatial_workspace)
        # Output / Verification is independently accessible, but the Design
        # Studio should own the majority of the frame in reference captures.
        app.hide_output_panel()
        workspace = app.spatial_workspace
        workspace.set_workspace_mode("3d")
        workspace.show_inspector()
        rooms = workspace.layout.get("rooms", [])
        if rooms:
            workspace.select_item("room", rooms[0]["id"], notify=True)
        root.geometry(f"{args.width}x{args.height}+0+0")
        root.update_idletasks()
        root.update()
        # A pending GUI layout callback may change panel geometry after idle.
        root.update_idletasks()
        root.update()
        actual_width = root.winfo_width()
        actual_height = root.winfo_height()
        if (actual_width, actual_height) != (args.width, args.height):
            raise RuntimeError(
                f"Real Tk window size {(actual_width, actual_height)} does not "
                f"equal requested {(args.width, args.height)}"
            )
        workspace.fit_3d()
        root.lift()
        root.update_idletasks()
        root.update()
        viewport_size = (workspace.canvas_3d.winfo_width(), workspace.canvas_3d.winfo_height())
        diagnostic = {
            "window_px": (root.winfo_width(), root.winfo_height()),
            "main_panes_px": (app.main_panes.winfo_width(), app.main_panes.winfo_height()),
            "workspace_panes_px": (app.workspace_panes.winfo_width(), app.workspace_panes.winfo_height()),
            "notebook_px": (app.notebook.winfo_width(), app.notebook.winfo_height()),
            "design_workspace_px": (workspace.winfo_width(), workspace.winfo_height()),
            "studio_body_px": (workspace._body.winfo_width(), workspace._body.winfo_height()),
            "view_frame_px": (workspace._three_d_frame.winfo_width(), workspace._three_d_frame.winfo_height()),
            "canvas_3d_px": viewport_size,
            "output_visible": app.output_panel_visible_var.get(),
            "output_panel_in_panes": str(app.output_panel) in [str(p) for p in app.workspace_panes.panes()],
        }
        print("GUI CAPTURE GEOMETRY", json.dumps(diagnostic), flush=True)
        if viewport_size[0] < 400 or viewport_size[1] < 200:
            raise RuntimeError(f"3D canvas too small even for basic capture: {diagnostic}")
        # ImageGrab reads the real on-screen X11/Windows Tk window.
        args.output.parent.mkdir(parents=True, exist_ok=True)
        ImageGrab.grab(bbox=(0, 0, args.width, args.height)).save(args.output)
        try:
            sha = subprocess.check_output(
                ["git", "-C", str(checkout), "rev-parse", "HEAD"],
                text=True,
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            sha = None
        layout = workspace.layout
        rooms = layout.get("rooms", [])
        devices = layout.get("devices", [])
        receipt = {
            "schema": "cleanroomx.gui-parity-capture",
            "version": 1,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "git_commit": sha,
            "filename": args.output.name,
            "resolution_px": [args.width, args.height],
            "actual_window_px": [actual_width, actual_height],
            "viewport_3d_px": list(viewport_size),
            "layout_diagnostics": diagnostic,
            "selected_room_id": workspace.selected.item_id if workspace.selected else None,
            "output_panel_hidden": not app.output_panel_visible_var.get(),
            "capture": "real Tk desktop framebuffer (Pillow ImageGrab)",
            "theme": "dark",
            "view_mode": "3d",
            "rooms": len(rooms),
            "floor_area_m2": sum(
                room["length_m"] * room["width_m"] for room in rooms
            ),
            "geometric_volume_m3": sum(
                room["length_m"] * room["width_m"] * room["height_m"]
                for room in rooms
            ),
            "placed_objects": len(devices),
            "openfoam_solver_executed": False,
            "reference_parity_verified": False,
        }
        receipt_path = args.output.with_suffix(".json")
        receipt_path.write_text(
            json.dumps(receipt, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        print(f"CAPTURED {args.output} | receipt {receipt_path}")
        return 0
    finally:
        root.destroy()


if __name__ == "__main__":
    raise SystemExit(main())
