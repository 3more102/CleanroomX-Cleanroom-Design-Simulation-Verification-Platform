from __future__ import annotations

from dataclasses import dataclass
import copy
from typing import Any


@dataclass(frozen=True)
class ProjectHistoryState:
    """Immutable-by-contract project snapshot used by desktop edit history."""

    document: dict[str, Any]
    editor_analysis_id: str | None


@dataclass(frozen=True)
class ProjectHistoryEntry:
    before: ProjectHistoryState
    after: ProjectHistoryState
    description: str


class ProjectEditHistory:
    """Bounded deterministic undo/redo history for non-spatial project edits.

    The caller owns project validation and state restoration. History snapshots are
    deep-copied on capture and return so later model mutations cannot rewrite
    previously recorded states.
    """

    def __init__(self, limit: int = 100):
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("history limit must be a positive integer")
        self.limit = limit
        self._undo: list[ProjectHistoryEntry] = []
        self._redo: list[ProjectHistoryEntry] = []

    @staticmethod
    def _validated_editor_id(editor_analysis_id: str | None) -> str | None:
        if editor_analysis_id is not None and not isinstance(editor_analysis_id, str):
            raise ValueError("editor_analysis_id must be a string or null")
        return editor_analysis_id

    @classmethod
    def _state(
        cls,
        document: dict[str, Any],
        editor_analysis_id: str | None,
    ) -> ProjectHistoryState:
        if not isinstance(document, dict):
            raise ValueError("project history document must be an object")
        return ProjectHistoryState(
            document=copy.deepcopy(document),
            editor_analysis_id=copy.deepcopy(
                cls._validated_editor_id(editor_analysis_id)
            ),
        )

    @classmethod
    def _copy_state(cls, state: ProjectHistoryState) -> ProjectHistoryState:
        return cls._state(state.document, state.editor_analysis_id)

    def capture(
        self,
        document: dict[str, Any],
        editor_analysis_id: str | None,
    ) -> ProjectHistoryState:
        """Capture an isolated state suitable for a later record() call."""

        return self._state(document, editor_analysis_id)

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
        before: ProjectHistoryState,
        after_document: dict[str, Any],
        after_editor_analysis_id: str | None,
        description: str,
    ) -> bool:
        """Record one completed project edit and invalidate redo history.

        Selection/editor-focus changes alone are intentionally not edit history.
        """

        after = self._state(after_document, after_editor_analysis_id)
        if before.document == after.document:
            return False

        entry = ProjectHistoryEntry(
            before=self._copy_state(before),
            after=after,
            description=str(description).strip() or "Project edit",
        )
        self._undo.append(entry)
        if len(self._undo) > self.limit:
            del self._undo[: len(self._undo) - self.limit]
        self._redo.clear()
        return True

    def undo(self) -> tuple[ProjectHistoryState, str] | None:
        if not self._undo:
            return None
        entry = self._undo.pop()
        self._redo.append(entry)
        return self._copy_state(entry.before), entry.description

    def redo(self) -> tuple[ProjectHistoryState, str] | None:
        if not self._redo:
            return None
        entry = self._redo.pop()
        self._undo.append(entry)
        return self._copy_state(entry.after), entry.description
