from __future__ import annotations

import copy
import os
import tkinter as tk

import pytest

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path


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


def _select_first_room(app):
    room = next(
        item
        for item in app.spatial_workspace.layout["rooms"]
        if isinstance(item, dict) and item.get("id")
    )
    assert app.spatial_workspace.select_item("room", str(room["id"]))
    app.root.update()
    return room


def test_properties_inspector_search_filters_visible_fields(app):
    _select_first_room(app)
    workspace = app.spatial_workspace

    workspace._property_filter_var.set("pressure")
    app.root.update()

    visible = {
        key
        for key, row in workspace._property_rows.items()
        if row.winfo_manager()
    }
    assert visible == {"pressure_pa"}
    assert "1/" in workspace._property_filter_summary_var.get()

    workspace._property_filter_var.set("")
    app.root.update()
    assert "fields" in workspace._property_filter_summary_var.get()


def test_invalid_property_shows_inline_error_without_mutating_project(app):
    _select_first_room(app)
    workspace = app.spatial_workspace
    before = copy.deepcopy(app.project.to_dict())

    workspace._property_vars["pressure_pa"].set("not-a-number")
    workspace.apply_properties()
    app.root.update()

    assert workspace._property_validation_var.get().startswith("Not applied")
    assert app.project.to_dict() == before
