"""Capture the actual live-preview widget by replaying a verified historical log.

No solver is executed. Replay is explicitly labelled in the running UI and
capture manifest. Requires Pillow, a real Tk display and a new output folder.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import tkinter as tk

from PIL import ImageGrab

from cleanroomx.cfd_multizone_gui import MultizoneCFDWindow
from cleanroomx.cfd_multizone_results import analyze_multizone_case


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_directory", type=Path)
    parser.add_argument("output_directory", type=Path)
    args = parser.parse_args()
    case = args.case_directory.resolve(strict=True)
    report = analyze_multizone_case(case, density_kg_m3=1.2, reference_room_id="corridor")
    args.output_directory.mkdir(parents=True, exist_ok=False)
    root = tk.Tk()
    root.withdraw()
    errors = []
    root.report_callback_exception = lambda *args: errors.append(repr(args))
    window = MultizoneCFDWindow(root, directory=case)
    window.geometry("1230x960+0+0")
    try:
        window.status.set("RECORDED LOG REPLAY — no new solver execution. Engineering HOLD.")
        panel = window.live_solver
        panel.begin(case, source="RECORDED LOG REPLAY — no new solver execution", allow_existing=True)
        window.tabs.select(panel)
        for _ in range(300):
            panel.poll()
            if panel.follower.offset == (case / "simpleFoam.log").stat().st_size:
                break
        assert list(panel.follower.monitor.history) == report["residual_history"]
        assert window.report is None
        assert panel.plot.model["selected_iteration"] is None
        panel.phase.set("RECORDED LOG REPLAY COMPLETE — no new solver execution; preview is unverified.")
        panel.plot.field.set("p")
        panel.plot.redraw()
        panel.plot._step_probe(-1)
        for _ in range(4):
            root.update()
            time.sleep(.025)
        assert not errors, errors
        x, y = window.winfo_rootx(), window.winfo_rooty()
        w, h = window.winfo_width(), window.winfo_height()
        image_path = args.output_directory / "01-recorded-log-preview.png"
        ImageGrab.grab(bbox=(x, y, x+w, y+h), xdisplay=os.environ.get("DISPLAY")).save(image_path)
        source = Path(__file__).resolve().parents[1]
        metadata = {
            "schema": "cleanroomx.live-preview-capture.v1", "kind": "actual_Tk_window_pixels",
            "mode": "explicit_recorded_log_replay", "new_solver_execution": False,
            "source_provenance": report["provenance"], "source_saved_iteration": report["time_name"],
            "source_solver_reported_convergence": report["solver_reported_convergence"],
            "canonical_residual_history_exactly_matched": True,
            "source_case_sha256": {name: hashlib.sha256((case / name).read_bytes()).hexdigest()
                                   for name in ("manifest.json", "run-receipt.json", "simpleFoam.log")},
            "implementation_sha256": {name: hashlib.sha256((source / name).read_bytes()).hexdigest()
                                      for name in ("src/cleanroomx/cfd_live_monitor.py",
                                                   "src/cleanroomx/cfd_live_monitor_gui.py",
                                                   "src/cleanroomx/cfd_multizone_gui.py",
                                                   "src/cleanroomx/cfd_residual_plot.py")},
            "observed_linear_solves": panel.follower.monitor.total_samples,
            "computed_fields_published_by_preview": window.report is not None,
            "saved_field_marker_in_preview": bool(panel.plot.canvas.find_withtag("selected-iteration")),
            "probe": panel.plot.detail.get(), "gui_callback_errors": errors,
            "engineering_release": "HOLD", "image": image_path.name,
            "width": w, "height": h, "image_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
        }
        (args.output_directory / "capture-manifest.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
        print("Captured actual live-preview UI with 400 historical residual entries; no new solver execution.")
    finally:
        window.close()
        root.destroy()


if __name__ == "__main__":
    main()
