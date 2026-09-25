from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from hmac import compare_digest
import json
import os
from pathlib import Path
import sys
import threading
import time
import uuid
from typing import Any

from . import __version__
from .project import ProjectDocument, atomic_write_text, project_from_dict


RECOVERY_SCHEMA = "cleanroomx.autosave"
RECOVERY_SCHEMA_VERSION = 1
RECOVERY_INTEGRITY_ALGORITHM = "sha256"
DEFAULT_AUTOSAVE_INTERVAL_SECONDS = 60.0
DEFAULT_RECOVERY_HISTORY_LIMIT = 5


class RecoveryFormatError(ValueError):
    """Raised when a recovery artifact is malformed or unsupported."""


@dataclass(frozen=True)
class AutosaveStatus:
    state: str
    message: str
    artifact_path: Path | None = None
    updated_at_utc: str | None = None
    sequence: int = 0


@dataclass(frozen=True)
class RecoveryCandidate:
    path: Path
    project_identity: str
    saved_at_utc: str
    project_name: str
    integrity_status: str
    source_path: Path | None
    source_relation: str
    source_is_newer: bool


@dataclass(frozen=True)
class RecoveryScanIssue:
    path: Path
    error: str


@dataclass(frozen=True)
class RecoveryScan:
    candidates: tuple[RecoveryCandidate, ...]
    issues: tuple[RecoveryScanIssue, ...]


@dataclass(frozen=True)
class RecoveredProjectState:
    project: ProjectDocument
    ui_state: dict[str, Any]
    source_path: Path | None
    saved_at_utc: str
    project_identity: str
    artifact_path: Path


@dataclass(frozen=True)
class _AutosaveRequest:
    project_identity: str
    epoch: int
    source_path: Path | None
    snapshot_text: str
    digest: str


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_utc(text: str) -> datetime:
    if not isinstance(text, str) or not text:
        raise RecoveryFormatError("saved_at_utc must be a non-empty string")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RecoveryFormatError("saved_at_utc is not a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise RecoveryFormatError("saved_at_utc must include a timezone")
    return parsed.astimezone(timezone.utc)


def default_recovery_dir() -> Path:
    override = os.environ.get("CLEANROOMX_RECOVERY_DIR")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "CleanroomX" / "Recovery"
        return Path.home() / "AppData" / "Local" / "CleanroomX" / "Recovery"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "CleanroomX" / "Recovery"
    state_home = os.environ.get("XDG_STATE_HOME")
    if state_home:
        return Path(state_home) / "cleanroomx" / "recovery"
    return Path.home() / ".local" / "state" / "cleanroomx" / "recovery"


def _ensure_recovery_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        try:
            path.chmod(0o700)
        except OSError:
            pass
    return path


def _reject_json_constant(value: str):
    raise RecoveryFormatError(f"non-finite JSON constant is not allowed: {value}")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )


def _recovery_payload_sha256(payload: dict[str, Any]) -> str:
    unsigned = {key: value for key, value in payload.items() if key != "integrity"}
    return sha256(_canonical_json(unsigned).encode("utf-8")).hexdigest()


def recovery_integrity_status(payload: dict[str, Any]) -> str:
    """Return the integrity evidence level for an already validated artifact."""
    return "verified" if payload.get("integrity") is not None else "legacy_unverified"


def _normalized_source_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def project_identity(path: str | Path | None, *, unsaved_id: str) -> str:
    if path is None:
        return f"session-{unsaved_id}"
    normalized = os.path.normcase(str(_normalized_source_path(path)))
    return "file-" + sha256(normalized.encode("utf-8")).hexdigest()[:24]


def _file_sha256(path: Path) -> tuple[os.stat_result, str]:
    last_error: OSError | None = None
    for _attempt in range(2):
        before = path.stat()
        digest = sha256()
        try:
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as exc:
            last_error = exc
            continue
        after = path.stat()
        if before.st_size == after.st_size and before.st_mtime_ns == after.st_mtime_ns:
            return after, digest.hexdigest()
        last_error = OSError(f"source changed while fingerprinting: {path}")
    assert last_error is not None
    raise last_error


