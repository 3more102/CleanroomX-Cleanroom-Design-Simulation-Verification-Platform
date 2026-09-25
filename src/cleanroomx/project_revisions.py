from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any

from . import __version__
from .persistence import atomic_write_bytes, atomic_write_text
from .project import (
    ProjectDocument,
    ProjectFileRevision,
    ProjectFormatError,
    ProjectWriteConflictError,
    capture_project_file_revision,
    project_file_revision_matches,
    project_from_dict,
    project_save_lock,
)
from .strict_json import StrictJSONError, strict_json_loads


PROJECT_REVISION_SCHEMA = "cleanroomx.project-revision"
PROJECT_REVISION_SCHEMA_VERSION = 1
DEFAULT_PROJECT_REVISION_HISTORY_LIMIT = 5


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
    try:
        data = strict_json_loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise ProjectRevisionError("project revision must be UTF-8 text") from exc
    except json.JSONDecodeError as exc:
        raise ProjectRevisionError(
            f"invalid project revision JSON at line {exc.lineno}, column {exc.colno}"
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


def scan_project_revisions(project_path: str | Path) -> ProjectRevisionScan:
    source = _normalized_path(project_path)
    directory = project_revision_dir(source)
    if not directory.exists():
        return ProjectRevisionScan(revisions=(), issues=())
    revisions: list[ProjectRevisionRecord] = []
    issues: list[ProjectRevisionIssue] = []
    for artifact in sorted(directory.glob("*.cleanroomx.revision.json")):
        try:
            snapshot = load_project_revision(
                artifact,
                expected_source_path=source,
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
            )
        )
    revisions.sort(
        key=lambda item: (item.created_at_utc, item.path.name),
        reverse=True,
    )
    issues.sort(key=lambda item: item.path.name)
    return ProjectRevisionScan(tuple(revisions), tuple(issues))


def rotate_project_revisions(
    project_path: str | Path,
    limit: int = DEFAULT_PROJECT_REVISION_HISTORY_LIMIT,
) -> None:
    if type(limit) is not int or limit < 0:
        raise ValueError("project revision history limit must be non-negative")
    scan = scan_project_revisions(project_path)
    for revision in scan.revisions[limit:]:
        try:
            revision.path.unlink(missing_ok=True)
        except OSError:
            # Retention cleanup is best effort after a committed save.
            pass


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
    payload = destination.read_bytes()
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
