from __future__ import annotations

from collections.abc import Iterable
import json
import math
from pathlib import Path
from typing import Any

from .strict_json import StrictJSONError


ProtectedPath = tuple[str, str | Path]


def _paths_alias(protected: str | Path, output: str | Path) -> bool:
    """Return whether an output destination refers to one protected input."""
    protected_candidate = Path(protected).expanduser()
    destination = Path(output).expanduser()
    try:
        protected_resolved = protected_candidate.resolve(strict=False)
        destination_resolved = destination.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise OSError(
            f"could not verify output path identity: {destination}"
        ) from exc

    if destination_resolved == protected_resolved:
        return True

    try:
        if not destination.exists() or not protected_candidate.exists():
            return False
        return destination.samefile(protected_candidate)
    except FileNotFoundError:
        # A path that disappears during the identity check cannot still be the
        # existing protected file. Resolved-path equality was checked above.
        return False
    except OSError as exc:
        raise OSError(
            "could not verify output path against protected input: "
            f"{destination}"
        ) from exc


def assert_output_is_distinct_from_paths(
    output: str | Path,
    protected_paths: Iterable[ProtectedPath],
) -> None:
    """Fail closed when an output could replace a protected engineering input."""
    for label, protected in protected_paths:
        if _paths_alias(protected, output):
            protected_path = Path(protected).expanduser().resolve(strict=False)
            raise ValueError(
                f"output path must be different from {label}: {protected_path}"
            )


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
