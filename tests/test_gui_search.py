from __future__ import annotations

from cleanroomx.gui_search import EngineeringSearchItem, filter_engineering_items


def _noop():
    return None


def test_global_engineering_search_matches_all_query_tokens():
    items = [
        EngineeringSearchItem(
            id="room-a",
            label="Room A",
            category="Model / Project",
            context="Level 01",
            callback=_noop,
            keywords=("ISO 7", "supply"),
        ),
        EngineeringSearchItem(
            id="diag-a",
            label="pressure.rule — Pressure cascade failed",
            category="Diagnostic",
            context="Room A",
            callback=_noop,
            keywords=("error", "pressure"),
        ),
    ]

    assert [item.id for item in filter_engineering_items(items, "room level")] == [
        "room-a"
    ]
    assert [item.id for item in filter_engineering_items(items, "pressure error")] == [
        "diag-a"
    ]
    assert filter_engineering_items(items, "pressure warning") == []


def test_global_engineering_search_empty_query_preserves_source_order():
    items = [
        EngineeringSearchItem("a", "A", "Model", "", _noop),
        EngineeringSearchItem("b", "B", "Evidence", "", _noop),
    ]
    assert filter_engineering_items(items, "") == items
