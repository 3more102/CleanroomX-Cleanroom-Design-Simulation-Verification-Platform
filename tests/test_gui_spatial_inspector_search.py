from __future__ import annotations

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


def test_spatial_inspector_search_filters_room_properties_by_label_key_and_unit(app):
    workspace = app.spatial_workspace
    room = workspace.layout["rooms"][0]
    workspace.select_item("room", room["id"])
    app.root.update()

    assert workspace._property_filter_var.get().endswith("properties")
    assert workspace._property_rows["pressure_pa"].winfo_manager() == "pack"
    assert workspace._property_rows["classification"].winfo_manager() == "pack"

    workspace._property_search_var.set("pressure pa")
    app.root.update()

    assert workspace._property_rows["pressure_pa"].winfo_manager() == "pack"
    assert workspace._property_rows["classification"].winfo_manager() == ""
    assert "1 of" in workspace._property_filter_var.get()
    assert "filtered" in workspace._property_filter_var.get()

    workspace.clear_property_filter()
    app.root.update()
    assert workspace._property_search_var.get() == ""
    assert workspace._property_rows["classification"].winfo_manager() == "pack"


def test_spatial_inspector_search_respects_contextual_device_fields(app):
    workspace = app.spatial_workspace
    device = workspace.layout["devices"][0]
    workspace.select_item("device", device["id"])
    app.root.update()

    workspace._property_search_var.set("room")
    app.root.update()

    assert workspace._property_rows["room_id"].winfo_manager() == "pack"
    assert workspace._property_rows["analysis_room_name"].winfo_manager() == ""
    assert workspace._property_rows["pressure_pa"].winfo_manager() == ""


def test_reset_edits_reloads_selected_object_without_mutating_layout(app):
    workspace = app.spatial_workspace
    room = workspace.layout["rooms"][0]
    workspace.select_item("room", room["id"])
    app.root.update()

    original_name = room["name"]
    layout_before = workspace.layout.copy()
    workspace._property_vars["name"].set("Draft name only")
    assert workspace._property_vars["name"].get() == "Draft name only"

    workspace._load_property_panel()
    app.root.update()

    assert workspace._property_vars["name"].get() == original_name
    assert workspace.layout == layout_before


def test_property_search_does_not_discard_unapplied_draft(app):
    workspace = app.spatial_workspace
    room = workspace.layout["rooms"][0]
    workspace.select_item("room", room["id"])
    app.root.update()

    workspace._property_vars["name"].set("Unapplied draft")
    workspace._property_search_var.set("pressure")
    app.root.update()

    assert workspace._property_vars["name"].get() == "Unapplied draft"
    assert workspace._property_rows["pressure_pa"].winfo_manager() == "pack"

    workspace.clear_property_filter()
    app.root.update()
    assert workspace._property_vars["name"].get() == "Unapplied draft"
