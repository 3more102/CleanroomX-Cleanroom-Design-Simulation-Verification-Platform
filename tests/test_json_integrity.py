from __future__ import annotations

import json

import pytest

from cleanroomx.json_integrity import (
    DuplicateJSONKeyError,
    NonFiniteJSONNumberError,
    load_json_file,
    strict_json_loads,
)


def test_strict_json_loads_preserves_valid_nested_json():
    value = strict_json_loads(
        '{"room":{"name":"A","length_m":5.0},"enabled":true,"items":[1,2,null]}'
    )
    assert value == {
        "room": {"name": "A", "length_m": 5.0},
        "enabled": True,
        "items": [1, 2, None],
    }


@pytest.mark.parametrize(
    "payload",
    [
        '{"value":1,"value":2}',
        '{"outer":{"pressure_pa":10,"pressure_pa":20}}',
    ],
)
def test_strict_json_loads_rejects_duplicate_keys_at_any_depth(payload):
    with pytest.raises(DuplicateJSONKeyError, match="duplicate JSON object key"):
        strict_json_loads(payload)


@pytest.mark.parametrize(
    "payload",
    [
        '{"value":NaN}',
        '{"value":Infinity}',
        '{"value":-Infinity}',
        '{"value":1e400}',
    ],
)
def test_strict_json_loads_rejects_all_non_finite_numbers(payload):
    with pytest.raises(NonFiniteJSONNumberError, match="non-finite JSON number"):
        strict_json_loads(payload)


def test_strict_json_loads_preserves_json_syntax_errors():
    with pytest.raises(json.JSONDecodeError):
        strict_json_loads('{"value":')


def test_load_json_file_uses_same_integrity_rules(tmp_path):
    path = tmp_path / "input.json"
    path.write_text('{"x":1,"x":2}', encoding="utf-8")

    with pytest.raises(DuplicateJSONKeyError):
        load_json_file(path)
