"""Capture real CleanroomX windows against an existing verified solver case.

Run on an actual desktop/Xvfb display after installing .[cfd]. This script
does not generate solver data, draw mock UI or modify the source CFD case.
Output directories must not already exist.
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
import vtk

from cleanroomx.cfd_multizone_gui import MultizoneCFDWindow
from cleanroomx.cfd_multizone_results import analyze_multizone_case, export_multizone_report
from cleanroomx.cfd_multizone_stability import analyze_recorded_iteration_history
from cleanroomx.cfd_multizone_vtk import open_multizone_vtk_window
from cleanroomx.cfd_particle_sources import export_particle_source_run, export_particle_source_csv
from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_directory", type=Path)
    parser.add_argument("image_directory", type=Path)
    parser.add_argument("evidence_directory", type=Path)
    args = parser.parse_args()
    report = analyze_multizone_case(args.case_directory, density_kg_m3=1.2, reference_room_id="corridor")
    args.image_directory.mkdir(parents=True, exist_ok=False)
    args.evidence_directory.mkdir(parents=True, exist_ok=False)
    export_multizone_report(report, args.evidence_directory/"computed-report")
    images, errors = [], []
    root = tk.Tk()
    root.report_callback_exception = lambda *exception: errors.append(repr(exception))
    app = CleanroomXApp(root, autosave_interval_seconds=0,
                       ui_state_path=args.evidence_directory/"capture-ui-state.json")
    app.set_theme("dark", persist=False)
    app.load_project_path(bundled_demo_project_path())

    def settle(target):
        target.lift()
        for _ in range(4):
            root.update_idletasks()
            root.update()
            time.sleep(.025)

    def screenshot(target, name, description):
        settle(target)
        x, y, w, h = target.winfo_rootx(), target.winfo_rooty(), target.winfo_width(), target.winfo_height()
        path = args.image_directory/name
        ImageGrab.grab(bbox=(x, y, x+w, y+h), xdisplay=os.environ.get("DISPLAY")).save(path)
        images.append({"file":name,"kind":"actual_Tk_window_pixels","description":description,
                       "width":w,"height":h,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()})

    def vtk_screenshot(viewer, name, description):
        settle(viewer)
        rw = viewer._cleanroomx_vtk_render_window
        rw.Render()
        buffer = vtk.vtkWindowToImageFilter()
        buffer.SetInput(rw)
        buffer.ReadFrontBufferOff()
        buffer.Update()
        writer = vtk.vtkPNGWriter()
        path = args.image_directory/name
        writer.SetFileName(str(path))
        writer.SetInputConnection(buffer.GetOutputPort())
        writer.Write()
        images.append({"file":name,"kind":"actual_VTK_render_window_framebuffer",
                       "description":description,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()})

    def wait_until(predicate, timeout=30):
        deadline = time.monotonic()+timeout
        while not predicate() and time.monotonic()<deadline:
            root.update()
            time.sleep(.02)
        if not predicate():
            raise RuntimeError("Timed out waiting for actual GUI worker")

    review, viewer = None, None
    try:
        app.notebook.select(app.start_center)
        screenshot(root, "01-main-workspace.png", "Running CleanroomX start workspace with the bundled input project")
        app._activate_spatial_workspace("3d")
        app.spatial_workspace.set_3d_view_preset("iso")
        screenshot(root, "02-design-studio.png", "Actual 3D design geometry; design arrows/pressure intent are not CFD fields")
        app._activate_spatial_workspace("split")
        screenshot(root, "03-multiroom-design.png", "Synchronized actual 2D/3D multiroom input geometry")
        app.spatial_workspace.select_item("room", "process", notify=True)
        app.spatial_workspace.set_inspector_visible(True)
        screenshot(root, "04-object-inspector.png", "Actual selected-room property inspector")
        review = MultizoneCFDWindow(root, directory=args.case_directory)
        review.geometry("1390x900+0+0")
        review.load_report(report)
        screenshot(review, "05-simulation-workspace.png", "Real imported OpenFOAM room/door p and phi review; nonconvergence/HOLD retained")
        review.tabs.select(1)
        review.field.set("Speed (m/s)")
        review.axis.set("z")
        review.position.set("1.35")
        review.draw_section()
        screenshot(review, "07-computed-velocity-section.png", "Actual recorded cell velocity magnitudes/vectors on a z layer; no interpolated cells")
        review.tabs.select(0)
        screenshot(review, "08-pressure-and-airflow.png", "Computed room pressures, door deltas and face-flux airflow balances")
        review.tabs.select(2)
        screenshot(review, "11-residual-graphs.png", "Actual saved solver initial/final residual histories")
        history = analyze_recorded_iteration_history(args.case_directory, density_kg_m3=1.2, reference_room_id="corridor")
        review.load_iteration_history(history)
        screenshot(review, "12-iteration-analysis.png", "Actual saved SIMPLE pressure/continuity observations; iteration is not physical time")
        review.withdraw()
        viewer = open_multizone_vtk_window(root, report, [], case_directory=args.case_directory)
        assert viewer._cleanroomx_load_verified_mesh()
        wait_until(lambda: not viewer._cleanroomx_mesh_state["busy"])
        if viewer._cleanroomx_mesh_state["dataset"] is None:
            raise RuntimeError(viewer._cleanroomx_view_status.get())
        viewer._cleanroomx_plane_var.set("z")
        viewer._cleanroomx_plane_position_var.set("1.35")
        viewer._cleanroomx_refresh_scene()
        vtk_screenshot(viewer, "06-original-openfoam-mesh.png", "Original verified polyMesh cell edges on the selected recorded z layer")
        viewer._cleanroomx_mesh_var.set(False)
        viewer._cleanroomx_plane_var.set("all")
        viewer._cleanroomx_plane_position_var.set("")
        viewer._cleanroomx_refresh_scene()
        vtk_screenshot(viewer, "15-computed-3d-velocity.png", "Actual recorded 3D velocity samples with isometric camera; no interpolated volume field")
        viewer._cleanroomx_field_var.set("pressure")
        viewer._cleanroomx_refresh_scene()
        vtk_screenshot(viewer, "16-computed-3d-pressure.png", "Actual recorded 3D relative pressure samples in Pa, using explicit density/reference")
        viewer._cleanroomx_field_var.set("speed")
        viewer._cleanroomx_refresh_scene()
        panel = viewer._cleanroomx_open_particle_sources()
        panel.geometry("1160x830+0+0")
        for number, room in enumerate(("process", "preparation"), start=1):
            cells = [c for c in report["cells"] if c["room_id"]==room]
            # Seed the strongest observed downflow cell in each room. This
            # makes transport visible without exaggerating computed motion.
            seed = max(cells, key=lambda c: -c["velocity_m_s"][2])["center_m"]
            panel.new_source(seed)
            for key, value in {"source_id":f"Source_{room}","particle_count":"4", "start_time_s":str(.3*(number-1)),
                               "duration_s":".6", "diameter_um":"5", "particle_density_kg_m3":"1000"}.items():
                panel.vars[key].set(value)
            if not panel.save_source():
                raise RuntimeError(panel.status.get())
        panel.save_configuration(args.evidence_directory/"particle-sources.json")
        screenshot(panel, "09-particle-injection.png", "Actual source editor with two saved fluid sources, diameter/density/count and release schedules")
        assert panel.start_run()
        wait_until(lambda: not panel.busy)
        if panel.last_run is None:
            raise RuntimeError(panel.status.get())
        screenshot(panel, "13-particle-population.png", "Computed numerical particle population chart/table from eight scheduled frozen-U trajectories")
        panel.withdraw()
        viewer._cleanroomx_field_points_var.set(False)
        viewer._cleanroomx_arrows_var.set(False)
        viewer._cleanroomx_refresh_scene()
        viewer._cleanroomx_camera_var.set("iso")
        viewer._cleanroomx_apply_camera()
        viewer._cleanroomx_playback_var.set(1.)
        viewer._cleanroomx_update_particle_markers()
        vtk_screenshot(viewer, "10-computed-particle-tracking.png", "Actual integrated particle paths and release-aware recorded-sample markers in computed 3D U")
        camera = viewer._cleanroomx_vtk_renderer.GetActiveCamera()
        original_camera = vtk.vtkCamera()
        original_camera.DeepCopy(camera)
        trajectory = panel.last_run["tracks"][0]["points"]
        focus = [(trajectory[0]["xyz_m"][a]+trajectory[-1]["xyz_m"][a])/2 for a in range(3)]
        camera.SetFocalPoint(*focus)
        camera.SetPosition(focus[0]+1.2, focus[1]-1.6, focus[2]+.8)
        camera.SetViewUp(0, 0, 1)
        camera.ParallelProjectionOn()
        camera.SetParallelScale(.35)
        viewer._cleanroomx_vtk_renderer.ResetCameraClippingRange()
        vtk_screenshot(viewer, "17-particle-source-closeup.png", "Actual camera close-up of computed process-source paths; no trajectory scaling or synthetic motion")
        camera.DeepCopy(original_camera)
        screenshot(viewer, "14-3d-review-controls.png", "Actual 3D field/source/mesh and particle playback controls")
        export_particle_source_run(report, panel.last_run, args.evidence_directory/"particle-run.json")
        export_particle_source_csv(report, panel.last_run, args.evidence_directory/"particle-trajectories.csv")
        if errors:
            raise RuntimeError(f"GUI callback errors: {errors}")
        manifest = {
            "description":"Genuine running Tk windows and VTK framebuffers; no mock UI or artificial solver data",
            "source_iteration":report["time_name"], "source_provenance":report["provenance"],
            "mesh":report["mesh"], "selected_iteration_solver_converged":report["solver_reported_convergence"],
            "engineering_release":"HOLD", "images":images, "gui_callback_errors":errors,
            "particle_source_count":len(panel.sources), "numerical_particle_count":len(panel.last_run["tracks"]),
            "physical_particle_validation":False,
        }
        (args.evidence_directory/"capture-manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False)+"\n")
        print(json.dumps({"captured_images":len(images),"solver_iteration":report["time_name"],
                          "solver_converged":report["solver_reported_convergence"],"gui_callback_errors":errors}))
    finally:
        if viewer is not None and viewer.winfo_exists():
            viewer.destroy()
        if review is not None and review.winfo_exists():
            review.close()
        root.destroy()


if __name__ == "__main__":
    main()
