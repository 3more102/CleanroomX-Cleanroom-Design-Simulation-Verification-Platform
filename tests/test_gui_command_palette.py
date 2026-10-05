from __future__ import annotations

import os
import tkinter as tk

import pytest

from cleanroomx.gui import CleanroomXApp
from cleanroomx.project import AnalysisDocument, ProjectDocument
from cleanroomx.spatial import SPATIAL_METADATA_KEY
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


def test_application_command_catalog_indexes_live_engineering_objects(root, tmp_path):
    app = CleanroomXApp(
        root,
        autosave_interval_seconds=0,
        ui_state_path=tmp_path / "gui-layout-search.json",
    )
    app.project = ProjectDocument(
        name="Search Demo",
        analyses=[
            AnalysisDocument(
                id="analysis-a",
                name="Room A ACH",
                kind="room_verification",
                input={},
            )
        ],
        active_analysis_id="analysis-a",
        metadata={
            SPATIAL_METADATA_KEY: {
                "rooms": [
                    {
                        "id": "room-a",
                        "name": "Room A",
                        "classification": "ISO 7",
                    }
                ],
                "devices": [
                    {
                        "id": "ahu-1",
                        "name": "AHU-1",
                        "type": "ahu",
                        "room_id": "room-a",
                    }
                ],
            }
        },
    )
    app.problems_panel.last_result = {
        "issues": [
            {
                "sequence": 7,
                "severity": "warning",
                "rule": "spatial.test_warning",
                "category": "spatial",
                "message": "Room A requires engineering review.",
                "suggested_action": "Inspect Room A.",
                "element": {
                    "type": "spatial_element",
                    "id": "room-a",
                    "name": "Room A",
                },
            }
        ]
    }

    commands = app._command_palette_commands()
    ids = {command.id for command in commands}
    labels = {command.label for command in commands}

    assert "workspace.design" in ids
    assert "workspace.verification" in ids
    assert "density.compact" in ids
    assert "Analysis: Room A ACH" in labels
    assert "Room: Room A" in labels
    assert "Device: AHU-1" in labels
    assert "Diagnostic: WARNING · spatial.test_warning · Room A" in labels

    assert [item.id for item in filter_commands(commands, "room room-a")]
    equipment = filter_commands(commands, "equipment ahu")
    assert [item.id for item in equipment] == ["search.device.ahu-1"]
    diagnostics = filter_commands(commands, "warning review room")
    assert any(item.id.startswith("search.diagnostic.") for item in diagnostics)
