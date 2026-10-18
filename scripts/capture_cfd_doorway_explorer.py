"""Capture actual Tk widgets with an explicitly synthetic native-mesh fixture.

Run on a virtual or real display with dev/CFD dependencies and Pillow present.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk

from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_cfd_room_flux import write_native_two_room_fixture, bind_fixture_receipt
from cleanroomx.cfd_result_analysis import analyze_two_room_results
from cleanroomx.gui_cfd_analysis import CFDAnalysisExplorer
from cleanroomx.gui_theme import configure_ttk_theme


def main():
    output = ROOT / "docs/screenshots/cfd-doorway-flow"
    output.mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    root.withdraw()
    configure_ttk_theme(root, "light")
    with tempfile.TemporaryDirectory(prefix="cleanroomx-synthetic-native-") as temporary:
        case, _ = write_native_two_room_fixture(Path(temporary))
        receipt = Path(temporary) / "receipt/two_room_run_receipt.json"
        bind_fixture_receipt(case, receipt)
        explorer = CFDAnalysisExplorer(root, lambda: analyze_two_room_results(case, receipt))
        explorer.title("CleanroomX · SYNTHETIC native mesh fixture · Doorway diagnostic")
        for widget in explorer.winfo_children():
            if widget.winfo_class() == "TLabel" and str(widget.cget("text")).startswith("Recorded solver outputs"):
                widget.configure(text="SYNTHETIC native mesh / phi parser fixture · no solver execution · physical validation BLOCKED")
        def wait():
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                root.update()
                if explorer.current_graph is not None and not explorer._busy:
                    return
                time.sleep(.02)
            raise RuntimeError("Timed out waiting for doorway explorer")
        captures = []
        try:
            wait()
            explorer.view_var.set("Two-room doorway transfer and balances")
            explorer.draw_graph()
            wait()
            for width, height in ((1180, 820), (1050, 680)):
                explorer.geometry(f"{width}x{height}")
                for _ in range(8):
                    root.update()
                    time.sleep(.05)
                x, y = explorer.winfo_rootx(), explorer.winfo_rooty()
                file = output / f"synthetic-native-doorway-{width}x{height}.png"
                ImageGrab.grab(bbox=(x, y, x+width, y+height), xdisplay=os.environ.get("DISPLAY")).save(file)
                captures.append({"path": file.name, "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
                                 "width": width, "height": height})
        finally:
            explorer._close()
            root.destroy()
    sources = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (
        "src/cleanroomx/cfd_room_flux.py", "src/cleanroomx/cfd_result_analysis.py",
        "src/cleanroomx/gui_cfd_analysis.py", "src/cleanroomx/cfd_analysis_export.py",
        "tests/test_cfd_room_flux.py", "scripts/capture_cfd_doorway_explorer.py")}
    (output / "manifest.json").write_text(json.dumps({"source": "SYNTHETIC native mesh and phi parser fixtures",
        "capture": "actual Tk widgets and Matplotlib TkAgg", "solver_executed": False,
        "scientific_validation": "BLOCKED", "source_sha256": sources, "captures": captures}, indent=2)+"\n")


if __name__ == "__main__":
    main()
