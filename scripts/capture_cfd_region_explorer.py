"""Capture actual Tk explorer widgets using explicitly SYNTHETIC field fixtures.

Run on a display-enabled machine with the development and CFD extras installed.
These images document UI behavior, never OpenFOAM execution or physical validation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk

from PIL import ImageGrab

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "tests"))
from cfd_analysis_fixtures import write_dense_sync_store
from cleanroomx.cfd_result_analysis import analyze_synced_results
from cleanroomx.gui_cfd_analysis import CFDAnalysisExplorer
from cleanroomx.gui_theme import configure_ttk_theme


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    root.withdraw()
    configure_ttk_theme(root, "light")
    artifacts = []
    with tempfile.TemporaryDirectory(prefix="cleanroomx-synthetic-ui-") as temporary:
        store = Path(temporary) / "store"
        write_dense_sync_store(store)
        explorer = CFDAnalysisExplorer(root, lambda: analyze_synced_results(store, "SYNTHETIC-room-grid"))
        explorer.title("CleanroomX · SYNTHETIC fixture · Region analysis preview")

        def wait_ready():
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                root.update()
                if explorer.current_graph is not None and not explorer._busy:
                    return
                time.sleep(.02)
            raise RuntimeError("Timed out waiting for the analysis explorer")

        def capture(name):
            for _ in range(5):
                root.update()
                time.sleep(.05)
            x, y = explorer.winfo_rootx(), explorer.winfo_rooty()
            width, height = explorer.winfo_width(), explorer.winfo_height()
            image = ImageGrab.grab(bbox=(x, y, x + width, y + height), xdisplay=os.getenv("DISPLAY"))
            path = args.output_dir / name
            image.save(path)
            artifacts.append({"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                              "width": width, "height": height,
                              "canvas_width": explorer.canvas.get_tk_widget().winfo_width(),
                              "canvas_height": explorer.canvas.get_tk_widget().winfo_height()})

        try:
            wait_ready()
            explorer.geometry("1180x820+10+10")
            explorer.case_var.set("configuration_1")
            explorer.field_var.set("T")
            explorer.view_var.set("3D cell samples")
            explorer.region_var.set("Custom box")
            explorer.region_label_var.set("West half · synthetic")
            for variable, value in zip(explorer.region_bounds_vars, (0, 3, 0, 4, 0, 3)):
                variable.set(str(value))
            explorer.draw_graph()
            wait_ready()
            capture("region-3d.png")
            explorer.notebook.select(explorer.selection_frame)
            capture("region-statistics.png")
            explorer.notebook.select(0)
            explorer.geometry("780x560+10+10")
            capture("region-laptop.png")
        finally:
            explorer._close()
            root.destroy()
    (args.output_dir / "manifest.json").write_text(json.dumps({
        "fixture": "SYNTHETIC parser data; no solver execution", "scientific_validation": "BLOCKED",
        "files": artifacts}, indent=2) + "\n")
    print(json.dumps(artifacts, indent=2))


if __name__ == "__main__":
    main()
