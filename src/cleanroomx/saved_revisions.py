from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import uuid
from typing import Any

from . import __version__
from .project import (
    ProjectDocument,
    ProjectFileRevision,
    ProjectWriteConflictError,
    atomic_write_text,
    project_file_revision_matches,
    project_from_dict,
    save_project_document_guarded,
)


SAVED_REVISION_SCHEMA = "cleanroomx.saved_revision"
SAVED_REVISION_SCHEMA_VERSION = 1
DEFAULT_SAVED_REVISION_HISTORY_LIMIT = 10


class SavedRevisionFormatError(ValueError):
    """Raised when a saved-revision artifact is malformed or unsupported."""


@dataclass(frozen=True)
class SavedRevisionCandidate:
    path: Path
    project_name: str
    source_path: Path
    archived_at_utc: str
    source_sha256: str
    source_size_bytes: int
    application_version: str


@dataclass(frozen=True)
class SavedRevisionScanIssue:
    path: Path
    error: str


@dataclass(frozen=True)
class SavedRevisionScan:
    candidates: tuple[SavedRevisionCandidate, ...]
    issues: tuple[SavedRevisionScanIssue, ...]


@dataclass(frozen=True)
class RestoredSavedRevision:
    project: ProjectDocument
    source_path: Path
    archived_at_utc: str
    artifact_path: Path
    source_sha256: str
    source_text: str


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_utc(text: Any) -> datetime:
    if not isinstance(text, str) or not text:
        raise SavedRevisionFormatError("archived_at_utc must be a non-empty string")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SavedRevisionFormatError(
            "archived_at_utc is not a valid ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise SavedRevisionFormatError("archived_at_utc must include a timezone")
    return parsed.astimezone(timezone.utc)


def default_saved_revision_dir() -> Path:
    override = os.environ.get("CLEANROOMX_SAVED_REVISIONS_DIR")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "CleanroomX" / "SavedRevisions"
        return Path.home() / "AppData" / "Local" / "CleanroomX" / "SavedRevisions"
    if sys.platform == "darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "CleanroomX"
            / "SavedRevisions"
        )
    state_home = os.environ.get("XDG_STATE_HOME")
    if state_home:
        return Path(state_home) / "cleanroomx" / "saved-revisions"
    return Path.home() / ".local" / "state" / "cleanroomx" / "saved-revisions"


def _ensure_saved_revision_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        try:
            path.chmod(0o700)
        except OSError:
            pass
    return path


def _reject_json_constant(value: str):
    raise SavedRevisionFormatError(f"non-finite JSON constant is not allowed: {value}")


def _normalized_source_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def saved_revision_identity(path: str | Path) -> str:
    normalized = os.path.normcase(str(_normalized_source_path(path)))
    return "file-" + sha256(normalized.encode("utf-8")).hexdigest()[:24]


