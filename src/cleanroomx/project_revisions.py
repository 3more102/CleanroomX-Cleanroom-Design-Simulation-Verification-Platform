from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any, Callable
import uuid

from . import __version__
from .persistence import atomic_write_bytes, atomic_write_text, stable_file_sha256
from .project import (
    PROJECT_FILE_MAX_BYTES,
    ProjectDocument,
    ProjectFileRevision,
    ProjectFormatError,
    ProjectWriteConflictError,
    _read_project_bytes_bounded,
    capture_project_file_revision,
    project_file_revision_matches,
    project_from_dict,
    project_save_lock,
)
from .strict_json import (
    StrictJSONError,
    StrictJSONSizeError,
    load_strict_json,
    strict_json_loads,
)


PROJECT_REVISION_SCHEMA = "cleanroomx.project-revision"
PROJECT_REVISION_SCHEMA_VERSION = 1
DEFAULT_PROJECT_REVISION_HISTORY_LIMIT = 5
PROJECT_REVISION_METADATA_MAX_BYTES = 1024 * 1024


def _project_revision_max_bytes() -> int:
    """Bound one revision envelope without rejecting a valid maximum-size project.

    The revision stores the full project as Base64 and also duplicates selected
    source strings such as the project name outside that payload. In the worst
    case those duplicated strings can consume nearly the full source-project
    byte budget, so reserve one additional project-size allowance plus a fixed
    envelope allowance for paths, keys, timestamps, hashes, and formatting.
    """
    encoded_project_bytes = ((PROJECT_FILE_MAX_BYTES + 2) // 3) * 4
    return (
        encoded_project_bytes
        + PROJECT_FILE_MAX_BYTES
        + PROJECT_REVISION_METADATA_MAX_BYTES
    )


class ProjectRevisionError(ProjectFormatError):
    """Raised when a saved-project revision is malformed, corrupted, or unsafe."""


@dataclass(frozen=True)
class ProjectRevisionRecord:
    path: Path
    created_at_utc: str
    project_name: str
    source_sha256: str
    source_size: int
    application_version: str
    artifact_size: int
    artifact_sha256: str
    artifact_identity: tuple[str, int, int]


@dataclass(frozen=True)
class ProjectRevisionIssue:
    path: Path
    error: str


@dataclass(frozen=True)
class ProjectRevisionScan:
    revisions: tuple[ProjectRevisionRecord, ...]
    issues: tuple[ProjectRevisionIssue, ...]


@dataclass(frozen=True)
class ProjectRevisionSnapshot:
    project: ProjectDocument
    source_path: Path
    source_bytes: bytes
    created_at_utc: str
    source_sha256: str
    application_version: str
    artifact_path: Path


def _normalized_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def project_revision_dir(project_path: str | Path) -> Path:
    source = Path(project_path)
    return source.parent / f".{source.name}.revisions"


def _utc_now_text() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _parse_utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise ProjectRevisionError("created_at_utc must be a non-empty string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProjectRevisionError("created_at_utc is not valid ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ProjectRevisionError("created_at_utc must include a timezone")
    return parsed.astimezone(timezone.utc)


def _project_from_bytes(payload: bytes) -> tuple[ProjectDocument, dict[str, Any]]:
    if len(payload) > PROJECT_FILE_MAX_BYTES:
        raise ProjectRevisionError(
            f"saved project revision size {len(payload)} bytes exceeds maximum "
            f"supported project size of {PROJECT_FILE_MAX_BYTES} bytes"
        )
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProjectRevisionError("saved project revision must be UTF-8") from exc
    try:
        data = strict_json_loads(text)
    except json.JSONDecodeError as exc:
        raise ProjectRevisionError(
            f"saved project revision contains invalid JSON at line {exc.lineno}, "
            f"column {exc.colno}"
        ) from exc
    except StrictJSONError as exc:
        raise ProjectRevisionError(
            f"saved project revision contains invalid strict JSON: {exc}"
        ) from exc
    try:
        project = project_from_dict(data)
    except ProjectFormatError as exc:
        raise ProjectRevisionError(f"saved revision project is invalid: {exc}") from exc
    return project, data


def _revision_payload(
    source_path: Path,
    source_bytes: bytes,
    *,
    created_at_utc: str,
) -> dict[str, Any]:
    project, source_document = _project_from_bytes(source_bytes)
    return {
        "schema": PROJECT_REVISION_SCHEMA,
        "schema_version": PROJECT_REVISION_SCHEMA_VERSION,
        "application_version": __version__,
        "created_at_utc": created_at_utc,
        "source": {
            "path": str(_normalized_path(source_path)),
            "size_bytes": len(source_bytes),
            "sha256": sha256(source_bytes).hexdigest(),
            "project_name": project.name,
            "application_version": str(
                source_document.get("application_version", "unknown")
            ),
            "content_base64": base64.b64encode(source_bytes).decode("ascii"),
        },
    }


def preserve_project_revision(
    project_path: str | Path,
    source_bytes: bytes,
) -> Path | None:
    """Persist exact prior project bytes before overwriting a valid CleanroomX project.

    Existing non-project destination bytes are protected by the guarded write conflict
    check but are not mislabeled as a CleanroomX project revision.
    """
    if not isinstance(source_bytes, bytes):
        raise TypeError("source_bytes must be bytes")
    source = _normalized_path(project_path)
    created_at = _utc_now_text()
    try:
        payload = _revision_payload(source, source_bytes, created_at_utc=created_at)
    except ProjectRevisionError:
        return None
    digest = payload["source"]["sha256"]
    stamp = _parse_utc(created_at).strftime("%Y%m%dT%H%M%S%fZ")
    directory = project_revision_dir(source)
    directory.mkdir(parents=True, exist_ok=True)
    candidate = directory / f"{stamp}-{digest[:12]}.cleanroomx.revision.json"
    suffix = 1
    while candidate.exists():
        candidate = directory / (
            f"{stamp}-{digest[:12]}-{suffix}.cleanroomx.revision.json"
        )
        suffix += 1
    text = json.dumps(
        payload,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"
    atomic_write_text(candidate, text)
    # Verify the artifact before allowing the project overwrite to continue.
    load_project_revision(candidate, expected_source_path=source)
    return candidate


def _load_payload(path: Path) -> dict[str, Any]:
    max_bytes = _project_revision_max_bytes()
    try:
        data = load_strict_json(path, max_bytes=max_bytes)
    except json.JSONDecodeError as exc:
        raise ProjectRevisionError(
            f"invalid project revision JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc
    except StrictJSONSizeError as exc:
        raise ProjectRevisionError(
            f"project revision artifact size {exc.observed_size} bytes exceeds "
            f"maximum supported size of {exc.limit} bytes"
        ) from exc
    except StrictJSONError as exc:
        raise ProjectRevisionError(
            f"invalid project revision strict JSON: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise ProjectRevisionError("project revision must contain a JSON object")
    if data.get("schema") != PROJECT_REVISION_SCHEMA:
        raise ProjectRevisionError(
            f"project revision schema must be {PROJECT_REVISION_SCHEMA!r}"
        )
    if data.get("schema_version") != PROJECT_REVISION_SCHEMA_VERSION:
        raise ProjectRevisionError(
            f"unsupported project revision schema version "
            f"{data.get('schema_version')!r}"
        )
    _parse_utc(data.get("created_at_utc"))
    if not isinstance(data.get("source"), dict):
        raise ProjectRevisionError("project revision source must be an object")
    return data


def load_project_revision(
    path: str | Path,
    *,
    expected_source_path: str | Path | None = None,
) -> ProjectRevisionSnapshot:
    artifact = Path(path)
    data = _load_payload(artifact)
    source = data["source"]
    source_path_text = source.get("path")
    if not isinstance(source_path_text, str) or not source_path_text:
        raise ProjectRevisionError("project revision source.path is required")
    source_path = _normalized_path(source_path_text)
    if expected_source_path is not None:
        expected = os.path.normcase(str(_normalized_path(expected_source_path)))
        recorded = os.path.normcase(str(source_path))
        if expected != recorded:
            raise ProjectRevisionError(
                "project revision belongs to a different source project"
            )

    size = source.get("size_bytes")
    digest = source.get("sha256")
    encoded = source.get("content_base64")
    if type(size) is not int or size < 0:
        raise ProjectRevisionError(
            "project revision source.size_bytes must be a non-negative integer"
        )
    if size > PROJECT_FILE_MAX_BYTES:
        raise ProjectRevisionError(
            f"saved project revision size {size} bytes exceeds maximum supported "
            f"project size of {PROJECT_FILE_MAX_BYTES} bytes"
        )
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(ch not in "0123456789abcdef" for ch in digest.lower())
    ):
        raise ProjectRevisionError(
            "project revision source.sha256 must be a SHA-256 digest"
        )
    if not isinstance(encoded, str) or not encoded:
        raise ProjectRevisionError("project revision source.content_base64 is required")
    try:
        source_bytes = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
        raise ProjectRevisionError("project revision content is not valid base64") from exc
    if len(source_bytes) != size:
        raise ProjectRevisionError(
            "project revision size does not match the recorded source size"
        )
    actual = sha256(source_bytes).hexdigest()
    if actual != digest.lower():
        raise ProjectRevisionError(
            "project revision SHA-256 does not match the recorded source digest"
        )
    project, _document = _project_from_bytes(source_bytes)
    recorded_name = source.get("project_name")
    if (
        isinstance(recorded_name, str)
        and recorded_name
        and recorded_name != project.name
    ):
        raise ProjectRevisionError(
            "project revision project name does not match its recorded metadata"
        )
    return ProjectRevisionSnapshot(
        project=project,
        source_path=source_path,
        source_bytes=source_bytes,
        created_at_utc=data["created_at_utc"],
        source_sha256=actual,
        application_version=str(source.get("application_version", "unknown")),
        artifact_path=artifact,
    )


def _revision_artifact_identity(
    metadata: os.stat_result,
) -> tuple[str, int, int] | None:
    """Return rename-stable artifact identity, or None when unavailable."""

    inode = int(metadata.st_ino)
    if inode != 0:
        return ("file-id", int(metadata.st_dev), inode)
    if os.name == "nt":
        birthtime_ns = getattr(metadata, "st_birthtime_ns", None)
        if birthtime_ns is not None:
            return ("windows-birthtime", 0, int(birthtime_ns))
        # On Windows versions without st_birthtime_ns, st_ctime_ns is creation
        # time and remains stable across a same-volume rename.
        return ("windows-creation-time", 0, int(metadata.st_ctime_ns))
    # Destructive retention must fail closed when the filesystem exposes no
    # stable identity that survives rename.
    return None


def scan_project_revisions(project_path: str | Path) -> ProjectRevisionScan:
    source = _normalized_path(project_path)
    directory = project_revision_dir(source)
    if not directory.exists():
        return ProjectRevisionScan(revisions=(), issues=())
    revisions: list[ProjectRevisionRecord] = []
    issues: list[ProjectRevisionIssue] = []
    for artifact in sorted(directory.glob("*.cleanroomx.revision.json")):
        try:
            artifact_before, artifact_sha256_before = stable_file_sha256(
                artifact,
                max_bytes=_project_revision_max_bytes(),
            )
            snapshot = load_project_revision(
                artifact,
                expected_source_path=source,
            )
            artifact_after, artifact_sha256_after = stable_file_sha256(
                artifact,
                max_bytes=_project_revision_max_bytes(),
            )
            artifact_identity_before = _revision_artifact_identity(artifact_before)
            artifact_identity_after = _revision_artifact_identity(artifact_after)
            if (
                artifact_identity_before is None
                or artifact_identity_after is None
                or artifact_identity_before != artifact_identity_after
                or artifact_before.st_size != artifact_after.st_size
                or artifact_sha256_before != artifact_sha256_after
            ):
                raise ProjectRevisionError(
                    "project revision artifact changed while scanning"
                )
        except (OSError, ProjectRevisionError) as exc:
            issues.append(ProjectRevisionIssue(path=artifact, error=str(exc)))
            continue
        revisions.append(
            ProjectRevisionRecord(
                path=artifact,
                created_at_utc=snapshot.created_at_utc,
                project_name=snapshot.project.name,
                source_sha256=snapshot.source_sha256,
                source_size=len(snapshot.source_bytes),
                application_version=snapshot.application_version,
                artifact_size=artifact_after.st_size,
                artifact_sha256=artifact_sha256_after,
                artifact_identity=artifact_identity_after,
            )
        )
    revisions.sort(
        key=lambda item: (item.created_at_utc, item.path.name),
        reverse=True,
    )
    issues.sort(key=lambda item: item.path.name)
    return ProjectRevisionScan(tuple(revisions), tuple(issues))


def _revision_record_is_verified(
    revision: ProjectRevisionRecord,
    *,
    expected_source_path: Path,
    artifact_path: Path | None = None,
) -> bool:
    """Return whether one artifact still represents the scanned revision."""
    artifact = revision.path if artifact_path is None else artifact_path
    try:
        current = load_project_revision(
            artifact,
            expected_source_path=expected_source_path,
        )
    except (OSError, ProjectRevisionError):
        return False
    if not (
        current.created_at_utc == revision.created_at_utc
        and current.project.name == revision.project_name
        and current.source_sha256 == revision.source_sha256
        and len(current.source_bytes) == revision.source_size
        and current.application_version == revision.application_version
    ):
        return False
    try:
        artifact_stat, artifact_sha256 = stable_file_sha256(
            artifact,
            max_bytes=_project_revision_max_bytes(),
        )
    except OSError:
        return False
    artifact_identity = _revision_artifact_identity(artifact_stat)
    return (
        artifact_identity is not None
        and artifact_identity == revision.artifact_identity
        and artifact_stat.st_size == revision.artifact_size
        and artifact_sha256 == revision.artifact_sha256
    )


def _restore_revision_prune_stage(staged_path: Path, original_path: Path) -> None:
    """Restore staged revision evidence without clobbering a recreated path."""
    try:
        os.link(staged_path, original_path)
    except OSError:
        # If another process recreated the public path, preserve both revisions:
        # the new public entry and the private staged evidence.
        return
    try:
        staged_path.unlink()
    except OSError:
        # The hard link already restored the original public name. Leaving a
        # private duplicate is safer than deleting evidence after cleanup failure.
        return


def _stage_revision_for_pruning(path: Path) -> Path | None:
    """Detach the exact pathname revision selected for retention pruning."""
    # Keep staged evidence discoverable by the normal revision scanner if a
    # concurrent replacement prevents no-clobber restoration.
    staged = path.with_name(
        f".retention-stage-{uuid.uuid4().hex}-{path.name}"
    )
    try:
        os.replace(path, staged)
    except OSError:
        return None
    return staged


def rotate_project_revisions(
    project_path: str | Path,
    limit: int = DEFAULT_PROJECT_REVISION_HISTORY_LIMIT,
) -> None:
    if type(limit) is not int or limit < 0:
        raise ValueError("project revision history limit must be non-negative")
    source = _normalized_path(project_path)
    scan = scan_project_revisions(source)
    for revision in scan.revisions[limit:]:
        # Detach the exact pathname revision first. Any replacement that wins
        # before this atomic move is captured by the private stage and must pass
        # full semantic + byte-identity verification before it can be deleted.
        staged = _stage_revision_for_pruning(revision.path)
        if staged is None:
            continue
        if not _revision_record_is_verified(
            revision,
            expected_source_path=source,
            artifact_path=staged,
        ):
            _restore_revision_prune_stage(staged, revision.path)
            continue
        try:
            staged.unlink()
        except OSError:
            # Retention cleanup is best effort after a committed save. Restore the
            # verified bytes when possible; never overwrite a concurrent replacement.
            _restore_revision_prune_stage(staged, revision.path)

def discard_project_revision(path: str | Path | None) -> None:
    if path is None:
        return
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def _expected_bytes(
    destination: Path,
    expected_revision: ProjectFileRevision,
) -> bytes | None:
    current = capture_project_file_revision(destination)
    if not project_file_revision_matches(expected_revision, current):
        raise ProjectWriteConflictError(destination, expected_revision, current)
    if not expected_revision.exists:
        return None
    payload = _read_project_bytes_bounded(destination)
    if (
        len(payload) != expected_revision.size
        or sha256(payload).hexdigest() != expected_revision.sha256
    ):
        current = capture_project_file_revision(destination)
        raise ProjectWriteConflictError(destination, expected_revision, current)
    return payload


def restore_project_revision(
    revision_path: str | Path,
    destination: str | Path,
    *,
    expected_source_path: str | Path | None = None,
    history_limit: int = DEFAULT_PROJECT_REVISION_HISTORY_LIMIT,
    before_replace: Callable[[Path], None] | None = None,
) -> Path:
    """Restore verified historical bytes to a separate guarded destination."""
    snapshot = load_project_revision(
        revision_path,
        expected_source_path=expected_source_path,
    )
    target = _normalized_path(destination)
    if os.path.normcase(str(target)) == os.path.normcase(str(snapshot.source_path)):
        raise ProjectRevisionError(
            "refusing to overwrite the source project; restore the revision "
            "to a separate file"
        )

    with project_save_lock(target):
        expected = capture_project_file_revision(target)
        previous = _expected_bytes(target, expected)
        if previous == snapshot.source_bytes:
            return target

        preserved: Path | None = None
        if previous is not None and history_limit > 0:
            preserved = preserve_project_revision(target, previous)

        def assert_target_unchanged() -> None:
            current = capture_project_file_revision(target)
            if not project_file_revision_matches(expected, current):
                raise ProjectWriteConflictError(target, expected, current)
            if before_replace is not None:
                before_replace(target)

        try:
            atomic_write_bytes(
                target,
                snapshot.source_bytes,
                before_replace=assert_target_unchanged,
            )
        except BaseException as exc:
            if not getattr(exc, "committed", False):
                discard_project_revision(preserved)
            raise

        written = capture_project_file_revision(target)
        if (
            not written.exists
            or written.size != len(snapshot.source_bytes)
            or written.sha256 != snapshot.source_sha256
        ):
            raise ProjectRevisionError(
                "restored project bytes do not match the verified revision"
            )
        rotate_project_revisions(target, history_limit)
        return target
