from __future__ import annotations

import os
import tkinter as tk

import pytest

import cleanroomx.gui as gui_module
from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path
from cleanroomx.spatial import _Hit
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


def test_command_palette_exposes_engineering_empty_state(root):
    palette = CommandPalette(
        root,
        commands=[
            PaletteCommand(
                "verify",
                "Verify Project Requirements",
                "Verification",
                lambda: None,
            )
        ],
    )
    root.update()

    palette._query_var.set("definitely-missing-command")
    root.update()

    assert palette.tree.get_children() == ()
    assert "No command matches" in palette._empty_hint.cget("text")
    assert palette._summary.cget("text") == "0 COMMANDS"
    palette._close()


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


def test_search_only_entries_are_lazy_until_query():
    noop = lambda: None
    commands = [
        PaletteCommand("save", "Save Project", "File", noop),
        PaletteCommand(
            "room-a",
            "Room · ISO 7 Suite",
            "Search · Room",
            noop,
            keywords=("room-a", "iso 7"),
            search_only=True,
        ),
    ]

    assert [item.id for item in filter_commands(commands, "")] == ["save"]
    assert [item.id for item in filter_commands(commands, "ISO 7")] == ["room-a"]


def test_application_palette_searches_and_focuses_real_model_objects(root, tmp_path):
    app = CleanroomXApp(
        root,
        autosave_interval_seconds=0,
        ui_state_path=tmp_path / "gui-layout-search.json",
    )
    app.load_project_path(bundled_demo_project_path())
    root.update()

    room = app.spatial_workspace.layout["rooms"][0]
    commands = app._command_palette_commands()
    matches = filter_commands(commands, str(room["name"]))

    room_commands = [
        command
        for command in matches
        if command.id == f"search.room.{room['id']}"
    ]
    assert len(room_commands) == 1
    assert room_commands[0].search_only is True

    room_commands[0].callback()
    root.update_idletasks()

    assert app.spatial_workspace.selected == _Hit("room", room["id"])
    assert app.notebook.select() == str(app.spatial_workspace)


def test_application_palette_indexes_requirements_and_routes_to_traceability(
    root,
    tmp_path,
    monkeypatch,
):
    app = CleanroomXApp(
        root,
        autosave_interval_seconds=0,
        ui_state_path=tmp_path / "gui-layout-requirement-search.json",
    )
    opened: list[str | None] = []
    monkeypatch.setattr(
        gui_module,
        "build_project_requirements_traceability",
        lambda _project: {
            "requirements": [
                {
                    "id": "REQ-ACH-01",
                    "title": "Minimum room air changes",
                    "description": "Maintain the approved room ACH criterion.",
                    "discipline": "HVAC",
                    "category": "air_changes",
                    "source": "URS",
                    "reference": "URS-7.2",
                    "set": {"title": "Cleanroom URS"},
                }
            ]
        },
    )
    monkeypatch.setattr(
        app,
        "show_requirements_traceability",
        lambda requirement_id=None: opened.append(requirement_id) or True,
    )

    commands = app._engineering_search_commands()
    matches = filter_commands(commands, "REQ-ACH-01")
    requirement_commands = [
        command
        for command in matches
        if command.id == "search.requirement.REQ-ACH-01"
    ]

    assert len(requirement_commands) == 1
    assert requirement_commands[0].search_only is True
    assert "Search · Requirement" == requirement_commands[0].category

    requirement_commands[0].callback()

    assert opened == ["REQ-ACH-01"]
    assert app.status_var.get() == "Requirement selected: REQ-ACH-01"
