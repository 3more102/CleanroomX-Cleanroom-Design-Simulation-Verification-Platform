from __future__ import annotations

import json
import math
from typing import Any

from .strict_json import StrictJSONError


def _clone_cli_json_value(
    value: Any,
    *,
    path: str = "$",
    ancestors: set[int] | None = None,
) -> Any:
    """Normalize a result to plain strict-JSON containers without silent coercions."""
    if value is None:
        return None
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        number = float(value)
        if not math.isfinite(number):
            raise StrictJSONError(f"{path} contains a non-finite number")
        return number
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise StrictJSONError(f"{path} must contain valid UTF-8 text") from exc
        return str(value)

    if ancestors is None:
        ancestors = set()

    if isinstance(value, dict):
        marker = id(value)
        if marker in ancestors:
            raise StrictJSONError(f"{path} contains a cyclic reference")
        ancestors.add(marker)
        try:
            cloned: dict[str, Any] = {}
            for key, item in value.items():
                if not isinstance(key, str):
                    raise StrictJSONError(
                        f"{path} contains a non-string object key: {key!r}"
                    )
                try:
                    key.encode("utf-8")
                except UnicodeEncodeError as exc:
                    raise StrictJSONError(
                        f"{path} contains an object key with invalid UTF-8 text"
                    ) from exc
                child_path = (
                    f"{path}.{key}"
                    if key.isidentifier()
                    else f"{path}[{key!r}]"
                )
                cloned[str(key)] = _clone_cli_json_value(
                    item,
                    path=child_path,
                    ancestors=ancestors,
                )
            return cloned
        finally:
            ancestors.remove(marker)

    if isinstance(value, (list, tuple)):
        marker = id(value)
        if marker in ancestors:
            raise StrictJSONError(f"{path} contains a cyclic reference")
        ancestors.add(marker)
        try:
            return [
                _clone_cli_json_value(
                    item,
                    path=f"{path}[{index}]",
                    ancestors=ancestors,
                )
                for index, item in enumerate(value)
            ]
        finally:
            ancestors.remove(marker)

    raise StrictJSONError(
        f"{path} contains non-JSON value of type {type(value).__name__}"
    )


def dumps_strict_json(
    value: Any,
    *,
    indent: int | None = 2,
    sort_keys: bool = False,
) -> str:
    """Serialize CLI results as standards-compliant JSON with no NaN/Infinity."""
    try:
        snapshot = _clone_cli_json_value(value)
        return json.dumps(
            snapshot,
            indent=indent,
            sort_keys=sort_keys,
            ensure_ascii=False,
            allow_nan=False,
        )
    except StrictJSONError:
        raise
    except (TypeError, ValueError, RecursionError) as exc:
        raise StrictJSONError(
            f"$ cannot be serialized as strict JSON: {exc}"
        ) from exc
