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
    undo/redo so callers cannot mutate stored history accidentally. Callers can
    optionally provide a state-weight function and soft weight budget for large
    snapshot histories; the newest reversible edit is always retained.
    """

    def __init__(
        self,
        limit: int = 100,
        *,
        clone: Callable[[StateT], StateT] = deepcopy,
        max_weight: int | None = None,
        measure: Callable[[StateT], int] | None = None,
    ):
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("history limit must be a positive integer")
        if not callable(clone):
            raise TypeError("history clone must be callable")
        if (max_weight is None) != (measure is None):
            raise ValueError("history max_weight and measure must be configured together")
        if max_weight is not None and (
            isinstance(max_weight, bool)
            or not isinstance(max_weight, int)
            or max_weight < 1
        ):
            raise ValueError("history max_weight must be a positive integer")
        if measure is not None and not callable(measure):
            raise TypeError("history measure must be callable")

        self.limit = limit
        self.max_weight = max_weight
        self._clone = clone
        self._measure = measure
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

    def _state_weight(self, state: StateT) -> int:
        if self._measure is None:
            return 0
        weight = self._measure(state)
        if isinstance(weight, bool) or not isinstance(weight, int) or weight < 0:
            raise ValueError("history state weight must be a non-negative integer")
        return weight

    @property
    def approximate_weight(self) -> int | None:
        if self._measure is None:
            return None
        return sum(
            self._state_weight(state)
            for entry in (*self._undo, *self._redo)
            for state in (entry.before, entry.after)
        )

    def _trim_undo(self) -> None:
        if len(self._undo) > self.limit:
            del self._undo[: len(self._undo) - self.limit]
        if self.max_weight is None:
            return
        while len(self._undo) > 1:
            weight = self.approximate_weight
            if weight is None or weight <= self.max_weight:
                break
            del self._undo[0]

    def record(self, *, before: StateT, after: StateT, description: str) -> bool:
        if before == after:
            return False
        entry = HistoryEntry(
            before=self._clone(before),
            after=self._clone(after),
            description=str(description).strip() or "Edit",
        )
        # Validate weights before mutating the stacks so a broken measure
        # function cannot partially record an edit.
        self._state_weight(entry.before)
        self._state_weight(entry.after)
        self._undo.append(entry)
        self._redo.clear()
        self._trim_undo()
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
