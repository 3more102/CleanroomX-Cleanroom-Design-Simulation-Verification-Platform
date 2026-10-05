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


def test_workspace_presets_coordinate_panels_and_primary_views(app):
    app._activate_design_workspace()
    app.root.update()
    assert app.navigator_panel_visible_var.get() is True
    assert app.output_panel_visible_var.get() is False
    assert app.spatial_workspace.inspector_visible() is True
    assert app.notebook.select() == str(app.spatial_workspace)
    assert app.workspace_status_var.get() == "Workspace: Design"

    app._activate_verification_workspace()
    app.root.update()
    assert app.navigator_panel_visible_var.get() is True
    assert app.output_panel_visible_var.get() is True
    assert app.spatial_workspace.inspector_visible() is False
    assert app.notebook.select() == str(app.spatial_workspace)
    assert app.output_notebook.select() == str(app.problems_panel)
    assert app.workspace_status_var.get() == "Workspace: Verification"

    app._activate_evidence_workspace()
    app.root.update()
    assert app.notebook.select() == str(app.proofgraph_viewer)
    assert app.output_notebook.select() == str(app.evidence_text.master)
    assert app.workspace_status_var.get() == "Workspace: Evidence"

    app._activate_reporting_workspace()
    app.root.update()
    assert app.navigator_panel_visible_var.get() is False
    assert app.output_panel_visible_var.get() is True
    assert app.notebook.select() == str(app.reporting_workspace)
    assert app.output_notebook.select() == str(app.report_text.master)
    assert app.workspace_status_var.get() == "Workspace: Reporting"


def test_simulation_workspace_uses_inputs_until_results_exist(app):
    app.last_run = None
    app._activate_simulation_workspace()
    app.root.update()

    assert app.navigator_panel_visible_var.get() is True
    assert app.output_panel_visible_var.get() is True
    assert app.notebook.select() == str(app.input_tab)
    assert app.workspace_status_var.get() == "Workspace: Simulation"


def test_density_switch_updates_state_without_touching_project(app):
    before = app.project.to_dict()

    app.set_density("compact", persist=False)
    assert app.density_var.get() == "compact"
    assert app._ui_layout_state["density"] == "compact"
    assert app.project.to_dict() == before

    app.toggle_density()
    assert app.density_var.get() == "comfortable"
    assert app._ui_layout_state["density"] == "comfortable"
    assert app.project.to_dict() == before
