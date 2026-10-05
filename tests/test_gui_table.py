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
        ("unknown", (2, "")),
    ),
)
def test_table_value_sort_key(value, expected) -> None:
    assert table_value_sort_key(value) == expected


def test_table_value_sort_key_keeps_nonfinite_textual_and_uses_natural_order() -> None:
    assert table_value_sort_key(math.inf) == (1, ((1, "inf"),))
    assert table_value_sort_key(math.nan) == (1, ((1, "nan"),))
    assert table_value_sort_key("Zone 2") < table_value_sort_key("Zone 10")


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


def test_table_behavior_copies_headers_selects_all_and_supports_columns(root) -> None:
    tree = _tree(root)
    behavior = TreeviewTableBehavior(
        tree,
        sortable_columns=("name", "value"),
        copy_columns=("name", "value"),
    )

    assert behavior.select_all()
    assert behavior.selected_tsv(include_headers=True) == (
        "Name\tValue\nBeta\t10\nMissing\t—\nAlpha\t2"
    )
    assert behavior.set_column_visible("value", False)
    assert behavior.visible_columns() == ("name",)
    assert not behavior.set_column_visible("name", False)
    assert behavior.set_column_visible("value", True)
    assert behavior.set_column_order(("value", "name"))
    assert behavior.move_column("value", 1)
    assert behavior.visible_columns() == ("name", "value")
    behavior.reset_column_layout()
    assert behavior.visible_columns() == ("name", "value")


def test_table_behavior_layout_state_round_trips_visibility_order_and_widths(root) -> None:
    tree = _tree(root)
    tree.column("name", width=180)
    tree.column("value", width=120)
    changes = []
    behavior = TreeviewTableBehavior(
        tree,
        sortable_columns=("name", "value"),
        on_layout_change=lambda state: changes.append(state),
    )

    assert behavior.set_column_order(("value", "name"))
    assert changes[-1]["visible_columns"] == ["value", "name"]
    tree.column("value", width=345)
    saved = behavior.layout_state()
    assert saved["widths"]["value"] == 345

    restored_tree = _tree(root)
    restored_tree.column("name", width=210)
    restored_tree.column("value", width=160)
    restored = TreeviewTableBehavior(
        restored_tree,
        sortable_columns=("name", "value"),
        layout_state=saved,
    )
    assert restored.visible_columns() == ("value", "name")
    assert int(restored_tree.column("value", "width")) == 345

    restored.reset_column_layout()
    assert restored.visible_columns() == ("name", "value")
    assert int(restored_tree.column("name", "width")) == 210
    assert int(restored_tree.column("value", "width")) == 160


def test_table_behavior_layout_state_includes_tree_column_width(root) -> None:
    tree = ttk.Treeview(
        root,
        columns=("state",),
        show="tree headings",
    )
    tree.heading("#0", text="Task")
    tree.heading("state", text="State")
    tree.column("#0", width=275)
    tree.column("state", width=115)

    behavior = TreeviewTableBehavior(tree, sortable_columns=("#0", "state"))

    assert behavior.layout_state()["widths"] == {"#0": 275, "state": 115}


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
    behavior = TreeviewTableBehavior(tree, sortable_columns=("name", "state"))

    behavior.sort_by("state")
    behavior.sort_by("state")
    assert tree.get_children("") == ("c", "a", "b")


def test_table_behavior_supports_domain_specific_sort_key(root) -> None:
    tree = ttk.Treeview(
        root,
        columns=("severity",),
        show="headings",
        selectmode="extended",
    )
    tree.heading("severity", text="Severity")
    tree.insert("", "end", iid="info", values=("INFO",))
    tree.insert("", "end", iid="error", values=("ERROR",))
    tree.insert("", "end", iid="warning", values=("WARNING",))
    rank = {"error": 0, "warning": 1, "info": 2}
    behavior = TreeviewTableBehavior(
        tree,
        sortable_columns=("severity",),
        sort_key_overrides={
            "severity": lambda raw: (0, rank.get(raw.casefold(), 99))
        },
    )

    behavior.sort_by("severity")
    assert tree.get_children("") == ("error", "warning", "info")


def test_table_behavior_optional_bindings_preserve_screen_specific_handlers(root) -> None:
    tree = _tree(root)
    behavior = TreeviewTableBehavior(
        tree,
        sortable_columns=("name", "value"),
        bind_copy=False,
        bind_context_menu=False,
    )

    assert "_copy_event" not in str(tree.bind("<Control-c>"))
    assert "_context_menu" not in str(tree.bind("<Button-3>"))
    behavior.prepare_columns_menu()
    assert behavior.columns_menu.winfo_exists()
