#!/usr/bin/env python3
"""Exercise the actual Studio → Run → Foundation v10 → analysis desktop path."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import tkinter as tk

from cleanroomx.cfd_analysis_export import export_analysis_bundle
from cleanroomx.cfd_result_analysis import analyze_synced_results, build_analysis_graph
from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--bashrc", default="/opt/openfoam10/etc/bashrc")
    parser.add_argument("--timeout-seconds", type=int, default=240)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    root = tk.Tk()
    root.geometry("1536x960+0+0")
    errors = []
    root.report_callback_exception = lambda kind, value, trace: errors.append(f"{kind.__name__}: {value}")
    app = CleanroomXApp(root, autosave_interval_seconds=0, ui_state_path=args.output / "ui.json")
    try:
        app.load_project_path(bundled_demo_project_path())
        root.update()
        app.open_design_studio()
        app.spatial_workspace.select_item("room", "process", notify=True)
        root.update()
        app.open_room_solver()
        workspace = app.openfoam_workspace
        workspace.runtime_mode_var.set("native")
        workspace.bashrc_var.set(args.bashrc)
        workspace.runs_folder_var.set(str(args.output / "runs"))
        workspace.mesh_var.set("12 10 6")
        workspace.iterations_var.set("150")
        workspace.open_results_var.set(True)
        # Keep normal application dialogs from hanging a noninteractive check.
        # Any error dialog is a test failure, never a suppressed solver error.
        from cleanroomx import gui_openfoam
        gui_openfoam.messagebox.showerror = lambda title, message, **kwargs: errors.append(f"{title}: {message}")
        root.update()
        workspace.run_room_button.invoke()
        if not workspace._busy:
            raise RuntimeError("Run button did not start a solver process: " + repr(errors))
        if app.cancel_button.cget("text") != "Stop" or "disabled" not in app.run_button.state():
            raise RuntimeError("Desktop execution controls were not connected to the solver process")
        progress = []
        deadline = time.monotonic() + args.timeout_seconds
        while workspace._busy and time.monotonic() < deadline:
            root.update()
            if not progress or progress[-1] != workspace.progress_var.get():
                progress.append(workspace.progress_var.get())
            time.sleep(.02)
        if workspace._busy:
            workspace._stop()
            raise RuntimeError("Timed out waiting for the real desktop solver run")
        if errors or "Failed" in workspace.progress_var.get():
            raise RuntimeError("Desktop solver failed: " + repr(errors) + "\n" + workspace._console_log.display_text[-6000:])
        explorer = workspace.last_explorer
        if explorer is None:
            raise RuntimeError("Successful run did not open the result explorer")
        while explorer._busy and time.monotonic() < deadline:
            root.update()
            time.sleep(.02)
        if explorer._busy or not explorer.sessions:
            raise RuntimeError("Result explorer did not load real synchronized data: " + explorer.status_var.get())
        session = analyze_synced_results(workspace.result_directory_var.get(), workspace.simulation_id_var.get(),
                                         case_directory=workspace.case_directory_var.get(), verify_native_sources=True)
        report = session.report
        if len(report.get("flow_balances", [])) != 3 or len(report.get("ventilations", [])) != 3:
            raise RuntimeError("Missing receipt-bound solver flux and supply ACH for the three domains")
        graphs = [build_analysis_graph([session], kind=kind, field_name="all" if kind == "residual_history" else "speed")
                  for kind in ("field_history", "residual_history", "flow_balance", "air_change_rate")]
        if any(graph["status"] != "computed_diagnostic" for graph in graphs):
            raise RuntimeError("A required real solver graph is unavailable")
        export_analysis_bundle([session], graphs, args.output / "analysis")
        # Check fail-closed behavior against this actual run, then restore the
        # exact original bytes before retaining or rendering its evidence.
        case_root = Path(workspace.case_directory_var.get())
        tamper_rejections = []
        for relative in ("configuration_1/0/U", "configuration_1/150/p",
                         "configuration_1/constant/polyMesh/boundary", "configuration_1/simpleFoam.log"):
            path = case_root / relative
            original = path.read_bytes()
            try:
                path.write_bytes(original + b"\n// verification: changed evidence\n")
                try:
                    analyze_synced_results(workspace.result_directory_var.get(), workspace.simulation_id_var.get(),
                                           case_directory=case_root, verify_native_sources=True)
                except ValueError:
                    tamper_rejections.append(relative)
                else:
                    raise RuntimeError("Changed solver evidence was accepted: " + relative)
            finally:
                path.write_bytes(original)
        if any("solver error" in text for text in progress):
            raise RuntimeError("Healthy solver progress was incorrectly labeled as an error")
        from PIL import ImageGrab
        shots = {}
        for name, view in (("residuals", "Solver residual history"), ("flow_balance", "Boundary airflow balance"),
                           ("supply_ach", "Whole-domain inlet supply ACH")):
            explorer.view_var.set(view)
            explorer._view_changed()
            explorer.draw_graph()
            while explorer._busy and time.monotonic() < deadline:
                root.update()
                time.sleep(.02)
            root.update()
            explorer.geometry("1280x900+0+0")
            root.update()
            box = (explorer.winfo_rootx(), explorer.winfo_rooty(),
                   explorer.winfo_rootx() + explorer.winfo_width(), explorer.winfo_rooty() + explorer.winfo_height())
            filename = args.output / f"actual-solver-{name}.png"
            ImageGrab.grab(bbox=box).save(filename)
            shots[filename.name] = hashlib.sha256(filename.read_bytes()).hexdigest()
        explorer._close()
        root.update()
        app.notebook.select(workspace)
        workspace._workflow_canvas.yview_moveto(0)
        root.update()
        ImageGrab.grab(bbox=(0, 0, root.winfo_width(), root.winfo_height())).save(args.output / "actual-solver-workflow.png")
        workspace._console_log.save_to(args.output / "desktop-console.log")
        receipt = json.loads((Path(workspace.case_directory_var.get()) / "execution-receipt.json").read_text())
        summary = {"schema_version": "cleanroomx.desktop-solver-verification.v1",
                   "source_commit": os.environ.get("CLEANROOMX_CAPTURE_SOURCE_SHA", os.environ.get("GITHUB_SHA")),
                   "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in Path(__file__).resolve().parents[1].joinpath("src/cleanroomx").glob("*.py")},
                   "run_source": "Actual Tk Run room study button; actual Foundation v10 processes; no solver mocks",
                   "solver_status": receipt["status"], "solver_release": receipt["solver_release"],
                   "solver_build": receipt["solver_build"], "stage_count": sum(len(c["stages"]) for c in receipt["cases"].values()),
                   "case_count": len(report["cases"]), "snapshots": len(report["snapshots"]),
                   "cell_counts": sorted({s["cell_count"] for s in report["snapshots"]}),
                   "source_files_verified": len(report["sources"]), "native_fields_rehashed": report["reproducibility"]["native_source_bytes_rehashed"],
                   "flow_balances": [{k: v for k, v in item.items() if k != "sources"} for item in report["flow_balances"]],
                   "ventilations": [{k: v for k, v in item.items() if k != "sources"} for item in report["ventilations"]],
                   "progress_observed": progress, "graph_kinds": [g["kind"] for g in graphs], "screenshots": shots,
                   "changed_evidence_rejected": tamper_rejections,
                   "scientific_validation": "BLOCKED", "gui_errors": errors}
        (args.output / "verification.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
        print(json.dumps({k: summary[k] for k in ("solver_status", "case_count", "stage_count", "snapshots", "native_fields_rehashed", "scientific_validation")}, indent=2))
        return 0
    finally:
        app._autosave_manager.shutdown(wait=False)
        root.destroy()


if __name__ == "__main__":
    raise SystemExit(main())
