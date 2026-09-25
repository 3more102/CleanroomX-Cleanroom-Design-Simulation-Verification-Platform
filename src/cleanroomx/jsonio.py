from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


class DuplicateJSONKeyError(ValueError):
    """Raised when a JSON object contains the same member name more than once."""


def _reject_non_finite_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is not allowed: {value}")


def _parse_finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"JSON number is outside finite float range: {value}")
    return parsed


def _reject_duplicate_object_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJSONKeyError(
                f"duplicate JSON object key is not allowed: {key!r}"
            )
        result[key] = value
    return result


def strict_json_loads(text: str) -> Any:
    """Parse deterministic JSON with finite numbers and unique object member names."""
    return json.loads(
        text,
        parse_constant=_reject_non_finite_constant,
        parse_float=_parse_finite_float,
        object_pairs_hook=_reject_duplicate_object_keys,
    )


def load_strict_json(path: str | Path) -> Any:
    """Read UTF-8 JSON from *path* through the shared strict ingestion boundary."""
    source = Path(path)
    return strict_json_loads(source.read_text(encoding="utf-8"))


def strict_json_dumps(value: Any, **kwargs: Any) -> str:
    """Serialize standards-compliant JSON and never emit NaN/Infinity tokens."""
    options = dict(kwargs)
    options["allow_nan"] = False
    return json.dumps(value, **options)
