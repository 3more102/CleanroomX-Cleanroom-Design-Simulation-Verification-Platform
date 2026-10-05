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
    root.update()
    try:
        yield application
        assert callback_errors == []
    finally:
        root.destroy()


def test_start_center_is_initial_workspace(app):
    assert app.notebook.select() == str(app.start_center)
    assert app.workspace_status_var.get() == "Workspace: Start"
    assert app.start_center.recent_tree.get_children() == ()


def test_loading_project_switches_to_design_and_updates_recent_projects(app):
    path = bundled_demo_project_path()

    app.load_project_path(path)
    app.root.update()

    assert app.notebook.select() == str(app.spatial_workspace)
    recent = app.start_center.recent_tree.get_children()
    assert len(recent) == 1
    values = app.start_center.recent_tree.item(recent[0], "values")
    assert values[0] == str(path.resolve(strict=False))


def test_start_center_can_be_reopened_without_mutating_project(app):
    path = bundled_demo_project_path()
    app.load_project_path(path)
    project_before = app.project.to_dict()

    app._activate_start_workspace()
    app.root.update()

    assert app.notebook.select() == str(app.start_center)
    assert app.workspace_status_var.get() == "Workspace: Start"
    assert app.project.to_dict() == project_before


def test_recent_project_list_is_deduplicated(app):
    path = bundled_demo_project_path()

    app._remember_recent_project(path)
    app._remember_recent_project(path)
    app.root.update()

    recent = app.start_center.recent_tree.get_children()
    assert len(recent) == 1


def test_start_center_recent_workspace_keeps_engineering_table_contract(app):
    tree = app.start_center.recent_tree

    assert tree.heading("#0", "text") == "Project"
    assert tree.heading("path", "text") == "Location"
    assert tree.heading("modified", "text") == "Modified"
    assert "No recent projects" in app.start_center.recent_hint.cget("text")
