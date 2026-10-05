from __future__ import annotations

from cleanroomx.gui_table import TreeviewSortController, engineering_table_sort_value


class FakeTree:
    def __init__(self, rows):
        self._rows = {iid: {"text": text, "values": dict(values)} for iid, text, values in rows}
        self._order = [iid for iid, _text, _values in rows]
        self._selection = ()
        self._focus = ""
        self.headings = {}
        self.seen = []

    def heading(self, column, **kwargs):
        self.headings[column] = kwargs

    def selection(self):
        return self._selection

    def selection_set(self, items):
        if isinstance(items, str):
            items = (items,)
        self._selection = tuple(items)

    def focus(self, iid=None):
        if iid is None:
            return self._focus
        self._focus = iid

    def get_children(self, parent=""):
        assert parent == ""
        return tuple(self._order)

    def item(self, iid, option=None):
        if option == "text":
            return self._rows[iid]["text"]
        return self._rows[iid]

    def set(self, iid, column):
        return self._rows[iid]["values"].get(column, "")

    def move(self, iid, parent, index):
        assert parent == ""
        self._order.remove(iid)
        self._order.insert(index, iid)

    def see(self, iid):
        self.seen.append(iid)


def test_engineering_table_sort_value_numeric_and_natural_text():
    assert engineering_table_sort_value("1,200") < engineering_table_sort_value("9000")
    assert engineering_table_sort_value("Zone 2") < engineering_table_sort_value("Zone 10")
    assert engineering_table_sort_value("alpha") == engineering_table_sort_value("ALPHA")


def test_engineering_table_sort_value_marks_missing_cells():
    for value in (None, "", " — ", "N/A", "unknown"):
        assert engineering_table_sort_value(value) is None


def test_sort_controller_keeps_missing_last_and_preserves_selection_focus():
    tree = FakeTree(
        [
            ("a", "Room 10", {"value": "—"}),
            ("b", "Room 2", {"value": "20"}),
            ("c", "Room 1", {"value": "3"}),
        ]
    )
    tree.selection_set("b")
    tree.focus("b")
    controller = TreeviewSortController(
        tree,
        {"#0": "Object", "value": "Value"},
        column="value",
    )

    controller.reapply()
    assert tree.get_children() == ("c", "b", "a")
    assert tree.selection() == ("b",)
    assert tree.focus() == "b"
    assert tree.seen[-1] == "b"

    controller.sort_by("value")
    assert tree.get_children() == ("b", "c", "a")
    assert tree.headings["value"]["text"].endswith("▼")


def test_sort_controller_heading_command_switches_columns_with_natural_order():
    tree = FakeTree(
        [
            ("a", "Zone 10", {"state": "Warning"}),
            ("b", "Zone 2", {"state": "Pass"}),
            ("c", "Zone 1", {"state": "Error"}),
        ]
    )
    controller = TreeviewSortController(
        tree,
        {"#0": "Object", "state": "State"},
    )

    tree.headings["#0"]["command"]()
    assert controller.column == "#0"
    assert tree.get_children() == ("c", "b", "a")
    assert tree.headings["#0"]["text"].endswith("▲")

    tree.headings["state"]["command"]()
    assert controller.column == "state"
    assert tree.get_children() == ("c", "b", "a")
