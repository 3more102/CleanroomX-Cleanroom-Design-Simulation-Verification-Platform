from __future__ import annotations

import re
from typing import Any


_NUMBER_PREFIX = re.compile(
    r"^\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)\s*(.*)$"
)

_STATE_ORDER = {
    "critical": 0,
    "error": 1,
    "fail": 1,
    "failed": 1,
    "warning": 2,
    "warn": 2,
    "stale": 3,
    "unresolved": 3,
    "not checked": 4,
    "not verified": 4,
    "unknown": 4,
    "info": 5,
    "running": 6,
    "current": 7,
    "pass": 8,
    "passed": 8,
    "available": 8,
}


def engineering_sort_key(value: Any) -> tuple:
    """Return a stable engineering-friendly key for Treeview cell values."""
    text = "" if value is None else str(value).strip()
    folded = text.casefold().replace("_", " ")
    if folded in _STATE_ORDER:
        return (0, _STATE_ORDER[folded], folded)

    normalized = text.replace(",", "").replace("−", "-")
    match = _NUMBER_PREFIX.match(normalized)
    if match:
        try:
            number = float(match.group(1))
        except ValueError:
            pass
        else:
            unit = match.group(2).strip().casefold()
            return (1, number, unit)

    return (2, folded)


class TreeviewSorter:
    """Attach reversible heading sorting to a ttk.Treeview-like widget."""

    def __init__(self, tree, headings: dict[str, str]) -> None:
        self.tree = tree
        self.headings = dict(headings)
        self._descending: dict[str, bool] = {}
        self._active_column: str | None = None
        for column in self.headings:
            self._configure_heading(column)

    def _configure_heading(self, column: str) -> None:
        label = self.headings[column]
        if column == self._active_column:
            label += " ▼" if self._descending.get(column, False) else " ▲"
        self.tree.heading(
            column,
            text=label,
            command=lambda value=column: self.sort(value),
        )

    def sort(self, column: str) -> None:
        descending = self._descending.get(column, False)
        rows = list(self.tree.get_children(""))
        values = []
        for index, iid in enumerate(rows):
            value = (
                self.tree.item(iid, "text")
                if column == "#0"
                else self.tree.set(iid, column)
            )
            values.append((engineering_sort_key(value), index, iid))

        values.sort(
            key=lambda item: (item[0], item[1]),
            reverse=descending,
        )
        for position, (_key, _index, iid) in enumerate(values):
            self.tree.move(iid, "", position)

        previous = self._active_column
        self._active_column = column
        self._descending[column] = not descending
        if previous is not None and previous != column:
            self._configure_heading(previous)
        self._configure_heading(column)
