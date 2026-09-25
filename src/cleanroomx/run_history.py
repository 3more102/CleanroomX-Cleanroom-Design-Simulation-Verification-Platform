from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sys
import threading
from typing import Any

from .application import AnalysisRun, analysis_run_matches_input
from .autosave import project_identity
from .project import (
    ProjectFileRevision,
    atomic_write_text,
    capture_project_file_revision,
    project_file_revision_matches,
)


RUN_HISTORY_SCHEMA = "cleanroomx.run-history"
RUN_HISTORY_SCHEMA_VERSION = 1
DEFAULT_RUN_HISTORY_LIMIT = 100
_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class RunHistoryFormatError(ValueError):
    """Raised when a persisted run-history artifact is malformed or inconsistent."""


@dataclass(frozen=True)
class RunHistoryEntry:
    path: Path
    record_id: str
    recorded_at_utc: str
    project_path: Path
    source_relation: str
    project_dirty: bool
    analysis_id: str
    analysis_name: str
    analysis_kind: str
    status: str


@dataclass(frozen=True)
class RunHistoryScanIssue:
    path: Path
    error: str


@dataclass(frozen=True)
class RunHistoryScan:
    entries: tuple[RunHistoryEntry, ...]
    issues: tuple[RunHistoryScanIssue, ...]


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_utc(text: Any) -> datetime:
    if not isinstance(text, str) or not text:
        raise RunHistoryFormatError("recorded_at_utc must be a non-empty string")
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RunHistoryFormatError("recorded_at_utc is not a valid ISO-8601 timestamp") from exc
    if value.tzinfo is None:
        raise RunHistoryFormatError("recorded_at_utc must include a timezone")
    return value.astimezone(timezone.utc)


def default_run_history_dir() -> Path:
    override = os.environ.get("CLEANROOMX_RUN_HISTORY_DIR")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "CleanroomX" / "RunHistory"
        return Path.home() / "AppData" / "Local" / "CleanroomX" / "RunHistory"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "CleanroomX" / "RunHistory"
    state_home = os.environ.get("XDG_STATE_HOME")
    if state_home:
        return Path(state_home) / "cleanroomx" / "run-history"
    return Path.home() / ".local" / "state" / "cleanroomx" / "run-history"


def _ensure_private_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        try:
            path.chmod(0o700)
        except OSError:
            pass
    return path


def _reject_json_constant(value: str):
    raise RunHistoryFormatError(f"non-finite JSON constant is not allowed: {value}")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )


def _json_snapshot(value: Any) -> Any:
    return json.loads(_canonical_json(value), parse_constant=_reject_json_constant)


def _revision_to_dict(revision: ProjectFileRevision | None) -> dict[str, Any] | None:
    if revision is None:
        return None
    return {
        "path": revision.path,
        "exists": revision.exists,
        "size": revision.size,
        "mtime_ns": revision.mtime_ns,
        "sha256": revision.sha256,
    }


def _analysis_run_from_dict(data: Any) -> AnalysisRun:
    if not isinstance(data, dict):
        raise RunHistoryFormatError("run must be an object")
    expected = {"kind", "title", "status", "result", "markdown", "diagnostics", "plot"}
    missing = sorted(expected - set(data))
    if missing:
        raise RunHistoryFormatError("run is missing required field(s): " + ", ".join(missing))
    if not isinstance(data["kind"], str) or not data["kind"]:
        raise RunHistoryFormatError("run.kind must be a non-empty string")
    if not isinstance(data["title"], str) or not data["title"]:
        raise RunHistoryFormatError("run.title must be a non-empty string")
    if not isinstance(data["status"], str) or not data["status"]:
        raise RunHistoryFormatError("run.status must be a non-empty string")
    if not isinstance(data["result"], dict):
        raise RunHistoryFormatError("run.result must be an object")
    if not isinstance(data["markdown"], str):
        raise RunHistoryFormatError("run.markdown must be a string")
    if not isinstance(data["diagnostics"], dict):
        raise RunHistoryFormatError("run.diagnostics must be an object")
    if data["plot"] is not None and not isinstance(data["plot"], dict):
        raise RunHistoryFormatError("run.plot must be an object or null")
    return AnalysisRun(
        kind=data["kind"],
        title=data["title"],
        status=data["status"],
        result=data["result"],
        markdown=data["markdown"],
        diagnostics=data["diagnostics"],
        plot=data["plot"],
    )


