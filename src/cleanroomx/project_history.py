from __future__ import annotations

from dataclasses import dataclass
import copy
from typing import Any


@dataclass(frozen=True)
class ProjectEditState:
    """Snapshot of undoable analysis-document state plus editor context.

    The analysis list is the authoritative persisted model. Editor text is kept
    separately so undo can restore an uncommitted or temporarily invalid draft
    without pretending that draft was already part of the project document.
    """

    analyses: list[dict[str, Any]]
    active_analysis_id: str | None
    editor_analysis_id: str | None
    editor_text: str


@dataclass(frozen=True)
class ProjectEditEntry:
    before: ProjectEditState
    after: ProjectEditState
    description: str


class ProjectEditHistory:
    """Bounded transactional undo/redo for project analysis-document edits.

    Selection/editor-context-only changes are intentionally not history entries.
    Callers record a completed transaction around mutations of the authoritative
    analysis collection.
    """

    def __init__(self, limit: int = 100):
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("history limit must be a positive integer")
        self.limit = limit
        self._undo: list[ProjectEditEntry] = []
        self._redo: list[ProjectEditEntry] = []

    @staticmethod
    def _copy_state(state: ProjectEditState) -> ProjectEditState:
        return ProjectEditState(
            analyses=copy.deepcopy(state.analyses),
            active_analysis_id=state.active_analysis_id,
            editor_analysis_id=state.editor_analysis_id,
            editor_text=state.editor_text,
        )

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()

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

    def record(
        self,
        *,
        before: ProjectEditState,
        after: ProjectEditState,
        description: str,
    ) -> bool:
        """Record one completed analysis-model transaction.

        Active selection and raw editor context are restored with an edit but do
        not create history by themselves.
        """

        if before.analyses == after.analyses:
            return False
        entry = ProjectEditEntry(
            before=self._copy_state(before),
            after=self._copy_state(after),
            description=str(description).strip() or "Project edit",
        )
        self._undo.append(entry)
        if len(self._undo) > self.limit:
            del self._undo[: len(self._undo) - self.limit]
        self._redo.clear()
        return True

    def undo(self) -> tuple[ProjectEditState, str] | None:
        if not self._undo:
            return None
        entry = self._undo.pop()
        self._redo.append(entry)
        return self._copy_state(entry.before), entry.description

    def redo(self) -> tuple[ProjectEditState, str] | None:
        if not self._redo:
            return None
        entry = self._redo.pop()
        self._undo.append(entry)
        return self._copy_state(entry.after), entry.description
