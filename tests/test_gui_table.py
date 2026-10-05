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


def test_table_behavior_supports_custom_sort_keys(root) -> None:
    tree = _tree(root)
    behavior = TreeviewTableBehavior(
        tree,
        sortable_columns=("name", "value"),
        sort_key_by_column={
            "name": lambda value: (
                0,
                {"Missing": 0, "Beta": 1, "Alpha": 2}[value],
            )
        },
    )

    behavior.sort_by("name")
    assert tree.get_children("") == ("missing", "b", "a")

    behavior.sort_by("name")
    assert tree.get_children("") == ("a", "b", "missing")


def test_table_behavior_reset_column_layout_restores_visibility_and_widths(root) -> None:
    tree = _tree(root)
    behavior = TreeviewTableBehavior(
        tree,
        sortable_columns=("name", "value"),
    )
    original_name_width = int(tree.column("name", "width"))

    assert behavior.set_column_visible("value", False) is True
    tree.column("name", width=333)
    behavior.reset_column_layout()

    assert behavior.visible_columns() == ("name", "value")
    assert int(tree.column("name", "width")) == original_name_width


def test_table_behavior_select_all_event_selects_rows(root) -> None:
    tree = _tree(root)
    behavior = TreeviewTableBehavior(
        tree,
        sortable_columns=("name", "value"),
    )

    assert behavior._select_all_event() == "break"
    assert set(tree.selection()) == {"a", "b", "missing"}
