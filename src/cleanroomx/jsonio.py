from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


def _reject_non_finite_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is not allowed: {value}")


def _parse_finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"JSON number is outside finite float range: {value}")
    return parsed


def strict_json_loads(text: str) -> Any:
    """Parse JSON without admitting non-finite runtime numeric values."""
    return json.loads(
        text,
        parse_constant=_reject_non_finite_constant,
        parse_float=_parse_finite_float,
    )


def load_strict_json(path: str | Path) -> Any:
    """Read UTF-8 JSON from *path* without accepting non-finite constants."""
    source = Path(path)
    return strict_json_loads(source.read_text(encoding="utf-8"))


def strict_json_dumps(value: Any, **kwargs: Any) -> str:
    """Serialize strict JSON and never emit NaN/Infinity tokens."""
    options = dict(kwargs)
    options["allow_nan"] = False
    return json.dumps(value, **options)
