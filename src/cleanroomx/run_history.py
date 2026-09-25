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
import time
import uuid
from typing import Any

from . import __version__
from .application import AnalysisRun
from .project import atomic_write_text


RUN_HISTORY_SCHEMA = "cleanroomx.analysis-run-history"
RUN_HISTORY_SCHEMA_VERSION = 1
RUN_HISTORY_CANONICALIZATION = "json-sort-keys-compact-utf8-v1"
DEFAULT_RUN_HISTORY_LIMIT = 20
_PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class RunHistoryFormatError(ValueError):
    """Raised when a retained analysis-run artifact is malformed or corrupted."""


@dataclass(frozen=True)
class ArchivedAnalysisRun:
    path: Path
    history_id: str
    saved_at_utc: str
    application_version: str
    project_identity: str
    project_name: str
    source_path: Path | None
    analysis_id: str
    analysis_name: str
    run: AnalysisRun


@dataclass(frozen=True)
class RunHistoryEntry:
    path: Path
    history_id: str
    saved_at_utc: str
    project_identity: str
    project_name: str
    source_path: Path | None
    analysis_id: str
    analysis_name: str
    analysis_kind: str
    run_status: str
    input_sha256: str


@dataclass(frozen=True)
class RunHistoryScanIssue:
    path: Path
    error: str


@dataclass(frozen=True)
class RunHistoryScan:
    entries: tuple[RunHistoryEntry, ...]
    issues: tuple[RunHistoryScanIssue, ...]


@dataclass(frozen=True)
class RunHistoryStatus:
    state: str
    message: str
    artifact_path: Path | None = None
    sequence: int = 0


