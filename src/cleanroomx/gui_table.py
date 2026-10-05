from __future__ import annotations

import math
from typing import Any, Iterable

import tkinter as tk
from tkinter import ttk


_MISSING_TOKENS = {"", "—", "-", "n/a", "na", "none", "null"}


def table_value_sort_key(value: Any) -> tuple[int, Any]:
    """Return a deterministic presentation-only key for displayed table cells."""
    text = str(value if value is not None else "").strip()
    if text.casefold() in _MISSING_TOKENS:
        return (2, "")
    numeric = text.replace(",", "").strip()
    if numeric.endswith("%"):
        numeric = numeric[:-1].strip()
    try:
        number = float(numeric)
    except (TypeError, ValueError, OverflowError):
        return (1, text.casefold())
    if not math.isfinite(number):
        return (1, text.casefold())
    return (0, number)


def treeview_cell_text(tree: ttk.Treeview, iid: str, column: str) -> str:
    if column == "#0":
        return str(tree.item(iid, "text") or "")
    return str(tree.set(iid, column) or "")


class TreeviewTableBehavior:
    """Shared professional behavior for flat, read-only engineering tables.

    This helper only changes presentation order and clipboard output. It never
    changes the backing domain records represented by a Treeview.
    """

    def __init__(
        self,
        tree: ttk.Treeview,
        *,
        sortable_columns: Iterable[str],
        copy_columns: Iterable[str] | None = None,
        parent: str = "",
    ) -> None:
        self.tree = tree
        self.parent = parent
        self.sortable_columns = tuple(dict.fromkeys(str(item) for item in sortable_columns))
        if copy_columns is None:
            self.copy_columns = self.sortable_columns
        else:
            self.copy_columns = tuple(dict.fromkeys(str(item) for item in copy_columns))
        self.sort_column: str | None = None
        self.sort_descending = False
        self._heading_text: dict[str, str] = {}
        self._menu = tk.Menu(tree, tearoff=False)
        self._menu.add_command(label="Copy selected row(s)", command=self.copy_selected)

        for column in self.sortable_columns:
            try:
                label = str(tree.heading(column, "text") or column)
            except tk.TclError:
                continue
            self._heading_text[column] = label
            tree.heading(
                column,
                text=label,
                command=lambda selected=column: self.sort_by(selected),
            )

        tree.bind("<Control-c>", self._copy_event, add="+")
        tree.bind("<Control-C>", self._copy_event, add="+")
        tree.bind("<Button-3>", self._context_menu, add="+")

    def _copy_event(self, _event=None):
        self.copy_selected()
        return "break"

    def _context_menu(self, event: tk.Event):
        iid = self.tree.identify_row(event.y)
        if iid:
            selection = set(self.tree.selection())
            if iid not in selection:
                self.tree.selection_set(iid)
                self.tree.focus(iid)
        if not self.tree.selection():
            return None
        try:
            self._menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._menu.grab_release()
        return "break"

    def _ordered_children(self) -> list[str]:
        return list(self.tree.get_children(self.parent))

    def sort_by(self, column: str) -> None:
        if column not in self.sortable_columns:
            return
        if column == self.sort_column:
            self.sort_descending = not self.sort_descending
        else:
            self.sort_column = column
            self.sort_descending = False
        self.reapply_sort()

    def reapply_sort(self) -> None:
        column = self.sort_column
        if column is None or column not in self.sortable_columns:
            self._refresh_headings()
            return

        children = self._ordered_children()
        populated: list[tuple[tuple[int, Any], int, str]] = []
        missing: list[tuple[int, str]] = []
        for index, iid in enumerate(children):
            raw = treeview_cell_text(self.tree, iid, column)
            key = table_value_sort_key(raw)
            if key[0] == 2:
                missing.append((index, iid))
            else:
                populated.append((key, index, iid))

        populated.sort(
            key=lambda item: (item[0], item[1]),
            reverse=self.sort_descending,
        )
        ordered = [iid for _key, _index, iid in populated]
        ordered.extend(iid for _index, iid in missing)
        for index, iid in enumerate(ordered):
            self.tree.move(iid, self.parent, index)
        self._refresh_headings()

    def _refresh_headings(self) -> None:
        for column, label in self._heading_text.items():
            marker = ""
            if column == self.sort_column:
                marker = " ▼" if self.sort_descending else " ▲"
            try:
                self.tree.heading(column, text=label + marker)
            except tk.TclError:
                continue

    def selected_tsv(self) -> str:
        rows: list[str] = []
        for iid in self.tree.selection():
            if not self.tree.exists(iid):
                continue
            values = [
                treeview_cell_text(self.tree, iid, column)
                for column in self.copy_columns
            ]
            rows.append("\t".join(value.replace("\t", " ").replace("\n", " ") for value in values))
        return "\n".join(rows)

    def copy_selected(self) -> bool:
        payload = self.selected_tsv()
        if not payload:
            return False
        try:
            self.tree.clipboard_clear()
            self.tree.clipboard_append(payload)
        except tk.TclError:
            return False
        return True
