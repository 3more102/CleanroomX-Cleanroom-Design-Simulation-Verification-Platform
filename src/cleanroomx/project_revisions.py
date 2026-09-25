from __future__ import annotations

import base64
import binascii
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
    capture_project_file_revision,
    project_file_revision_matches,
    project_from_dict,
    project_path_identity,
)


PROJECT_REVISION_SCHEMA = "cleanroomx.project_revision"
PROJECT_REVISION_SCHEMA_VERSION = 1
DEFAULT_PROJECT_REVISION_HISTORY_LIMIT = 5


class ProjectRevisionFormatError(ValueError):
    """Raised when a saved-project revision artifact is malformed or unsupported."""


class ProjectRevisionWriteError(RuntimeError):
    """Raised when CleanroomX cannot preserve the prior saved revision safely."""


@dataclass(frozen=True)
class ProjectRevisionCandidate:
    path: Path
    project_identity: str
    archived_at_utc: str
    source_path: Path
    source_sha256: str
    source_size: int
    project_name: str
    restorable: bool


@dataclass(frozen=True)
class ProjectRevisionScanIssue:
    path: Path
    error: str


@dataclass(frozen=True)
class ProjectRevisionScan:
    candidates: tuple[ProjectRevisionCandidate, ...]
    issues: tuple[ProjectRevisionScanIssue, ...]


@dataclass(frozen=True)
class RestoredProjectRevision:
    project: ProjectDocument
    source_path: Path
    archived_at_utc: str
    source_sha256: str
    artifact_path: Path


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_utc(text: Any) -> datetime:
    if not isinstance(text, str) or not text:
        raise ProjectRevisionFormatError("archived_at_utc must be a non-empty string")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProjectRevisionFormatError(
            "archived_at_utc is not a valid ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise ProjectRevisionFormatError("archived_at_utc must include a timezone")
    return parsed.astimezone(timezone.utc)


def default_project_revision_dir() -> Path:
    override = os.environ.get("CLEANROOMX_REVISION_DIR")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "CleanroomX" / "Revisions"
        return Path.home() / "AppData" / "Local" / "CleanroomX" / "Revisions"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "CleanroomX" / "Revisions"
    state_home = os.environ.get("XDG_STATE_HOME")
    if state_home:
        return Path(state_home) / "cleanroomx" / "revisions"
    return Path.home() / ".local" / "state" / "cleanroomx" / "revisions"


def _ensure_revision_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        try:
            path.chmod(0o700)
        except OSError:
            pass
    return path


def _reject_json_constant(value: str):
    raise ProjectRevisionFormatError(f"non-finite JSON constant is not allowed: {value}")


def _artifact_filename(
    project_identity_value: str,
    archived_at_utc: str,
    source_sha256: str,
) -> str:
    stamp = _parse_utc(archived_at_utc).strftime("%Y%m%dT%H%M%S%fZ")
    return (
        f"{project_identity_value}-{stamp}-{source_sha256[:12]}-"
        f"{uuid.uuid4().hex[:8]}.revision.json"
    )


def _validate_source_block(source: Any) -> dict[str, Any]:
    if not isinstance(source, dict):
        raise ProjectRevisionFormatError("source must be an object")
    path_text = source.get("path")
    if not isinstance(path_text, str) or not path_text:
        raise ProjectRevisionFormatError("source.path must be a non-empty string")
    size = source.get("size")
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise ProjectRevisionFormatError("source.size must be a non-negative integer")
    mtime_ns = source.get("mtime_ns")
    if mtime_ns is not None and (
        isinstance(mtime_ns, bool) or not isinstance(mtime_ns, int) or mtime_ns < 0
    ):
        raise ProjectRevisionFormatError(
            "source.mtime_ns must be a non-negative integer or null"
        )
    digest = source.get("sha256")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest.lower())
    ):
        raise ProjectRevisionFormatError("source.sha256 must be a 64-character hex digest")
    return source


