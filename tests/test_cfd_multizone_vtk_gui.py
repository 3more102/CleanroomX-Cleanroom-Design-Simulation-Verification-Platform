"""Real VTK-on-Tk widget smoke test under Xvfb, using *labeled synthetic fixtures*.

This checks an actual native window and GUI field/vector controls. It is not
OpenFOAM execution or CFD validation. See test_cfd_multizone_execution.py for
real solver-field contract tests.
"""
import tkinter as tk

import pytest

vtk = pytest.importorskip("vtk")

from cleanroomx.cfd_multizone_vtk import open_multizone_vtk_window
from test_cfd_multizone_vtk import _source
from cleanroomx.cfd_streamlines import trace_computed_streamline


def test_real_tk_vtk_window_opens_and_updates_selected_field_and_glyphs():
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
        assert window._cleanroomx_vtk_renderer.GetActors().GetNumberOfItems() >= 4
        assert window._cleanroomx_field_var.get() == "speed"
        window._cleanroomx_field_var.set("pressure")
        window._cleanroomx_arrows_var.set(False)
        window._cleanroomx_refresh_scene()
        root.update()
        assert window._cleanroomx_field_var.get() == "pressure"
        assert window._cleanroomx_vtk_renderer.GetActors().GetNumberOfItems() >= 3
        assert window._cleanroomx_vtk_renderer.GetActors().GetNumberOfItems() < 5
    finally:
        if window is not None:
            window.destroy()
        root.destroy()
