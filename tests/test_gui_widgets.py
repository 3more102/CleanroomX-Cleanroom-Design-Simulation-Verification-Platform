from __future__ import annotations

from cleanroomx.gui_widgets import engineering_sort_key


def test_engineering_sort_key_orders_numeric_values_numerically():
    values = ["10", "2", "1.5", "-3"]
    assert sorted(values, key=engineering_sort_key) == ["-3", "1.5", "2", "10"]


def test_engineering_sort_key_prioritizes_diagnostic_severity():
    values = ["PASS", "INFO", "WARNING", "ERROR"]
    assert sorted(values, key=engineering_sort_key) == [
        "ERROR",
        "WARNING",
        "INFO",
        "PASS",
    ]


def test_engineering_sort_key_falls_back_to_case_insensitive_text():
    values = ["Zone B", "zone a", "Room"]
    assert sorted(values, key=engineering_sort_key) == [
        "Room",
        "zone a",
        "Zone B",
    ]
