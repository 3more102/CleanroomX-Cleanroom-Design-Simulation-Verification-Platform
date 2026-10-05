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


def test_start_center_uses_live_autosave_status_and_exposes_recovery_workflow(app):
    assert app.start_center.autosave_status_var is app.autosave_status_var
    assert app.start_center.autosave_status_var.get() == "Autosave: disabled"
    assert str(app.start_center.recovery_button.cget("state")) == "normal"

    app.autosave_status_var.set("Autosave: clean")
    app.root.update_idletasks()

    assert app.start_center.autosave_status_var.get() == "Autosave: clean"


def test_loading_project_switches_to_design_and_updates_recent_projects(app):
    path = bundled_demo_project_path()

    app.load_project_path(path)
    app.root.update()

    assert app.notebook.select() == str(app.spatial_workspace)
    recent = app.start_center.recent_tree.get_children()
    assert len(recent) == 1



def test_start_center_recent_search_and_remove_only_updates_recent_state(app, tmp_path):
    alpha = tmp_path / "Alpha.cleanroomx.json"
    beta = tmp_path / "Beta.cleanroomx.json"
    alpha.write_text("{}\n", encoding="utf-8")
    beta.write_text("{}\n", encoding="utf-8")

    app._remember_recent_project(alpha)
    app._remember_recent_project(beta)
    app.root.update()

    assert app.start_center.recent_count_var.get() == "2 of 2 recent projects"

    app.start_center.recent_search_var.set("alpha")
    app.root.update()
    visible = app.start_center.recent_tree.get_children()
    assert len(visible) == 1
    assert app.start_center._recent_paths[visible[0]] == str(alpha.resolve(strict=False))

    app.start_center.recent_tree.selection_set(visible[0])
    app.start_center.recent_tree.focus(visible[0])
    app.start_center._forget_selected_recent()
    app.root.update()

    assert alpha.is_file()
    assert beta.is_file()
    assert alpha.resolve(strict=False) not in app._recent_project_paths
    assert beta.resolve(strict=False) in app._recent_project_paths
    assert app.start_center.recent_count_var.get() == "0 of 1 recent projects"
    assert "match the search" in app.start_center.recent_hint.cget("text").lower()

    app.start_center.recent_search_var.set("")
    app.root.update()
    remaining = app.start_center.recent_tree.get_children()
    assert len(remaining) == 1
    values = app.start_center.recent_tree.item(remaining[0], "values")
    assert values[0] == str(beta.resolve(strict=False))


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
