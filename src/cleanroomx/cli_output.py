from __future__ import annotations

import json
import math
from typing import Any

from .strict_json import StrictJSONError


def _validate_cli_json_value(
    value: Any,
    *,
    path: str = "$",
    ancestors: set[int] | None = None,
) -> None:
    """Validate CLI JSON hazards while preserving existing JSON-compatible containers."""

    if isinstance(value, float):
        if not math.isfinite(value):
            raise StrictJSONError(f"{path} contains a non-finite number")
        return
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise StrictJSONError(f"{path} must contain valid UTF-8 text") from exc
        return

    if ancestors is None:
        ancestors = set()

    if isinstance(value, dict):
        marker = id(value)
        if marker in ancestors:
            raise StrictJSONError(f"{path} contains a cyclic reference")
        ancestors.add(marker)
        try:
            for key, item in value.items():
                if isinstance(key, str):
                    try:
                        key.encode("utf-8")
                    except UnicodeEncodeError as exc:
                        raise StrictJSONError(
                            f"{path} contains an object key with invalid UTF-8 text"
                        ) from exc
                    child_path = f"{path}.{key}" if key.isidentifier() else f"{path}[{key!r}]"
                else:
                    child_path = f"{path}[{key!r}]"
                _validate_cli_json_value(
                    item,
                    path=child_path,
                    ancestors=ancestors,
                )
        finally:
            ancestors.remove(marker)
        return

    if isinstance(value, (list, tuple)):
        marker = id(value)
        if marker in ancestors:
            raise StrictJSONError(f"{path} contains a cyclic reference")
        ancestors.add(marker)
        try:
            for index, item in enumerate(value):
                _validate_cli_json_value(
                    item,
                    path=f"{path}[{index}]",
                    ancestors=ancestors,
                )
        finally:
            ancestors.remove(marker)


def dumps_strict_json(
    value: Any,
    *,
    indent: int | None = 2,
    sort_keys: bool = False,
) -> str:
    """Serialize a CLI result as standards-compliant JSON without NaN/Infinity."""

    _validate_cli_json_value(value)
    try:
        return json.dumps(
            value,
            indent=indent,
            sort_keys=sort_keys,
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise StrictJSONError(
            f"$ cannot be serialized as strict JSON: {exc}"
        ) from exc
