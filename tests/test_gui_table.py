from __future__ import annotations

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
        ("Alpha", (1, ((1, "alpha"),))),
        ("—", (2, "")),
        ("", (2, "")),
    ),
)
def test_table_value_sort_key(value, expected) -> None:
    assert table_value_sort_key(value) == expected


def test_table_value_sort_key_keeps_nonfinite_textual() -> None:
    assert table_value_sort_key(math.inf) == (1, ((1, "inf"),))
    assert table_value_sort_key(math.nan) == (1, ((1, "nan"),))


def test_table_value_sort_key_uses_natural_text_order_and_missing_unknown() -> None:
    assert table_value_sort_key("Zone 2") < table_value_sort_key("Zone 10")
    assert table_value_sort_key("unknown") == (2, "")


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


def test_table_behavior_copies_selected_rows_as_tsv(root) -> None:
    tree = _tree(root)
    behavior = TreeviewTableBehavior(
        tree,
        sortable_columns=("name", "value"),
        copy_columns=("name", "value"),
    )
    tree.selection_set(("a", "b"))
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

def test_table_behavior_keeps_equal_values_stable_when_descending(root) -> None:
    tree = ttk.Treeview(
        root,
        columns=("name", "state"),
        show="headings",
        selectmode="extended",
    )
    tree.heading("name", text="Name")
    tree.heading("state", text="State")
    tree.insert("", "end", iid="a", values=("A", "Pass"))
    tree.insert("", "end", iid="b", values=("B", "Pass"))
    tree.insert("", "end", iid="c", values=("C", "Warning"))
    behavior = TreeviewTableBehavior(
        tree,
        sortable_columns=("name", "state"),
    )

    behavior.sort_by("state")
    behavior.sort_by("state")
    assert tree.get_children("") == ("c", "a", "b")

