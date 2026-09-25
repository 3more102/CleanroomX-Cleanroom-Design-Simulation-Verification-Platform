from __future__ import annotations

from dataclasses import dataclass
import copy
from typing import Any

from .edit_history import BoundedSnapshotHistory


SelectionState = tuple[str, str] | None


@dataclass(frozen=True)
class SpatialHistoryState:
    """Immutable-by-contract snapshot returned by spatial edit history."""

    layout: dict[str, Any]
    selection: SelectionState


@dataclass(frozen=True)
class SpatialHistoryEntry:
    """Compatibility shape retained for callers importing the prior public type."""

    before: SpatialHistoryState
    after: SpatialHistoryState
    description: str


class SpatialEditHistory:
    """Bounded transactional undo/redo history for spatial model edits.

    Callers provide layout snapshots that contain only undoable design state.
    View/camera state can therefore remain outside the edit history.
    """

    def __init__(self, limit: int = 100):
        self.limit = limit
        self._history = BoundedSnapshotHistory[SpatialHistoryState](
            limit=limit,
            equivalent=lambda before, after: before.layout == after.layout,
        )

    @staticmethod
    def _state(layout: dict[str, Any], selection: SelectionState) -> SpatialHistoryState:
        return SpatialHistoryState(copy.deepcopy(layout), copy.deepcopy(selection))

    @staticmethod
    def _copy_state(state: SpatialHistoryState) -> SpatialHistoryState:
        return BoundedSnapshotHistory.copy_state(state)

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
        before_layout: dict[str, Any],
        before_selection: SelectionState,
        after_layout: dict[str, Any],
        after_selection: SelectionState,
        description: str,
    ) -> bool:
        """Record one completed edit and invalidate redo history.

        Selection-only changes are intentionally not history entries.
        """

        return self._history.record(
            before=self._state(before_layout, before_selection),
            after=self._state(after_layout, after_selection),
            description=str(description).strip() or "Spatial edit",
        )

    def undo(self) -> tuple[SpatialHistoryState, str] | None:
        return self._history.undo()

    def redo(self) -> tuple[SpatialHistoryState, str] | None:
        return self._history.redo()