def source_fingerprint(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {
            "path": None,
            "exists": False,
            "size": None,
            "mtime_ns": None,
            "sha256": None,
        }
    source = _normalized_source_path(path)
    if not source.exists():
        return {
            "path": str(source),
            "exists": False,
            "size": None,
            "mtime_ns": None,
            "sha256": None,
        }
    stat, digest = _file_sha256(source)
    return {
        "path": str(source),
        "exists": True,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": digest,
    }


def _artifact_filename(project_identity_value: str, recovery_id: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{project_identity_value}-{stamp}-{recovery_id[:8]}.recovery.json"


def _validate_recovery_payload(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise RecoveryFormatError("recovery artifact must contain a JSON object")
    if data.get("schema") != RECOVERY_SCHEMA:
        raise RecoveryFormatError(f"recovery schema must be {RECOVERY_SCHEMA!r}")
    version = data.get("schema_version")
    if version != RECOVERY_SCHEMA_VERSION:
        raise RecoveryFormatError(
            f"unsupported recovery schema version {version!r}; "
            f"expected {RECOVERY_SCHEMA_VERSION}"
        )
    identity = data.get("project_identity")
    if not isinstance(identity, str) or not identity:
        raise RecoveryFormatError("project_identity must be a non-empty string")
    _parse_utc(data.get("saved_at_utc"))
    source = data.get("source")
    if not isinstance(source, dict):
        raise RecoveryFormatError("source must be an object")
    source_path = source.get("path")
    if source_path is not None and not isinstance(source_path, str):
        raise RecoveryFormatError("source.path must be a string or null")
    snapshot = data.get("snapshot")
    if not isinstance(snapshot, dict):
        raise RecoveryFormatError("snapshot must be an object")

    integrity = data.get("integrity")
    if integrity is not None:
        if not isinstance(integrity, dict):
            raise RecoveryFormatError("integrity must be an object when present")
        algorithm = integrity.get("algorithm")
        if algorithm != RECOVERY_INTEGRITY_ALGORITHM:
            raise RecoveryFormatError(
                "unsupported recovery integrity algorithm "
                f"{algorithm!r}; expected {RECOVERY_INTEGRITY_ALGORITHM!r}"
            )
        recorded_digest = integrity.get("payload_sha256")
        if (
            not isinstance(recorded_digest, str)
            or len(recorded_digest) != 64
            or any(char not in "0123456789abcdef" for char in recorded_digest)
        ):
            raise RecoveryFormatError(
                "integrity.payload_sha256 must be a lowercase SHA-256 hex digest"
            )
        computed_digest = _recovery_payload_sha256(data)
        if not compare_digest(recorded_digest, computed_digest):
            raise RecoveryFormatError(
                "recovery payload integrity check failed; artifact contents changed"
            )
    return data


def load_recovery_artifact(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        data = json.loads(
            source.read_text(encoding="utf-8"),
            parse_constant=_reject_json_constant,
        )
    except json.JSONDecodeError as exc:
        raise RecoveryFormatError(
            f"invalid recovery JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc
    return _validate_recovery_payload(data)


def restore_recovery_artifact(path: str | Path) -> RecoveredProjectState:
    artifact_path = Path(path)
    recovery = load_recovery_artifact(artifact_path)
    snapshot = recovery["snapshot"]
    project_data = snapshot.get("project")
    if not isinstance(project_data, dict):
        raise RecoveryFormatError("snapshot.project must be an object")
    try:
        project = project_from_dict(project_data)
    except (TypeError, ValueError) as exc:
        raise RecoveryFormatError(f"recovered project is invalid: {exc}") from exc

    ui_state = snapshot.get("ui_state", {})
    if not isinstance(ui_state, dict):
        raise RecoveryFormatError("snapshot.ui_state must be an object")

    source_path_text = recovery["source"].get("path")
    source_path = Path(source_path_text) if source_path_text is not None else None
    return RecoveredProjectState(
        project=project,
        ui_state=dict(ui_state),
        source_path=source_path,
        saved_at_utc=recovery["saved_at_utc"],
        project_identity=recovery["project_identity"],
        artifact_path=artifact_path,
    )


def discard_recovery_artifact(
    path: str | Path,
    *,
    recovery_dir: str | Path | None = None,
) -> None:
    artifact_path = Path(path)
    directory = (
        Path(recovery_dir) if recovery_dir is not None else default_recovery_dir()
    )
    try:
        resolved_artifact = artifact_path.resolve(strict=True)
        resolved_directory = directory.resolve(strict=True)
        resolved_artifact.relative_to(resolved_directory)
    except (FileNotFoundError, ValueError) as exc:
        raise RecoveryFormatError(
            "recovery artifact must be an existing file inside the recovery directory"
        ) from exc
    if not resolved_artifact.name.endswith(".recovery.json"):
        raise RecoveryFormatError("refusing to discard a non-recovery file")
    load_recovery_artifact(resolved_artifact)
    resolved_artifact.unlink()


def _compare_source(recovery: dict[str, Any]) -> tuple[str, bool, Path | None]:
    source = recovery["source"]
    source_path_text = source.get("path")
    if source_path_text is None:
        return "unsaved", False, None
    source_path = Path(source_path_text)
    if not source_path.exists():
        return "source_missing", False, source_path

    current = source_fingerprint(source_path)
    if (
        source.get("exists") is True
        and source.get("sha256")
        and current.get("sha256") == source.get("sha256")
    ):
        return "source_unchanged", False, source_path

    saved_at = _parse_utc(recovery["saved_at_utc"])
    current_mtime_ns = current.get("mtime_ns")
    current_mtime = (
        datetime.fromtimestamp(current_mtime_ns / 1_000_000_000, tz=timezone.utc)
        if isinstance(current_mtime_ns, int)
        else None
    )
    is_newer = current_mtime is not None and current_mtime > saved_at
    return ("source_newer" if is_newer else "source_changed"), is_newer, source_path


def scan_recovery_artifacts(recovery_dir: str | Path | None = None) -> RecoveryScan:
    directory = Path(recovery_dir) if recovery_dir is not None else default_recovery_dir()
    if not directory.exists():
        return RecoveryScan(candidates=(), issues=())

    candidates: list[RecoveryCandidate] = []
    issues: list[RecoveryScanIssue] = []
    for path in sorted(directory.glob("*.recovery.json")):
        try:
            recovery = load_recovery_artifact(path)
            relation, is_newer, source_path = _compare_source(recovery)
            project = recovery["snapshot"].get("project", {})
            project_block = project.get("project", {}) if isinstance(project, dict) else {}
            project_name = (
                project_block.get("name", "Untitled Project")
                if isinstance(project_block, dict)
                else "Untitled Project"
            )
            if not isinstance(project_name, str) or not project_name:
                project_name = "Untitled Project"
            candidates.append(
                RecoveryCandidate(
                    path=path,
                    project_identity=recovery["project_identity"],
                    saved_at_utc=recovery["saved_at_utc"],
                    project_name=project_name,
                    integrity_status=recovery_integrity_status(recovery),
                    source_path=source_path,
                    source_relation=relation,
                    source_is_newer=is_newer,
                )
            )
        except (OSError, RecoveryFormatError, TypeError, ValueError) as exc:
            issues.append(RecoveryScanIssue(path=path, error=str(exc)))

    candidates.sort(key=lambda item: item.saved_at_utc, reverse=True)
    return RecoveryScan(candidates=tuple(candidates), issues=tuple(issues))


class AutosaveManager:
    """Serialize recovery snapshots away from the Tk/UI thread.

    Explicit project files are never written by this class. Recovery artifacts are
    separate JSON envelopes with bounded per-project history.
    """

    def __init__(
        self,
        recovery_dir: str | Path | None = None,
        *,
        history_limit: int = DEFAULT_RECOVERY_HISTORY_LIMIT,
        session_id: str | None = None,
    ) -> None:
        if history_limit < 1:
            raise ValueError("history_limit must be at least 1")
        self.recovery_dir = (
            Path(recovery_dir) if recovery_dir is not None else default_recovery_dir()
        )
        self.history_limit = history_limit
        self.session_id = session_id or uuid.uuid4().hex
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="cleanroomx-autosave",
        )
        self._lock = threading.RLock()
        self._current_identity = project_identity(None, unsaved_id=self.session_id)
        self._epochs: dict[str, int] = {self._current_identity: 0}
        self._last_saved_digest: dict[str, str] = {}
        self._artifacts_by_identity: dict[str, set[Path]] = {}
        self._active_request: _AutosaveRequest | None = None
        self._pending_request: _AutosaveRequest | None = None
        self._future: Future[Path] | None = None
        self._status = AutosaveStatus(
            state="idle",
            message="Autosave ready",
            updated_at_utc=_utc_now_text(),
        )
        self._sequence = 0
        self._closed = False

    @property
    def current_identity(self) -> str:
        with self._lock:
            return self._current_identity

    def begin_project(self, source_path: str | Path | None) -> str:
        with self._lock:
            if source_path is None:
                identity = project_identity(None, unsaved_id=uuid.uuid4().hex)
            else:
                identity = project_identity(source_path, unsaved_id=self.session_id)
            self._current_identity = identity
            self._epochs.setdefault(identity, 0)
            self._last_saved_digest.pop(identity, None)
            self._set_status_locked("idle", "Autosave ready")
            return identity

    def status(self) -> AutosaveStatus:
        with self._lock:
            return self._status

    def request_autosave(
        self,
        snapshot: dict[str, Any],
        *,
        source_path: str | Path | None,
    ) -> bool:
        snapshot_text = _canonical_json(snapshot)
        digest = sha256(snapshot_text.encode("utf-8")).hexdigest()
        normalized_source = (
            None if source_path is None else _normalized_source_path(source_path)
        )

        with self._lock:
            if self._closed:
                return False
            identity = self._current_identity
            epoch = self._epochs.setdefault(identity, 0)
            if self._last_saved_digest.get(identity) == digest:
                return False
            active_digest = (
                self._active_request.digest if self._active_request is not None else None
            )
            pending_digest = (
                self._pending_request.digest if self._pending_request is not None else None
            )
            if digest in {active_digest, pending_digest}:
                return False

            request = _AutosaveRequest(
                project_identity=identity,
                epoch=epoch,
                source_path=normalized_source,
                snapshot_text=snapshot_text,
                digest=digest,
            )
            if self._future is not None and not self._future.done():
                self._pending_request = request
                self._set_status_locked("saving", "Autosave queued")
                return True

            self._submit_locked(request)
            return True

    def _submit_locked(self, request: _AutosaveRequest) -> None:
        self._active_request = request
        self._set_status_locked("saving", "Autosave saving")
        future = self._executor.submit(self._write_recovery, request)
        self._future = future
        future.add_done_callback(
            lambda completed, request=request: self._on_write_done(request, completed)
        )

    def _write_recovery(self, request: _AutosaveRequest) -> Path:
        snapshot = json.loads(request.snapshot_text)
        recovery_id = uuid.uuid4().hex
        payload = {
            "schema": RECOVERY_SCHEMA,
            "schema_version": RECOVERY_SCHEMA_VERSION,
            "application_version": __version__,
            "session_id": self.session_id,
            "recovery_id": recovery_id,
            "project_identity": request.project_identity,
            "saved_at_utc": _utc_now_text(),
            "source": source_fingerprint(request.source_path),
            "snapshot": snapshot,
        }
        payload["integrity"] = {
            "algorithm": RECOVERY_INTEGRITY_ALGORITHM,
            "payload_sha256": _recovery_payload_sha256(payload),
        }
        _validate_recovery_payload(payload)
        directory = _ensure_recovery_dir(self.recovery_dir)
        destination = directory / _artifact_filename(
            request.project_identity, recovery_id
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

    def _rotate_history(self, identity: str) -> None:
        artifacts = sorted(
            self.recovery_dir.glob(f"{identity}-*.recovery.json"),
            key=lambda path: path.name,
            reverse=True,
        )
        for stale in artifacts[self.history_limit :]:
            stale.unlink(missing_ok=True)

    def _on_write_done(
        self,
        request: _AutosaveRequest,
        future: Future[Path],
    ) -> None:
        try:
            artifact = future.result()
            failure: Exception | None = None
        except Exception as exc:  # background-worker error boundary
            artifact = None
            failure = exc

        with self._lock:
            current_epoch = self._epochs.get(request.project_identity, 0)
            stale = request.epoch != current_epoch
            if stale and artifact is not None:
                try:
                    artifact.unlink(missing_ok=True)
                except OSError:
                    pass

            if not stale:
                if failure is None:
                    self._last_saved_digest[request.project_identity] = request.digest
                    assert artifact is not None
                    self._artifacts_by_identity.setdefault(
                        request.project_identity, set()
                    ).add(artifact)
                    self._set_status_locked(
                        "saved",
                        "Autosave saved",
                        artifact_path=artifact,
                    )
                else:
                    self._set_status_locked(
                        "failed",
                        f"Autosave failed: {failure}",
                    )

            self._active_request = None
            self._future = None
            pending = self._pending_request
            self._pending_request = None
            if pending is not None:
                pending_epoch = self._epochs.get(pending.project_identity, 0)
                if pending.epoch == pending_epoch and not self._closed:
                    self._submit_locked(pending)

    def _set_status_locked(
        self,
        state: str,
        message: str,
        *,
        artifact_path: Path | None = None,
    ) -> None:
        self._sequence += 1
        self._status = AutosaveStatus(
            state=state,
            message=message,
            artifact_path=artifact_path,
            updated_at_utc=_utc_now_text(),
            sequence=self._sequence,
        )

    def _clear_identity_locked(self, identity: str) -> None:
        self._epochs[identity] = self._epochs.get(identity, 0) + 1
        self._last_saved_digest.pop(identity, None)
        if (
            self._pending_request is not None
            and self._pending_request.project_identity == identity
        ):
            self._pending_request = None
        artifacts = self._artifacts_by_identity.pop(identity, set())
        for artifact in artifacts:
            try:
                artifact.unlink(missing_ok=True)
            except OSError:
                pass

    def discard_current_recoveries(self) -> None:
        with self._lock:
            self._clear_identity_locked(self._current_identity)
            self._set_status_locked("idle", "Autosave recovery discarded")

    def notify_explicit_save(self, source_path: str | Path) -> None:
        with self._lock:
            previous = self._current_identity
            new_identity = project_identity(source_path, unsaved_id=self.session_id)
            self._clear_identity_locked(previous)
            if new_identity != previous:
                self._clear_identity_locked(new_identity)
            self._current_identity = new_identity
            self._epochs.setdefault(new_identity, 0)
            self._set_status_locked("idle", "Autosave clean after explicit save")

    def wait_for_idle(self, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                idle = self._future is None and self._pending_request is None
                failure = self._status if self._status.state == "failed" else None
            if idle:
                if failure is not None:
                    raise RuntimeError(failure.message)
                return
            if time.monotonic() >= deadline:
                raise TimeoutError("autosave worker did not become idle before timeout")
            time.sleep(0.01)

    def shutdown(self, *, wait: bool = False) -> None:
        with self._lock:
            self._closed = True
            self._pending_request = None
        self._executor.shutdown(wait=wait, cancel_futures=False)
