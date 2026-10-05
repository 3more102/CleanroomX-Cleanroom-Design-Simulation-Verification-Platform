from __future__ import annotations

import os
import tkinter as tk

import pytest

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path
from cleanroomx.gui_command_palette import (
    CommandPalette,
    PaletteCommand,
    MAX_VISIBLE_RESULTS,
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
    assert palette._summary.cget("text") == "0 MATCHES"
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



def test_command_palette_limits_rendered_rows_but_keeps_full_search_index(root):
    commands = [
        PaletteCommand(
            f"item-{index}",
            f"Engineering object {index}",
            "Search / Object",
            lambda: None,
            keywords=(f"object-{index}",),
        )
        for index in range(MAX_VISIBLE_RESULTS + 25)
    ]
    palette = CommandPalette(root, commands=commands)
    try:
        root.update()
        assert len(palette.tree.get_children()) == MAX_VISIBLE_RESULTS
        assert palette._summary.cget("text") == (
            f"{MAX_VISIBLE_RESULTS} OF {MAX_VISIBLE_RESULTS + 25} MATCHES"
        )

        palette._query_var.set(f"object-{MAX_VISIBLE_RESULTS + 24}")
        root.update()
        children = palette.tree.get_children()
        assert len(children) == 1
        assert palette.tree.item(children[0], "text") == (
            f"Engineering object {MAX_VISIBLE_RESULTS + 24}"
        )
    finally:
        palette._close()


def test_application_palette_indexes_current_engineering_entities(root, tmp_path):
    app = CleanroomXApp(
        root,
        autosave_interval_seconds=0,
        ui_state_path=tmp_path / "gui-layout.json",
    )
    app.load_project_path(bundled_demo_project_path())
    root.update()

    commands = app._engineering_search_commands()
    categories = {command.category for command in commands}
    labels = [command.label for command in commands]

    assert "Search / Analysis" in categories
    assert "Search / Room" in categories
    assert any(label.startswith("Analysis · ") for label in labels)
    assert any(label.startswith("Room · ") for label in labels)

    room_command = next(
        command for command in commands if command.category == "Search / Room"
    )
    room_command.callback()
    root.update()
    assert app.notebook.select() == str(app.spatial_workspace)
    assert app.spatial_workspace.selected is not None
