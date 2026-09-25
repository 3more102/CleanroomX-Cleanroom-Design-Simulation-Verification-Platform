from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
import math
import os
from pathlib import Path
import platform
import sys
import threading
import traceback
from typing import Any


LOGGER_NAME = "cleanroomx"
LOG_SCHEMA = "cleanroomx.local-log"
LOG_SCHEMA_VERSION = 1
DIAGNOSTIC_BUNDLE_SCHEMA = "cleanroomx.diagnostic-bundle"
DIAGNOSTIC_BUNDLE_SCHEMA_VERSION = 1
DEFAULT_LOG_MAX_BYTES = 2 * 1024 * 1024
DEFAULT_LOG_BACKUP_COUNT = 5
DEFAULT_BUNDLE_LOG_BYTES = 256 * 1024
DEFAULT_BUNDLE_LOG_RECORDS = 500


@dataclass(frozen=True)
class DiagnosticSession:
    directory: Path
    log_path: Path


def _utc_now_text() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def default_diagnostics_dir() -> Path:
    override = os.environ.get("CLEANROOMX_DIAGNOSTICS_DIR")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "CleanroomX" / "Diagnostics"
        return Path.home() / "AppData" / "Local" / "CleanroomX" / "Diagnostics"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "CleanroomX" / "Diagnostics"
    state_home = os.environ.get("XDG_STATE_HOME")
    if state_home:
        return Path(state_home) / "cleanroomx" / "diagnostics"
    return Path.home() / ".local" / "state" / "cleanroomx" / "diagnostics"


def _ensure_diagnostics_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        try:
            path.chmod(0o700)
        except OSError:
            pass
    return path


def _json_safe(value: Any, *, depth: int = 0) -> Any:
    if depth >= 16:
        return "<maximum diagnostic depth reached>"
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else repr(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {
            str(key): _json_safe(item, depth=depth + 1)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_json_safe(item, depth=depth + 1) for item in value]
    if isinstance(value, (set, frozenset)):
        return [
            _json_safe(item, depth=depth + 1)
            for item in sorted(value, key=repr)
        ]
    value_type = type(value)
    return f"<{value_type.__module__}.{value_type.__qualname__}>"


class _PrivateRotatingFileHandler(RotatingFileHandler):
    """Rotating handler that reapplies owner-only permissions on POSIX."""

    def _open(self):
        stream = super()._open()
        if os.name != "nt":
            try:
                Path(self.baseFilename).chmod(0o600)
            except OSError:
                pass
        return stream


class _JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "schema": LOG_SCHEMA,
            "schema_version": LOG_SCHEMA_VERSION,
            "timestamp_utc": _utc_now_text(),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "cleanroomx_event", "log"),
            "message": record.getMessage(),
            "process_id": os.getpid(),
            "thread": threading.current_thread().name,
            "fields": _json_safe(getattr(record, "cleanroomx_fields", {})),
        }
        if record.exc_info:
            exc_type, exc_value, exc_tb = record.exc_info
            payload["exception"] = {
                "type": getattr(exc_type, "__name__", str(exc_type)),
                "message": str(exc_value),
                "traceback": "".join(
                    traceback.format_exception(exc_type, exc_value, exc_tb)
                ),
            }
        return json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )


def configure_local_diagnostics(
    directory: str | Path | None = None,
    *,
    max_bytes: int = DEFAULT_LOG_MAX_BYTES,
    backup_count: int = DEFAULT_LOG_BACKUP_COUNT,
    level: int = logging.INFO,
) -> DiagnosticSession:
    """Configure bounded local JSONL diagnostics without network transmission."""
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1024:
        raise ValueError("max_bytes must be an integer of at least 1024")
    if (
        isinstance(backup_count, bool)
        or not isinstance(backup_count, int)
        or backup_count < 0
    ):
        raise ValueError("backup_count must be a non-negative integer")

    target_dir = _ensure_diagnostics_dir(
        Path(directory) if directory is not None else default_diagnostics_dir()
    )
    log_path = target_dir / "cleanroomx.jsonl"

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False

    for handler in list(logger.handlers):
        if getattr(handler, "_cleanroomx_local_handler", False):
            logger.removeHandler(handler)
            handler.close()

    handler = _PrivateRotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
        delay=False,
    )
    handler._cleanroomx_local_handler = True
    handler.setLevel(level)
    handler.setFormatter(_JsonLineFormatter())
    logger.addHandler(handler)

    if os.name != "nt":
        try:
            log_path.chmod(0o600)
        except OSError:
            pass

    return DiagnosticSession(directory=target_dir, log_path=log_path)


