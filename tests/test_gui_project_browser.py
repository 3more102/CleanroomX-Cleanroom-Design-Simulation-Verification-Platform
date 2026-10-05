from __future__ import annotations

import copy
import os
import tkinter as tk
from tkinter import ttk

import pytest

from cleanroomx.gui import (
    CleanroomXApp,
    bundled_demo_project_path,
    spatial_navigator_issue_counts,
)
from cleanroomx.spatial import SPATIAL_METADATA_KEY, empty_layout, validate_layout


@pytest.fixture
def app(tmp_path):
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    callback_errors = []
    root.report_callback_exception = lambda *args: callback_errors.append(args)
    application = CleanroomXApp(
        root,
        autosave_interval_seconds=0,
        ui_state_path=tmp_path / "gui-layout.json",
    )
    application.load_project_path(bundled_demo_project_path())
    root.update()
    try:
        yield application
        assert callback_errors == []
    finally:
        root.destroy()


def _all_tree_ids(tree: ttk.Treeview, parent: str = "") -> list[str]:
    result: list[str] = []
    for iid in tree.get_children(parent):
        result.append(iid)
        result.extend(_all_tree_ids(tree, iid))
    return result


def test_project_browser_filter_does_not_reload_or_commit_unsaved_editor(app):
    before_project = copy.deepcopy(app.project.to_dict())
    app.input_text.insert("end", "\nUNSAVED_NAVIGATOR_SENTINEL")
    editor_before = app.input_text.get("1.0", "end-1c")

    app.navigator_filter_var.set("ProofGraph")
    app.root.update()

    assert app.input_text.get("1.0", "end-1c") == editor_before
    assert app.project.to_dict() == before_project
    assert app.analysis_tree.get_children() == ("nav-proofgraph",)

    app.navigator_filter_var.set("")
    app.root.update()

    restored = set(app.analysis_tree.get_children())
    assert "nav-building" in restored
    assert "nav-analyses" in restored
    assert "nav-proofgraph" in restored
    assert app.input_text.get("1.0", "end-1c") == editor_before


def test_project_browser_filter_survives_spatial_tree_refresh(app):
    app.navigator_filter_var.set("ProofGraph")
    app.root.update()

    app._refresh_spatial_navigator()
    app.root.update()

    assert app.analysis_tree.get_children() == ("nav-proofgraph",)

    app.navigator_filter_var.set("")
    app.root.update()
    ids = _all_tree_ids(app.analysis_tree)
    assert "nav-building" in ids
    assert any(iid.startswith("room:") for iid in ids)


def test_room_context_menu_delegates_existing_spatial_view_commands(app):
    app.navigator_filter_var.set("")
    app.root.update()
    room_id = next(
        iid for iid in _all_tree_ids(app.analysis_tree) if iid.startswith("room:")
    )

    menu = app._build_navigator_context_menu(room_id)
    assert menu is not None
    try:
        labels = [
            menu.entrycget(index, "label")
            for index in range(menu.index("end") + 1)
            if menu.type(index) != "separator"
        ]
    finally:
        menu.destroy()

    assert labels == [
        "Open / Properties",
        "Fit Selected",
        "Isolate",
        "Hide",
        "Show All",
    ]


def test_section_context_menu_keeps_expand_collapse_local_to_tree(app):
    project_before = copy.deepcopy(app.project.to_dict())

    menu = app._build_navigator_context_menu("nav-building")
    assert menu is not None
    try:
        labels = [
            menu.entrycget(index, "label")
            for index in range(menu.index("end") + 1)
        ]
    finally:
        menu.destroy()

    assert labels == ["Expand", "Collapse"]
    assert app.project.to_dict() == project_before


def test_spatial_navigator_issue_counts_use_canonical_item_references():
    layout = empty_layout()
    layout["rooms"] = [
        {
            "id": "room-a",
            "name": "Process",
            "x_m": 0.0,
            "y_m": 0.0,
            "length_m": 4.0,
            "width_m": 4.0,
            "height_m": 3.0,
            "floor_elevation_m": 0.0,
        },
        {
            "id": "room-b",
            "name": "Process",
            "x_m": 2.0,
            "y_m": 2.0,
            "length_m": 4.0,
            "width_m": 4.0,
            "height_m": 3.0,
            "floor_elevation_m": 0.0,
        },
    ]
    layout["devices"] = [
        {
            "id": "sensor-a",
            "name": "Monitor",
            "type": "sensor",
            "room_id": None,
            "x_m": 1.0,
            "y_m": 1.0,
            "z_m": 1.0,
        }
    ]

    issues = validate_layout(layout)
    counts = spatial_navigator_issue_counts(issues)

    assert counts["room-a"] >= 2
    assert counts["room-b"] >= 2
    assert counts["sensor-a"] == 1


def test_project_browser_marks_spatial_items_with_validation_badges(app):
    layout = app.project.metadata.get(SPATIAL_METADATA_KEY)
    assert isinstance(layout, dict)
    devices = layout.get("devices")
    if not isinstance(devices, list) or not devices:
        pytest.skip("bundled demo has no device to exercise navigator warning badge")

    device = devices[0]
    device["room_id"] = None
    app._refresh_spatial_navigator()
    app.root.update()

    iid = f"device:{device['id']}"
    item = app.analysis_tree.item(iid)
    assert "⚠" in item["text"]
    assert "spatial_warning" in item["tags"]
