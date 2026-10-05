from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk

import pytest

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path
from cleanroomx.gui_workspace import workspace_profile_keys, workspace_profile_spec


def test_workspace_profiles_cover_first_class_engineering_workflows():
    assert workspace_profile_keys() == (
        "design",
        "simulation",
        "verification",
        "evidence",
        "reporting",
    )
    assert workspace_profile_spec("design").primary_view == "design"
    assert workspace_profile_spec("simulation").primary_view == "simulation"
    assert workspace_profile_spec("verification").primary_view == "verification"
    assert workspace_profile_spec("evidence").primary_view == "evidence"
    assert workspace_profile_spec("reporting").primary_view == "reporting"
    assert workspace_profile_spec("not-a-workspace").key == "design"


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


def test_density_mode_is_real_style_state_and_is_captured(app):
    style = ttk.Style(app.root)

    app.set_density("compact", persist=False)
    app.root.update_idletasks()
    compact_height = int(style.lookup("Treeview", "rowheight"))

    app.set_density("comfortable", persist=False)
    app.root.update_idletasks()
    comfortable_height = int(style.lookup("Treeview", "rowheight"))

    assert app.density_var.get() == "comfortable"
    assert comfortable_height > compact_height
    assert app._capture_ui_layout_state()["density"] == "comfortable"


def test_workspace_profiles_route_first_class_views_and_panel_visibility(app):
    app.apply_workspace_profile("verification", persist=False)
    app.root.update_idletasks()
    assert app.notebook.select() == str(app.verification_workspace)
    assert app.navigator_panel_visible_var.get() is True
    assert app.output_panel_visible_var.get() is True
    assert app.spatial_workspace.inspector_visible() is False
    assert app.output_notebook.select() == str(app.problems_panel)

    app.apply_workspace_profile("evidence", persist=False)
    app.root.update_idletasks()
    assert app.notebook.select() == str(app.evidence_workspace)
    assert app.workspace_profile_var.get() == "evidence"

    app.apply_workspace_profile("reporting", persist=False)
    app.root.update_idletasks()
    assert app.notebook.select() == str(app.reporting_workspace)
    assert app.navigator_panel_visible_var.get() is False
    assert app.output_panel_visible_var.get() is True
    assert app._capture_ui_layout_state()["workspace_profile"] == "reporting"


def test_named_workspace_layouts_round_trip_panel_state(app):
    app.apply_workspace_profile("verification", persist=False)
    app.navigator_panel_visible_var.set(True)
    app.output_panel_visible_var.set(True)
    app._sync_navigator_panel_visibility()
    app._sync_output_panel_visibility()
    app.spatial_workspace.set_inspector_visible(False)
    app.root.update_idletasks()

    assert app.save_named_layout("Review") is True
    assert "Review" in app._ui_layout_state["saved_layouts"]
    assert app.save_named_layout(" review ") is False

    app.apply_workspace_profile("design", persist=False)
    app.navigator_panel_visible_var.set(False)
    app.output_panel_visible_var.set(False)
    app._sync_navigator_panel_visibility()
    app._sync_output_panel_visibility()
    app.spatial_workspace.set_inspector_visible(True)
    app.root.update_idletasks()

    assert app.apply_saved_layout("Review") is True
    app.root.update_idletasks()
    assert app.workspace_profile_var.get() == "verification"
    assert app.navigator_panel_visible_var.get() is True
    assert app.output_panel_visible_var.get() is True
    assert app.spatial_workspace.inspector_visible() is False

    assert app.delete_saved_layout("Review") is True
    assert "Review" not in app._ui_layout_state["saved_layouts"]
    assert app.apply_saved_layout("Review") is False


def test_reset_panel_layout_preserves_named_layouts(app):
    assert app.save_named_layout("Keep") is True
    app.apply_workspace_profile("reporting", persist=False)
    app.navigator_panel_visible_var.set(False)
    app.output_panel_visible_var.set(False)
    app._sync_navigator_panel_visibility()
    app._sync_output_panel_visibility()

    app.reset_panel_layout()
    app.root.update_idletasks()
    app.root.update()

    assert "Keep" in app._ui_layout_state["saved_layouts"]
    assert app.workspace_profile_var.get() == "design"
    assert app.navigator_panel_visible_var.get() is True
    assert app.output_panel_visible_var.get() is True
    assert app.spatial_workspace.inspector_visible() is True


def test_fullscreen_workspace_is_explicit_reversible_window_state(app):
    app.set_fullscreen_workspace(True)
    app.root.update_idletasks()

    assert app.fullscreen_var.get() is True
    assert bool(app.root.attributes("-fullscreen")) is True
    assert "Full-screen workspace enabled" in app.status_var.get()

    app.exit_fullscreen_workspace()
    app.root.update_idletasks()

    assert app.fullscreen_var.get() is False
    assert bool(app.root.attributes("-fullscreen")) is False
