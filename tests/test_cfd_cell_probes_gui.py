"""Actual Tk interactions on a labelled synthetic field, not CFD evidence."""
import json
import os
import tkinter as tk

import pytest

from cleanroomx import cfd_multizone_gui as gui
from test_cfd_cell_probes import _report


@pytest.fixture
def desktop():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY") or os.name == "nt":
            raise
        pytest.skip(f"Actual Tk display required: {exc}")
    root.withdraw()
    errors = []
    root.report_callback_exception = lambda *args: errors.append(args)
    window = gui.MultizoneCFDWindow(root)
    window.geometry("850x600")
    # Finish startup callbacks before supplying the deliberately minimal field.
    root.update()
    window.report = _report()
    window.position.set(".5")
    window.tabs.select(window.fields_tab)
    root.update()
    window.draw_section()
    try:
        yield root, window
        assert not errors
    finally:
        window.close()
        root.destroy()


def test_click_and_xyz_probe_exact_values_without_creating_streamlines(desktop):
    root, window = desktop
    window.section_click_mode.set("Probe cell")
    x, y = window._section_to_pixel(.5, .5)
    window.section_canvas.event_generate("<Button-1>", x=round(x), y=round(y))
    root.update()
    assert len(window.cell_probes) == 1
    assert window.cell_probes[0]["cell_index"] == 0
    assert window.cell_probes[0]["velocity_m_s"] == [3., 4., 0.]
    assert "NOT CONVERGED" in window.probe_status.get()
    assert "relative to A" in window.probe_status.get()
    assert not window.trace_paths
    assert len(window.section_canvas.find_withtag("recorded-cell-probe")) == 3
    for variable, value in zip(window.probe_coordinates, [1.5, .5, .5]):
        variable.set(str(value))
    probe = window.probe_xyz()
    root.update()
    assert probe["cell_index"] == 1
    assert probe["pressure_pa_relative_to_reference"] == -4.25
    # The table selects prior measurements and redraws their own cell marker.
    window.probe_table.selection_set("0")
    root.update()
    assert window._active_cell_probe["cell_index"] == 0
    # Existing streamline mode and its default remain functional.
    window.section_click_mode.set("Streamline")
    window.section_canvas.event_generate("<Button-1>", x=round(x), y=round(y))
    root.update()
    assert len(window.trace_paths) == 1
    assert len(window.cell_probes) == 2


def test_sections_filter_marker_and_empty_xyz_cannot_substitute_values(desktop):
    root, window = desktop
    window.add_cell_probe([.5, .5, .5])
    window.room.set("B")
    window.draw_section()
    assert not window.section_canvas.find_withtag("recorded-cell-probe")
    window.room.set("all")
    for axis in "xyz":
        window.axis.set(axis)
        window.draw_section()
        root.update()
        assert window.section_canvas.find_withtag("recorded-cell-probe")
    window.axis.set("z")
    window.position.set("5")
    window.draw_section()
    assert window._section_to_world is None
    assert not window.section_canvas.find_withtag("recorded-cell-probe")
    for point in ([2.5, .5, .5], ["nan", .5, .5], ["invalid", .5, .5]):
        for variable, value in zip(window.probe_coordinates, point):
            variable.set(str(value))
        assert window.probe_xyz() is None
        assert len(window.cell_probes) == 1


def test_source_reset_export_and_small_window_scrolling(desktop, tmp_path, monkeypatch):
    root, window = desktop
    window.add_cell_probe([.5, .5, .5])
    saved = tmp_path/"probes.json"
    monkeypatch.setattr(gui.filedialog, "asksaveasfilename", lambda **kwargs: str(saved))
    window.export_probes_button.invoke()
    assert json.loads(saved.read_text())["probes"] == window.cell_probes
    window.export_probes_button.invoke()
    assert "export rejected" in window.probe_status.get()
    root.update()
    scroll = window.fields_tab._cleanroomx_scroll_canvas
    assert scroll.yview()[1] < 1
    before = scroll.yview()[0]
    window.section_canvas.event_generate("<MouseWheel>", delta=-120)
    root.update()
    assert scroll.yview()[0] > before
    # Both directions reach all controls at 850x600.
    assert scroll.xview()[1] < 1
    window.section_canvas.event_generate("<Shift-MouseWheel>", delta=-120)
    root.update()
    assert scroll.xview()[0] > 0
    window.report = None
    window._clear_results()
    root.update()
    assert not window.cell_probes
    assert not window.probe_table.get_children()
    assert window._active_cell_probe is None
    assert window._cell_probe_index is None
    assert window._section_to_world is None
    assert not window.section_canvas.find_withtag("recorded-cell-probe")
    assert str(window.export_probes_button.cget("state")) == "disabled"


def test_active_solver_blocks_probe_and_export(desktop, tmp_path, monkeypatch):
    _, window = desktop
    window.add_cell_probe([.5, .5, .5])
    saved = tmp_path/"blocked.json"
    monkeypatch.setattr(gui.filedialog, "asksaveasfilename", lambda **kwargs: str(saved))
    window.running = True
    try:
        assert window.add_cell_probe([1.5, .5, .5]) is None
        window.export_cell_probes()
        assert not saved.exists()
        assert len(window.cell_probes) == 1
    finally:
        window.running = False