def _artifact_filename(identity: str, revision_id: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{identity}-{stamp}-{revision_id[:8]}.saved-revision.json"


def _read_stable_bytes(path: Path) -> tuple[os.stat_result, bytes]:
    last_error: OSError | None = None
    for _attempt in range(2):
        before = path.stat()
        try:
            data = path.read_bytes()
        except OSError as exc:
            last_error = exc
            continue
        after = path.stat()
        if (
            before.st_size == after.st_size
            and before.st_mtime_ns == after.st_mtime_ns
            and len(data) == after.st_size
        ):
            return after, data
        last_error = OSError(f"project changed while archiving saved revision: {path}")
    assert last_error is not None
    raise last_error


def _validated_project_text(text: str) -> ProjectDocument:
    try:
        data = json.loads(text, parse_constant=_reject_json_constant)
    except json.JSONDecodeError as exc:
        raise SavedRevisionFormatError(
            f"saved project contains invalid JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc
    try:
        return project_from_dict(data)
    except (TypeError, ValueError) as exc:
        raise SavedRevisionFormatError(f"saved project is invalid: {exc}") from exc


def _validate_saved_revision_payload(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise SavedRevisionFormatError("saved-revision artifact must contain a JSON object")
    if data.get("schema") != SAVED_REVISION_SCHEMA:
        raise SavedRevisionFormatError(
            f"saved-revision schema must be {SAVED_REVISION_SCHEMA!r}"
        )
    version = data.get("schema_version")
    if version != SAVED_REVISION_SCHEMA_VERSION:
        raise SavedRevisionFormatError(
            f"unsupported saved-revision schema version {version!r}; "
            f"expected {SAVED_REVISION_SCHEMA_VERSION}"
        )
    _parse_utc(data.get("archived_at_utc"))
    source = data.get("source")
    if not isinstance(source, dict):
        raise SavedRevisionFormatError("source must be an object")
    source_path = source.get("path")
    if not isinstance(source_path, str) or not source_path:
        raise SavedRevisionFormatError("source.path must be a non-empty string")
    source_sha256 = source.get("sha256")
    if (
        not isinstance(source_sha256, str)
        or len(source_sha256) != 64
        or any(ch not in "0123456789abcdef" for ch in source_sha256)
    ):
        raise SavedRevisionFormatError("source.sha256 must be a lowercase SHA-256 hex digest")
    source_size = source.get("size_bytes")
    if not isinstance(source_size, int) or source_size < 0:
        raise SavedRevisionFormatError("source.size_bytes must be a non-negative integer")
    source_text = data.get("source_text")
    if not isinstance(source_text, str):
        raise SavedRevisionFormatError("source_text must be a string")
    raw = source_text.encode("utf-8")
    if len(raw) != source_size:
        raise SavedRevisionFormatError(
            "saved-revision source size does not match the archived UTF-8 bytes"
        )
    digest = sha256(raw).hexdigest()
    if digest != source_sha256:
        raise SavedRevisionFormatError(
            "saved-revision source checksum does not match the archived content"
        )
    _validated_project_text(source_text)
    return data


def load_saved_revision_artifact(path: str | Path) -> dict[str, Any]:
    artifact = Path(path)
    try:
        data = json.loads(
            artifact.read_text(encoding="utf-8"),
            parse_constant=_reject_json_constant,
        )
    except json.JSONDecodeError as exc:
        raise SavedRevisionFormatError(
            f"invalid saved-revision JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc
    return _validate_saved_revision_payload(data)


def restore_saved_revision_artifact(path: str | Path) -> RestoredSavedRevision:
    artifact_path = Path(path)
    payload = load_saved_revision_artifact(artifact_path)
    source = payload["source"]
    source_text = payload["source_text"]
    project = _validated_project_text(source_text)
    return RestoredSavedRevision(
        project=project,
        source_path=Path(source["path"]),
        archived_at_utc=payload["archived_at_utc"],
        artifact_path=artifact_path,
        source_sha256=source["sha256"],
        source_text=source_text,
    )


def _candidate_from_payload(path: Path, payload: dict[str, Any]) -> SavedRevisionCandidate:
    project = _validated_project_text(payload["source_text"])
    source = payload["source"]
    return SavedRevisionCandidate(
        path=path,
        project_name=project.name,
        source_path=Path(source["path"]),
        archived_at_utc=payload["archived_at_utc"],
        source_sha256=source["sha256"],
        source_size_bytes=source["size_bytes"],
        application_version=str(payload.get("application_version", "unknown")),
    )


def scan_saved_revisions(
    source_path: str | Path,
    revision_dir: str | Path | None = None,
) -> SavedRevisionScan:
    source = _normalized_source_path(source_path)
    directory = (
        Path(revision_dir) if revision_dir is not None else default_saved_revision_dir()
    )
    if not directory.exists():
        return SavedRevisionScan(candidates=(), issues=())

    identity = saved_revision_identity(source)
    candidates: list[SavedRevisionCandidate] = []
    issues: list[SavedRevisionScanIssue] = []
    for path in sorted(directory.glob(f"{identity}-*.saved-revision.json")):
        try:
            payload = load_saved_revision_artifact(path)
            archived_source = _normalized_source_path(payload["source"]["path"])
            if os.path.normcase(str(archived_source)) != os.path.normcase(str(source)):
                raise SavedRevisionFormatError(
                    "saved-revision source path does not match requested project"
                )
            candidates.append(_candidate_from_payload(path, payload))
        except (OSError, SavedRevisionFormatError, TypeError, ValueError) as exc:
            issues.append(SavedRevisionScanIssue(path=path, error=str(exc)))

    candidates.sort(key=lambda item: item.archived_at_utc, reverse=True)
    return SavedRevisionScan(candidates=tuple(candidates), issues=tuple(issues))


def _rotate_history(
    source_path: Path,
    revision_dir: Path,
    *,
    history_limit: int,
) -> None:
    if history_limit < 1:
        raise ValueError("history_limit must be at least 1")
    scan = scan_saved_revisions(source_path, revision_dir)
    # Rotate only artifacts that passed schema, checksum, and embedded-project
    # validation. Unreadable/corrupt artifacts are evidence and are never silently
    # deleted by ordinary save rotation.
    for stale in scan.candidates[history_limit:]:
        stale.path.unlink(missing_ok=True)


def archive_project_revision(
    source_path: str | Path,
    *,
    expected_revision: ProjectFileRevision | None = None,
    revision_dir: str | Path | None = None,
    history_limit: int = DEFAULT_SAVED_REVISION_HISTORY_LIMIT,
) -> Path | None:
    if history_limit < 1:
        raise ValueError("history_limit must be at least 1")

    source = _normalized_source_path(source_path)
    if not source.exists():
        return None
    if not source.is_file():
        raise OSError(f"project path is not a file: {source}")

    stat, raw = _read_stable_bytes(source)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SavedRevisionFormatError(
            "existing project cannot be archived because it is not valid UTF-8"
        ) from exc
    project = _validated_project_text(text)
    digest = sha256(raw).hexdigest()
    current_revision = ProjectFileRevision(
        path=os.path.normcase(str(source)),
        exists=True,
        size=len(raw),
        mtime_ns=stat.st_mtime_ns,
        sha256=digest,
    )
    if (
        expected_revision is not None
        and not project_file_revision_matches(expected_revision, current_revision)
    ):
        raise ProjectWriteConflictError(source, expected_revision, current_revision)

    directory = _ensure_saved_revision_dir(
        Path(revision_dir) if revision_dir is not None else default_saved_revision_dir()
    )
    scan = scan_saved_revisions(source, directory)
    if scan.candidates and scan.candidates[0].source_sha256 == digest:
        return scan.candidates[0].path

    revision_id = uuid.uuid4().hex
    payload = {
        "schema": SAVED_REVISION_SCHEMA,
        "schema_version": SAVED_REVISION_SCHEMA_VERSION,
        "application_version": __version__,
        "revision_id": revision_id,
        "archived_at_utc": _utc_now_text(),
        "source": {
            "path": str(source),
            "size_bytes": len(raw),
            "mtime_ns": stat.st_mtime_ns,
            "sha256": digest,
        },
        "project_name": project.name,
        "source_text": text,
    }
    _validate_saved_revision_payload(payload)
    destination = directory / _artifact_filename(
        saved_revision_identity(source), revision_id
    )
    artifact_text = json.dumps(
        payload,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"
    atomic_write_text(destination, artifact_text)
    _rotate_history(source, directory, history_limit=history_limit)
    return destination


def save_project_document_guarded_with_revision(
    path: str | Path,
    project: ProjectDocument,
    *,
    expected_revision: ProjectFileRevision,
    revision_dir: str | Path | None = None,
    history_limit: int = DEFAULT_SAVED_REVISION_HISTORY_LIMIT,
) -> tuple[Path, ProjectFileRevision]:
    """Guard an explicit save and preserve the exact expected pre-image first.

    When the expected destination exists, its stable bytes must still match the
    optimistic-concurrency revision captured by the application before they are
    archived. Any mismatch or archive failure aborts the explicit overwrite.
    The existing guarded save then performs its own pre-write and pre-replace
    checks, so a race after archival still cannot overwrite newer external data.
    """
    destination = Path(path)
    if expected_revision.exists:
        archive_project_revision(
            destination,
            expected_revision=expected_revision,
            revision_dir=revision_dir,
            history_limit=history_limit,
        )
    return save_project_document_guarded(
        destination,
        project,
        expected_revision=expected_revision,
    )


def discard_saved_revision_artifact(
    path: str | Path,
    *,
    revision_dir: str | Path | None = None,
) -> None:
    artifact_path = Path(path)
    directory = (
        Path(revision_dir) if revision_dir is not None else default_saved_revision_dir()
    )
    try:
        resolved_artifact = artifact_path.resolve(strict=True)
        resolved_directory = directory.resolve(strict=True)
        resolved_artifact.relative_to(resolved_directory)
    except (FileNotFoundError, ValueError) as exc:
        raise SavedRevisionFormatError(
            "saved revision must be an existing file inside the saved-revision directory"
        ) from exc
    if not resolved_artifact.name.endswith(".saved-revision.json"):
        raise SavedRevisionFormatError("refusing to discard a non-saved-revision file")
    load_saved_revision_artifact(resolved_artifact)
    resolved_artifact.unlink()
