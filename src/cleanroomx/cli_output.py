from __future__ import annotations

import json
from typing import Any

from .strict_json import clone_strict_json


def dumps_strict_json(
    value: Any,
    *,
    indent: int | None = 2,
    sort_keys: bool = False,
) -> str:
    """Serialize a CleanroomX CLI payload as standards-compliant strict JSON.

    The shared strict clone rejects non-finite floats, non-string object keys,
    cyclic references, invalid UTF-8 text, and Python-only container/value
    types before serialization. allow_nan=False remains explicit as a final
    encoder-side guard.
    """

    payload = clone_strict_json(value)
    return json.dumps(
        payload,
        indent=indent,
        sort_keys=sort_keys,
        ensure_ascii=False,
        allow_nan=False,
    )
