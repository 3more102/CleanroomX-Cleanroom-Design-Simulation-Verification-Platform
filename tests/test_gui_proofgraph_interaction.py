from __future__ import annotations

import os
import tkinter as tk

import pytest

from cleanroomx.gui_proofgraph import ProofGraphViewer
from cleanroomx.gui_theme import theme_palette


@pytest.fixture
def viewer():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    root.geometry("1000x700")
    messages = []
    widget = ProofGraphViewer(root, status_setter=messages.append)
    widget.pack(fill="both", expand=True)
    root.update()
    try:
        yield widget, messages
    finally:
        root.destroy()


def test_proofgraph_zoom_is_bounded_and_resettable(viewer):
    widget, messages = viewer

    assert widget._graph_zoom == pytest.approx(1.0)
    widget._zoom_by(1.15)
    assert widget._graph_zoom == pytest.approx(1.15)
    assert messages[-1].startswith("ProofGraph zoom:")

    for _ in range(20):
        widget._zoom_by(2.0)
    assert widget._graph_zoom == pytest.approx(2.5)

    for _ in range(30):
        widget._zoom_by(0.1)
    assert widget._graph_zoom == pytest.approx(0.55)

    widget._reset_zoom()
    assert widget._graph_zoom == pytest.approx(1.0)


def test_proofgraph_theme_updates_canvas_and_detail(viewer):
    widget, _messages = viewer
    palette = theme_palette("dark")

    widget.apply_theme(palette)

    assert widget.canvas.cget("background") == palette["plot"]
    assert widget.detail.cget("background") == palette["field"]
    assert widget.detail.cget("foreground") == palette["field_text"]


def test_proofgraph_expand_and_collapse_controls_tree_groups(viewer):
    widget, _messages = viewer
    widget.tree.insert("", "end", iid="group:test", text="Test", open=True)

    widget._set_tree_open(False)
    assert bool(widget.tree.item("group:test", "open")) is False

    widget._set_tree_open(True)
    assert bool(widget.tree.item("group:test", "open")) is True
