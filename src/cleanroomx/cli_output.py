from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable

from .persistence import atomic_write_text
from .strict_json import StrictJSONError



class CLIOutputError(RuntimeError):
    """Raised when a CLI report cannot be published safely."""


def _paths_alias(first: str | Path, second: str | Path) -> bool:
    left = Path(first).expanduser()
    right = Path(second).expanduser()
    try:
        if left.resolve(strict=False) == right.resolve(strict=False):
            return True
    except (OSError, RuntimeError) as exc:
        raise CLIOutputError("could not resolve CLI input/output paths") from exc
    try:
        if left.exists() and right.exists():
            return left.samefile(right)
    except OSError as exc:
        raise CLIOutputError("could not compare CLI input/output paths") from exc
    return False


def assert_output_path_distinct_from_inputs(
    output: str | Path,
    protected_inputs: Iterable[str | Path],
) -> None:
    """Fail closed when a CLI output aliases any source engineering input."""
    for protected in protected_inputs:
        if _paths_alias(protected, output):
            source = Path(protected).expanduser().resolve(strict=False)
            raise CLIOutputError(
                f"output path must be different from protected input: {source}"
            )


def write_cli_output(
    output: str | Path,
    text: str,
    *,
    protected_inputs: Iterable[str | Path] = (),
) -> Path:
    """Atomically publish CLI output without replacing any protected input.

    The identity check runs both before the temporary write and immediately
    before the final replace so path/hardlink changes during analysis or output
    preparation fail closed.
    """
    protected = tuple(protected_inputs)
    assert_output_path_distinct_from_inputs(output, protected)

    def recheck() -> None:
        assert_output_path_distinct_from_inputs(output, protected)

    try:
        return atomic_write_text(output, text, before_replace=recheck)
    except CLIOutputError:
        raise
    except OSError as exc:
        raise CLIOutputError(f"could not write CLI output {output}: {exc}") from exc

def _clone_cli_json_value(
    value: Any,
    *,
    path: str = "$",
    ancestors: set[int] | None = None,
) -> Any:
    """Normalize a result to plain strict-JSON containers without silent coercions."""
    if value is None:
        return None
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        number = float(value)
        if not math.isfinite(number):
            raise StrictJSONError(f"{path} contains a non-finite number")
        return number
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise StrictJSONError(f"{path} must contain valid UTF-8 text") from exc
        return str(value)

    if ancestors is None:
        ancestors = set()

    if isinstance(value, dict):
        marker = id(value)
        if marker in ancestors:
            raise StrictJSONError(f"{path} contains a cyclic reference")
        ancestors.add(marker)
        try:
            cloned: dict[str, Any] = {}
            for key, item in value.items():
                if not isinstance(key, str):
                    raise StrictJSONError(
                        f"{path} contains a non-string object key: {key!r}"
                    )
                try:
                    key.encode("utf-8")
                except UnicodeEncodeError as exc:
                    raise StrictJSONError(
                        f"{path} contains an object key with invalid UTF-8 text"
                    ) from exc
                child_path = (
                    f"{path}.{key}"
                    if key.isidentifier()
                    else f"{path}[{key!r}]"
                )
                cloned[str(key)] = _clone_cli_json_value(
                    item,
                    path=child_path,
                    ancestors=ancestors,
                )
            return cloned
        finally:
            ancestors.remove(marker)

    if isinstance(value, (list, tuple)):
        marker = id(value)
        if marker in ancestors:
            raise StrictJSONError(f"{path} contains a cyclic reference")
        ancestors.add(marker)
        try:
            return [
                _clone_cli_json_value(
                    item,
                    path=f"{path}[{index}]",
                    ancestors=ancestors,
                )
                for index, item in enumerate(value)
            ]
        finally:
            ancestors.remove(marker)

    raise StrictJSONError(
        f"{path} contains non-JSON value of type {type(value).__name__}"
    )


def dumps_strict_json(
    value: Any,
    *,
    indent: int | None = 2,
    sort_keys: bool = False,
) -> str:
    """Serialize CLI results as standards-compliant JSON with no NaN/Infinity."""
    try:
        snapshot = _clone_cli_json_value(value)
        return json.dumps(
            snapshot,
            indent=indent,
            sort_keys=sort_keys,
            ensure_ascii=False,
            allow_nan=False,
        )
    except StrictJSONError:
        raise
    except (TypeError, ValueError, RecursionError) as exc:
        raise StrictJSONError(
            f"$ cannot be serialized as strict JSON: {exc}"
        ) from exc
