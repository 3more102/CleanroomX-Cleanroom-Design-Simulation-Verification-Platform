from __future__ import annotations

import os
import tkinter as tk

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

def test_global_palette_indexes_current_engineering_entities(root, tmp_path):
    app = CleanroomXApp(
        root,
        autosave_interval_seconds=0,
        ui_state_path=tmp_path / "gui-layout.json",
    )
    app.load_project_path(bundled_demo_project_path())
    root.update()

    commands = app._command_palette_commands()
    by_category = {}
    for command in commands:
        by_category.setdefault(command.category, []).append(command)

    assert by_category["Find / Analysis"]
    assert by_category["Find / Model"]

    diagnostic_result = app.problems_panel.last_result
    diagnostic_issues = (
        diagnostic_result.get("issues", [])
        if isinstance(diagnostic_result, dict)
        else []
    )
    if diagnostic_issues:
        assert by_category["Find / Diagnostics"]
    else:
        assert "Find / Diagnostics" not in by_category

    room_command = next(
        command
        for command in by_category["Find / Model"]
        if command.id.startswith("entity.room.")
    )
    room_command.callback()
    root.update()

    assert app.notebook.select() == str(app.spatial_workspace)
    assert app.spatial_workspace.selected is not None
    assert app.spatial_workspace.selected.kind == "room"

