from __future__ import annotations

from dataclasses import dataclass
import json

from .history import SnapshotHistory
from .project import ProjectDocument, project_from_dict


@dataclass(frozen=True)
class ProjectHistoryState:
    """Complete undoable project/UI state for one desktop document transaction."""

    project_json: str
    name_text: str
    description_text: str
    editor_analysis_id: str | None
    editor_text: str


def make_project_history_state(
    project: ProjectDocument,
    *,
    name_text: str,
    description_text: str,
    editor_analysis_id: str | None,
    editor_text: str,
) -> ProjectHistoryState:
    project_json = json.dumps(
        project.to_dict(),
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    return ProjectHistoryState(
        project_json=project_json,
        name_text=str(name_text),
        description_text=str(description_text),
        editor_analysis_id=editor_analysis_id,
        editor_text=str(editor_text),
    )


def project_from_history_state(state: ProjectHistoryState) -> ProjectDocument:
    data = json.loads(state.project_json)
    return project_from_dict(data)


class ProjectEditHistory:
    """Bounded undo/redo for project-level desktop editing transactions."""

    def __init__(self, limit: int = 100):
        self._history = SnapshotHistory[ProjectHistoryState](limit=limit)

    @property
    def limit(self) -> int:
        return self._history.limit

    def clear(self) -> None:
        self._history.clear()

    @property
    def can_undo(self) -> bool:
        return self._history.can_undo

    @property
    def can_redo(self) -> bool:
        return self._history.can_redo

    @property
    def undo_description(self) -> str | None:
        return self._history.undo_description

    @property
    def redo_description(self) -> str | None:
        return self._history.redo_description

    def record(
        self,
        *,
        before: ProjectHistoryState,
        after: ProjectHistoryState,
        description: str,
    ) -> bool:
        return self._history.record(
            before=before,
            after=after,
            description=description,
        )

    def undo(self) -> tuple[ProjectHistoryState, str] | None:
        return self._history.undo()

    def redo(self) -> tuple[ProjectHistoryState, str] | None:
        return self._history.redo()
