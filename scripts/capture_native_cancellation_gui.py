"""Exercise real Tk -> native OpenFOAM -> cancellation and retain original pixels.

Requires a sourced Foundation v10 environment, display and optional Pillow.
The case and image directories must be new; no solver fields are fabricated.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import time
import tkinter as tk

from PIL import ImageGrab

from cleanroomx.cfd_multizone import generate_multizone_open_door_case
from cleanroomx.cfd_multizone_gui import MultizoneCFDWindow
from cleanroomx.cfd_multizone_results import analyze_multizone_case
from cleanroomx.gui import bundled_demo_project_path
from cleanroomx.gui_theme import configure_ttk_theme


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_directory",type=Path)
    parser.add_argument("image_directory",type=Path)
    args=parser.parse_args()
    generate_multizone_open_door_case(
        bundled_demo_project_path(),args.case_directory,door_mode="open",
        kinematic_viscosity_m2_s=1.5e-5,max_iterations=10000,output_interval=100,
    )
    args.image_directory.mkdir(parents=True,exist_ok=False)
    errors,images=[],[]
    root=tk.Tk()
    configure_ttk_theme(root,"dark")
    root.withdraw()
    root.report_callback_exception=lambda *exc:errors.append(repr(exc))
    view=MultizoneCFDWindow(root,directory=args.case_directory)
    view.geometry("1390x930+0+0")

    def capture(name,description):
        view.lift()
        for _ in range(3):
            root.update()
            time.sleep(.025)
        x,y=view.winfo_rootx(),view.winfo_rooty()
        width,height=view.winfo_width(),view.winfo_height()
        path=args.image_directory/name
        ImageGrab.grab(
            bbox=(x,y,x+width,y+height),xdisplay=os.environ.get("DISPLAY"),
        ).save(path)
        images.append({"file":name,"description":description,"width":width,"height":height,
                       "kind":"actual_Tk_window_pixels","sha256":hashlib.sha256(path.read_bytes()).hexdigest()})

    try:
        root.update()
        view.run_case()
        deadline=time.monotonic()+45
        log=args.case_directory/"simpleFoam.log"
        solver_pid=None
        while view.running and time.monotonic()<deadline:
            root.update()
            if log.is_file():
                text=log.read_text()
                match=re.search(r"(?m)^PID\s*:\s*(\d+)",text)
                if match and "Time =" in text:
                    solver_pid=int(match[1])
                    break
            time.sleep(.01)
        if solver_pid is None:
            raise RuntimeError("Actual solver did not enter its iteration loop")
        if str(view.cancel_native_button["state"])!="normal":
            raise RuntimeError("Native cancellation control is unavailable during the real run")
        capture("01-running-native-solver.png","Actual live native simpleFoam, with enabled cancellation control")
        view.cancel_native_button.invoke()
        deadline=time.monotonic()+10
        while view.running and time.monotonic()<deadline:
            root.update()
            time.sleep(.01)
        if view.running:
            raise RuntimeError("Native cancellation did not finish before deadline")
        receipt=json.loads((args.case_directory/"run-receipt.json").read_text())
        if receipt["status"]!="cancelled" or receipt["outputs"] or view.report is not None:
            raise RuntimeError("Cancelled GUI operation exposed a completed CFD result")
        try:
            os.kill(solver_pid,0)
        except ProcessLookupError:
            pass
        else:
            raise RuntimeError("The cancelled solver process still exists")
        try:
            analyze_multizone_case(args.case_directory,density_kg_m3=1.2,reference_room_id="corridor")
        except ValueError as exc:
            if "successful recorded" not in str(exc):
                raise
        else:
            raise RuntimeError("Partial fields were incorrectly accepted")
        capture("02-cancelled-and-rejected.png","Actual cancelled receipt; GUI refuses partial fields as completed CFD")
        if errors:
            raise RuntimeError(f"GUI callback failures: {errors}")
        retained,source_hashes={},{}
        for name in ("manifest.json","run-receipt.json","blockMesh.log","checkMesh.log","simpleFoam.log"):
            data=(args.case_directory/name).read_bytes()
            target="source-manifest.json" if name=="manifest.json" else name
            source_hashes[name]=hashlib.sha256(data).hexdigest()
            if name.endswith(".log"):
                target += ".gz"
                data=gzip.compress(data,mtime=0)
            (args.image_directory/target).write_bytes(data)
            retained[target]=hashlib.sha256(data).hexdigest()
        manifest={
            "created_utc":datetime.now(timezone.utc).isoformat(),
            "operation":"genuine_Tk_native_OpenFOAM_cancellation",
            "solver_pid_reaped":True,"receipt_status":receipt["status"],
            "partial_field_import_rejected":True,"gui_callback_errors":errors,
            "engineering_release":"HOLD","images":images,"evidence_sha256":retained,
            "raw_source_sha256":source_hashes,
        }
        (args.image_directory/"capture-manifest.json").write_text(
            json.dumps(manifest,indent=2,allow_nan=False)+"\n",encoding="utf-8")
        print(json.dumps({"actual_images":len(images),"status":receipt["status"],"callback_errors":len(errors)}))
        return 0
    finally:
        if view._native_cancel_event is not None:
            view._native_cancel_event.set()
        root.destroy()


if __name__=="__main__":
    raise SystemExit(main())
