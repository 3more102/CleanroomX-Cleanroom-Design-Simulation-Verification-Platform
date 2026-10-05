from __future__ import annotations

import os
import tkinter as tk

import pytest

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path
from cleanroomx.spatial import _Hit


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


def _select_tree_item(app: CleanroomXApp, item_id: str) -> None:
    app.analysis_tree.selection_set(item_id)
    app.analysis_tree.focus(item_id)
    app.analysis_tree.event_generate("<<TreeviewSelect>>")
    app.root.update()


def test_navigator_recent_tracks_actionable_engineering_selections(app):
    rooms = app.spatial_workspace.layout["rooms"]
    assert len(rooms) >= 2

    first_id = f"room:{rooms[0]['id']}"
    second_id = f"room:{rooms[1]['id']}"
    _select_tree_item(app, first_id)
    _select_tree_item(app, second_id)

    values = tuple(app.navigator_recent_picker.cget("values"))
    assert len(values) >= 2
    assert app._navigator_recent_display_to_id[values[0]] == second_id
    assert app._navigator_recent_display_to_id[values[1]] == first_id

    app.clear_navigator_recent()
    assert tuple(app.navigator_recent_picker.cget("values")) == ()


def test_navigator_favorite_is_project_scoped_gui_state_and_updates_button(app):
    room = app.spatial_workspace.layout["rooms"][0]
    item_id = f"room:{room['id']}"
    _select_tree_item(app, item_id)

    assert app.toggle_selected_navigator_favorite()
    app.root.update()
    assert item_id in app._navigator_favorite_ids
    assert app.navigator_favorite_toggle_button.cget("text") == "★"

    state = app._capture_ui_layout_state()
    key = str(app.project_path)
    assert state["navigator_favorites"][key] == [item_id]

    assert app.toggle_selected_navigator_favorite()
    app.root.update()
    assert item_id not in app._navigator_favorite_ids
    assert app.navigator_favorite_toggle_button.cget("text") == "☆"


def test_favorite_picker_clears_filter_and_opens_spatial_object(app):
    room = app.spatial_workspace.layout["rooms"][0]
    item_id = f"room:{room['id']}"
    _select_tree_item(app, item_id)
    assert app.toggle_selected_navigator_favorite()
    app.root.update()

    display = tuple(app.navigator_favorites_picker.cget("values"))[0]
    app.navigator_filter_var.set("definitely-no-match")
    app.root.update()
    assert app.navigator_filter_var.get()

    app.navigator_favorites_var.set(display)
    app._on_favorite_navigator_selected()
    app.root.update()

    assert app.navigator_filter_var.get() == ""
    assert app.analysis_tree.selection() == (item_id,)
    assert app.spatial_workspace.selected == _Hit("room", room["id"])


def test_navigator_sections_that_do_not_open_are_not_favoritable(app):
    _select_tree_item(app, "nav-building")

    assert not app.toggle_selected_navigator_favorite()
    assert "nav-building" not in app._navigator_favorite_ids
    assert app.navigator_favorite_toggle_button.cget("state") == "disabled"
