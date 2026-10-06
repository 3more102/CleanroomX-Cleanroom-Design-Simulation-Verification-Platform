"""Shared field validation for engineering editors, independent of Tk."""

from __future__ import annotations

import json
import math
from typing import Any

from .strict_json import strict_json_loads


def parse_json_field(text: str, field_name: str) -> Any:
    try:
        return strict_json_loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{field_name} is invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    except ValueError as exc:
        raise ValueError(f"{field_name} must be strict JSON: {exc}") from exc


def parse_finite_number(text: str, field_name: str) -> float:
    try:
        value = float(text.strip())
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a finite numeric value") from exc
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be a finite numeric value")
    return value
