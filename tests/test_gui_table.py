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


def test_table_behavior_copies_headers_and_selects_all(root) -> None:
    tree = _tree(root)
    behavior = TreeviewTableBehavior(
        tree,
        sortable_columns=("name", "value"),
        copy_columns=("name", "value"),
    )

    assert behavior.select_all() is True
    assert set(tree.selection()) == {"a", "b", "missing"}
    payload = behavior.selected_tsv(include_headers=True)
    assert payload.splitlines()[0] == "Name\tValue"
    assert "Alpha\t2" in payload
    assert "Beta\t10" in payload


def test_table_behavior_controls_column_visibility_without_hiding_everything(root) -> None:
    tree = _tree(root)
    behavior = TreeviewTableBehavior(
        tree,
        sortable_columns=("name", "value"),
    )

    assert behavior.visible_columns == ("name", "value")
    assert behavior.set_column_visible("value", False) is True
    assert behavior.visible_columns == ("name",)
    assert behavior.set_column_visible("name", False) is False
    assert behavior.visible_columns == ("name",)

    behavior.show_all_columns()
    assert behavior.visible_columns == ("name", "value")


def test_table_behavior_autosizes_visible_columns_with_bounds(root) -> None:
    tree = _tree(root)
    behavior = TreeviewTableBehavior(
        tree,
        sortable_columns=("name", "value"),
    )
    tree.insert("", "end", iid="long", values=("Very long engineering row label", "123456789"))

    behavior.autosize_columns(min_width=80, max_width=180, padding=20)

    assert 80 <= int(tree.column("name", "width")) <= 180
    assert 80 <= int(tree.column("value", "width")) <= 180


def test_table_behavior_rejects_invalid_autosize_bounds(root) -> None:
    tree = _tree(root)
    behavior = TreeviewTableBehavior(
        tree,
        sortable_columns=("name", "value"),
    )

    with pytest.raises(ValueError, match="invalid autosize bounds"):
        behavior.autosize_columns(min_width=100, max_width=90)
