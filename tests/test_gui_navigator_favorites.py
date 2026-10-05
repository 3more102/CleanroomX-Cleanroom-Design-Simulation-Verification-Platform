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


def test_navigator_simulation_section_opens_workspace_and_is_recent(app):
    assert app._navigator_item_is_actionable("nav-simulation")

    _select_tree_item(app, "nav-simulation")

    assert app.workspace_profile_var.get() == "simulation"
    assert app.notebook.select() == str(app.simulation_workspace)
    assert app.selection_status_var.get() == "Selected: Simulation / Results"
    assert "nav-simulation" in app._navigator_recent_ids


def test_navigator_requirements_section_routes_to_existing_traceability_dialog(app, monkeypatch):
    calls = []
    monkeypatch.setattr(
        app,
        "show_requirements_traceability",
        lambda: calls.append("requirements") or True,
    )
    assert app._navigator_item_is_actionable("nav-requirements")

    _select_tree_item(app, "nav-requirements")

    assert calls == ["requirements"]
    assert app.selection_status_var.get() == "Selected: Requirements"
    assert "nav-requirements" in app._navigator_recent_ids


def test_navigator_workspace_context_menus_do_not_navigate_until_invoked(app, monkeypatch):
    app.activate_workspace_profile("design")
    app.root.update()
    requirements_calls = []
    monkeypatch.setattr(
        app,
        "show_requirements_traceability",
        lambda: requirements_calls.append("requirements") or True,
    )

    simulation_menu = app._build_navigator_context_menu("nav-simulation")
    assert simulation_menu is not None
    simulation_labels = [
        simulation_menu.entrycget(index, "label")
        for index in range(simulation_menu.index("end") + 1)
        if simulation_menu.type(index) != "separator"
    ]
    assert "Open Simulation Workspace" in simulation_labels
    assert app.workspace_profile_var.get() == "design"

    requirements_menu = app._build_navigator_context_menu("nav-requirements")
    assert requirements_menu is not None
    requirement_labels = [
        requirements_menu.entrycget(index, "label")
        for index in range(requirements_menu.index("end") + 1)
        if requirements_menu.type(index) != "separator"
    ]
    assert "Open Requirements Traceability..." in requirement_labels
    assert requirements_calls == []
