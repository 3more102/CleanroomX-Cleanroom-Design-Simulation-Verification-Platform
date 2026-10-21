"""Capture the actual probe UI over a verified recorded case; no solver is run."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tkinter as tk

from PIL import ImageGrab

from cleanroomx.cfd_multizone_gui import MultizoneCFDWindow, slice_samples
from cleanroomx.cfd_multizone_results import analyze_multizone_case


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_directory", type=Path)
    parser.add_argument("output_directory", type=Path)
    args = parser.parse_args()
    report = analyze_multizone_case(args.case_directory, density_kg_m3=1.2,
                                   reference_room_id="corridor")
    args.output_directory.mkdir(parents=True, exist_ok=False)
    root = tk.Tk()
    root.withdraw()
    errors = []
    root.report_callback_exception = lambda *exc: errors.append(repr(exc))
    window = MultizoneCFDWindow(root, directory=args.case_directory)
    window.geometry("1230x940+0+0")
    window.title("CleanroomX | Recorded cell probes — archived CFD; no new solver run")
    try:
        window.load_report(report)
        window.tabs.select(window.fields_tab)
        window.section_click_mode.set("Probe cell")
        window.axis.set("z")
        window.position.set("1.35")
        root.update()
        window.draw_section()
        samples = slice_samples(report, "z", 1.35)
        seeds = [samples[len(samples)//4], samples[len(samples)//2], samples[-1]]
        for cell in seeds:
            window.add_cell_probe(cell["center_m"])
        root.update()
        # Exercise the actual canvas click on the displayed archived field.
        center = seeds[0]["center_m"]
        x, y = window._section_to_pixel(center[0], center[1])
        window.section_canvas.event_generate("<Button-1>", x=round(x), y=round(y))
        root.update()
        assert not errors, errors
        assert window.section_canvas.find_withtag("recorded-cell-probe")
        image = args.output_directory/"01-recorded-cell-probes.png"
        x, y = window.winfo_rootx(), window.winfo_rooty()
        width, height = window.winfo_width(), window.winfo_height()
        ImageGrab.grab(bbox=(x, y, x+width, y+height), xdisplay=os.environ.get("DISPLAY")).save(image)
        checkout = Path(__file__).resolve().parents[1]
        sources = ("src/cleanroomx/cfd_multizone_gui.py", "src/cleanroomx/cfd_cell_probes.py",
                   "scripts/capture_cell_probe_gui.py")
        metadata = {
            "schema": "cleanroomx.recorded-cell-probe-capture.v1",
            "new_solver_execution": False, "engineering_release": "HOLD",
            "source_iteration": report["time_name"],
            "source_manifest_sha256": report["provenance"]["manifest_sha256"],
            "source_run_receipt_sha256": report["provenance"]["run_receipt_sha256"],
            "solver_reported_convergence": report["solver_reported_convergence"],
            "mesh_cells": len(report["cells"]), "gui_callback_errors": errors,
            "selected_probe": window._active_cell_probe,
            "readout": window.probe_status.get(),
            "file": image.name, "kind": "actual_Tk_window_pixels",
            "width": width, "height": height,
            "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
            "implementation_sha256": {name: hashlib.sha256((checkout/name).read_bytes()).hexdigest()
                                      for name in sources},
        }
        (args.output_directory/"capture-manifest.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True, allow_nan=False)+"\n", encoding="utf-8")
        print(f"Captured actual {width}x{height} probe UI, {len(window.cell_probes)} selections, zero callback errors.")
    finally:
        window.close()
        root.destroy()


if __name__ == "__main__":
    main()
