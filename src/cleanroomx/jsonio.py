from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _reject_non_finite_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is not allowed: {value}")


def strict_json_loads(text: str) -> Any:
    """Parse standards-compliant JSON and reject NaN/Infinity extensions."""
    return json.loads(text, parse_constant=_reject_non_finite_constant)


def load_strict_json(path: str | Path) -> Any:
    """Read UTF-8 JSON from *path* without accepting non-finite constants."""
    source = Path(path)
    return strict_json_loads(source.read_text(encoding="utf-8"))


def strict_json_dumps(value: Any, **kwargs: Any) -> str:
    """Serialize strict JSON and never emit NaN/Infinity tokens."""
    options = dict(kwargs)
    options["allow_nan"] = False
    return json.dumps(value, **options)
