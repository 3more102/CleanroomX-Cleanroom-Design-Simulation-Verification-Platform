from __future__ import annotations

import math
from typing import Any


def finite_float(value: Any, field_name: str) -> float:
    """Return *value* as a finite float or fail before engineering use."""
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field_name} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    return number


def positive_float(value: Any, field_name: str) -> float:
    number = finite_float(value, field_name)
    if number <= 0.0:
        raise ValueError(f"{field_name} must be > 0")
    return number


def nonnegative_float(value: Any, field_name: str) -> float:
    number = finite_float(value, field_name)
    if number < 0.0:
        raise ValueError(f"{field_name} must be >= 0")
    return number


def efficiency_float(value: Any, field_name: str) -> float:
    number = finite_float(value, field_name)
    if not 0.0 < number <= 1.0:
        raise ValueError(f"{field_name} must be in (0, 1]")
    return number
