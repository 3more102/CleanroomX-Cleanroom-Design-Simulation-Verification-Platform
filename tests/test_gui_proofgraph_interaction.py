from __future__ import annotations

import os
from types import SimpleNamespace
import tkinter as tk

import pytest

from cleanroomx.gui_proofgraph import (
    _GRAPH_ZOOM_MAX,
    _GRAPH_ZOOM_MIN,
    ProofGraphViewer,
)
from cleanroomx.proofgraph_models import ProofGraph, Requirement, RequirementSet


def _minimal_graph() -> dict:
    requirement = Requirement(
        id="REQ-ZOOM",
        title="Zoom interaction requirement",
        source="GUI interaction regression",
    )
    requirement_set = RequirementSet(
        id="REQSET-ZOOM",
        version="1",
        title="Interaction requirements",
        source="GUI interaction regression",
        requirements=(requirement,),
    )
    return ProofGraph(
        id="GRAPH-ZOOM",
        requirement_set=requirement_set,
    ).to_dict()


@pytest.fixture
def viewer():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    root.geometry("900x620")
    widget = ProofGraphViewer(root)
    widget.pack(fill="both", expand=True)
    widget.set_documents([_minimal_graph()])
    root.update()
    try:
        yield root, widget
    finally:
        root.destroy()


def test_proofgraph_zoom_is_bounded_and_keyboard_mouse_controls_are_wired(viewer):
    root, widget = viewer

    widget._set_zoom(99.0, announce=False)
    root.update()
    assert widget._graph_scale == _GRAPH_ZOOM_MAX
    assert widget.zoom_var.get() == f"{round(_GRAPH_ZOOM_MAX * 100):d}%"

    widget._set_zoom(0.01, announce=False)
    root.update()
    assert widget._graph_scale == _GRAPH_ZOOM_MIN

    before = widget._graph_scale
    widget._wheel_zoom(SimpleNamespace(delta=120, num=0))
    root.update()
    assert widget._graph_scale > before

    assert widget.canvas.bind("<ButtonPress-2>")
    assert widget.canvas.bind("<B2-Motion>")
    assert widget.canvas.bind("<Control-MouseWheel>")


def test_proofgraph_fit_and_programmatic_focus_preserve_canonical_node(viewer):
    root, widget = viewer

    widget._set_zoom(1.8, announce=False)
    widget._fit_graph()
    root.update()

    assert _GRAPH_ZOOM_MIN <= widget._graph_scale <= _GRAPH_ZOOM_MAX
    assert widget.zoom_var.get().endswith("%")
    assert widget.focus_node("requirement:REQ-ZOOM")
    root.update()
    assert widget.selected_node()["id"] == "REQ-ZOOM"
    assert not widget.focus_node("requirement:missing")
