from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


class StrictJSONError(ValueError):
    """Raised when a value cannot be represented as deterministic strict JSON."""


def _json_child_path(path: str, key: str) -> str:
    if key.isidentifier():
        return f"{path}.{key}"
    return f"{path}[{json.dumps(key, ensure_ascii=True)}]"


def _validate_json_string(value: str, path: str) -> str:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise StrictJSONError(f"{path} must contain valid UTF-8 text") from exc
    return value


def clone_strict_json(
    value: Any,
    *,
    path: str = "$",
    ancestors: set[int] | None = None,
) -> Any:
    """Return a detached strict-JSON snapshot without Python-side coercions."""
    if value is None:
        return None
    if type(value) is bool:
        return value
    if type(value) is int:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise StrictJSONError(f"{path} contains a non-finite number")
        return value
    if type(value) is str:
        return _validate_json_string(value, path)

    if ancestors is None:
        ancestors = set()

    if type(value) is list:
        marker = id(value)
        if marker in ancestors:
            raise StrictJSONError(f"{path} contains a cyclic reference")
        ancestors.add(marker)
        try:
            return [
                clone_strict_json(
                    item,
                    path=f"{path}[{index}]",
                    ancestors=ancestors,
                )
                for index, item in enumerate(value)
            ]
        finally:
            ancestors.remove(marker)

    if type(value) is dict:
        marker = id(value)
        if marker in ancestors:
            raise StrictJSONError(f"{path} contains a cyclic reference")
        ancestors.add(marker)
        try:
            cloned: dict[str, Any] = {}
            for key, item in value.items():
                if type(key) is not str:
                    raise StrictJSONError(
                        f"{path} must contain only string object keys; "
                        f"got {type(key).__name__}"
                    )
                _validate_json_string(key, f"{path} object key")
                cloned[key] = clone_strict_json(
                    item,
                    path=_json_child_path(path, key),
                    ancestors=ancestors,
                )
            return cloned
        finally:
            ancestors.remove(marker)

    raise StrictJSONError(
        f"{path} contains non-JSON value of type {type(value).__name__}"
    )


def _reject_json_constant(value: str) -> None:
    raise StrictJSONError(f"non-finite JSON constant is not allowed: {value}")


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StrictJSONError(
                f"duplicate JSON object key {key!r} is not allowed"
            )
        result[key] = value
    return result


def strict_json_loads(text: str) -> Any:
    """Parse strict JSON and normalize excessive nesting to StrictJSONError."""
    try:
        value = json.loads(
            text,
            parse_constant=_reject_json_constant,
            object_pairs_hook=_object_without_duplicate_keys,
        )
        return clone_strict_json(value)
    except RecursionError as exc:
        raise StrictJSONError(
            "JSON nesting exceeds the supported parser/validation depth"
        ) from exc


def load_strict_json(path: str | Path) -> Any:
    """Read a UTF-8 JSON file through the canonical strict parser."""
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise StrictJSONError(
            f"{source} must contain valid UTF-8 JSON text"
        ) from exc
    return strict_json_loads(text)
