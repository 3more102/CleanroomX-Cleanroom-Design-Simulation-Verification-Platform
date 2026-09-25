from __future__ import annotations

from difflib import get_close_matches
from functools import wraps
from typing import Any


def reject_unknown_fields(
    data: Any,
    allowed_fields: frozenset[str],
    *,
    context: str,
) -> None:
    """Reject unsupported object fields deterministically before defaults are applied."""
    if not isinstance(data, dict):
        raise ValueError(f"{context} must be an object")

    unknown = [
        key
        for key in data
        if not isinstance(key, str) or key not in allowed_fields
    ]
    if not unknown:
        return

    unknown.sort(key=lambda key: (type(key).__name__, repr(key)))
    allowed_sorted = sorted(allowed_fields)
    details: list[str] = []
    for key in unknown:
        rendered = repr(key)
        if isinstance(key, str):
            matches = get_close_matches(key, allowed_sorted, n=1, cutoff=0.72)
            if matches:
                rendered += f" (did you mean {matches[0]!r}?)"
        details.append(rendered)

    raise ValueError(
        f"unsupported {context} field(s): " + ", ".join(details)
    )


def strict_input_fields(*allowed_fields: str, context: str):
    """Decorate a dictionary parser with an explicit accepted-field contract."""
    allowed = frozenset(allowed_fields)
    if not allowed or any(not isinstance(field, str) or not field for field in allowed):
        raise ValueError("strict input contracts require non-empty string field names")
    if not isinstance(context, str) or not context.strip():
        raise ValueError("strict input contracts require a non-empty context")

    def decorate(parser):
        @wraps(parser)
        def checked(data, *args, **kwargs):
            reject_unknown_fields(data, allowed, context=context)
            return parser(data, *args, **kwargs)

        checked.__cleanroomx_allowed_fields__ = allowed
        checked.__cleanroomx_input_context__ = context
        return checked

    return decorate
