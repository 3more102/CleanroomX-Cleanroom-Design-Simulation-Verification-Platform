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


def test_spatial_inspector_live_validation_blocks_invalid_draft_without_mutation(app):
    workspace = app.spatial_workspace
    room = workspace.layout["rooms"][0]
    workspace.select_item("room", room["id"])
    app.root.update()

    before = copy.deepcopy(workspace.layout)
    assert workspace._property_apply_button.instate(["disabled"])
    assert workspace._property_reset_button.instate(["disabled"])
    assert workspace._property_draft_var.get() == "Draft: matches stored values"

    workspace._property_vars["length_m"].set("")
    app.root.update()

    assert workspace._property_draft_var.get().startswith("Draft: INVALID")
    assert "Length (m)" in workspace._property_draft_var.get()
    assert workspace._property_apply_button.instate(["disabled"])
    assert not workspace._property_reset_button.instate(["disabled"])
    assert workspace.layout == before


def test_spatial_inspector_valid_draft_enables_apply_and_returns_clean(app):
    workspace = app.spatial_workspace
    room = workspace.layout["rooms"][0]
    workspace.select_item("room", room["id"])
    app.root.update()

    revised_name = room["name"] + " revised"
    workspace._property_vars["name"].set(revised_name)
    app.root.update()

    assert workspace._property_draft_var.get() == "Draft: valid · unapplied changes"
    assert not workspace._property_apply_button.instate(["disabled"])
    assert not workspace._property_reset_button.instate(["disabled"])

    workspace.apply_properties()
    app.root.update()

    selected = workspace._selected_object()
    assert selected is not None
    assert selected["name"] == revised_name
    assert workspace._property_apply_button.instate(["disabled"])
    assert workspace._property_reset_button.instate(["disabled"])
    assert workspace._property_draft_var.get() == "Draft: matches stored values"


def test_spatial_inspector_semantically_equal_numeric_text_is_not_dirty(app):
    workspace = app.spatial_workspace
    room = workspace.layout["rooms"][0]
    workspace.select_item("room", room["id"])
    app.root.update()

    workspace._property_vars["length_m"].set(f"{float(room['length_m']):.3f}")
    app.root.update()

    assert workspace._property_draft_var.get() == "Draft: matches stored values"
    assert workspace._property_apply_button.instate(["disabled"])
    assert workspace._property_reset_button.instate(["disabled"])


def test_reset_property_edits_clears_invalid_draft(app):
    workspace = app.spatial_workspace
    room = workspace.layout["rooms"][0]
    workspace.select_item("room", room["id"])
    app.root.update()

    stored_width = str(room["width_m"])
    workspace._property_vars["width_m"].set("-1")
    app.root.update()
    assert workspace._property_draft_error is not None

    workspace.reset_property_edits()
    app.root.update()

    assert workspace._property_vars["width_m"].get() == stored_width
    assert workspace._property_draft_error is None
    assert workspace._property_draft_var.get() == "Draft: matches stored values"
    assert workspace._property_apply_button.instate(["disabled"])
    assert workspace._property_reset_button.instate(["disabled"])
