from __future__ import annotations

from cleanroomx.project import AnalysisDocument, ProjectDocument
from cleanroomx.project_history import (
    ProjectEditHistory,
    make_project_history_state,
    project_from_history_state,
)


def _project(value: int) -> ProjectDocument:
    return ProjectDocument(
        name="History",
        analyses=[
            AnalysisDocument(
                id="room-1",
                name="Room",
                kind="room_verification",
                input={"value": value},
            )
        ],
        active_analysis_id="room-1",
    )


def test_project_history_restores_validated_document_and_raw_editor_draft():
    before_project = _project(1)
    before = make_project_history_state(
        before_project,
        name_text="History",
        description_text="before",
        editor_analysis_id="room-1",
        editor_text='{"unfinished":',
    )
    after = make_project_history_state(
        _project(2),
        name_text="History renamed",
        description_text="after",
        editor_analysis_id="room-1",
        editor_text='{"value": 2}',
    )

    history = ProjectEditHistory(limit=4)
    assert history.record(before=before, after=after, description="Import input") is True

    restored, description = history.undo()
    assert description == "Import input"
    assert restored.editor_text == '{"unfinished":'
    project = project_from_history_state(restored)
    assert project.analysis_by_id("room-1").input == {"value": 1}
    assert project.name == "History"

    replayed, description = history.redo()
    assert description == "Import input"
    assert replayed.name_text == "History renamed"
    assert project_from_history_state(replayed).analysis_by_id("room-1").input == {"value": 2}


def test_project_history_snapshots_do_not_alias_mutable_project_data():
    project = _project(1)
    state = make_project_history_state(
        project,
        name_text=project.name,
        description_text=project.description,
        editor_analysis_id="room-1",
        editor_text='{"value": 1}',
    )
    project.analysis_by_id("room-1").input["value"] = 99

    restored = project_from_history_state(state)
    assert restored.analysis_by_id("room-1").input == {"value": 1}
