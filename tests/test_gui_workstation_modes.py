from __future__ import annotations

import copy
import os
import tkinter as tk
from tkinter import ttk

import pytest

from cleanroomx.gui import CleanroomXApp


@pytest.fixture
def app(tmp_path):
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    instance = CleanroomXApp(
        root,
        autosave_interval_seconds=0,
        ui_state_path=tmp_path / "gui-layout.json",
    )
    root.update_idletasks()
    root.update()
    try:
        yield instance
    finally:
        instance._autosave_manager.shutdown(wait=False)
        root.destroy()


def test_density_switch_is_view_only_and_changes_engineering_metrics(app):
    project_before = copy.deepcopy(app.project.to_dict())
    style = ttk.Style(app.root)

    app.set_density("compact", persist=False)
    app.root.update_idletasks()
    app.root.update()

    assert app.density_var.get() == "compact"
    assert int(style.lookup("Treeview", "rowheight")) == 20
    assert int(style.lookup("CX.Navigator.Treeview", "rowheight")) == 20
    assert app.project.to_dict() == project_before

    state = app._capture_ui_layout_state()
    assert state["density"] == "compact"

    app.set_density("comfortable", persist=False)
    app.root.update()
    assert int(style.lookup("Treeview", "rowheight")) == 24
    assert app.project.to_dict() == project_before


def test_workspace_presets_rearrange_existing_surfaces_without_model_mutation(app):
    project_before = copy.deepcopy(app.project.to_dict())

    app.activate_workspace_preset("design")
    app.root.update()
    assert app.notebook.select() == str(app.spatial_workspace)
    assert not app._paned_contains(app.workspace_panes, app.output_panel)
    assert app.spatial_workspace.inspector_visible()

    app.activate_workspace_preset("simulation")
    app.root.update()
    assert app.notebook.select() == str(app.plot_tab)
    assert app.output_notebook.select() == str(app.result_text.master)
    assert app._paned_contains(app.workspace_panes, app.output_panel)

    app.activate_workspace_preset("verification")
    app.root.update()
    assert app.output_notebook.select() == str(app.problems_panel)
    assert app.spatial_workspace.inspector_visible()

    app.activate_workspace_preset("evidence")
    app.root.update()
    assert app.notebook.select() == str(app.proofgraph_viewer)
    assert app.output_notebook.select() == str(app.evidence_text.master)

    app.activate_workspace_preset("reporting")
    app.root.update()
    assert app.notebook.select() == str(app.plot_tab)
    assert app.output_notebook.select() == str(app.report_text.master)

    assert app.workspace_status_var.get() == "Workspace: Reporting"
    assert app.project.to_dict() == project_before


def test_unknown_workspace_preset_fails_closed(app):
    with pytest.raises(ValueError, match="unknown workspace preset"):
        app.activate_workspace_preset("imaginary")
