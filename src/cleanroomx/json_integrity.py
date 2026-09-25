from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


class JSONIntegrityError(ValueError):
    """Raised when JSON is syntactically valid but unsafe to interpret silently."""


class DuplicateJSONKeyError(JSONIntegrityError):
    """Raised when a JSON object repeats a key."""


class NonFiniteJSONNumberError(JSONIntegrityError):
    """Raised when JSON contains a non-finite numeric value."""


def _reject_constant(token: str):
    raise NonFiniteJSONNumberError(
        f"non-finite JSON number is not allowed: {token}"
    )


def _parse_finite_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        raise NonFiniteJSONNumberError(
            f"non-finite JSON number is not allowed: {token}"
        )
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJSONKeyError(
                f"duplicate JSON object key is not allowed: {key!r}"
            )
        result[key] = value
    return result


def strict_json_loads(text: str) -> Any:
    """Parse standards-compliant JSON without lossy or non-finite extensions.

    Python's default JSON decoder accepts NaN/Infinity and silently keeps the
    last value for duplicate object keys. Engineering inputs must fail closed
    instead because either behavior can change the interpreted data without an
    explicit operator decision.
    """

    return json.loads(
        text,
        parse_constant=_reject_constant,
        parse_float=_parse_finite_float,
        object_pairs_hook=_unique_object,
    )


def load_json_file(path: str | Path) -> Any:
    """Read one UTF-8 JSON file through the strict engineering-input decoder."""

    return strict_json_loads(Path(path).read_text(encoding="utf-8"))
