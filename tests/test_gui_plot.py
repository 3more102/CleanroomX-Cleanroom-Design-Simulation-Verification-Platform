from __future__ import annotations

import csv
import io
import os
from types import SimpleNamespace
import tkinter as tk

import pytest

from cleanroomx.gui import CleanroomXApp


def _plot() -> dict:
    return {
        "title": "Fan curve",
        "x_label": "Airflow (m³/h)",
        "y_label": "Pressure (Pa)",
        "series": [
            {
                "name": "Fan curve",
                "x": [100.0, 200.0, 300.0],
                "y": [90.0, 70.0, 40.0],
            },
            {
                "name": "System curve",
                "x": [100.0, 200.0, 300.0],
                "y": [20.0, 55.0, 95.0],
            },
        ],
        "markers": [
            {
                "name": "Operating point",
                "x": 215.0,
                "y": 62.0,
            }
        ],
    }


def test_plot_csv_content_preserves_series_and_marker_values():
    text = CleanroomXApp._plot_csv_content(_plot())
    rows = list(csv.reader(io.StringIO(text)))

    assert rows[0] == ["kind", "name", "index", "x", "y"]
    assert rows[1] == ["series", "Fan curve", "1", "100.0", "90.0"]
    assert ["series", "System curve", "3", "300.0", "95.0"] in rows
    assert rows[-1] == [
        "marker",
        "Operating point",
        "1",
        "215.0",
        "62.0",
    ]


@pytest.fixture
def app(tmp_path):
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    application = CleanroomXApp(
        root,
        autosave_interval_seconds=0,
        ui_state_path=tmp_path / "gui-layout.json",
    )
    root.geometry("1200x800")
    application.notebook.select(application.plot_tab)
    root.update()
    try:
        yield application
    finally:
        root.destroy()


def test_plot_hover_uses_rendered_backend_values_without_model_changes(app):
    plot = _plot()
    app.last_run = SimpleNamespace(plot=plot)
    app._draw_plot()
    app.root.update()

    assert len(app._plot_hit_points) == 7
    point = app._plot_hit_points[0]
    event = SimpleNamespace(x=round(point["px"]), y=round(point["py"]))
    app._on_plot_motion(event)
    app.root.update()

    assert "Fan curve" in app.plot_cursor_var.get()
    assert "x=100" in app.plot_cursor_var.get()
    assert "y=90" in app.plot_cursor_var.get()
    assert app.plot_canvas.find_withtag("plot_hover")

    app._clear_plot_hover()
    assert app.plot_cursor_var.get() == "Cursor: —"
    assert not app.plot_canvas.find_withtag("plot_hover")
    assert plot == _plot()
