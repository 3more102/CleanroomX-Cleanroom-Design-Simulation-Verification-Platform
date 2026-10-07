from __future__ import annotations

import copy
import math
import os
import tkinter as tk
from tkinter import ttk

import pytest

from cleanroomx.gui_table import TreeviewTableBehavior, table_value_sort_key


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        ("1,250", (0, 1250.0)),
        ("12.5%", (0, 12.5)),
        ("Alpha", (1, "alpha")),
        ("—", (2, "")),
        ("", (2, "")),
    ),
)
def test_table_value_sort_key(value, expected) -> None:
    assert table_value_sort_key(value) == expected


def test_table_value_sort_key_keeps_nonfinite_textual() -> None:
    assert table_value_sort_key(math.inf) == (1, "inf")
    assert table_value_sort_key(math.nan) == (1, "nan")


@pytest.mark.parametrize(
    ("lower", "higher"),
    [("9007199254740992", "9007199254740993"),
     ("1.00000000000000001", "1.00000000000000002"),
     ("1e400", "2e400")],
)
def test_numeric_sort_preserves_displayed_precision(lower, higher) -> None:
    assert table_value_sort_key(lower) < table_value_sort_key(higher)


class _HeadlessTree:
    def __init__(self, rows, selected=()):
        self.rows = rows
        self.order = list(rows)
        self.selected = tuple(selected)
        self.labels = {"name": "Name", "value": "Value"}

    def get_children(self, _parent=""):
        return tuple(self.order)

    def set(self, iid, column):
        return self.rows[iid][column]

    def move(self, iid, _parent, index):
        self.order.remove(iid)
        self.order.insert(index, iid)

    def heading(self, column, option=None, **kwargs):
        if "text" in kwargs:
            self.labels[column] = kwargs["text"]
        return self.labels[column]

    def selection(self):
        return self.selected

    def selection_set(self, selected):
        self.selected = tuple(selected)

    def exists(self, iid):
        return iid in self.rows


def _headless_behavior(tree):
    behavior = object.__new__(TreeviewTableBehavior)
    behavior.tree = tree
    behavior.parent = ""
    behavior.sortable_columns = ("name", "value")
    behavior.copy_columns = ("name", "value")
    behavior.sort_column = None
    behavior.sort_descending = False
    behavior._heading_text = {"name": "Name", "value": "Value"}
    return behavior


def test_descending_refresh_is_stable_for_equal_rows_without_changing_data() -> None:
    rows = {
        "first": {"name": "First", "value": "10"},
        "second": {"name": "Second", "value": "10.0"},
        "lower": {"name": "Lower", "value": "2"},
        "missing": {"name": "Missing", "value": "—"},
    }
    tree = _HeadlessTree(rows)
    before = copy.deepcopy(rows)
    behavior = _headless_behavior(tree)
    behavior.sort_by("value")
    behavior.sort_by("value")
    expected = ("first", "second", "lower", "missing")
    assert tree.get_children() == expected
    behavior.reapply_sort()
    behavior.reapply_sort()
    assert tree.get_children() == expected
    assert tree.rows == before


def test_copy_follows_visible_row_order_and_contains_line_breaks() -> None:
    tree = _HeadlessTree(
        {"a": {"name": "A\r\nline", "value": "2"},
         "b": {"name": "B\tline", "value": "10"}},
        selected=("a", "missing-row", "b"),
    )
    behavior = _headless_behavior(tree)
    behavior.sort_by("value")
    behavior.sort_by("value")
    behavior._heading_text["name"] = "Na\rme"
    assert behavior.selected_tsv(include_headers=True) == (
        "Na me\tValue\nB line\t10\nA  line\t2"
    )
    assert behavior._select_all_event() == "break"
    assert tree.selection() == ("b", "a")


@pytest.fixture
def root():
    try:
        window = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    window.withdraw()
    try:
        yield window
    finally:
        window.destroy()


def _tree(root: tk.Tk) -> ttk.Treeview:
    tree = ttk.Treeview(
        root,
        columns=("name", "value"),
        show="headings",
        selectmode="extended",
    )
    tree.heading("name", text="Name")
    tree.heading("value", text="Value")
    tree.insert("", "end", iid="b", values=("Beta", "10"))
    tree.insert("", "end", iid="missing", values=("Missing", "—"))
    tree.insert("", "end", iid="a", values=("Alpha", "2"))
    return tree


def test_table_behavior_sorts_flat_rows_and_keeps_missing_last(root) -> None:
    tree = _tree(root)
    behavior = TreeviewTableBehavior(
        tree,
        sortable_columns=("name", "value"),
    )

    behavior.sort_by("value")
    assert tree.get_children("") == ("a", "b", "missing")
    assert tree.heading("value", "text").endswith("▲")

    behavior.sort_by("value")
    assert tree.get_children("") == ("b", "a", "missing")
    assert tree.heading("value", "text").endswith("▼")


def test_table_behavior_copies_selected_rows_in_visible_order_as_tsv(root) -> None:
    tree = _tree(root)
    behavior = TreeviewTableBehavior(
        tree,
        sortable_columns=("name", "value"),
        copy_columns=("name", "value"),
    )
    tree.selection_set(("a", "b"))

    # Tcl/Tk does not guarantee that selection() preserves selection_set()
    # argument order across runtime versions. Clipboard output is defined by
    # the table's visible row order instead.
    assert behavior.selected_tsv() == "Beta\t10\nAlpha\t2"

    behavior.sort_by("name")
    assert behavior.selected_tsv() == "Alpha\t2\nBeta\t10"



def test_table_behavior_can_copy_headers_and_select_all(root) -> None:
    tree = _tree(root)
    behavior = TreeviewTableBehavior(
        tree,
        sortable_columns=("name", "value"),
        copy_columns=("name", "value"),
    )

    assert behavior.select_all() is True
    assert behavior.selected_tsv(include_headers=True) == (
        "Name\tValue\nBeta\t10\nMissing\t—\nAlpha\t2"
    )


def test_table_behavior_supports_column_visibility_and_order(root) -> None:
    tree = _tree(root)
    behavior = TreeviewTableBehavior(
        tree,
        sortable_columns=("name", "value"),
    )

    assert behavior.visible_columns() == ("name", "value")
    assert behavior.set_column_visible("value", False) is True
    assert behavior.visible_columns() == ("name",)
    assert behavior.set_column_visible("name", False) is False
    assert behavior.visible_columns() == ("name",)

    assert behavior.set_column_visible("value", True) is True
    assert behavior.set_column_order(("value", "name")) is True
    assert behavior.visible_columns() == ("value", "name")

    behavior.show_all_columns()
    assert behavior.visible_columns() == ("name", "value")
