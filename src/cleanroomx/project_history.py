from __future__ import annotations

from dataclasses import dataclass
import copy
from typing import Any

from .edit_history import BoundedSnapshotHistory


@dataclass(frozen=True)
class ProjectHistoryState:
    """Immutable-by-contract project snapshot used by desktop edit history."""

    document: dict[str, Any]
    editor_analysis_id: str | None


@dataclass(frozen=True)
class ProjectHistoryEntry:
    """Compatibility-friendly project history entry shape."""

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
        self.limit = limit
        self._history = BoundedSnapshotHistory[ProjectHistoryState](
            limit=limit,
            equivalent=lambda before, after: before.document == after.document,
        )

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

    def capture(
        self,
        document: dict[str, Any],
        editor_analysis_id: str | None,
    ) -> ProjectHistoryState:
        """Capture an isolated state suitable for a later record() call."""

        return self._state(document, editor_analysis_id)

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
        after_document: dict[str, Any],
        after_editor_analysis_id: str | None,
        description: str,
    ) -> bool:
        """Record one completed project edit and invalidate redo history.

        Selection/editor-focus changes alone are intentionally not edit history.
        """

        return self._history.record(
            before=before,
            after=self._state(after_document, after_editor_analysis_id),
            description=str(description).strip() or "Project edit",
        )

    def undo(self) -> tuple[ProjectHistoryState, str] | None:
        return self._history.undo()

    def redo(self) -> tuple[ProjectHistoryState, str] | None:
        return self._history.redo()
