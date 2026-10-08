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

    This helper changes only presentation order, visible columns, selection, and
    clipboard output. It never changes backing domain records represented by a
    Treeview.
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
        self.sortable_columns = tuple(
            dict.fromkeys(str(item) for item in sortable_columns)
        )
        if copy_columns is None:
            self.copy_columns = self.sortable_columns
        else:
            self.copy_columns = tuple(
                dict.fromkeys(str(item) for item in copy_columns)
            )
        self.data_columns = tuple(str(item) for item in tree["columns"])
        self._default_display_columns = self.data_columns
        self.sort_column: str | None = None
        self.sort_descending = False
        self._heading_text: dict[str, str] = {}
        self._column_vars: dict[str, tk.BooleanVar] = {}

        self._menu = tk.Menu(tree, tearoff=False)
        self._menu.add_command(
            label="Copy selected row(s)",
            command=self.copy_selected,
        )
        self._menu.add_command(
            label="Copy selected row(s) with headers",
            command=lambda: self.copy_selected(with_headers=True),
        )
        self._menu.add_command(label="Select all rows", command=self.select_all)
        self._menu.add_separator()

        self._columns_menu = tk.Menu(self._menu, tearoff=False)
        self._menu.add_cascade(label="Columns", menu=self._columns_menu)
        for column in self.data_columns:
            try:
                label = str(tree.heading(column, "text") or column)
            except tk.TclError:
                label = column
            variable = tk.BooleanVar(master=tree, value=True)
            self._column_vars[column] = variable
            self._columns_menu.add_checkbutton(
                label=label,
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
        region = self.tree.identify_region(event.x, event.y)
        if region == "heading":
            self._sync_column_vars()
        else:
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

    def _column_label(self, column: str) -> str:
        if column in self._heading_text:
            return self._heading_text[column]
        try:
            return str(self.tree.heading(column, "text") or column)
        except tk.TclError:
            return column

    def visible_columns(self) -> tuple[str, ...]:
        raw = self.tree["displaycolumns"]
        if raw == "#all" or raw == ("#all",):
            return self.data_columns
        if isinstance(raw, str):
            return (raw,) if raw else ()
        return tuple(str(item) for item in raw)

    def _sync_column_vars(self) -> None:
        visible = set(self.visible_columns())
        for column, variable in self._column_vars.items():
            variable.set(column in visible)

    def _column_visibility_requested(self, column: str) -> None:
        variable = self._column_vars.get(column)
        if variable is None:
            return
        requested = bool(variable.get())
        if not self.set_column_visible(column, requested):
            self._sync_column_vars()

    def set_column_visible(self, column: str, visible: bool) -> bool:
        if column not in self.data_columns:
            return False
        current = list(self.visible_columns())
        if visible:
            if column not in current:
                current.append(column)
        else:
            if column not in current:
                return True
            if len(current) <= 1:
                return False
            current.remove(column)
        try:
            self.tree.configure(displaycolumns=tuple(current))
        except tk.TclError:
            return False
        self._sync_column_vars()
        return True

    def set_column_order(self, columns: Iterable[str]) -> bool:
        requested = tuple(dict.fromkeys(str(item) for item in columns))
        current = self.visible_columns()
        if (
            not requested
            or set(requested) != set(current)
            or any(item not in self.data_columns for item in requested)
        ):
            return False
        try:
            self.tree.configure(displaycolumns=requested)
        except tk.TclError:
            return False
        self._sync_column_vars()
        return True

    def show_all_columns(self) -> None:
        try:
            self.tree.configure(displaycolumns=self._default_display_columns)
        except tk.TclError:
            return
        self._sync_column_vars()

    def select_all(self) -> bool:
        children = self._ordered_children()
        if not children:
            return False
        try:
            self.tree.selection_set(children)
        except tk.TclError:
            return False
        return True

    def selected_tsv(self, *, include_headers: bool = False) -> str:
        rows: list[str] = []
        if include_headers:
            rows.append(
                "\t".join(
                    self._column_label(column)
                    .replace("\t", " ")
                    .replace("\n", " ")
                    for column in self.copy_columns
                )
            )
        # ttk.Treeview.selection() ordering varies across Tcl/Tk versions.
        # Export selected rows in their current visible table order.
        selected_ids = set(self.tree.selection())
        selected_rows = []
        for iid in self._ordered_children():
            if iid not in selected_ids:
                continue
            values = [
                treeview_cell_text(self.tree, iid, column)
                for column in self.copy_columns
            ]
            selected_rows.append(
                "\t".join(
                    value.replace("\t", " ").replace("\n", " ")
                    for value in values
                )
            )
        if not selected_rows:
            return ""
        rows.extend(selected_rows)
        return "\n".join(rows)

    def copy_selected(self, *, with_headers: bool = False) -> bool:
        payload = self.selected_tsv(include_headers=with_headers)
        if not payload:
            return False
        try:
            self.tree.clipboard_clear()
            self.tree.clipboard_append(payload)
        except tk.TclError:
            return False
        return True
