from __future__ import annotations

import os
import tkinter as tk
from types import SimpleNamespace

import pytest

from cleanroomx.gui import CleanroomXApp
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


def test_palette_prioritizes_label_matches_and_keeps_equal_rank_order():
    invoked = []
    callback = lambda: invoked.append("executed")
    commands = [
        PaletteCommand("keyword", "Save Project", "Project", callback, keywords=("open",)),
        PaletteCommand("partial", "Reopen Project", "Project", callback),
        PaletteCommand("prefix-a", "Open Project", "Project", callback),
        PaletteCommand("exact", "Open", "Project", callback),
        PaletteCommand("prefix-b", "Open IFC", "BIM", callback),
    ]
    assert [command.id for command in filter_commands(commands, " OPEN ")] == [
        "exact", "prefix-a", "prefix-b", "partial", "keyword",
    ]
    assert filter_commands(commands, "") == commands
    assert invoked == []


def test_palette_ranking_retains_multi_token_metadata_search():
    commands = [
        PaletteCommand("keyword", "Load Layout", "BIM", lambda: None,
                       keywords=("open", "ifc")),
        PaletteCommand("label", "Open IFC", "BIM", lambda: None),
    ]
    assert [command.id for command in filter_commands(commands, "open ifc")] == [
        "label", "keyword",
    ]
    assert [command.id for command in filter_commands(commands, "bim ifc")] == [
        "keyword", "label",
    ]


@pytest.mark.parametrize("focused", ["first", "second"])
def test_up_from_first_command_returns_to_search_without_executing(focused):
    focused_search = []
    palette = SimpleNamespace(
        tree=SimpleNamespace(get_children=lambda: ("first", "second"), focus=lambda: focused),
        search=SimpleNamespace(focus_set=lambda: focused_search.append(True)),
    )
    result = CommandPalette._return_to_search(palette)
    assert result == ("break" if focused == "first" else None)
    assert focused_search == ([True] if focused == "first" else [])


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
