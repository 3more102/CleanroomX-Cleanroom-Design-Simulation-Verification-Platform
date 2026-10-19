"""Capture the actual Tk analysis explorer using explicitly labeled test fixtures.

Run under an X display, e.g. xvfb-run -a python tools/capture_cfd_analysis_screenshots.py.
This does not start OpenFOAM and creates no CFD validation evidence.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
from tkinter import ttk

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

from cleanroomx.cfd_result_analysis import analyze_synced_results, analyze_two_room_results
from cleanroomx.gui_cfd_analysis import CFDAnalysisExplorer
from cleanroomx.gui_theme import configure_ttk_theme
from cfd_analysis_fixtures import write_sync_store, write_two_room_analysis_fixture


def wait(root, condition):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        root.update()
        if condition():
            root.update_idletasks()
            return
        time.sleep(0.01)
    raise RuntimeError("Timed out loading the real analysis explorer")


def capture(output: Path):
    from PIL import ImageGrab
    import os
    output.mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    root.withdraw()
    configure_ttk_theme(root, "light")
    records = []
    try:
        with tempfile.TemporaryDirectory(prefix="cleanroomx-analysis-screenshot-") as temporary:
            scratch = Path(temporary)
            write_sync_store(scratch / "store", "SYNTHETIC-before")
            write_sync_store(scratch / "store", "SYNTHETIC-after", factor=1.2)
            session = analyze_synced_results(scratch / "store", "SYNTHETIC-before")
            explorer = CFDAnalysisExplorer(root, lambda: session)
            explorer.geometry("1280x900+30+30")
            ttk.Label(explorer, text="SYNTHETIC PARSER FIXTURE - no OpenFOAM solver run", foreground="#a02a20").pack(side="top", before=explorer.winfo_children()[0])

            def save(name):
                explorer.canvas.draw()
                root.update()
                image = ImageGrab.grab(xdisplay=os.environ.get("DISPLAY"))
                box = (explorer.winfo_rootx(), explorer.winfo_rooty(),
                       explorer.winfo_rootx()+explorer.winfo_width(), explorer.winfo_rooty()+explorer.winfo_height())
                image = image.crop(box)
                path = output / name
                image.save(path)
                records.append({"path": name, "size_px": list(image.size), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                "view": explorer.view_var.get(), "source": "synthetic_test_fixture_not_solver_execution"})

            wait(root, lambda: explorer.current_graph is not None and not explorer._busy)
            save("cfd-analysis-field-history.png")
            explorer.sessions.append(analyze_synced_results(scratch / "store", "SYNTHETIC-after"))
            explorer._refresh_choices()
            explorer.view_var.set("Compare cases / runs at selected time")
            explorer.draw_graph()
            wait(root, lambda: not explorer._busy)
            save("cfd-analysis-run-comparison.png")
            explorer.view_var.set("3D cell samples")
            explorer.case_var.set("configuration_1")
            explorer.time_var.set("2")
            explorer.field_var.set("T")
            explorer.draw_graph()
            wait(root, lambda: not explorer._busy)
            save("cfd-analysis-3d-temperature.png")
            explorer._close()

            case, receipt = write_two_room_analysis_fixture(scratch)
            explorer = CFDAnalysisExplorer(root, lambda: analyze_two_room_results(case, receipt))
            explorer.geometry("1280x900+30+30")
            ttk.Label(explorer, text="SYNTHETIC PARSER FIXTURE - no OpenFOAM solver run", foreground="#a02a20").pack(side="top", before=explorer.winfo_children()[0])
            wait(root, lambda: explorer.current_graph is not None and not explorer._busy)
            save("cfd-analysis-room-pressure.png")
            for view, name in (("Boundary airflow balance", "cfd-analysis-flow-balance.png"),
                               ("Solver residual history", "cfd-analysis-residuals.png")):
                explorer.view_var.set(view)
                explorer.field_var.set("all")
                explorer.draw_graph()
                wait(root, lambda: not explorer._busy)
                save(name)
            explorer._close()
        (output / "manifest.json").write_text(json.dumps({"capture": "real_Tk_widgets_and_Matplotlib_TkAgg",
            "capture_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "fixture_module_sha256": hashlib.sha256((ROOT / "tests/cfd_analysis_fixtures.py").read_bytes()).hexdigest(),
            "data": "SYNTHETIC parser fixtures; no OpenFOAM execution or physical validation",
            "screenshots": records}, indent=2) + "\n", encoding="utf-8")
    finally:
        root.destroy()


if __name__ == "__main__":
    capture(ROOT / "docs" / "screenshots" / "cfd-analysis")
