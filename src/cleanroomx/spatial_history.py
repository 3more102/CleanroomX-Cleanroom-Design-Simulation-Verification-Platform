from __future__ import annotations

from dataclasses import dataclass
import copy
from typing import Any


SelectionState = tuple[str, str] | None


@dataclass(frozen=True)
class SpatialHistoryState:
    """Immutable-by-contract snapshot returned by spatial edit history."""

    layout: dict[str, Any]
    selection: SelectionState


@dataclass(frozen=True)
class SpatialHistoryEntry:
    before: SpatialHistoryState
    after: SpatialHistoryState
    description: str


class SpatialEditHistory:
    """Bounded transactional undo/redo history for spatial model edits.

    Callers provide layout snapshots that contain only undoable design state.
    View/camera state can therefore remain outside the edit history.
    """

    def __init__(self, limit: int = 100):
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("history limit must be a positive integer")
        self.limit = limit
        self._undo: list[SpatialHistoryEntry] = []
        self._redo: list[SpatialHistoryEntry] = []

    @staticmethod
    def _state(layout: dict[str, Any], selection: SelectionState) -> SpatialHistoryState:
        return SpatialHistoryState(copy.deepcopy(layout), copy.deepcopy(selection))

    @staticmethod
    def _copy_state(state: SpatialHistoryState) -> SpatialHistoryState:
        return SpatialHistoryState(copy.deepcopy(state.layout), copy.deepcopy(state.selection))

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
        before_layout: dict[str, Any],
        before_selection: SelectionState,
        after_layout: dict[str, Any],
        after_selection: SelectionState,
        description: str,
    ) -> bool:
        """Record one completed edit and invalidate redo history.

        Selection-only changes are intentionally not history entries.
        """

        if before_layout == after_layout:
            return False
        entry = SpatialHistoryEntry(
            before=self._state(before_layout, before_selection),
            after=self._state(after_layout, after_selection),
            description=str(description).strip() or "Spatial edit",
        )
        self._undo.append(entry)
        if len(self._undo) > self.limit:
            del self._undo[: len(self._undo) - self.limit]
        self._redo.clear()
        return True

    def undo(self) -> tuple[SpatialHistoryState, str] | None:
        if not self._undo:
            return None
        entry = self._undo.pop()
        self._redo.append(entry)
        return self._copy_state(entry.before), entry.description

    def redo(self) -> tuple[SpatialHistoryState, str] | None:
        if not self._redo:
            return None
        entry = self._redo.pop()
        self._undo.append(entry)
        return self._copy_state(entry.after), entry.description
