from __future__ import annotations

import json
import math
from pathlib import Path
import sys
from typing import Any, Iterable

from .persistence import atomic_write_text
from .strict_json import StrictJSONError


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


class CliOutputProtectionError(ValueError):
    """Raised when a CLI output destination aliases protected engineering input."""


def _paths_alias(first: str | Path, second: str | Path) -> bool:
    left = Path(first).expanduser()
    right = Path(second).expanduser()
    try:
        if left.resolve(strict=False) == right.resolve(strict=False):
            return True
        if left.exists() and right.exists():
            return left.samefile(right)
    except (OSError, RuntimeError) as exc:
        raise CliOutputProtectionError(
            f"could not verify CLI output identity for {right}"
        ) from exc
    return False


def atomic_write_cli_output(
    path: str | Path,
    text: str,
    *,
    protected_inputs: Iterable[str | Path] = (),
) -> Path:
    """Atomically publish CLI text without replacing declared engineering inputs.

    Protection is checked before staging and again through the shared persistence
    pre-replace hook. The second check closes the normal analysis-to-publication
    window for path, symlink, or hardlink aliases.
    """
    destination = Path(path).expanduser()
    protected = tuple(Path(item).expanduser() for item in protected_inputs)

    def assert_distinct() -> None:
        for source in protected:
            if _paths_alias(source, destination):
                raise CliOutputProtectionError(
                    "CLI output path must be different from protected engineering "
                    f"input: {source.resolve(strict=False)}"
                )

    assert_distinct()
    return atomic_write_text(
        destination,
        text,
        before_replace=assert_distinct,
    )

def write_cli_output_or_report_error(
    path: str | Path,
    text: str,
    *,
    command: str,
    protected_inputs: Iterable[str | Path] = (),
) -> bool:
    """Publish CLI output and convert expected publication failures to stderr.

    Returns True after successful publication. Protection failures and filesystem
    publication errors are reported as concise command-prefixed diagnostics and
    return False so callers preserve existing engineering/status exit semantics.
    """
    try:
        atomic_write_cli_output(
            path,
            text,
            protected_inputs=protected_inputs,
        )
    except (CliOutputProtectionError, OSError) as exc:
        print(
            f"{command}: error: output publication failed: {exc}",
            file=sys.stderr,
        )
        return False
    return True

