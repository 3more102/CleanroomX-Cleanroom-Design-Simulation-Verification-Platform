"""Capture actual residual controls using an existing, verified OpenFOAM case.

Requires Pillow and a real Tk display. No solver is run and no data are invented.
The output directory must be new. Use the archived reproduction case to repeat
the historical, unconverged design-flow capture; it is not new solver evidence.
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
from cleanroomx.cfd_residual_plot import residual_plot_data


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
    errors, captures = [], []
    root.report_callback_exception = lambda *exception: errors.append(repr(exception))
    window = MultizoneCFDWindow(root, directory=case)
    window.geometry("1230x920+0+0")

    def capture(name, description):
        for _ in range(4):
            root.update()
            time.sleep(.025)
        assert not errors, errors
        image = args.output_directory/name
        x, y = window.winfo_rootx(), window.winfo_rooty()
        w, h = window.winfo_width(), window.winfo_height()
        ImageGrab.grab(bbox=(x, y, x+w, y+h), xdisplay=os.environ.get("DISPLAY")).save(image)
        plot = window.residual_plot
        captures.append({
            "file": name, "kind": "actual_Tk_window_pixels", "description": description,
            "width": w, "height": h, "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
            "field": plot.field.get(), "residual_kind": plot.kind.get(),
            "scale": plot.scale.get(), "window": plot.window.get(),
            "displayed_linear_solves": len(plot.points), "probe": plot.detail.get(),
        })

    try:
        window.load_report(report)
        window.tabs.select(2)
        capture("01-native-initial-residuals.png", "All recorded initial residuals and configured initial limits")
        plot = window.residual_plot
        plot.field.set("p")
        plot.redraw()
        plot._step_probe(-1)
        capture("02-pressure-point-inspection.png", "Exact recorded pressure solve inspected in the native canvas")
        plot.kind.set("Final linear")
        plot.scale.set("linear")
        plot.redraw()
        plot._step_probe(-1)
        capture("03-final-linear-residuals.png", "Actual final linear residuals, without applying initial convergence limits")
        verified = analyze_multizone_case(case, density_kg_m3=1.2, reference_room_id="corridor")
        assert residual_plot_data(verified) == residual_plot_data(report)
        assert not errors, errors
        source = Path(__file__).resolve().parents[1]
        metadata = {
            "schema": "cleanroomx.native-residual-capture.v1",
            "source_iteration": report["time_name"], "source_provenance": report["provenance"],
            "source_case_sha256": {name: hashlib.sha256((case/name).read_bytes()).hexdigest()
                                   for name in ("manifest.json", "run-receipt.json", "simpleFoam.log", "system/fvSolution")},
            "implementation_sha256": {name: hashlib.sha256((source/name).read_bytes()).hexdigest()
                                      for name in ("src/cleanroomx/cfd_multizone_gui.py", "src/cleanroomx/cfd_residual_plot.py")},
            "solver_reported_convergence": report["solver_reported_convergence"],
            "engineering_release": "HOLD", "new_solver_execution": False,
            "gui_callback_errors": errors, "images": captures,
        }
        (args.output_directory/"capture-manifest.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True, allow_nan=False)+"\n", encoding="utf-8")
        print(f"Captured {len(captures)} actual Tk views; zero callback errors; engineering HOLD.")
    finally:
        window.close()
        root.destroy()


if __name__ == "__main__":
    main()
