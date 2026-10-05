from __future__ import annotations

import copy

import pytest

from cleanroomx.gui import (
    replace_structured_json_value,
    structured_json_entries,
)


def test_structured_json_entries_preserve_unambiguous_nested_edit_tokens() -> None:
    payload = {
        "room": {
            "name": "Process",
            "dimensions_m": [6.0, 5.0, 3.0],
            "enabled": True,
        },
        "notes": None,
    }

    rows = structured_json_entries(payload)
    by_path = {path: (tokens, value, unit) for path, tokens, value, unit in rows}

    assert by_path["$.room.name"][:2] == (("room", "name"), "Process")
    assert by_path["$.room.dimensions_m[1]"][:2] == (
        ("room", "dimensions_m", 1),
        5.0,
    )
    assert by_path["$.room.enabled"][:2] == (("room", "enabled"), True)
    assert by_path["$.notes"][:2] == (("notes",), None)


def test_replace_structured_json_value_is_detached_and_changes_one_scalar() -> None:
    payload = {
        "rooms": [
            {"name": "Process", "min_ach": 20.0},
            {"name": "Ante", "min_ach": 10.0},
        ]
    }
    before = copy.deepcopy(payload)

    updated = replace_structured_json_value(
        payload,
        ("rooms", 0, "min_ach"),
        25.0,
    )

    assert payload == before
    assert updated["rooms"][0]["min_ach"] == 25.0
    assert updated["rooms"][1]["min_ach"] == 10.0


@pytest.mark.parametrize(
    ("tokens", "replacement", "match"),
    [
        ((), 1, "root cannot be replaced"),
        (("rooms", 9, "min_ach"), 1, "path no longer exists"),
        (("rooms", 0), 1, "scalar leaves only"),
        (("rooms", 0, "min_ach"), {"unsafe": "container"}, "scalar JSON values only"),
    ],
)
def test_replace_structured_json_value_rejects_unsafe_paths_and_containers(
    tokens,
    replacement,
    match,
) -> None:
    payload = {"rooms": [{"min_ach": 20.0}]}

    with pytest.raises(ValueError, match=match):
        replace_structured_json_value(payload, tokens, replacement)
