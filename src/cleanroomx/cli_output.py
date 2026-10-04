from __future__ import annotations

from collections.abc import Callable
from functools import wraps
import json
import math
import sys
from pathlib import Path
from typing import Any, Iterable, ParamSpec, TypeVar

from .persistence import atomic_write_text
from .strict_json import StrictJSONError


_P = ParamSpec("_P")
_T = TypeVar("_T")


def cli_error_boundary(
    command: str,
) -> Callable[[Callable[_P, int]], Callable[_P, int]]:
    """Convert expected standalone-CLI failures into deterministic diagnostics."""
    if not isinstance(command, str) or not command.strip():
        raise ValueError("command must be a non-empty string")

    def decorate(func: Callable[_P, int]) -> Callable[_P, int]:
        @wraps(func)
        def guarded(*args: _P.args, **kwargs: _P.kwargs) -> int:
            try:
                return func(*args, **kwargs)
            except (OSError, ValueError) as exc:
                print(f"{command}: error: {exc}", file=sys.stderr)
                return 1

        return guarded

    return decorate


class CliInputError(ValueError):
    """Raised when file-backed CLI input has an invalid user-supplied structure."""


class CliStateError(RuntimeError):
    """Raised for expected CLI state/revision failures, not programming defects."""


def resolve_cli_path(
    path: str | Path,
    *,
    label: str = "input",
) -> Path:
    """Resolve one user-supplied path while preserving unrelated runtime defects."""
    try:
        return Path(path).expanduser().resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise CliInputError(
            f"could not resolve {label} path: {path}: {exc}"
        ) from exc


def load_cli_input(
    loader: Callable[[str | Path], _T],
    path: str | Path,
) -> _T:
    """Load one user input while normalizing structural parser failures only."""
    try:
        return loader(path)
    except (OSError, ValueError):
        raise
    except KeyError as exc:
        field = exc.args[0] if exc.args else "<unknown>"
        raise CliInputError(
            f"invalid input structure: missing required field {field!r}"
        ) from exc
    except (IndexError, TypeError, AttributeError) as exc:
        raise CliInputError(f"invalid input structure: {exc}") from exc


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
                    f"input: {source}"
                )

    assert_distinct()
    return atomic_write_text(
        destination,
        text,
        before_replace=assert_distinct,
    )


def publish_cli_output(
    command: str,
    path: str | Path,
    text: str,
    *,
    protected_inputs: Iterable[str | Path] = (),
) -> bool:
    """Publish CLI text and report output failures without a Python traceback."""
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