def log_event(
    event: str,
    *,
    level: int = logging.INFO,
    message: str | None = None,
    **fields: Any,
) -> None:
    normalized_event = str(event).strip() or "event"
    logging.getLogger(LOGGER_NAME).log(
        level,
        message or normalized_event,
        extra={
            "cleanroomx_event": normalized_event,
            "cleanroomx_fields": fields,
        },
    )


def log_exception(
    event: str,
    exc_type,
    exc_value,
    exc_tb,
    **fields: Any,
) -> None:
    normalized_event = str(event).strip() or "exception"
    logging.getLogger(LOGGER_NAME).error(
        normalized_event,
        exc_info=(exc_type, exc_value, exc_tb),
        extra={
            "cleanroomx_event": normalized_event,
            "cleanroomx_fields": fields,
        },
    )


def _flush_local_handlers() -> None:
    for handler in logging.getLogger(LOGGER_NAME).handlers:
        if getattr(handler, "_cleanroomx_local_handler", False):
            handler.flush()


def read_log_tail(
    log_path: str | Path,
    *,
    max_bytes: int = DEFAULT_BUNDLE_LOG_BYTES,
    max_records: int = DEFAULT_BUNDLE_LOG_RECORDS,
) -> tuple[dict[str, Any], ...]:
    """Read a bounded tail of the current log without loading an unbounded file."""
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1:
        raise ValueError("max_bytes must be a positive integer")
    if (
        isinstance(max_records, bool)
        or not isinstance(max_records, int)
        or max_records < 1
    ):
        raise ValueError("max_records must be a positive integer")

    path = Path(log_path)
    if not path.exists():
        return ()

    _flush_local_handlers()
    size = path.stat().st_size
    start = max(0, size - max_bytes)
    with path.open("rb") as handle:
        handle.seek(start)
        raw = handle.read(max_bytes)

    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if start > 0 and lines:
        lines = lines[1:]

    records: list[dict[str, Any]] = []
    for line in lines[-max_records:]:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            item = {
                "schema": "cleanroomx.unparsed-log-line",
                "text": line[:2048],
            }
        if isinstance(item, dict):
            records.append(item)
        else:
            records.append(
                {
                    "schema": "cleanroomx.unparsed-log-value",
                    "value": _json_safe(item),
                }
            )
    return tuple(records[-max_records:])


def build_diagnostic_bundle(
    log_path: str | Path,
    *,
    context: dict[str, Any] | None = None,
    max_log_bytes: int = DEFAULT_BUNDLE_LOG_BYTES,
    max_log_records: int = DEFAULT_BUNDLE_LOG_RECORDS,
) -> dict[str, Any]:
    """Build a strict-JSON, bounded, local diagnostic support bundle."""
    from . import __version__

    path = Path(log_path)
    records = read_log_tail(
        path,
        max_bytes=max_log_bytes,
        max_records=max_log_records,
    )
    bundle = {
        "schema": DIAGNOSTIC_BUNDLE_SCHEMA,
        "schema_version": DIAGNOSTIC_BUNDLE_SCHEMA_VERSION,
        "application_version": __version__,
        "generated_at_utc": _utc_now_text(),
        "runtime": {
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "process_id": os.getpid(),
        },
        "context": _json_safe(context or {}),
        "log": {
            "filename": path.name,
            "exists": path.exists(),
            "size_bytes": path.stat().st_size if path.exists() else None,
            "tail_max_bytes": max_log_bytes,
            "tail_max_records": max_log_records,
            "records": list(records),
        },
        "privacy": {
            "network_transmission": False,
            "note": (
                "This bundle is generated locally. Review file paths and other "
                "diagnostic context before sharing it outside your organization."
            ),
        },
    }
    json.dumps(bundle, allow_nan=False)
    return bundle
