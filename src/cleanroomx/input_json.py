from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class NonFiniteJSONError(ValueError):
    """Raised when JSON input uses NaN or Infinity constants."""


def _reject_nonfinite_constant(value: str):
    raise NonFiniteJSONError(
        f"non-finite JSON constant is not allowed: {value}"
    )


def strict_json_loads(text: str) -> Any:
    """Parse standards-compliant JSON while preserving normal syntax errors."""
    return json.loads(text, parse_constant=_reject_nonfinite_constant)


def load_strict_json(path: str | Path) -> Any:
    """Read UTF-8 JSON and reject non-standard NaN/Infinity constants."""
    return strict_json_loads(Path(path).read_text(encoding="utf-8"))
