from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Callable

from tkinter import ttk


_MISSING_TEXT = {"", "—", "-", "n/a", "none", "unknown"}
_NATURAL_PART = re.compile(r"(\\d+)")


def engineering_table_sort_value(value: Any) -> tuple[int, Any] | None:
    """Return a deterministic sort token for user-visible engineering table cells.

    Numeric text sorts numerically, ordinary text sorts naturally/case-insensitively,
    and explicit missing-value markers return None so controllers can keep them at
    the bottom in either direction.
    """
    if value is None:
        return None
    cell_text = str(value).strip()
    if cell_text.casefold() in _MISSING_TEXT:
        return None

    numeric = cell_text.replace(",", "")
    try:
        return (0, Decimal(numeric))
    except (InvalidOperation, ValueError):
        pass

    parts: list[tuple[int, Any]] = []
    for part in _NATURAL_PART.split(cell_text.casefold()):
        if not part:
            continue
        if part.isdigit():
            parts.append((0, int(part)))
        else:
            parts.append((1, part))
    return (1, tuple(parts))


@dataclass
class TreeviewSortController:
    """Reusable sortable-heading behavior for ttk.Treeview engineering tables."""

    tree: ttk.Treeview
    headings: dict[str, str]
    column: str | None = None
    descending: bool = False
    key_overrides: dict[str, Callable[[str], Any]] | None = None

    def __post_init__(self) -> None:
        self.key_overrides = dict(self.key_overrides or {})
        for column in self.headings:
            self.tree.heading(
                column,
                text=self.headings[column],
                command=lambda selected=column: self.sort_by(selected),
            )
        self._refresh_headings()

    def sort_by(self, column: str) -> None:
        if column not in self.headings:
            raise KeyError(column)
        if self.column == column:
            self.descending = not self.descending
        else:
            self.column = column
            self.descending = False
        self.reapply()

    def set_sort(self, column: str | None, *, descending: bool = False) -> None:
        if column is not None and column not in self.headings:
            raise KeyError(column)
        self.column = column
        self.descending = bool(descending)
        self.reapply()

    def reapply(self) -> None:
        self._refresh_headings()
        if self.column is None:
            return

        selected = tuple(self.tree.selection())
        focused = self.tree.focus()
        rows = list(self.tree.get_children(""))

        present: list[tuple[Any, int, str]] = []
        missing: list[tuple[int, str]] = []
        for index, iid in enumerate(rows):
            raw = (
                self.tree.item(iid, "text")
                if self.column == "#0"
                else self.tree.set(iid, self.column)
            )
            override = self.key_overrides.get(self.column)
            token = (
                override(raw)
                if override is not None
                else engineering_table_sort_value(raw)
            )
            if token is None:
                missing.append((index, iid))
            else:
                present.append((token, index, iid))

        present.sort(
            key=lambda item: (item[0], item[1]),
            reverse=self.descending,
        )
        ordered = [iid for _, _, iid in present]
        ordered.extend(iid for _, iid in missing)
        for index, iid in enumerate(ordered):
            self.tree.move(iid, "", index)

        existing = set(ordered)
        keep_selected = [iid for iid in selected if iid in existing]
        if keep_selected:
            self.tree.selection_set(keep_selected)
        if focused in existing:
            self.tree.focus(focused)
            self.tree.see(focused)

    def _refresh_headings(self) -> None:
        for column, title in self.headings.items():
            marker = ""
            if self.column == column:
                marker = " ▼" if self.descending else " ▲"
            self.tree.heading(
                column,
                text=title + marker,
                command=lambda selected=column: self.sort_by(selected),
            )