@dataclass(frozen=True)
class _ArchiveRequest:
    project_identity: str
    project_name: str
    source_path: str | None
    analysis_id: str
    analysis_name: str
    run_bundle_json: str


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_utc(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise RunHistoryFormatError("saved_at_utc must be a non-empty ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RunHistoryFormatError("saved_at_utc is not valid ISO-8601") from exc
    if parsed.tzinfo is None:
        raise RunHistoryFormatError("saved_at_utc must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


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


def _ensure_history_dir(path: Path) -> Path:
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


def _payload_sha256(core: dict[str, Any]) -> str:
    return sha256(_canonical_json(core).encode("utf-8")).hexdigest()


def _validated_nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RunHistoryFormatError(f"{field} must be a non-empty string")
    return value


def _validated_run_dict(value: Any, *, expected_kind: str | None = None) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RunHistoryFormatError("run must be an object")
    kind = _validated_nonempty_string(value.get("kind"), "run.kind")
    if expected_kind is not None and kind != expected_kind:
        raise RunHistoryFormatError(
            f"run.kind {kind!r} does not match archived analysis kind {expected_kind!r}"
        )
    _validated_nonempty_string(value.get("title"), "run.title")
    _validated_nonempty_string(value.get("status"), "run.status")
    if not isinstance(value.get("result"), dict):
        raise RunHistoryFormatError("run.result must be an object")
    if not isinstance(value.get("markdown"), str):
        raise RunHistoryFormatError("run.markdown must be a string")
    diagnostics = value.get("diagnostics")
    if not isinstance(diagnostics, dict):
        raise RunHistoryFormatError("run.diagnostics must be an object")
    plot = value.get("plot")
    if plot is not None and not isinstance(plot, dict):
        raise RunHistoryFormatError("run.plot must be an object or null")

    provenance = diagnostics.get("application_execution_provenance")
    if not isinstance(provenance, dict):
        raise RunHistoryFormatError(
            "run diagnostics must contain application execution provenance"
        )
    if provenance.get("analysis_kind") != kind:
        raise RunHistoryFormatError(
            "run provenance analysis_kind does not match run.kind"
        )
    input_sha256 = provenance.get("input_sha256")
    if (
        not isinstance(input_sha256, str)
        or len(input_sha256) != 64
        or any(ch not in "0123456789abcdef" for ch in input_sha256.lower())
    ):
        raise RunHistoryFormatError(
            "run provenance input_sha256 must be a 64-character hexadecimal digest"
        )
    return value


def _run_from_dict(value: dict[str, Any]) -> AnalysisRun:
    return AnalysisRun(
        kind=value["kind"],
        title=value["title"],
        status=value["status"],
        result=value["result"],
        markdown=value["markdown"],
        diagnostics=value["diagnostics"],
        plot=value["plot"],
    )


def _validated_payload(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise RunHistoryFormatError("run-history artifact must contain a JSON object")
    if data.get("schema") != RUN_HISTORY_SCHEMA:
        raise RunHistoryFormatError(f"run-history schema must be {RUN_HISTORY_SCHEMA!r}")
    if data.get("schema_version") != RUN_HISTORY_SCHEMA_VERSION:
        raise RunHistoryFormatError(
            f"unsupported run-history schema version {data.get('schema_version')!r}; "
            f"expected {RUN_HISTORY_SCHEMA_VERSION}"
        )

    history_id = _validated_nonempty_string(data.get("history_id"), "history_id")
    if not re.fullmatch(r"[0-9a-f]{32}", history_id):
        raise RunHistoryFormatError("history_id must be a lowercase 32-character hex id")
    saved_at = _parse_utc(data.get("saved_at_utc"))
    _validated_nonempty_string(data.get("application_version"), "application_version")

    project = data.get("project")
    if not isinstance(project, dict):
        raise RunHistoryFormatError("project must be an object")
    identity = _validated_nonempty_string(project.get("identity"), "project.identity")
    if not _PROJECT_ID_RE.fullmatch(identity):
        raise RunHistoryFormatError("project.identity contains unsupported characters")
    _validated_nonempty_string(project.get("name"), "project.name")
    source_path = project.get("source_path")
    if source_path is not None and not isinstance(source_path, str):
        raise RunHistoryFormatError("project.source_path must be a string or null")

    analysis = data.get("analysis")
    if not isinstance(analysis, dict):
        raise RunHistoryFormatError("analysis must be an object")
    _validated_nonempty_string(analysis.get("id"), "analysis.id")
    _validated_nonempty_string(analysis.get("name"), "analysis.name")
    analysis_kind = _validated_nonempty_string(analysis.get("kind"), "analysis.kind")
    _validated_run_dict(data.get("run"), expected_kind=analysis_kind)

    integrity = data.get("integrity")
    if not isinstance(integrity, dict):
        raise RunHistoryFormatError("integrity must be an object")
    if integrity.get("algorithm") != "sha256":
        raise RunHistoryFormatError("integrity.algorithm must be 'sha256'")
    if integrity.get("canonicalization") != RUN_HISTORY_CANONICALIZATION:
        raise RunHistoryFormatError(
            "unsupported run-history integrity canonicalization"
        )
    recorded_digest = integrity.get("payload_sha256")
    if not isinstance(recorded_digest, str) or len(recorded_digest) != 64:
        raise RunHistoryFormatError("integrity.payload_sha256 must be a SHA-256 digest")

    core = {key: value for key, value in data.items() if key != "integrity"}
    actual_digest = _payload_sha256(core)
    if actual_digest != recorded_digest:
        raise RunHistoryFormatError(
            "run-history integrity check failed; the artifact is corrupted or modified"
        )

    if saved_at != data["saved_at_utc"]:
        data = dict(data)
        data["saved_at_utc"] = saved_at
    return data


def load_run_history_artifact(path: str | Path) -> ArchivedAnalysisRun:
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
    payload = _validated_payload(data)
    project = payload["project"]
    analysis = payload["analysis"]
    source_path = project["source_path"]
    return ArchivedAnalysisRun(
        path=source,
        history_id=payload["history_id"],
        saved_at_utc=payload["saved_at_utc"],
        application_version=payload["application_version"],
        project_identity=project["identity"],
        project_name=project["name"],
        source_path=Path(source_path) if source_path is not None else None,
        analysis_id=analysis["id"],
        analysis_name=analysis["name"],
        run=_run_from_dict(payload["run"]),
    )


def _entry_from_archive(archive: ArchivedAnalysisRun) -> RunHistoryEntry:
    provenance = archive.run.diagnostics["application_execution_provenance"]
    return RunHistoryEntry(
        path=archive.path,
        history_id=archive.history_id,
        saved_at_utc=archive.saved_at_utc,
        project_identity=archive.project_identity,
        project_name=archive.project_name,
        source_path=archive.source_path,
        analysis_id=archive.analysis_id,
        analysis_name=archive.analysis_name,
        analysis_kind=archive.run.kind,
        run_status=archive.run.status,
        input_sha256=provenance["input_sha256"],
    )


def scan_run_history(
    history_dir: str | Path | None = None,
    *,
    project_identity_value: str | None = None,
) -> RunHistoryScan:
    directory = Path(history_dir) if history_dir is not None else default_run_history_dir()
    if not directory.exists():
        return RunHistoryScan(entries=(), issues=())

    entries: list[RunHistoryEntry] = []
    issues: list[RunHistoryScanIssue] = []
    for path in sorted(directory.glob("*.run.json")):
        try:
            archive = load_run_history_artifact(path)
            if (
                project_identity_value is None
                or archive.project_identity == project_identity_value
            ):
                entries.append(_entry_from_archive(archive))
        except (OSError, RunHistoryFormatError, TypeError, ValueError) as exc:
            issues.append(RunHistoryScanIssue(path=path, error=str(exc)))

    entries.sort(key=lambda item: (item.saved_at_utc, item.history_id), reverse=True)
    return RunHistoryScan(entries=tuple(entries), issues=tuple(issues))


class RunHistoryManager:
    """Asynchronously retain accepted analysis evidence as bounded local artifacts."""

    def __init__(
        self,
        history_dir: str | Path | None = None,
        *,
        history_limit: int = DEFAULT_RUN_HISTORY_LIMIT,
    ) -> None:
        if history_limit < 1:
            raise ValueError("history_limit must be at least 1")
        self.history_dir = (
            Path(history_dir) if history_dir is not None else default_run_history_dir()
        )
        self.history_limit = history_limit
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="cleanroomx-run-history",
        )
        self._lock = threading.RLock()
        self._pending = 0
        self._closed = False
        self._sequence = 0
        self._status = RunHistoryStatus(
            state="idle",
            message="Run history ready",
            sequence=self._sequence,
        )
        self._failures: list[str] = []

    def status(self) -> RunHistoryStatus:
        with self._lock:
            return self._status

    def drain_failures(self) -> tuple[str, ...]:
        with self._lock:
            failures = tuple(self._failures)
            self._failures.clear()
            return failures

    def archive(
        self,
        *,
        project_identity: str,
        project_name: str,
        source_path: str | Path | None,
        analysis_id: str,
        analysis_name: str,
        run: AnalysisRun,
    ) -> bool:
        if not isinstance(project_identity, str) or not _PROJECT_ID_RE.fullmatch(
            project_identity
        ):
            raise ValueError("project_identity must contain only filename-safe characters")
        if not isinstance(project_name, str) or not project_name.strip():
            raise ValueError("project_name must be a non-empty string")
        if not isinstance(analysis_id, str) or not analysis_id.strip():
            raise ValueError("analysis_id must be a non-empty string")
        if not isinstance(analysis_name, str) or not analysis_name.strip():
            raise ValueError("analysis_name must be a non-empty string")
        if run.kind != run.diagnostics.get("application_execution_provenance", {}).get(
            "analysis_kind"
        ):
            raise ValueError("run provenance does not match run kind")

        run_bundle_json = _canonical_json(run.to_dict())
        _validated_run_dict(json.loads(run_bundle_json), expected_kind=run.kind)
        normalized_source = (
            None
            if source_path is None
            else str(Path(source_path).expanduser().resolve(strict=False))
        )
        request = _ArchiveRequest(
            project_identity=project_identity,
            project_name=project_name,
            source_path=normalized_source,
            analysis_id=analysis_id,
            analysis_name=analysis_name,
            run_bundle_json=run_bundle_json,
        )

        with self._lock:
            if self._closed:
                return False
            self._pending += 1
            self._set_status_locked("saving", "Run history saving")
            future = self._executor.submit(self._write_archive, request)
            future.add_done_callback(self._on_archive_done)
            return True

    def _write_archive(self, request: _ArchiveRequest) -> Path:
        run = json.loads(request.run_bundle_json, parse_constant=_reject_json_constant)
        history_id = uuid.uuid4().hex
        saved_at_utc = _utc_now_text()
        core = {
            "schema": RUN_HISTORY_SCHEMA,
            "schema_version": RUN_HISTORY_SCHEMA_VERSION,
            "history_id": history_id,
            "saved_at_utc": saved_at_utc,
            "application_version": __version__,
            "project": {
                "identity": request.project_identity,
                "name": request.project_name,
                "source_path": request.source_path,
            },
            "analysis": {
                "id": request.analysis_id,
                "name": request.analysis_name,
                "kind": run["kind"],
            },
            "run": run,
        }
        payload = {
            **core,
            "integrity": {
                "algorithm": "sha256",
                "canonicalization": RUN_HISTORY_CANONICALIZATION,
                "payload_sha256": _payload_sha256(core),
            },
        }
        _validated_payload(payload)

        directory = _ensure_history_dir(self.history_dir)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        destination = directory / (
            f"{request.project_identity}-{stamp}-{history_id[:8]}.run.json"
        )
        text = json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        ) + "\n"
        atomic_write_text(destination, text)
        self._rotate_history(request.project_identity)
        return destination

    def _rotate_history(self, project_identity: str) -> None:
        artifacts = sorted(
            self.history_dir.glob(f"{project_identity}-*.run.json"),
            key=lambda path: path.name,
            reverse=True,
        )
        for stale in artifacts[self.history_limit :]:
            stale.unlink(missing_ok=True)

    def _on_archive_done(self, future: Future[Path]) -> None:
        try:
            artifact = future.result()
            failure: Exception | None = None
        except Exception as exc:  # background persistence boundary
            artifact = None
            failure = exc

        with self._lock:
            self._pending = max(0, self._pending - 1)
            if failure is not None:
                message = f"Run history save failed: {failure}"
                self._failures.append(message)
                self._set_status_locked("failed", message)
            elif self._pending:
                self._set_status_locked(
                    "saving",
                    f"Run history saving ({self._pending} pending)",
                    artifact_path=artifact,
                )
            else:
                self._set_status_locked(
                    "saved",
                    "Run history saved",
                    artifact_path=artifact,
                )

    def _set_status_locked(
        self,
        state: str,
        message: str,
        *,
        artifact_path: Path | None = None,
    ) -> None:
        self._sequence += 1
        self._status = RunHistoryStatus(
            state=state,
            message=message,
            artifact_path=artifact_path,
            sequence=self._sequence,
        )

    def wait_for_idle(self, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                idle = self._pending == 0
                failures = tuple(self._failures)
            if idle:
                if failures:
                    raise RuntimeError(failures[-1])
                return
            if time.monotonic() >= deadline:
                raise TimeoutError("run-history worker did not become idle before timeout")
            time.sleep(0.01)

    def shutdown(self, *, wait: bool = True) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._executor.shutdown(wait=wait, cancel_futures=False)
