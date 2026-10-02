from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
from typing import Any


STRICT_JSON_FILE_MAX_BYTES = 64 * 1024 * 1024


class StrictJSONError(ValueError):
    """Raised when a value cannot be represented as deterministic strict JSON."""


class StrictJSONFileChangedError(StrictJSONError):
    """Raised when an opened JSON file or its live path changes during ingestion."""


class StrictJSONSizeError(StrictJSONError):
    """Raised when a bounded strict-JSON read observes too many bytes."""

    def __init__(self, source: Path, observed_size: int, limit: int):
        self.source = source
        self.observed_size = observed_size
        self.limit = limit
        super().__init__(
            f"{source} exceeds maximum supported JSON size "
            f"({observed_size} > {limit} bytes)"
        )


@dataclass(frozen=True)
class StrictJSONFileSnapshot:
    """Parsed strict JSON plus the exact stable bytes and descriptor metadata."""

    value: Any
    raw_bytes: bytes
    size: int
    mtime_ns: int


def _json_child_path(path: str, key: str) -> str:
    if key.isidentifier():
        return f"{path}.{key}"
    return f"{path}[{json.dumps(key, ensure_ascii=True)}]"


def _validate_json_string(value: str, path: str) -> str:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise StrictJSONError(f"{path} must contain valid UTF-8 text") from exc
    return value


def clone_strict_json(
    value: Any,
    *,
    path: str = "$",
    ancestors: set[int] | None = None,
) -> Any:
    """Return a detached strict-JSON snapshot without Python-side coercions."""
    if value is None:
        return None
    if type(value) is bool:
        return value
    if type(value) is int:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise StrictJSONError(f"{path} contains a non-finite number")
        return value
    if type(value) is str:
        return _validate_json_string(value, path)

    if ancestors is None:
        ancestors = set()

    if type(value) is list:
        marker = id(value)
        if marker in ancestors:
            raise StrictJSONError(f"{path} contains a cyclic reference")
        ancestors.add(marker)
        try:
            return [
                clone_strict_json(
                    item,
                    path=f"{path}[{index}]",
                    ancestors=ancestors,
                )
                for index, item in enumerate(value)
            ]
        finally:
            ancestors.remove(marker)

    if type(value) is dict:
        marker = id(value)
        if marker in ancestors:
            raise StrictJSONError(f"{path} contains a cyclic reference")
        ancestors.add(marker)
        try:
            cloned: dict[str, Any] = {}
            for key, item in value.items():
                if type(key) is not str:
                    raise StrictJSONError(
                        f"{path} must contain only string object keys; "
                        f"got {type(key).__name__}"
                    )
                _validate_json_string(key, f"{path} object key")
                cloned[key] = clone_strict_json(
                    item,
                    path=_json_child_path(path, key),
                    ancestors=ancestors,
                )
            return cloned
        finally:
            ancestors.remove(marker)

    raise StrictJSONError(
        f"{path} contains non-JSON value of type {type(value).__name__}"
    )


def _reject_json_constant(value: str) -> None:
    raise StrictJSONError(f"non-finite JSON constant is not allowed: {value}")


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StrictJSONError(
                f"duplicate JSON object key {key!r} is not allowed"
            )
        result[key] = value
    return result


def strict_json_loads(text: str) -> Any:
    """Parse strict JSON and normalize excessive nesting to StrictJSONError."""
    try:
        value = json.loads(
            text,
            parse_constant=_reject_json_constant,
            object_pairs_hook=_object_without_duplicate_keys,
        )
        return clone_strict_json(value)
    except RecursionError as exc:
        raise StrictJSONError(
            "JSON nesting exceeds the supported parser/validation depth"
        ) from exc


def _file_revision(stat_result: os.stat_result) -> tuple[int, int, int, int]:
    return (
        stat_result.st_dev,
        stat_result.st_ino,
        stat_result.st_size,
        stat_result.st_mtime_ns,
    )


def load_strict_json_snapshot(
    path: str | Path,
    *,
    max_bytes: int | None = None,
) -> StrictJSONFileSnapshot:
    """Parse one bounded, revision-stable file and retain its exact byte snapshot."""
    source = Path(path)
    limit = STRICT_JSON_FILE_MAX_BYTES if max_bytes is None else max_bytes
    if type(limit) is not int or limit < 1:
        raise ValueError("max_bytes must be a positive integer")

    with source.open("rb") as stream:
        before = os.fstat(stream.fileno())
        if before.st_size > limit:
            raise StrictJSONSizeError(source, before.st_size, limit)
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
        try:
            current = source.stat()
        except OSError as exc:
            raise StrictJSONFileChangedError(
                f"{source} changed while reading JSON input"
            ) from exc

    if len(raw) > limit or after.st_size > limit:
        observed_size = max(len(raw), after.st_size)
        raise StrictJSONSizeError(source, observed_size, limit)

    if (
        _file_revision(before) != _file_revision(after)
        or _file_revision(after) != _file_revision(current)
        or len(raw) != after.st_size
    ):
        raise StrictJSONFileChangedError(
            f"{source} changed while reading JSON input"
        )

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StrictJSONError(
            f"{source} must contain valid UTF-8 JSON text"
        ) from exc

    return StrictJSONFileSnapshot(
        value=strict_json_loads(text),
        raw_bytes=raw,
        size=len(raw),
        mtime_ns=after.st_mtime_ns,
    )


def load_strict_json(
    path: str | Path,
    *,
    max_bytes: int | None = None,
) -> Any:
    """Read one bounded, revision-stable UTF-8 file through the strict parser."""
    return load_strict_json_snapshot(path, max_bytes=max_bytes).value
