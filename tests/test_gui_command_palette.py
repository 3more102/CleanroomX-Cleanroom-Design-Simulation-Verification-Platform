from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk

import pytest

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path
from cleanroomx.gui_command_palette import (
    CommandPalette,
    PaletteCommand,
    filter_commands,
)


def test_filter_commands_matches_label_category_shortcut_and_keywords():
    noop = lambda: None
    commands = [
        PaletteCommand(
            "proof",
            "Open ProofGraph Explorer",
            "Evidence",
            noop,
            keywords=("provenance", "traceability"),
        ),
        PaletteCommand(
            "run",
            "Run Current Analysis",
            "Analysis",
            noop,
            shortcut="F5",
            keywords=("solver",),
        ),
    ]

    assert [item.id for item in filter_commands(commands, "proof")] == ["proof"]
    assert [item.id for item in filter_commands(commands, "evidence provenance")] == [
        "proof"
    ]
    assert [item.id for item in filter_commands(commands, "F5 solver")] == ["run"]
    assert filter_commands(commands, "missing") == []
    assert filter_commands(commands, "") == commands


@pytest.fixture
def root():
    try:
        window = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    window.withdraw()
    try:
        yield window
    finally:
        window.destroy()


def test_command_palette_filters_and_dispatches_existing_callback(root):
    invoked: list[str] = []
    palette = CommandPalette(
        root,
        commands=[
            PaletteCommand(
                "proof",
                "Open ProofGraph Explorer",
                "Evidence",
                lambda: invoked.append("proof"),
                keywords=("provenance",),
            ),
            PaletteCommand(
                "run",
                "Run Current Analysis",
                "Analysis",
                lambda: invoked.append("run"),
                shortcut="F5",
            ),
        ],
    )
    root.update()

    palette._query_var.set("proof")
    root.update()
    children = palette.tree.get_children()
    assert len(children) == 1
    assert palette.tree.item(children[0], "text") == "Open ProofGraph Explorer"

    palette.tree.selection_set(children[0])
    palette._invoke_selected()
    root.update()

    assert invoked == ["proof"]
    assert not palette.winfo_exists()


def test_application_command_catalog_uses_existing_workflows_without_duplicates(root, tmp_path):
    app = CleanroomXApp(
        root,
        autosave_interval_seconds=0,
        ui_state_path=tmp_path / "gui-layout.json",
    )

    commands = app._command_palette_commands()
    ids = [command.id for command in commands]
    labels = {command.label for command in commands}

    assert len(ids) == len(set(ids))
    assert "Open 2D Workspace" in labels
    assert "Open 3D Workspace" in labels
    assert "Open ProofGraph Explorer" in labels
    assert "Verify Project Requirements" in labels
    assert "Import IFC Spatial Layout" in labels

    app.show_command_palette()
    root.update()
    assert app._command_palette_window is not None
    assert app._command_palette_window.winfo_exists()
    app._command_palette_window._close()


def test_command_palette_blends_dynamic_engineering_results(root):
    invoked: list[str] = []

    def provider(query: str):
        if "room" not in query.casefold():
            return []
        return [
            PaletteCommand(
                "entity.room.clean",
                "Room · Clean Area",
                "Engineering Object",
                lambda: invoked.append("room"),
                keywords=("clean", "room"),
            )
        ]

    palette = CommandPalette(
        root,
        commands=[
            PaletteCommand(
                "run",
                "Run Current Analysis",
                "Analysis",
                lambda: invoked.append("run"),
                shortcut="F5",
            )
        ],
        search_provider=provider,
    )
    root.update()

    palette._query_var.set("room")
    root.update()
    children = palette.tree.get_children()
    assert len(children) == 1
    assert palette.tree.item(children[0], "text") == "Room · Clean Area"
    assert palette.tree.set(children[0], "category") == "Engineering Object"

    palette.tree.selection_set(children[0])
    palette._invoke_selected()
    root.update()

    assert invoked == ["room"]


def test_global_engineering_search_finds_and_opens_real_project_entities(root, tmp_path):
    app = CleanroomXApp(
        root,
        autosave_interval_seconds=0,
        ui_state_path=tmp_path / "gui-layout.json",
    )
    app.load_project_path(bundled_demo_project_path())
    root.update()

    room = app.spatial_workspace.layout["rooms"][0]
    room_commands = app._global_engineering_search_commands(str(room["name"]))
    room_command = next(
        command
        for command in room_commands
        if command.id == f"entity.room.{room['id']}"
    )
    assert room_command.category == "Engineering Object"
    assert room_command.callback()
    root.update()
    assert app.spatial_workspace.selected is not None
    assert app.spatial_workspace.selected.kind == "room"
    assert app.spatial_workspace.selected.item_id == room["id"]

    analysis = app.project.analyses[0]
    analysis_commands = app._global_engineering_search_commands(analysis.id)
    analysis_command = next(
        command
        for command in analysis_commands
        if command.id == f"entity.analysis.{analysis.id}"
    )
    assert analysis_command.callback()
    root.update()
    assert app.project.active_analysis_id == analysis.id
    assert app.notebook.select() == str(app.input_tab)


def test_application_density_switch_updates_ttk_metrics_without_project_mutation(root, tmp_path):
    app = CleanroomXApp(
        root,
        autosave_interval_seconds=0,
        ui_state_path=tmp_path / "gui-layout.json",
    )
    before = app.project.to_dict()
    style = ttk.Style(root)

    app.set_density("compact", persist=False)
    root.update()
    assert app.density_var.get() == "compact"
    assert int(style.lookup("Treeview", "rowheight")) == 20

    app.set_density("comfortable", persist=False)
    root.update()
    assert app.density_var.get() == "comfortable"
    assert int(style.lookup("Treeview", "rowheight")) == 24
    assert app.project.to_dict() == before