def _decode_content(data: dict[str, Any]) -> bytes:
    if data.get("content_encoding") != "base64":
        raise ProjectRevisionFormatError("content_encoding must be 'base64'")
    encoded = data.get("content")
    if not isinstance(encoded, str) or not encoded:
        raise ProjectRevisionFormatError("content must be a non-empty base64 string")
    try:
        raw = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error) as exc:
        raise ProjectRevisionFormatError("content is not valid base64") from exc

    source = _validate_source_block(data.get("source"))
    digest = sha256(raw).hexdigest()
    if len(raw) != source["size"]:
        raise ProjectRevisionFormatError(
            "revision content size does not match the recorded source size"
        )
    if digest != source["sha256"].lower():
        raise ProjectRevisionFormatError(
            "revision content checksum does not match the recorded source SHA-256"
        )
    return raw


def _validate_revision_payload(data: Any) -> tuple[dict[str, Any], bytes]:
    if not isinstance(data, dict):
        raise ProjectRevisionFormatError("revision artifact must contain a JSON object")
    if data.get("schema") != PROJECT_REVISION_SCHEMA:
        raise ProjectRevisionFormatError(
            f"revision schema must be {PROJECT_REVISION_SCHEMA!r}"
        )
    version = data.get("schema_version")
    if version != PROJECT_REVISION_SCHEMA_VERSION:
        raise ProjectRevisionFormatError(
            f"unsupported revision schema version {version!r}; "
            f"expected {PROJECT_REVISION_SCHEMA_VERSION}"
        )

    identity = data.get("project_identity")
    if not isinstance(identity, str) or not identity:
        raise ProjectRevisionFormatError("project_identity must be a non-empty string")
    _parse_utc(data.get("archived_at_utc"))
    source = _validate_source_block(data.get("source"))
    source_identity = project_path_identity(source["path"])
    if identity != source_identity:
        raise ProjectRevisionFormatError(
            "project_identity does not match the normalized source path"
        )

    raw = _decode_content(data)
    return data, raw


