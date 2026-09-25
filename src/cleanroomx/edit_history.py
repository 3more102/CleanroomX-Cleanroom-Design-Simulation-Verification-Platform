from __future__ import annotations

from dataclasses import dataclass
import copy
from typing import Callable, Generic, TypeVar


StateT = TypeVar("StateT")


@dataclass(frozen=True)
class SnapshotHistoryEntry(Generic[StateT]):
    before: StateT
    after: StateT
    description: str


class BoundedSnapshotHistory(Generic[StateT]):
    """Shared bounded undo/redo storage for isolated state snapshots.

    Domain-specific history adapters decide what belongs to a snapshot and what
    constitutes a no-op. This class only owns deterministic stack semantics and
    defensive deep copies.
    """

    def __init__(
        self,
        *,
        limit: int = 100,
        equivalent: Callable[[StateT, StateT], bool] | None = None,
    ):
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("history limit must be a positive integer")
        self.limit = limit
        self._equivalent = equivalent or (lambda before, after: before == after)
        self._undo: list[SnapshotHistoryEntry[StateT]] = []
        self._redo: list[SnapshotHistoryEntry[StateT]] = []

    @staticmethod
    def copy_state(state: StateT) -> StateT:
        return copy.deepcopy(state)

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

    def record(self, *, before: StateT, after: StateT, description: str) -> bool:
        isolated_before = self.copy_state(before)
        isolated_after = self.copy_state(after)
        if self._equivalent(isolated_before, isolated_after):
            return False

        self._undo.append(
            SnapshotHistoryEntry(
                before=isolated_before,
                after=isolated_after,
                description=str(description).strip() or "Edit",
            )
        )
        if len(self._undo) > self.limit:
            del self._undo[: len(self._undo) - self.limit]
        self._redo.clear()
        return True

    def undo(self) -> tuple[StateT, str] | None:
        if not self._undo:
            return None
        entry = self._undo.pop()
        self._redo.append(entry)
        return self.copy_state(entry.before), entry.description

    def redo(self) -> tuple[StateT, str] | None:
        if not self._redo:
            return None
        entry = self._redo.pop()
        self._undo.append(entry)
        return self.copy_state(entry.after), entry.description
