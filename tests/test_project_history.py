from __future__ import annotations

import pytest

from cleanroomx.project import AnalysisDocument, ProjectDocument, ProjectFormatError
from cleanroomx.project_history import (
    ProjectEditHistory,
    ProjectHistoryConflictError,
)


def _project(value: int = 1) -> ProjectDocument:
    return ProjectDocument(
        name="History",
        analyses=[
            AnalysisDocument(
                id="analysis-a",
                name="A",
                kind="room_verification",
                input={"value": value},
            ),
            AnalysisDocument(
                id="analysis-b",
                name="B",
                kind="room_verification",
                input={"value": 9},
            ),
        ],
        active_analysis_id="analysis-a",
        metadata={
            "spatial_layout": {"version": 1, "rooms": [{"id": "room-a"}]},
            "owner_note": "tracked",
        },
    )


def test_project_history_round_trip_restores_deleted_analysis_and_input():
    project = _project()
    history = ProjectEditHistory(limit=5, preserved_metadata_keys={"spatial_layout"})
    before = history.capture(project, selected_analysis_id="analysis-a")

    project.analysis_by_id("analysis-a").input = {"value": 2}
    project.analyses = [project.analysis_by_id("analysis-a")]
    project.active_analysis_id = "analysis-a"

    assert history.record(
        before,
        project,
        selected_analysis_id="analysis-a",
        description="Remove analysis B",
    )

    restored, description = history.undo(project)
    assert description == "Remove analysis B"
    assert [item.id for item in restored.analyses] == ["analysis-a", "analysis-b"]
    assert restored.analysis_by_id("analysis-a").input == {"value": 1}

    replayed, description = history.redo(restored)
    assert description == "Remove analysis B"
    assert [item.id for item in replayed.analyses] == ["analysis-a"]
    assert replayed.analysis_by_id("analysis-a").input == {"value": 2}


def test_project_history_preserves_independent_spatial_history_on_restore():
    project = _project()
    history = ProjectEditHistory(preserved_metadata_keys={"spatial_layout"})
    before = history.capture(project, selected_analysis_id="analysis-a")

    project.analysis_by_id("analysis-a").input = {"value": 2}
    history.record(
        before,
        project,
        selected_analysis_id="analysis-a",
        description="Edit input",
    )

    project.metadata["spatial_layout"] = {
        "version": 1,
        "rooms": [{"id": "room-current", "x_m": 8.0}],
    }

    restored, _ = history.undo(project)
    assert restored.analysis_by_id("analysis-a").input == {"value": 1}
    assert restored.metadata["spatial_layout"]["rooms"][0]["id"] == "room-current"


def test_project_history_ignores_selection_only_changes():
    project = _project()
    history = ProjectEditHistory()
    before = history.capture(project, selected_analysis_id="analysis-a")

    project.active_analysis_id = "analysis-b"

    assert history.record(
        before,
        project,
        selected_analysis_id="analysis-b",
        description="Select B",
    ) is False
    assert history.can_undo is False


def test_project_history_detects_untracked_divergence_without_consuming_entry():
    project = _project()
    history = ProjectEditHistory()
    before = history.capture(project, selected_analysis_id="analysis-a")
    project.analysis_by_id("analysis-a").input = {"value": 2}
    history.record(
        before,
        project,
        selected_analysis_id="analysis-a",
        description="Edit A",
    )

    project.metadata["owner_note"] = "changed outside history"

    with pytest.raises(ProjectHistoryConflictError, match="outside"):
        history.undo(project)
    assert history.can_undo is True
    assert history.can_redo is False
    assert project.analysis_by_id("analysis-a").input == {"value": 2}


def test_project_history_new_edit_invalidates_redo_and_is_bounded():
    project = _project()
    history = ProjectEditHistory(limit=2)

    for value in (2, 3, 4):
        before = history.capture(project, selected_analysis_id="analysis-a")
        project.analysis_by_id("analysis-a").input = {"value": value}
        history.record(
            before,
            project,
            selected_analysis_id="analysis-a",
            description=f"Set {value}",
        )

    restored, description = history.undo(project)
    assert description == "Set 4"
    restored, description = history.undo(restored)
    assert description == "Set 3"
    assert history.undo(restored) is None

    before = history.capture(restored, selected_analysis_id="analysis-a")
    restored.analysis_by_id("analysis-a").input = {"value": 8}
    history.record(
        before,
        restored,
        selected_analysis_id="analysis-a",
        description="Set 8",
    )
    assert history.can_redo is False


def test_project_history_snapshots_are_isolated_and_strictly_validated():
    project = _project()
    history = ProjectEditHistory()
    before = history.capture(project, selected_analysis_id="analysis-a")

    project.analysis_by_id("analysis-a").input["value"] = 99
    restored = before.restore()
    assert restored.analysis_by_id("analysis-a").input == {"value": 1}

    project.analyses.append(
        AnalysisDocument(
            id="analysis-a",
            name="Duplicate",
            kind="room_verification",
            input={},
        )
    )
    with pytest.raises(ProjectFormatError, match="unique"):
        history.capture(project)
