"""Real VTK-on-Tk widget smoke test under Xvfb, using *labeled synthetic fixtures*.

This checks an actual native window and GUI field/vector controls. It is not
OpenFOAM execution or CFD validation. See test_cfd_multizone_execution.py for
real solver-field contract tests.
"""
import tkinter as tk
import json

import pytest

vtk = pytest.importorskip("vtk")

from cleanroomx.cfd_multizone_vtk import open_multizone_vtk_window
from test_cfd_multizone_vtk import _source
from cleanroomx.cfd_streamlines import trace_computed_streamline


def test_real_tk_vtk_window_opens_and_updates_selected_field_and_glyphs(tmp_path):
    root = tk.Tk()
    root.geometry("900x700")
    window = None
    try:
        report = _source()
        trace = trace_computed_streamline(report,(0.5,0.5,0.5),max_integration_s=1.)
        root.update()
        window = open_multizone_vtk_window(root,report,[trace])
        root.update()
        assert isinstance(window,tk.Toplevel)
        assert window._cleanroomx_vtk_mode in ("embedded","native")
        assert window._cleanroomx_vtk_render_window is not None
        assert window._cleanroomx_vtk_renderer.GetActors().GetNumberOfItems() >= 4
        assert window._cleanroomx_field_var.get() == "speed"
        window._cleanroomx_field_var.set("pressure")
        window._cleanroomx_arrows_var.set(False)
        window._cleanroomx_refresh_scene()
        root.update()
        assert window._cleanroomx_field_var.get() == "pressure"
        assert window._cleanroomx_vtk_renderer.GetActors().GetNumberOfItems() >= 3
        assert window._cleanroomx_vtk_renderer.GetActors().GetNumberOfItems() < 5
        # Rebuild from the exact recorded x-cell layer and reject missing data.
        window._cleanroomx_room_var.set("r1")
        window._cleanroomx_plane_var.set("x")
        window._cleanroomx_plane_position_var.set("1.5")
        window._cleanroomx_refresh_scene()
        root.update()
        assert "1 recorded cells" in window._cleanroomx_view_status.get()
        old_renderer=window._cleanroomx_vtk_renderer
        window._cleanroomx_plane_position_var.set("100")
        window._cleanroomx_refresh_scene()
        assert window._cleanroomx_vtk_renderer is old_renderer
        assert "Selection rejected" in window._cleanroomx_view_status.get()
        window._cleanroomx_plane_var.set("all")
        window._cleanroomx_plane_position_var.set("")
        window._cleanroomx_refresh_scene()
        assert "3 recorded cells" in window._cleanroomx_view_status.get()
        # Genuine VTK display-to-world projection followed by vtkPointPicker.
        renderer=window._cleanroomx_vtk_renderer
        renderer.SetWorldPoint(1.5,0.5,0.5,1.0)
        renderer.WorldToDisplay()
        x,y,_=renderer.GetDisplayPoint()
        assert window._cleanroomx_seed_display_point(x,y)
        assert len(window._cleanroomx_traces)==2
        assert window._cleanroomx_traces[-1]["points"][0]["xyz_m"]==[1.5,0.5,0.5]
        assert "NOT particle tracking" in window._cleanroomx_view_status.get()
        assert not window._cleanroomx_seed_display_point(-100,-100)
        assert len(window._cleanroomx_traces)==2
        exported=tmp_path/"vtk3d-paths.json"
        assert window._cleanroomx_export_traces_to_path(exported)
        payload=json.loads(exported.read_text(encoding="utf-8"))
        assert payload["source_iteration"]=="50"
        assert len(payload["traces"])==2
        assert payload["validation"]=="steady_visualization_only_not_particle_transport"
        assert not window._cleanroomx_export_traces_to_path(exported)
        assert "Export rejected" in window._cleanroomx_view_status.get()
    finally:
        if window is not None:
            window.destroy()
        root.destroy()
