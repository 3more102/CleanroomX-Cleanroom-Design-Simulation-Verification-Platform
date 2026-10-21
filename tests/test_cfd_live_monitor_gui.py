"""Actual Tk interaction; controlled workers/fixture logs are software tests only."""
from __future__ import annotations

import os
from pathlib import Path
import threading
import time
import tkinter as tk

import pytest

from cleanroomx import cfd_multizone_gui as gui
from test_cfd_live_monitor import _iteration


@pytest.fixture
def window():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.name == "nt" or os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    errors = []
    root.report_callback_exception = lambda *args: errors.append(args)
    view = gui.MultizoneCFDWindow(root)
    try:
        yield root, view
    finally:
        view.close()
        root.destroy()
        assert errors == []


def test_new_run_preview_is_responsive_and_cancelled_fields_stay_unimported(window, monkeypatch, tmp_path):
    root, view = window
    ready = threading.Event()
    def controlled_worker(directory, *, on_progress, cancel_event):
        on_progress({"stage": "simpleFoam", "event": "started", "log": str(tmp_path / "simpleFoam.log")})
        (tmp_path / "simpleFoam.log").write_bytes(_iteration(1) + _iteration(2))
        ready.set()
        assert cancel_event.wait(4)
        return {"status": "cancelled"}
    monkeypatch.setattr(gui, "verify_multizone_inputs", lambda path: (tmp_path, {}))
    monkeypatch.setattr(gui, "run_multizone_open_door_case", controlled_worker)
    view.run_button.invoke()
    assert ready.wait(1)
    root.update()
    view._poll()
    panel = view.live_solver
    assert view.tabs.select() == str(panel)
    assert panel.follower.monitor.total_samples == 10
    assert "UNVERIFIED" in panel.summary.get()
    assert panel.latest.item("p", "values")[1] == "2"
    assert panel.plot.model["selected_iteration"] is None
    assert not panel.plot.canvas.find_withtag("selected-iteration")
    assert not panel.plot.canvas.find_withtag("residual-limit")
    assert view.report is None
    view.cancel_native_button.invoke()
    deadline = time.monotonic() + 4
    while view.running and time.monotonic() < deadline:
        root.update()
        time.sleep(.01)
    assert not view.running
    assert "cancelled" in panel.phase.get()
    assert view.report is None
    assert panel.follower.monitor.total_samples == 10
    panel.plot.field.set("p")
    panel.plot.redraw()
    panel.plot._step_probe(1)
    assert "residual = 0.1" in panel.plot.detail.get()
    view._clear_results()
    assert panel.follower is None
    assert not panel.latest.get_children()
    assert panel.plot.report is None


def test_wsl_preview_uses_independent_log_offsets_and_drains_after_completion(window, monkeypatch, tmp_path):
    root, view = window
    case = tmp_path / "case"
    case.mkdir()
    monkeypatch.setattr(gui, "_windows_wsl_available", lambda: True)
    monkeypatch.setattr(gui, "verify_multizone_inputs", lambda path: (case, {}))
    def worker(function):
        view.running = True
    monkeypatch.setattr(view, "_worker", worker)
    view.run_wsl_case()
    log = case / "simpleFoam.log"
    log.write_bytes(b"".join(_iteration(i) for i in range(1, 501)))
    view._poll()
    panel = view.live_solver
    assert 0 < panel.follower.offset <= 128 * 1024
    view.events.put(("result", {"status": "wsl_solver_executed_requires_convergence_review"}))
    for _ in range(6):
        view._poll()
    assert not view.running
    assert panel.follower.offset == log.stat().st_size
    assert panel.follower.monitor.total_samples == 2500
    assert view.report is None
    assert "import computed fields" in panel.phase.get()
    # Raw-log WSL tailing must not replay numerical records into the preview.
    before = panel.follower.monitor.total_samples
    view._poll_wsl_logs()
    panel.poll()
    assert panel.follower.monitor.total_samples == before


def test_invalid_log_stops_only_preview_and_new_case_clears_it(window, tmp_path):
    root, view = window
    panel = view.live_solver
    panel.begin(tmp_path)
    log = tmp_path / "simpleFoam.log"
    log.write_bytes(_iteration(1))
    panel.poll()
    assert panel.latest.get_children()
    with log.open("ab") as stream:
        stream.write(b"Time = 2\nSolving for p, Initial residual = nan, Final residual = 0\n")
    panel.poll()
    assert "Preview stopped" in panel.summary.get()
    assert not panel.latest.get_children()
    assert panel.plot.report is None
    assert view.report is None
    other = tmp_path / "fresh"
    other.mkdir()
    panel.begin(other)
    (other / "simpleFoam.log").write_bytes(_iteration(5))
    panel.poll()
    assert panel.follower.monitor.error is None
    assert panel.follower.monitor.total_samples == 5
    assert panel.latest.item("p", "values")[1] == "5"


def test_minimum_window_keeps_live_plot_and_explanation_reachable_by_scrolling(window, tmp_path):
    root, view = window
    view.geometry("850x600")
    panel = view.live_solver
    panel.begin(tmp_path)
    (tmp_path / "simpleFoam.log").write_bytes(_iteration(1))
    panel.poll()
    view.tabs.select(panel)
    root.update()
    scroll = panel._cleanroomx_scroll_canvas
    before = scroll.yview()
    assert before[1] < 1
    panel.plot.canvas.event_generate("<Button-5>")
    root.update()
    assert scroll.yview()[0] > before[0]
    scroll.yview_moveto(1)
    root.update()
    assert scroll.yview()[1] == pytest.approx(1)
    assert panel.plot.points
