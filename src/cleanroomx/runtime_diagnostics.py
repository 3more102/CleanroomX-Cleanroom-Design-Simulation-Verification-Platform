from __future__ import annotations

import copy
import json
import math
import platform
import sys
import threading
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from . import __version__
DIAGNOSTIC_BUNDLE_SCHEMA = "cleanroomx.runtime-diagnostics"
DIAGNOSTIC_BUNDLE_SCHEMA_VERSION = 1
DEFAULT_EVENT_CAPACITY = 256
_MAX_CONTEXT_DEPTH = 5
_MAX_TEXT_LENGTH = 2000


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _bounded_text(value: str) -> str:
    if len(value) <= _MAX_TEXT_LENGTH:
        return value
    return value[: _MAX_TEXT_LENGTH - 1] + "…"


def _normalize_value(value: Any, *, depth: int = 0) -> Any:
    """Return a strict-JSON-safe diagnostic value without invoking arbitrary reprs."""
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        return {"non_finite_float": str(value)}
    if isinstance(value, str):
        return _bounded_text(value)
    if isinstance(value, Path):
        return {"path_name": value.name, "path_is_absolute": value.is_absolute()}
    if depth >= _MAX_CONTEXT_DEPTH:
        return {"truncated_type": type(value).__name__}
    if isinstance(value, Mapping):
        return {
            _bounded_text(str(key)): _normalize_value(item, depth=depth + 1)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_normalize_value(item, depth=depth + 1) for item in value]
    return {"unsupported_type": type(value).__name__}


@dataclass(frozen=True)
class RuntimeEvent:
    sequence: int
    timestamp_utc: str
    level: str
    event: str
    message: str
    context: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "timestamp_utc": self.timestamp_utc,
            "level": self.level,
            "event": self.event,
            "message": self.message,
            "context": copy.deepcopy(self.context),
        }


class RuntimeEventJournal:
    """Thread-safe bounded in-memory runtime event journal owned by one app instance."""

    _LEVELS = {"debug", "info", "warning", "error"}

    def __init__(
        self,
        *,
        capacity: int = DEFAULT_EVENT_CAPACITY,
        clock: Callable[[], str] = _utc_now,
    ) -> None:
        if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity <= 0:
            raise ValueError("capacity must be a positive integer")
        self._capacity = capacity
        self._clock = clock
        self._events: deque[RuntimeEvent] = deque(maxlen=capacity)
        self._sequence = 0
        self._lock = threading.Lock()

    @property
    def capacity(self) -> int:
        return self._capacity

    def record(
        self,
        event: str,
        *,
        level: str = "info",
        message: str = "",
        **context: Any,
    ) -> RuntimeEvent:
        if level not in self._LEVELS:
            raise ValueError(f"unsupported diagnostic level: {level}")
        if not isinstance(event, str) or not event.strip():
            raise ValueError("event must be a non-empty string")
        if not isinstance(message, str):
            raise TypeError("message must be a string")
        normalized_context = _normalize_value(context)
        assert isinstance(normalized_context, dict)
        with self._lock:
            self._sequence += 1
            item = RuntimeEvent(
                sequence=self._sequence,
                timestamp_utc=self._clock(),
                level=level,
                event=event.strip(),
                message=_bounded_text(message),
                context=normalized_context,
            )
            self._events.append(item)
            return item

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [item.to_dict() for item in self._events]


def runtime_environment() -> dict[str, Any]:
    return {
        "cleanroomx_version": __version__,
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "executable_name": Path(sys.executable).name,
    }


def sanitized_run_summary(run: Any | None) -> dict[str, Any] | None:
    if run is None:
        return None
    diagnostics = getattr(run, "diagnostics", {})
    provenance = (
        diagnostics.get("application_execution_provenance", {})
        if isinstance(diagnostics, dict)
        else {}
    )
    dependencies = []
    for item in provenance.get("external_dependencies", []):
        if not isinstance(item, dict):
            continue
        declared = item.get("declared_path")
        declared_path = Path(declared) if isinstance(declared, str) and declared else None
        dependencies.append(
            {
                "field": item.get("field"),
                "path_name": declared_path.name if declared_path is not None else None,
                "path_was_absolute": (
                    declared_path.is_absolute() if declared_path is not None else None
                ),
                "sha256_before": item.get("sha256_before"),
                "sha256_after": item.get("sha256_after"),
                "size_bytes_before": item.get("size_bytes_before"),
                "size_bytes_after": item.get("size_bytes_after"),
                "stable_during_run": item.get("stable_during_run"),
            }
        )
    return {
        "kind": getattr(run, "kind", None),
        "title": getattr(run, "title", None),
        "status": getattr(run, "status", None),
        "execution_provenance": {
            "schema": provenance.get("schema"),
            "schema_version": provenance.get("schema_version"),
            "cleanroomx_version": provenance.get("cleanroomx_version"),
            "analysis_kind": provenance.get("analysis_kind"),
            "input_canonicalization": provenance.get("input_canonicalization"),
            "input_sha256": provenance.get("input_sha256"),
            "external_dependency_count": provenance.get("external_dependency_count", 0),
            "external_dependencies_stable": provenance.get(
                "external_dependencies_stable", True
            ),
            "external_dependencies": dependencies,
        },
    }


def build_diagnostic_bundle(
    journal: RuntimeEventJournal,
    *,
    project: dict[str, Any],
    runtime_state: dict[str, Any],
    current_run: Any | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build a support bundle without copying full engineering analysis inputs/results."""
    bundle = {
        "schema": DIAGNOSTIC_BUNDLE_SCHEMA,
        "schema_version": DIAGNOSTIC_BUNDLE_SCHEMA_VERSION,
        "generated_at_utc": generated_at_utc or _utc_now(),
        "environment": runtime_environment(),
        "project": _normalize_value(project),
        "runtime_state": _normalize_value(runtime_state),
        "current_run": sanitized_run_summary(current_run),
        "events": journal.snapshot(),
    }
    # Fail here rather than producing a diagnostic artifact that violates strict JSON.
    json.dumps(bundle, allow_nan=False, sort_keys=True)
    return bundle