def load_project_revision_artifact(
    path: str | Path,
) -> tuple[dict[str, Any], bytes]:
    artifact = Path(path)
    try:
        data = json.loads(
            artifact.read_text(encoding="utf-8"),
            parse_constant=_reject_json_constant,
        )
    except json.JSONDecodeError as exc:
        raise ProjectRevisionFormatError(
            f"invalid revision JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc
    return _validate_revision_payload(data)


def _project_from_bytes(raw: bytes) -> ProjectDocument:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProjectRevisionFormatError(
            "archived content is not a UTF-8 CleanroomX project"
        ) from exc
    try:
        data = json.loads(text, parse_constant=_reject_json_constant)
    except json.JSONDecodeError as exc:
        raise ProjectRevisionFormatError(
            f"archived project JSON is invalid at line {exc.lineno}, column {exc.colno}"
        ) from exc
    try:
        return project_from_dict(data)
    except (TypeError, ValueError) as exc:
        raise ProjectRevisionFormatError(
            f"archived content is not a valid CleanroomX project: {exc}"
        ) from exc


def restore_project_revision_artifact(
    path: str | Path,
) -> RestoredProjectRevision:
    artifact = Path(path)
    data, raw = load_project_revision_artifact(artifact)
    project = _project_from_bytes(raw)
    source = data["source"]
    return RestoredProjectRevision(
        project=project,
        source_path=Path(source["path"]),
        archived_at_utc=data["archived_at_utc"],
        source_sha256=source["sha256"],
        artifact_path=artifact,
    )


def _revision_files(
    source_path: str | Path,
    revision_dir: str | Path | None,
) -> tuple[Path, list[Path]]:
    directory = (
        Path(revision_dir)
        if revision_dir is not None
        else default_project_revision_dir()
    )
    identity = project_path_identity(source_path)
    if not directory.exists():
        return directory, []
    files = sorted(
        directory.glob(f"{identity}-*.revision.json"),
        key=lambda item: item.name,
        reverse=True,
    )
    return directory, files


def scan_project_revisions(
    source_path: str | Path,
    *,
    revision_dir: str | Path | None = None,
) -> ProjectRevisionScan:
    _, files = _revision_files(source_path, revision_dir)
    expected_identity = project_path_identity(source_path)
    candidates: list[ProjectRevisionCandidate] = []
    issues: list[ProjectRevisionScanIssue] = []

    for path in files:
        try:
            data, raw = load_project_revision_artifact(path)
            if data["project_identity"] != expected_identity:
                raise ProjectRevisionFormatError(
                    "revision artifact belongs to a different project path"
                )
            source = data["source"]
            try:
                project_name = _project_from_bytes(raw).name
                restorable = True
            except ProjectRevisionFormatError:
                project_name = "Non-CleanroomX previous file"
                restorable = False
            candidates.append(
                ProjectRevisionCandidate(
                    path=path,
                    project_identity=data["project_identity"],
                    archived_at_utc=data["archived_at_utc"],
                    source_path=Path(source["path"]),
                    source_sha256=source["sha256"],
                    source_size=source["size"],
                    project_name=project_name,
                    restorable=restorable,
                )
            )
        except (OSError, ProjectRevisionFormatError, TypeError, ValueError) as exc:
            issues.append(ProjectRevisionScanIssue(path=path, error=str(exc)))

    candidates.sort(key=lambda item: item.archived_at_utc, reverse=True)
    return ProjectRevisionScan(candidates=tuple(candidates), issues=tuple(issues))


def _rotate_history(
    source_path: str | Path,
    directory: Path,
    history_limit: int,
) -> None:
    identity = project_path_identity(source_path)
    artifacts = sorted(
        directory.glob(f"{identity}-*.revision.json"),
        key=lambda item: item.name,
        reverse=True,
    )
    for stale in artifacts[history_limit:]:
        stale.unlink(missing_ok=True)


def archive_project_revision(
    source_path: str | Path,
    *,
    expected_revision: ProjectFileRevision,
    revision_dir: str | Path | None = None,
    history_limit: int = DEFAULT_PROJECT_REVISION_HISTORY_LIMIT,
) -> Path | None:
    """Preserve the exact expected on-disk bytes before an explicit replacement.

    A missing destination has no prior revision to preserve. The source is checked
    before and after reading so an external change cannot be archived as though it
    were the revision the caller actually opened.
    """

    if (
        isinstance(history_limit, bool)
        or not isinstance(history_limit, int)
        or history_limit < 1
    ):
        raise ValueError("history_limit must be a positive integer")

    source = Path(source_path).expanduser().resolve(strict=False)
    current = capture_project_file_revision(source)
    if not project_file_revision_matches(expected_revision, current):
        raise ProjectWriteConflictError(source, expected_revision, current)
    if not expected_revision.exists:
        return None

    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise ProjectRevisionWriteError(
            f"could not read the previous saved revision; original project was not changed: {exc}"
        ) from exc

    after_read = capture_project_file_revision(source)
    if not project_file_revision_matches(expected_revision, after_read):
        raise ProjectWriteConflictError(source, expected_revision, after_read)

    digest = sha256(raw).hexdigest()
    if len(raw) != expected_revision.size or digest != expected_revision.sha256:
        observed = capture_project_file_revision(source)
        raise ProjectWriteConflictError(source, expected_revision, observed)

    directory = (
        Path(revision_dir)
        if revision_dir is not None
        else default_project_revision_dir()
    )
    try:
        directory = _ensure_revision_dir(directory)
        _, existing = _revision_files(source, directory)
        if existing:
            try:
                newest_data, _ = load_project_revision_artifact(existing[0])
                if newest_data["source"]["sha256"] == digest:
                    return existing[0]
            except (OSError, ProjectRevisionFormatError, TypeError, ValueError):
                # Preserve new evidence rather than trusting a damaged newest artifact.
                pass

        archived_at = _utc_now_text()
        identity = project_path_identity(source)
        payload = {
            "schema": PROJECT_REVISION_SCHEMA,
            "schema_version": PROJECT_REVISION_SCHEMA_VERSION,
            "application_version": __version__,
            "project_identity": identity,
            "archived_at_utc": archived_at,
            "source": {
                "path": str(source),
                "size": len(raw),
                "mtime_ns": expected_revision.mtime_ns,
                "sha256": digest,
            },
            "content_encoding": "base64",
            "content": base64.b64encode(raw).decode("ascii"),
        }
        _validate_revision_payload(payload)
        destination = directory / _artifact_filename(identity, archived_at, digest)
        text = json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        ) + "\n"
        atomic_write_text(destination, text)
        _rotate_history(source, directory, history_limit)
        return destination
    except ProjectWriteConflictError:
        raise
    except (OSError, ProjectRevisionFormatError, TypeError, ValueError) as exc:
        raise ProjectRevisionWriteError(
            "could not preserve the previous saved revision; "
            f"original project was not changed: {exc}"
        ) from exc
