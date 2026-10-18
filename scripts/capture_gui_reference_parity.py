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
        root.geometry(f"{args.width}x{args.height}+0+0")
        app = CleanroomXApp(
            root,
            autosave_interval_seconds=0,
            ui_state_path=args.output.parent / "parity-capture-layout.json",
        )
        app.set_theme("dark", persist=False)
        app.load_project_path(bundled_demo_project_path())
        app.notebook.select(app.spatial_workspace)
        workspace = app.spatial_workspace
        workspace.set_workspace_mode("3d")
        workspace.show_inspector()
        root.update_idletasks()
        root.update()
        workspace.fit_3d()
        root.lift()
        root.update_idletasks()
        root.update()
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