def _record_id_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in record.items()
        if key not in {"record_id", "integrity"}
    }


def _integrity_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key != "integrity"}


def _digest(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _validate_record(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise RunHistoryFormatError("run-history artifact must contain a JSON object")
    try:
        json.dumps(data, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise RunHistoryFormatError("run-history artifact must contain only strict JSON values") from exc

    if data.get("schema") != RUN_HISTORY_SCHEMA:
        raise RunHistoryFormatError(f"run-history schema must be {RUN_HISTORY_SCHEMA!r}")
    if data.get("schema_version") != RUN_HISTORY_SCHEMA_VERSION:
        raise RunHistoryFormatError(
            f"unsupported run-history schema version {data.get('schema_version')!r}; "
            f"expected {RUN_HISTORY_SCHEMA_VERSION}"
        )

    recorded_at = data.get("recorded_at_utc")
    _parse_utc(recorded_at)

    record_id = data.get("record_id")
    if not isinstance(record_id, str) or _HEX_SHA256.fullmatch(record_id) is None:
        raise RunHistoryFormatError("record_id must be a lowercase SHA-256 hex digest")
    expected_record_id = _digest(_record_id_payload(data))
    if record_id != expected_record_id:
        raise RunHistoryFormatError("run-history record_id does not match the record content")

    project = data.get("project")
    if not isinstance(project, dict):
        raise RunHistoryFormatError("project must be an object")
    project_path = project.get("path")
    if not isinstance(project_path, str) or not project_path:
        raise RunHistoryFormatError("project.path must be a non-empty string")
    identity = project.get("identity")
    expected_identity = project_identity(project_path, unsaved_id="unused")
    if identity != expected_identity:
        raise RunHistoryFormatError("project.identity does not match project.path")
    if not isinstance(project.get("dirty"), bool):
        raise RunHistoryFormatError("project.dirty must be a boolean")
    relation = project.get("source_relation")
    if relation not in {"matches_loaded_revision", "changed_on_disk", "untracked"}:
        raise RunHistoryFormatError("project.source_relation is invalid")

    analysis = data.get("analysis")
    if not isinstance(analysis, dict):
        raise RunHistoryFormatError("analysis must be an object")
    for key in ("id", "name", "kind"):
        if not isinstance(analysis.get(key), str) or not analysis[key].strip():
            raise RunHistoryFormatError(f"analysis.{key} must be a non-empty string")
    analysis_input = analysis.get("input")
    if not isinstance(analysis_input, dict):
        raise RunHistoryFormatError("analysis.input must be an object")

    run = _analysis_run_from_dict(data.get("run"))
    if run.kind != analysis["kind"]:
        raise RunHistoryFormatError("run.kind does not match analysis.kind")
    if not analysis_run_matches_input(run, analysis["kind"], analysis_input):
        raise RunHistoryFormatError(
            "run execution provenance does not match the archived analysis input"
        )

    integrity = data.get("integrity")
    if not isinstance(integrity, dict):
        raise RunHistoryFormatError("integrity must be an object")
    if integrity.get("algorithm") != "sha256":
        raise RunHistoryFormatError("integrity.algorithm must be 'sha256'")
    expected_digest = integrity.get("payload_sha256")
    if not isinstance(expected_digest, str) or _HEX_SHA256.fullmatch(expected_digest) is None:
        raise RunHistoryFormatError("integrity.payload_sha256 must be a lowercase SHA-256 digest")
    actual_digest = _digest(_integrity_payload(data))
    if expected_digest != actual_digest:
        raise RunHistoryFormatError("run-history integrity digest mismatch")

    return data


def load_run_history_record(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        data = json.loads(
            source.read_text(encoding="utf-8"),
            parse_constant=_reject_json_constant,
        )
    except json.JSONDecodeError as exc:
        raise RunHistoryFormatError(
            f"invalid run-history JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc
    return _validate_record(data)


def analysis_run_from_history_record(record: dict[str, Any]) -> AnalysisRun:
    validated = _validate_record(record)
    return _analysis_run_from_dict(_json_snapshot(validated["run"]))


def _history_directory(history_dir: str | Path, project_path: str | Path) -> Path:
    identity = project_identity(project_path, unsaved_id="unused")
    return Path(history_dir) / identity


def _safe_filename_component(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return (sanitized or "analysis")[:48]


def _entry_from_record(path: Path, record: dict[str, Any]) -> RunHistoryEntry:
    project = record["project"]
    analysis = record["analysis"]
    run = record["run"]
    return RunHistoryEntry(
        path=path,
        record_id=record["record_id"],
        recorded_at_utc=record["recorded_at_utc"],
        project_path=Path(project["path"]),
        source_relation=project["source_relation"],
        project_dirty=project["dirty"],
        analysis_id=analysis["id"],
        analysis_name=analysis["name"],
        analysis_kind=analysis["kind"],
        status=run["status"],
    )


def scan_run_history(
    history_dir: str | Path,
    project_path: str | Path,
) -> RunHistoryScan:
    directory = _history_directory(history_dir, project_path)
    if not directory.exists():
        return RunHistoryScan(entries=(), issues=())
    if not directory.is_dir():
        raise OSError(f"run-history path is not a directory: {directory}")

    entries: list[RunHistoryEntry] = []
    issues: list[RunHistoryScanIssue] = []
    for path in sorted(directory.glob("*.run.json")):
        try:
            record = load_run_history_record(path)
            entries.append(_entry_from_record(path, record))
        except (OSError, ValueError) as exc:
            issues.append(RunHistoryScanIssue(path=path, error=str(exc)))

    entries.sort(
        key=lambda item: (_parse_utc(item.recorded_at_utc), item.record_id),
        reverse=True,
    )
    issues.sort(key=lambda item: item.path.name)
    return RunHistoryScan(entries=tuple(entries), issues=tuple(issues))


def _rotate_history(
    history_dir: Path,
    project_path: Path,
    *,
    history_limit: int,
) -> None:
    scan = scan_run_history(history_dir, project_path)
    for entry in scan.entries[history_limit:]:
        entry.path.unlink(missing_ok=True)


def archive_analysis_run(
    history_dir: str | Path,
    *,
    project_path: str | Path,
    expected_project_revision: ProjectFileRevision | None,
    project_dirty: bool,
    analysis_id: str,
    analysis_name: str,
    analysis_kind: str,
    analysis_input: dict[str, Any],
    run: AnalysisRun,
    history_limit: int = DEFAULT_RUN_HISTORY_LIMIT,
    recorded_at_utc: str | None = None,
) -> Path:
    if history_limit < 1:
        raise ValueError("history_limit must be at least 1")
    if not isinstance(project_dirty, bool):
        raise TypeError("project_dirty must be a boolean")
    for label, value in (
        ("analysis_id", analysis_id),
        ("analysis_name", analysis_name),
        ("analysis_kind", analysis_kind),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} must be a non-empty string")
    if run.kind != analysis_kind:
        raise RunHistoryFormatError("run.kind does not match analysis_kind")
    input_snapshot = _json_snapshot(analysis_input)
    if not isinstance(input_snapshot, dict):
        raise RunHistoryFormatError("analysis_input must be a JSON object")
    if not analysis_run_matches_input(run, analysis_kind, input_snapshot):
        raise RunHistoryFormatError(
            "run execution provenance does not match the supplied analysis input"
        )

    normalized_project_path = Path(project_path).expanduser().resolve(strict=False)
    current_revision = capture_project_file_revision(normalized_project_path)
    if expected_project_revision is None:
        source_relation = "untracked"
    elif project_file_revision_matches(expected_project_revision, current_revision):
        source_relation = "matches_loaded_revision"
    else:
        source_relation = "changed_on_disk"

    timestamp = recorded_at_utc or _utc_now_text()
    _parse_utc(timestamp)
    identity = project_identity(normalized_project_path, unsaved_id="unused")
    run_snapshot = _json_snapshot(run.to_dict())

    record: dict[str, Any] = {
        "schema": RUN_HISTORY_SCHEMA,
        "schema_version": RUN_HISTORY_SCHEMA_VERSION,
        "recorded_at_utc": timestamp,
        "project": {
            "path": str(normalized_project_path),
            "identity": identity,
            "dirty": project_dirty,
            "source_relation": source_relation,
            "loaded_revision": _revision_to_dict(expected_project_revision),
            "current_disk_revision": _revision_to_dict(current_revision),
        },
        "analysis": {
            "id": analysis_id,
            "name": analysis_name,
            "kind": analysis_kind,
            "input": input_snapshot,
        },
        "run": run_snapshot,
    }
    record["record_id"] = _digest(_record_id_payload(record))
    record["integrity"] = {
        "algorithm": "sha256",
        "payload_sha256": _digest(_integrity_payload(record)),
    }
    _validate_record(record)

    directory = _ensure_private_dir(_history_directory(history_dir, normalized_project_path))
    stamp = _parse_utc(timestamp).strftime("%Y%m%dT%H%M%S%fZ")
    name = (
        f"{stamp}-{_safe_filename_component(analysis_id)}-"
        f"{record['record_id'][:12]}.run.json"
    )
    destination = directory / name
    text = json.dumps(
        record,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"
    atomic_write_text(destination, text)

    try:
        verified = load_run_history_record(destination)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    if verified["record_id"] != record["record_id"]:
        destination.unlink(missing_ok=True)
        raise OSError(f"run-history verification failed after write: {destination}")

    _rotate_history(
        Path(history_dir),
        normalized_project_path,
        history_limit=history_limit,
    )
    return destination


class RunHistoryManager:
    """Serialize immutable run-history writes off the GUI thread."""

    def __init__(
        self,
        history_dir: str | Path | None = None,
        *,
        history_limit: int = DEFAULT_RUN_HISTORY_LIMIT,
    ) -> None:
        if history_limit < 1:
            raise ValueError("history_limit must be at least 1")
        self.history_dir = (
            default_run_history_dir() if history_dir is None else Path(history_dir)
        )
        self.history_limit = history_limit
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="cleanroomx-run-history",
        )
        self._lock = threading.Lock()
        self._closed = False

    def submit(
        self,
        *,
        project_path: str | Path,
        expected_project_revision: ProjectFileRevision | None,
        project_dirty: bool,
        analysis_id: str,
        analysis_name: str,
        analysis_kind: str,
        analysis_input: dict[str, Any],
        run: AnalysisRun,
    ) -> Future[Path]:
        input_snapshot = _json_snapshot(analysis_input)
        run_snapshot = _analysis_run_from_dict(_json_snapshot(run.to_dict()))
        with self._lock:
            if self._closed:
                raise RuntimeError("run-history manager is shut down")
            return self._executor.submit(
                archive_analysis_run,
                self.history_dir,
                project_path=project_path,
                expected_project_revision=expected_project_revision,
                project_dirty=project_dirty,
                analysis_id=analysis_id,
                analysis_name=analysis_name,
                analysis_kind=analysis_kind,
                analysis_input=input_snapshot,
                run=run_snapshot,
                history_limit=self.history_limit,
            )

    def wait_for_idle(self, timeout: float | None = None) -> None:
        with self._lock:
            if self._closed:
                return
            marker = self._executor.submit(lambda: None)
        marker.result(timeout=timeout)

    def shutdown(self, *, wait: bool = False) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._executor.shutdown(wait=wait, cancel_futures=False)
