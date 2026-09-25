from __future__ import annotations

from dataclasses import dataclass
import copy
import json
from typing import Iterable

from .project import ProjectDocument, project_from_dict


class ProjectHistoryConflictError(RuntimeError):
    """Raised when undo/redo would overwrite project changes outside the history."""


@dataclass(frozen=True)
class ProjectHistoryState:
    """Immutable, validated snapshot of one committed project edit state."""

    document_json: str
    tracked_json: str
    selected_analysis_id: str | None

    def restore(self) -> ProjectDocument:
        return project_from_dict(json.loads(self.document_json))


@dataclass(frozen=True)
class _ProjectHistoryEntry:
    before: ProjectHistoryState
    after: ProjectHistoryState
    description: str


class ProjectEditHistory:
    """Bounded undo/redo history for committed project-document edits.

    Some project metadata can be owned by an independent editor with its own
    history. Such keys are excluded from project-history comparison and are
    preserved from the current document during restore.
    """

    def __init__(
        self,
        *,
        limit: int = 100,
        preserved_metadata_keys: Iterable[str] = (),
    ):
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValueError("project history limit must be a positive integer")
        keys = tuple(dict.fromkeys(preserved_metadata_keys))
        if any(not isinstance(key, str) or not key for key in keys):
            raise ValueError("preserved metadata keys must be non-empty strings")
        self.limit = limit
        self.preserved_metadata_keys = keys
        self._undo: list[_ProjectHistoryEntry] = []
        self._redo: list[_ProjectHistoryEntry] = []

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def undo_description(self) -> str | None:
        return self._undo[-1].description if self._undo else None

    @property
    def redo_description(self) -> str | None:
        return self._redo[-1].description if self._redo else None

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()

    def _validated_data(self, project: ProjectDocument) -> dict:
        # Round-trip through the ordinary project validator so history never
        # becomes a side channel for invalid project states.
        validated = project_from_dict(copy.deepcopy(project.to_dict()))
        return validated.to_dict()

    def capture(
        self,
        project: ProjectDocument,
        *,
        selected_analysis_id: str | None = None,
    ) -> ProjectHistoryState:
        data = self._validated_data(project)
        ids = {item["id"] for item in data["analyses"]}
        if selected_analysis_id is not None and selected_analysis_id not in ids:
            selected_analysis_id = None

        tracked = copy.deepcopy(data)
        # active_analysis_id is application view state, not an engineering edit.
        tracked["active_analysis_id"] = None
        metadata = tracked["project"]["metadata"]
        for key in self.preserved_metadata_keys:
            metadata.pop(key, None)

        return ProjectHistoryState(
            document_json=json.dumps(
                data,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            tracked_json=json.dumps(
                tracked,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            selected_analysis_id=selected_analysis_id,
        )

    def record(
        self,
        before: ProjectHistoryState,
        project: ProjectDocument,
        *,
        selected_analysis_id: str | None = None,
        description: str,
    ) -> bool:
        if not isinstance(before, ProjectHistoryState):
            raise TypeError("before must be a ProjectHistoryState")
        if not isinstance(description, str) or not description.strip():
            raise ValueError("project history description must be a non-empty string")

        after = self.capture(
            project,
            selected_analysis_id=selected_analysis_id,
        )
        if before.tracked_json == after.tracked_json:
            return False

        # If tracked state changed outside this history, older entries cannot be
        # replayed safely. Start a new valid chain instead of risking overwrite.
        if self._undo and self._undo[-1].after.tracked_json != before.tracked_json:
            self.clear()

        self._undo.append(
            _ProjectHistoryEntry(
                before=before,
                after=after,
                description=description.strip(),
            )
        )
        if len(self._undo) > self.limit:
            del self._undo[: len(self._undo) - self.limit]
        self._redo.clear()
        return True

    def _current_tracked_json(self, project: ProjectDocument) -> str:
        return self.capture(project).tracked_json

    def _restore(
        self,
        state: ProjectHistoryState,
        current_project: ProjectDocument,
    ) -> ProjectDocument:
        restored = state.restore()
        current_metadata = self._validated_data(current_project)["project"]["metadata"]

        for key in self.preserved_metadata_keys:
            if key in current_metadata:
                restored.metadata[key] = copy.deepcopy(current_metadata[key])
            else:
                restored.metadata.pop(key, None)

        ids = {item.id for item in restored.analyses}
        target = state.selected_analysis_id
        if target not in ids:
            target = restored.active_analysis_id if restored.active_analysis_id in ids else None
        if target is None and restored.analyses:
            target = restored.analyses[0].id
        restored.active_analysis_id = target

        # Validate the merged state as well.
        return project_from_dict(restored.to_dict())

    def undo(self, current_project: ProjectDocument) -> tuple[ProjectDocument, str] | None:
        if not self._undo:
            return None
        entry = self._undo[-1]
        if self._current_tracked_json(current_project) != entry.after.tracked_json:
            raise ProjectHistoryConflictError(
                "project changed outside the project edit history; undo was not applied"
            )

        restored = self._restore(entry.before, current_project)
        self._undo.pop()
        self._redo.append(entry)
        return restored, entry.description

    def redo(self, current_project: ProjectDocument) -> tuple[ProjectDocument, str] | None:
        if not self._redo:
            return None
        entry = self._redo[-1]
        if self._current_tracked_json(current_project) != entry.before.tracked_json:
            raise ProjectHistoryConflictError(
                "project changed outside the project edit history; redo was not applied"
            )

        restored = self._restore(entry.after, current_project)
        self._redo.pop()
        self._undo.append(entry)
        return restored, entry.description
