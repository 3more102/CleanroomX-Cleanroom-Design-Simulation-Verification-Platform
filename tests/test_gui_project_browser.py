from __future__ import annotations

import copy
import os
import tkinter as tk
from tkinter import ttk

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


def _all_tree_ids(tree: ttk.Treeview, parent: str = "") -> list[str]:
    result: list[str] = []
    for iid in tree.get_children(parent):
        result.append(iid)
        result.extend(_all_tree_ids(tree, iid))
    return result


def test_project_browser_filter_does_not_reload_or_commit_unsaved_editor(app):
    before_project = copy.deepcopy(app.project.to_dict())
    app.input_text.insert("end", "\nUNSAVED_NAVIGATOR_SENTINEL")
    editor_before = app.input_text.get("1.0", "end-1c")

    app.navigator_filter_var.set("ProofGraph")
    app.root.update()

    assert app.input_text.get("1.0", "end-1c") == editor_before
    assert app.project.to_dict() == before_project
    assert app.analysis_tree.get_children() == ("nav-proofgraph",)

    app.navigator_filter_var.set("")
    app.root.update()

    restored = set(app.analysis_tree.get_children())
    assert "nav-building" in restored
    assert "nav-analyses" in restored
    assert "nav-proofgraph" in restored
    assert app.input_text.get("1.0", "end-1c") == editor_before


def test_project_browser_filter_survives_spatial_tree_refresh(app):
    app.navigator_filter_var.set("ProofGraph")
    app.root.update()

    app._refresh_spatial_navigator()
    app.root.update()

    assert app.analysis_tree.get_children() == ("nav-proofgraph",)

    app.navigator_filter_var.set("")
    app.root.update()
    ids = _all_tree_ids(app.analysis_tree)
    assert "nav-building" in ids
    assert any(iid.startswith("room:") for iid in ids)


def test_room_context_menu_delegates_existing_spatial_view_commands(app):
    app.navigator_filter_var.set("")
    app.root.update()
    room_id = next(
        iid for iid in _all_tree_ids(app.analysis_tree) if iid.startswith("room:")
    )

    menu = app._build_navigator_context_menu(room_id)
    assert menu is not None
    try:
        labels = [
            menu.entrycget(index, "label")
            for index in range(menu.index("end") + 1)
            if menu.type(index) != "separator"
        ]
    finally:
        menu.destroy()

    assert labels == [
        "Open / Properties",
        "Fit Selected",
        "Duplicate",
        "Delete",
        "Isolate",
        "Hide",
        "Show All",
    ]


def test_section_context_menu_keeps_expand_collapse_local_to_tree(app):
    project_before = copy.deepcopy(app.project.to_dict())

    menu = app._build_navigator_context_menu("nav-building")
    assert menu is not None
    try:
        labels = [
            menu.entrycget(index, "label")
            for index in range(menu.index("end") + 1)
        ]
    finally:
        menu.destroy()

    assert labels == ["Expand", "Collapse"]
    assert app.project.to_dict() == project_before



def test_project_browser_filter_opens_matching_ancestor_and_restores_open_state(app):
    app.navigator_filter_var.set("")
    app.root.update()

    room_id = next(
        iid for iid in _all_tree_ids(app.analysis_tree) if iid.startswith("room:")
    )
    room_name = app.analysis_tree.item(room_id, "text")
    app.analysis_tree.item("nav-building", open=False)

    app.navigator_filter_var.set(room_name)
    app.root.update()

    assert bool(app.analysis_tree.item("nav-building", "open"))
    assert "/" in app.navigator_filter_status_var.get()

    app.navigator_filter_var.set("")
    app.root.update()

    assert not bool(app.analysis_tree.item("nav-building", "open"))
    assert app.navigator_filter_status_var.get().endswith(" items")


def test_focus_navigator_filter_reveals_hidden_panel(app):
    app.hide_navigator_panel()
    app.root.update()
    assert not app.navigator_panel_visible_var.get()

    app.focus_navigator_filter()
    app.root.update()

    assert app.navigator_panel_visible_var.get()
    assert app._paned_contains(app.main_panes, app.navigator_panel)


def test_navigator_enter_opens_selected_analysis_input_workspace(app):
    analysis = app.project.analyses[0]
    app.analysis_tree.selection_set(analysis.id)
    app.analysis_tree.focus(analysis.id)
    app.root.update()

    assert app._activate_navigator_item() == "break"
    app.root.update()

    assert app.notebook.select() == str(app.input_tab)


def test_navigator_f2_delegates_analysis_rename(app, monkeypatch):
    analysis = app.project.analyses[0]
    app.analysis_tree.selection_set(analysis.id)
    app.analysis_tree.focus(analysis.id)
    invoked = []
    monkeypatch.setattr(app, "rename_analysis", lambda: invoked.append(analysis.id))

    assert app._navigator_rename_selected() == "break"

    assert invoked == [analysis.id]


def test_analysis_context_menu_exposes_direct_management_actions(app):
    analysis = app.project.analyses[0]
    menu = app._build_navigator_context_menu(analysis.id)
    assert menu is not None
    try:
        labels = [
            menu.entrycget(index, "label")
            for index in range(menu.index("end") + 1)
            if menu.type(index) != "separator"
        ]
    finally:
        menu.destroy()

    assert labels == [
        "Open Analysis Input",
        "Rename Analysis",
        "Run Analysis",
        "Remove Analysis",
    ]


def test_navigator_delete_spatial_item_delegates_existing_workspace_delete(
    app,
    monkeypatch,
):
    room_id = next(
        iid for iid in _all_tree_ids(app.analysis_tree) if iid.startswith("room:")
    )
    deleted = []
    monkeypatch.setattr(
        "cleanroomx.gui.messagebox.askyesno",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        app.spatial_workspace,
        "delete_selected",
        lambda: deleted.append(app.spatial_workspace.selected.item_id),
    )

    app._delete_navigator_item(room_id)

    assert deleted == [room_id.split(":", 1)[1]]
