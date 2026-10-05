from __future__ import annotations

import math
from typing import Any, Iterable

import tkinter as tk
import tkinter.font as tkfont
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


def _treeview_columns(tree: ttk.Treeview) -> tuple[str, ...]:
    return tuple(str(column) for column in tree.cget("columns"))


def _treeview_display_columns(tree: ttk.Treeview) -> tuple[str, ...]:
    columns = _treeview_columns(tree)
    configured = tree.cget("displaycolumns")
    if configured in ("#all", ("#all",)):
        return columns
    if isinstance(configured, str):
        configured = tree.tk.splitlist(configured)
    visible = tuple(str(column) for column in configured)
    return tuple(column for column in columns if column in visible)


class TreeviewTableBehavior:
    """Shared professional behavior for flat, read-only engineering tables.

    This helper changes presentation order, visible columns, selection, sizing,
    and clipboard output only. It never mutates the backing engineering records
    represented by a Treeview.
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
        self.columns = _treeview_columns(tree)
        self.sortable_columns = tuple(
            dict.fromkeys(str(item) for item in sortable_columns)
        )
        if copy_columns is None:
            self.copy_columns = self.sortable_columns
        else:
            self.copy_columns = tuple(
                dict.fromkeys(str(item) for item in copy_columns)
            )
        self.sort_column: str | None = None
        self.sort_descending = False
        self._heading_text: dict[str, str] = {}
        self._column_vars: dict[str, tk.BooleanVar] = {}

        self._menu = tk.Menu(tree, tearoff=False)
        self._menu.add_command(
            label="Copy selected row(s)",
            accelerator="Ctrl+C",
            command=self.copy_selected,
        )
        self._menu.add_command(
            label="Copy with headers",
            accelerator="Ctrl+Shift+C",
            command=lambda: self.copy_selected(include_headers=True),
        )
        self._menu.add_command(
            label="Select all rows",
            accelerator="Ctrl+A",
            command=self.select_all,
        )
        self._menu.add_separator()
        self._menu.add_command(
            label="Autosize columns",
            command=self.autosize_columns,
        )
        self._columns_menu = tk.Menu(self._menu, tearoff=False)
        self._menu.add_cascade(label="Columns", menu=self._columns_menu)

        for column in self.columns:
            try:
                label = str(tree.heading(column, "text") or column)
            except tk.TclError:
                label = column
            self._heading_text[column] = label

        for column in self.sortable_columns:
            if column not in self.columns:
                continue
            label = self._heading_text.get(column, column)
            tree.heading(
                column,
                text=label,
                command=lambda selected=column: self.sort_by(selected),
            )

        self._build_columns_menu()

        tree.bind("<Control-c>", self._copy_event, add="+")
        tree.bind("<Control-C>", self._copy_event, add="+")
        tree.bind("<Control-Shift-c>", self._copy_headers_event, add="+")
        tree.bind("<Control-Shift-C>", self._copy_headers_event, add="+")
        tree.bind("<Control-a>", self._select_all_event, add="+")
        tree.bind("<Control-A>", self._select_all_event, add="+")
        tree.bind("<Button-3>", self._context_menu, add="+")

    @property
    def visible_columns(self) -> tuple[str, ...]:
        return _treeview_display_columns(self.tree)

    def _build_columns_menu(self) -> None:
        self._columns_menu.delete(0, "end")
        visible = set(self.visible_columns)
        self._column_vars.clear()
        for column in self.columns:
            variable = tk.BooleanVar(
                master=self.tree,
                value=column in visible,
            )
            self._column_vars[column] = variable
            self._columns_menu.add_checkbutton(
                label=self._heading_text.get(column, column),
                variable=variable,
                command=lambda selected=column: self._column_visibility_requested(
                    selected
                ),
            )
        self._columns_menu.add_separator()
        self._columns_menu.add_command(
            label="Show all columns",
            command=self.show_all_columns,
        )

    def _column_visibility_requested(self, column: str) -> None:
        variable = self._column_vars.get(column)
        if variable is None:
            return
        if not self.set_column_visible(column, bool(variable.get())):
            variable.set(True)

    def _copy_event(self, _event=None):
        self.copy_selected()
        return "break"

    def _copy_headers_event(self, _event=None):
        self.copy_selected(include_headers=True)
        return "break"

    def _select_all_event(self, _event=None):
        self.select_all()
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

    def set_column_visible(self, column: str, visible: bool) -> bool:
        """Show or hide one data column while always retaining one visible column."""
        if column not in self.columns:
            return False
        current = list(self.visible_columns)
        if visible:
            if column not in current:
                selected = set(current)
                selected.add(column)
                current = [item for item in self.columns if item in selected]
        else:
            if column not in current:
                return True
            if len(current) <= 1:
                return False
            current.remove(column)

        self.tree.configure(displaycolumns=tuple(current))
        variable = self._column_vars.get(column)
        if variable is not None:
            variable.set(column in current)
        return True

    def show_all_columns(self) -> None:
        self.tree.configure(displaycolumns="#all")
        for variable in self._column_vars.values():
            variable.set(True)

    def autosize_columns(
        self,
        *,
        min_width: int = 72,
        max_width: int = 420,
        padding: int = 24,
    ) -> None:
        """Size visible data columns from current presentation text.

        Measurement is bounded so a single unusually long evidence string cannot
        make the rest of the engineering table unusable.
        """
        if min_width <= 0 or max_width < min_width or padding < 0:
            raise ValueError("invalid autosize bounds")

        try:
            font = tkfont.nametofont("TkDefaultFont")
        except tk.TclError:
            font = tkfont.Font(master=self.tree)

        children = self._ordered_children()
        for column in self.visible_columns:
            label = self._heading_text.get(column, column)
            width = font.measure(label) + padding
            for iid in children:
                width = max(
                    width,
                    font.measure(treeview_cell_text(self.tree, iid, column)) + padding,
                )
                if width >= max_width:
                    width = max_width
                    break
            configured_min = int(self.tree.column(column, "minwidth") or 0)
            width = max(min_width, configured_min, min(max_width, width))
            self.tree.column(column, width=width)

    def select_all(self) -> bool:
        children = self._ordered_children()
        if not children:
            return False
        self.tree.selection_set(children)
        self.tree.focus(children[0])
        return True

    def selected_tsv(self, *, include_headers: bool = False) -> str:
        rows: list[str] = []
        if include_headers:
            rows.append(
                "\t".join(
                    self._heading_text.get(column, column)
                    .replace("\t", " ")
                    .replace("\n", " ")
                    for column in self.copy_columns
                )
            )
        for iid in self.tree.selection():
            if not self.tree.exists(iid):
                continue
            values = [
                treeview_cell_text(self.tree, iid, column)
                for column in self.copy_columns
            ]
            rows.append(
                "\t".join(
                    value.replace("\t", " ").replace("\n", " ")
                    for value in values
                )
            )
        if include_headers and len(rows) == 1:
            return ""
        return "\n".join(rows)

    def copy_selected(self, *, include_headers: bool = False) -> bool:
        payload = self.selected_tsv(include_headers=include_headers)
        if not payload:
            return False
        try:
            self.tree.clipboard_clear()
            self.tree.clipboard_append(payload)
        except tk.TclError:
            return False
        return True
