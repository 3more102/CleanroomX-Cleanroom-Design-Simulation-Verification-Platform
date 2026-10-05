from __future__ import annotations

import os
import tkinter as tk

import pytest

from cleanroomx.gui import CleanroomXApp, RequirementsTraceabilityDialog, bundled_demo_project_path
from cleanroomx.gui_command_palette import (
    CommandPalette,
    MAX_RENDERED_RESULTS,
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


def test_requirements_traceability_dialog_can_focus_requested_requirement(root):
    snapshot = {
        "requirement_set_count": 1,
        "requirement_count": 2,
        "mapping_count": 0,
        "active_mapping_count": 0,
        "active_mapped_requirement_count": 0,
        "requirements_sha256": "req-digest",
        "mappings_sha256": "map-digest",
        "requirements": [
            {
                "id": "REQ-1",
                "title": "First requirement",
                "status": "active",
                "applicability": "applicable",
                "scope": ["room-a"],
                "criterion": "min=1",
                "detail": {"id": "REQ-1"},
            },
            {
                "id": "REQ-2",
                "title": "Second requirement",
                "status": "active",
                "applicability": "applicable",
                "scope": ["room-b"],
                "criterion": "max=2",
                "detail": {"id": "REQ-2"},
            },
        ],
        "mappings": [],
    }
    dialog = RequirementsTraceabilityDialog(
        root,
        snapshot,
        focus_requirement_id="REQ-2",
    )
    root.update()

    assert dialog.tree.selection() == ("requirement:REQ-2",)
    assert dialog.tree.focus() == "requirement:REQ-2"
    dialog.destroy()


def test_command_palette_bounds_rendering_for_large_engineering_catalog(root):
    commands = [
        PaletteCommand(
            f"room-{index}",
            f"Room — R{index:04d}",
            "Project Search · Room",
            lambda: None,
        )
        for index in range(MAX_RENDERED_RESULTS + 25)
    ]
    palette = CommandPalette(root, commands=commands)
    root.update()

    assert len(palette.tree.get_children()) == MAX_RENDERED_RESULTS
    assert str(MAX_RENDERED_RESULTS + 25) in palette._summary.cget("text")
    assert f"FIRST {MAX_RENDERED_RESULTS}" in palette._summary.cget("text")
    palette._close()


def test_application_command_palette_searches_and_opens_real_project_entities(root, tmp_path):
    app = CleanroomXApp(
        root,
        autosave_interval_seconds=0,
        ui_state_path=tmp_path / "gui-layout.json",
    )
    app.load_project_path(bundled_demo_project_path())
    root.update()

    commands = app._command_palette_commands()
    by_id = {command.id: command for command in commands}

    analysis = app.project.analyses[0]
    assert f"entity.analysis.{analysis.id}" in by_id

    room = app.spatial_workspace.layout["rooms"][0]
    room_id = str(room["id"])
    room_command = by_id[f"entity.room.{room_id}"]
    assert room_command.label.startswith("Room — ")

    room_command.callback()
    root.update()
    assert app.spatial_workspace.selected is not None
    assert app.spatial_workspace.selected.kind == "room"
    assert app.spatial_workspace.selected.item_id == room_id
    assert app.spatial_workspace.inspector_visible()

    analysis_command = by_id[f"entity.analysis.{analysis.id}"]
    analysis_command.callback()
    root.update()
    assert app.analysis_tree.selection() == (analysis.id,)
    assert app.notebook.select() == str(app.input_tab)


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
