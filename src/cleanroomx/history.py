from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Callable, Generic, TypeVar


StateT = TypeVar("StateT")


@dataclass(frozen=True)
class HistoryEntry(Generic[StateT]):
    before: StateT
    after: StateT
    description: str


class SnapshotHistory(Generic[StateT]):
    """Bounded transactional history for immutable-by-contract snapshots.

    The history owns copies of every recorded state and returns fresh copies from
    undo/redo so callers cannot mutate stored history accidentally.
    """

    def __init__(
        self,
        limit: int = 100,
        *,
        clone: Callable[[StateT], StateT] = deepcopy,
    ):
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("history limit must be a positive integer")
        if not callable(clone):
            raise TypeError("history clone must be callable")
        self.limit = limit
        self._clone = clone
        self._undo: list[HistoryEntry[StateT]] = []
        self._redo: list[HistoryEntry[StateT]] = []

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
        if before == after:
            return False
        entry = HistoryEntry(
            before=self._clone(before),
            after=self._clone(after),
            description=str(description).strip() or "Edit",
        )
        self._undo.append(entry)
        if len(self._undo) > self.limit:
            del self._undo[: len(self._undo) - self.limit]
        self._redo.clear()
        return True

    def undo(self) -> tuple[StateT, str] | None:
        if not self._undo:
            return None
        entry = self._undo.pop()
        self._redo.append(entry)
        return self._clone(entry.before), entry.description

    def redo(self) -> tuple[StateT, str] | None:
        if not self._redo:
            return None
        entry = self._redo.pop()
        self._undo.append(entry)
        return self._clone(entry.after), entry.description
