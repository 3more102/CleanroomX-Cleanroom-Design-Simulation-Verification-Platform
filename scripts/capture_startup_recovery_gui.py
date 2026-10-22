"""Capture actual running desktop pixels with an integrity-checked solver case.

Requires Pillow and a real display (an Xvfb display is sufficient on Linux).
This reads an existing case and never fabricates results or edits its inputs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
import tkinter as tk

from PIL import ImageGrab

from cleanroomx.cfd_multizone_gui import MultizoneCFDWindow
from cleanroomx.cfd_multizone_results import analyze_multizone_case
from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_directory", type=Path)
    parser.add_argument("image_directory", type=Path)
    args = parser.parse_args()
    report = analyze_multizone_case(
        args.case_directory, density_kg_m3=1.2, reference_room_id="corridor",
    )
    args.image_directory.mkdir(parents=True, exist_ok=False)
    errors, images = [], []
    root = tk.Tk()
    root.report_callback_exception = lambda *exc: errors.append(repr(exc))
    app = None
    try:
        app = CleanroomXApp(root, autosave_interval_seconds=0,
                            ui_state_path=args.image_directory/"temporary-ui-state.json")
        app.set_theme("dark", persist=False)
        app.load_project_path(bundled_demo_project_path())

        def capture(window, filename, description):
            window.lift()
            for _ in range(4):
                root.update_idletasks()
                root.update()
                time.sleep(.025)
            x, y = window.winfo_rootx(), window.winfo_rooty()
            w, h = window.winfo_width(), window.winfo_height()
            path = args.image_directory / filename
            ImageGrab.grab(bbox=(x, y, x+w, y+h), xdisplay=os.environ.get("DISPLAY")).save(path)
            images.append({"file": filename, "description": description,
                           "kind": "actual_Tk_window_pixels", "width": w, "height": h,
                           "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})

        app._activate_spatial_workspace("split")
        app.hide_output_panel()  # Existing View control; give geometry the full viewport.
        root.update_idletasks()
        root.update()
        app.spatial_workspace.fit_views()
        capture(root, "01-design-workspace.png", "Actual synchronized design workspace; no sourced solver environment is needed for startup")
        review = MultizoneCFDWindow(root, directory=args.case_directory)
        review.geometry("1390x930+0+0")
        review.load_report(report)
        capture(review, "02-runtime-and-computed-fields.png", "Current runtime/checkout controls and genuine imported p/U/phi; WSL controls unavailable on this Linux host")
        review.tabs.select(2)
        capture(review, "03-recorded-residuals.png", "Actual solver residual curves calculated by the running GUI from recorded stage logs")
        if errors:
            raise RuntimeError(f"GUI callback failures: {errors}")
        manifest = {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "source_manifest_sha256": report["provenance"]["manifest_sha256"],
            "source_run_receipt_sha256": report["provenance"]["run_receipt_sha256"],
            "source_iteration": report["time_name"],
            "solver_reported_convergence": report["solver_reported_convergence"],
            "engineering_release": "HOLD", "gui_callback_errors": errors, "images": images,
        }
        (args.image_directory/"manifest.json").write_text(
            json.dumps(manifest, indent=2, allow_nan=False)+"\n", encoding="utf-8",
        )
        print(json.dumps({"images": len(images), "callback_errors": len(errors)}))
        return 0
    finally:
        if app is not None:
            app._autosave_manager.shutdown(wait=False)
        root.destroy()
        (args.image_directory/"temporary-ui-state.json").unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
