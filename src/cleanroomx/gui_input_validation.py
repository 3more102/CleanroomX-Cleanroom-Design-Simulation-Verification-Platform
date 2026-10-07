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
        value = parse_json_field(text.strip(), field_name)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a finite JSON number: {exc}") from exc
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a finite JSON number")
    try:
        numeric = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a finite JSON number") from exc
    if not math.isfinite(numeric):
        raise ValueError(f"{field_name} must be a finite JSON number")
    return numeric
