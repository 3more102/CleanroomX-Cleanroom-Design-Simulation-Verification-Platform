"""Actual Tk/VTK interactions on labelled synthetic fields, not CFD evidence."""
import copy
import json
import time
import tkinter as tk

import pytest

from cleanroomx.cfd_particle_sources_gui import ParticleSourcesWindow
from cleanroomx.gui_theme import configure_ttk_theme
from test_cfd_particle_sources import _report


@pytest.fixture
def root():
    window = tk.Tk()
    configure_ttk_theme(window, "dark")
    yield window
    window.destroy()


def _wait(root, panel):
    deadline = time.monotonic()+10
    while panel.busy and time.monotonic() < deadline:
        root.update()
        time.sleep(.01)
    root.update()
    assert not panel.busy, panel.status.get()


def _configure(panel):
    panel.end_var.set("1")
    for key, value in {"particle_count": "3", "start_time_s": ".2", "duration_s": ".4"}.items():
        panel.vars[key].set(value)
    assert panel.save_source(), panel.status.get()


def test_real_source_editor_crud_rejects_invalid_fluid_and_roundtrips(root, tmp_path):
    panel = ParticleSourcesWindow(root, _report(), on_run=lambda _: None)
    _configure(panel)
    root.update()
    assert len(panel.table.get_children()) == 1
    assert panel.sources[0]["position_m"] == [.5, .5, .5]
    saved = copy.deepcopy(panel.sources)
    panel.vars["x"].set("999")
    assert not panel.save_source()
    assert panel.sources == saved
    panel.table.selection_set(saved[0]["source_id"])
    assert panel.toggle_source()
    assert not panel.sources[0]["enabled"]
    panel.table.selection_set(saved[0]["source_id"])
    assert panel.toggle_source()
    path = tmp_path/"sources.json"
    panel.save_configuration(path)
    panel.new_source([4.5, .5, .5])
    panel.vars["particle_count"].set("1")
    assert panel.save_source()
    assert len(panel.sources) == 2
    panel.load_configuration(path)
    assert panel.sources == saved
    panel.table.selection_set(saved[0]["source_id"])
    panel.delete_source()
    assert panel.sources == []
    assert panel.last_run is None


def test_worker_run_population_and_replayed_exports_use_real_widgets(root, tmp_path):
    applied = []
    panel = ParticleSourcesWindow(root, _report(), on_run=applied.append)
    _configure(panel)
    assert panel.start_run()
    _wait(root, panel)
    assert len(applied) == 1
    assert panel.last_run is applied[0]
    assert len(panel.population_table.get_children()) == 41
    assert all(row["accounting_complete"] for row in panel.population)
    assert panel.population[0]["not_yet_released"] == 3
    assert panel.population[-1]["observation_complete"] == 3
    assert panel.chart.find_all()
    assert "Engineering HOLD" in panel.status.get()
    path = tmp_path/"scheduled.json"
    assert panel.export_run(path)
    _wait(root, panel)
    assert json.loads(path.read_text())["tracks"][0]["release_time_s"] == .2
    assert panel.export_run(tmp_path/"samples.csv", csv_output=True)
    _wait(root, panel)
    assert "particle_age_s" in (tmp_path/"samples.csv").read_text()
    assert panel.export_run(path)
    _wait(root, panel)
    assert "rejected" in panel.status.get()


def test_cancel_or_edited_sources_never_publishes_partial_worker_result(root, monkeypatch):
    import cleanroomx.cfd_particle_sources_gui as ui
    real_run = ui.run_particle_sources
    heartbeat = []
    def delayed(*args, **kwargs):
        # Worker delay permits actual Tk callbacks while numerical work is pending.
        time.sleep(.15)
        return real_run(*args, **kwargs)
    monkeypatch.setattr(ui, "run_particle_sources", delayed)
    applied = []
    panel = ParticleSourcesWindow(root, _report(), on_run=applied.append)
    _configure(panel)
    assert panel.start_run()
    root.after(10, lambda: heartbeat.append(True))
    root.after(20, panel.cancel)
    _wait(root, panel)
    assert heartbeat and not applied
    assert panel.last_run is None
    assert "cancelled" in panel.status.get()
    assert panel.start_run()
    root.after(20, lambda: panel.end_var.set("1.2"))
    _wait(root, panel)
    assert not applied
    assert "discarded" in panel.status.get()


def test_viewer_changed_while_worker_runs_rejects_stale_paths(root, monkeypatch):
    import cleanroomx.cfd_particle_sources_gui as ui
    real_run = ui.run_particle_sources
    def delayed(*args, **kwargs):
        time.sleep(.1)
        return real_run(*args, **kwargs)
    monkeypatch.setattr(ui, "run_particle_sources", delayed)
    scene, applied = [], []
    panel = ParticleSourcesWindow(root, _report(), on_run=applied.append, scene_state=lambda: list(scene))
    _configure(panel)
    assert panel.start_run()
    root.after(10, lambda: scene.append("a manually added path"))
    _wait(root, panel)
    assert not applied and panel.last_run is None
    assert "3D particle paths changed" in panel.status.get()


def test_actual_vtk_point_pick_prefills_source_and_scheduled_markers(root, tmp_path):
    pytest.importorskip("vtk")
    from cleanroomx.cfd_multizone_vtk import open_multizone_vtk_window
    from test_cfd_multizone_vtk import _source
    viewer = open_multizone_vtk_window(root, _source(), [])
    root.update()
    renderer = viewer._cleanroomx_vtk_renderer
    renderer.SetWorldPoint(1.5, .5, .5, 1.)
    renderer.WorldToDisplay()
    x, y, _ = renderer.GetDisplayPoint()
    viewer._cleanroomx_source_mode_var.set(True)
    assert viewer._cleanroomx_seed_display_point(x, y)
    panel = viewer._cleanroomx_open_particle_sources()
    assert float(panel.vars["x"].get()) == 1.5
    _configure(panel)
    assert viewer._cleanroomx_source_marker_points.GetNumberOfPoints() == 1
    assert panel.start_run()
    _wait(root, panel)
    assert len(viewer._cleanroomx_particles) == 3
    assert viewer._cleanroomx_update_particle_markers() == []
    viewer._cleanroomx_playback_var.set(.25)
    assert len(viewer._cleanroomx_update_particle_markers()) == 1
    viewer._cleanroomx_playback_var.set(.5)
    assert len(viewer._cleanroomx_update_particle_markers()) == 2
    assert viewer._cleanroomx_particle_marker_points.GetNumberOfPoints() == 2
    assert not viewer._cleanroomx_seed_display_point(-100, -100)
    path = tmp_path/"vtk-sources.json"
    panel.save_configuration(path)
    assert json.loads(path.read_text())["sources"][0]["position_m"] == [1.5, .5, .5]
    viewer.destroy()
    # X11 must unregister the closed native interactor before a second opens.
    reopened = open_multizone_vtk_window(root, _source(), [])
    root.update()
    assert reopened._cleanroomx_vtk_render_window.GetNeverRendered() == 0
    reopened.destroy()
