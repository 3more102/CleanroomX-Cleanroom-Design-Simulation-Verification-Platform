from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


class NonFiniteJSONError(ValueError):
    """Raised when JSON input would introduce a non-finite numeric value."""


def _reject_nonfinite_constant(value: str):
    raise NonFiniteJSONError(
        f"non-finite JSON constant is not allowed: {value}"
    )


def _parse_finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise NonFiniteJSONError(
            f"JSON number is outside the finite floating-point range: {value}"
        )
    return parsed


def strict_json_loads(text: str) -> Any:
    """Parse JSON while rejecting non-finite constants and float overflow."""
    return json.loads(
        text,
        parse_constant=_reject_nonfinite_constant,
        parse_float=_parse_finite_float,
    )


def load_strict_json(path: str | Path) -> Any:
    """Read UTF-8 JSON and reject any value that would decode as non-finite."""
    return strict_json_loads(Path(path).read_text(encoding="utf-8"))
