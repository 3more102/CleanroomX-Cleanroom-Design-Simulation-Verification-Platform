from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from . import __version__
from .application import ANALYSIS_SPECS

PROJECT_SCHEMA = "cleanroomx.project"
PROJECT_SCHEMA_VERSION = 1
PROJECT_REVISION_SCHEMA = "cleanroomx.project-revision"
PROJECT_REVISION_SCHEMA_VERSION = 1
DEFAULT_PROJECT_REVISION_HISTORY_LIMIT = 5


class ProjectFormatError(ValueError):
    pass


class ProjectRevisionError(ProjectFormatError):
    """Raised when a saved project revision is malformed, unsafe, or unusable."""


@dataclass
class AnalysisDocument:
    id: str
    name: str
    kind: str
    input: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "kind": self.kind, "input": self.input}


@dataclass
class ProjectDocument:
    name: str
    description: str = ""
    analyses: list[AnalysisDocument] = field(default_factory=list)
    active_analysis_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "schema": PROJECT_SCHEMA,
            "schema_version": PROJECT_SCHEMA_VERSION,
            "application_version": __version__,
            "project": {
                "name": self.name,
                "description": self.description,
                "metadata": self.metadata,
            },
            "analyses": [item.to_dict() for item in self.analyses],
            "active_analysis_id": self.active_analysis_id,
        }

    def analysis_by_id(self, analysis_id: str) -> AnalysisDocument:
        for item in self.analyses:
            if item.id == analysis_id:
                return item
        raise KeyError(analysis_id)


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


def _reject_json_constant(value: str):
    raise ProjectFormatError(f"non-finite JSON constant is not allowed: {value}")


def _validated_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProjectFormatError(f"{field_name} must be a non-empty string")
    return value.strip()


def _analysis_from_dict(data: dict) -> AnalysisDocument:
    if not isinstance(data, dict):
        raise ProjectFormatError("every analysis entry must be an object")
    analysis_id = _validated_string(data.get("id"), "analysis.id")
    name = _validated_string(data.get("name", analysis_id), "analysis.name")
    kind = _validated_string(data.get("kind"), "analysis.kind")
    if kind not in ANALYSIS_SPECS:
        raise ProjectFormatError(f"unsupported analysis kind in project: {kind}")
    payload = data.get("input", {})
    if not isinstance(payload, dict):
        raise ProjectFormatError(f"analysis {analysis_id!r} input must be an object")
    return AnalysisDocument(id=analysis_id, name=name, kind=kind, input=payload)


def _migrate_legacy(data: dict) -> dict:
    if data.get("schema") == PROJECT_SCHEMA and data.get("schema_version") == 0:
        analysis = data.get("analysis", {})
        if not isinstance(analysis, dict):
            raise ProjectFormatError("legacy v0 analysis must be an object")
        analysis_id = analysis.get("id", "analysis-1")
        return {
            "schema": PROJECT_SCHEMA,
            "schema_version": PROJECT_SCHEMA_VERSION,
            "application_version": data.get("application_version", "legacy"),
            "project": {
                "name": data.get("name", "Migrated CleanroomX Project"),
                "description": data.get("description", ""),
                "metadata": data.get("metadata", {}),
            },
            "analyses": [{
                "id": analysis_id,
                "name": analysis.get("name", analysis.get("kind", "Analysis")),
                "kind": analysis.get("kind"),
                "input": analysis.get("input", {}),
            }],
            "active_analysis_id": analysis_id,
        }

    if "schema" not in data and "analysis_type" in data and "input" in data:
        return {
            "schema": PROJECT_SCHEMA,
            "schema_version": PROJECT_SCHEMA_VERSION,
            "application_version": "legacy",
            "project": {
                "name": data.get("name", "Migrated CleanroomX Project"),
                "description": data.get("description", ""),
                "metadata": {},
            },
            "analyses": [{
                "id": "analysis-1",
                "name": data.get("analysis_name", data["analysis_type"]),
                "kind": data["analysis_type"],
                "input": data["input"],
            }],
            "active_analysis_id": "analysis-1",
        }
    return data


def project_from_dict(data: dict) -> ProjectDocument:
    if not isinstance(data, dict):
        raise ProjectFormatError("project file must contain a JSON object")
    try:
        json.dumps(data, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ProjectFormatError("project must contain only strict JSON values") from exc
    data = _migrate_legacy(data)

    if data.get("schema") != PROJECT_SCHEMA:
        raise ProjectFormatError(f"project schema must be {PROJECT_SCHEMA!r}")
    version = data.get("schema_version")
    if not isinstance(version, int):
        raise ProjectFormatError("schema_version must be an integer")
    if version > PROJECT_SCHEMA_VERSION:
        raise ProjectFormatError(
            f"unsupported future project schema version {version}; "
            f"this build supports up to {PROJECT_SCHEMA_VERSION}"
        )
    if version < PROJECT_SCHEMA_VERSION:
        raise ProjectFormatError(f"unsupported legacy project schema version {version}")

    project_data = data.get("project")
    if not isinstance(project_data, dict):
        raise ProjectFormatError("project metadata block must be an object")
    name = _validated_string(project_data.get("name"), "project.name")
    description = project_data.get("description", "")
    if not isinstance(description, str):
        raise ProjectFormatError("project.description must be a string")
    metadata = project_data.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ProjectFormatError("project.metadata must be an object")

    raw_analyses = data.get("analyses", [])
    if not isinstance(raw_analyses, list):
        raise ProjectFormatError("analyses must be an array")
    analyses = [_analysis_from_dict(item) for item in raw_analyses]
    ids = [item.id for item in analyses]
    if len(ids) != len(set(ids)):
        raise ProjectFormatError("analysis ids must be unique")

    active = data.get("active_analysis_id")
    if active is not None:
        if not isinstance(active, str):
            raise ProjectFormatError("active_analysis_id must be a string or null")
        if active not in set(ids):
            raise ProjectFormatError(
                "active_analysis_id must reference an analysis present in the project"
            )

    return ProjectDocument(
        name=name,
        description=description,
        analyses=analyses,
        active_analysis_id=active,
        metadata=metadata,
    )


def new_project(name: str = "Untitled Project") -> ProjectDocument:
    return ProjectDocument(name=_validated_string(name, "project.name"))


def _project_from_bytes(data: bytes) -> ProjectDocument:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProjectFormatError("project file must be UTF-8 text") from exc
    try:
        payload = json.loads(text, parse_constant=_reject_json_constant)
    except json.JSONDecodeError as exc:
        raise ProjectFormatError(
            f"invalid JSON in project file at line {exc.lineno}, column {exc.colno}"
        ) from exc
    return project_from_dict(payload)


def load_project_document(path: str | Path) -> ProjectDocument:
    return _project_from_bytes(Path(path).read_bytes())


def _fsync_directory(directory: Path) -> None:
    """Best-effort directory metadata sync after replace/delete on POSIX filesystems."""
    if os.name == "nt":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        fd = os.open(directory, flags)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write_bytes(path: str | Path, payload: bytes) -> Path:
    """Atomically replace a file with flushed bytes and sync directory metadata."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

        temp_path.replace(destination)
        _fsync_directory(destination.parent)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise
    return destination


def atomic_write_text(path: str | Path, text: str) -> Path:
    """Atomically replace a UTF-8 text file using a same-directory temporary file."""
    return atomic_write_bytes(path, text.encode("utf-8"))


def _normalized_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_revision_time(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise ProjectRevisionError("created_at_utc must be a non-empty string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProjectRevisionError("created_at_utc is not a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ProjectRevisionError("created_at_utc must include a timezone")
    return parsed.astimezone(timezone.utc)


def project_revision_dir(project_path: str | Path) -> Path:
    project = Path(project_path)
    return project.parent / f".{project.name}.revisions"


def _validate_history_limit(limit: int) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        raise ValueError("project revision history limit must be a non-negative integer")
    return limit


def _revision_payload(
    destination: Path,
    source_bytes: bytes,
    *,
    created_at_utc: str,
) -> dict[str, Any]:
    previous_project = _project_from_bytes(source_bytes)
    digest = sha256(source_bytes).hexdigest()
    return {
        "schema": PROJECT_REVISION_SCHEMA,
        "schema_version": PROJECT_REVISION_SCHEMA_VERSION,
        "application_version": __version__,
        "created_at_utc": created_at_utc,
        "source": {
            "path": str(_normalized_path(destination)),
            "size": len(source_bytes),
            "sha256": digest,
            "project_name": previous_project.name,
            "content_base64": base64.b64encode(source_bytes).decode("ascii"),
        },
    }


def _write_project_revision(destination: Path, source_bytes: bytes) -> Path:
    created_at = _utc_now_text()
    payload = _revision_payload(destination, source_bytes, created_at_utc=created_at)
    digest = payload["source"]["sha256"]
    stamp = (
        _parse_revision_time(created_at)
        .strftime("%Y%m%dT%H%M%S%fZ")
    )
    directory = project_revision_dir(destination)
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
    return atomic_write_text(candidate, text)


def _load_revision_payload(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_json_constant,
        )
    except UnicodeDecodeError as exc:
        raise ProjectRevisionError("project revision must be UTF-8 text") from exc
    except json.JSONDecodeError as exc:
        raise ProjectRevisionError(
            f"invalid project revision JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc
    if not isinstance(data, dict):
        raise ProjectRevisionError("project revision must contain a JSON object")
    if data.get("schema") != PROJECT_REVISION_SCHEMA:
        raise ProjectRevisionError(
            f"project revision schema must be {PROJECT_REVISION_SCHEMA!r}"
        )
    version = data.get("schema_version")
    if version != PROJECT_REVISION_SCHEMA_VERSION:
        raise ProjectRevisionError(
            f"unsupported project revision schema version {version!r}; "
            f"expected {PROJECT_REVISION_SCHEMA_VERSION}"
        )
    _parse_revision_time(data.get("created_at_utc"))
    source = data.get("source")
    if not isinstance(source, dict):
        raise ProjectRevisionError("project revision source must be an object")
    return data


def load_project_revision(
    path: str | Path,
    *,
    expected_source_path: str | Path | None = None,
) -> ProjectRevisionSnapshot:
    artifact_path = Path(path)
    data = _load_revision_payload(artifact_path)
    source = data["source"]

    source_path_text = source.get("path")
    if not isinstance(source_path_text, str) or not source_path_text:
        raise ProjectRevisionError("project revision source.path must be a non-empty string")
    source_path = _normalized_path(source_path_text)
    if expected_source_path is not None:
        expected = os.path.normcase(str(_normalized_path(expected_source_path)))
        recorded = os.path.normcase(str(source_path))
        if recorded != expected:
            raise ProjectRevisionError(
                "project revision belongs to a different source project"
            )

    source_size = source.get("size")
    if isinstance(source_size, bool) or not isinstance(source_size, int) or source_size < 0:
        raise ProjectRevisionError("project revision source.size must be a non-negative integer")
    source_digest = source.get("sha256")
    if (
        not isinstance(source_digest, str)
        or len(source_digest) != 64
        or any(ch not in "0123456789abcdef" for ch in source_digest.lower())
    ):
        raise ProjectRevisionError("project revision source.sha256 must be a SHA-256 hex digest")
    encoded = source.get("content_base64")
    if not isinstance(encoded, str) or not encoded:
        raise ProjectRevisionError("project revision source.content_base64 is required")
    try:
        source_bytes = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
        raise ProjectRevisionError("project revision content is not valid base64") from exc
    if len(source_bytes) != source_size:
        raise ProjectRevisionError(
            "project revision size does not match the recorded source size"
        )
    actual_digest = sha256(source_bytes).hexdigest()
    if actual_digest != source_digest.lower():
        raise ProjectRevisionError(
            "project revision SHA-256 does not match the recorded source digest"
        )

    try:
        project = _project_from_bytes(source_bytes)
    except ProjectFormatError as exc:
        raise ProjectRevisionError(f"saved revision project is invalid: {exc}") from exc

    project_name = source.get("project_name")
    if isinstance(project_name, str) and project_name and project.name != project_name:
        raise ProjectRevisionError(
            "project revision project name does not match its recorded metadata"
        )

    application_version = data.get("application_version", "unknown")
    return ProjectRevisionSnapshot(
        project=project,
        source_path=source_path,
        source_bytes=source_bytes,
        created_at_utc=data["created_at_utc"],
        source_sha256=actual_digest,
        application_version=str(application_version),
        artifact_path=artifact_path,
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
    revisions.sort(key=lambda item: (item.created_at_utc, item.path.name), reverse=True)
    issues.sort(key=lambda item: item.path.name)
    return ProjectRevisionScan(revisions=tuple(revisions), issues=tuple(issues))


def _rotate_project_revisions(project_path: Path, limit: int) -> None:
    limit = _validate_history_limit(limit)
    directory = project_revision_dir(project_path)
    if not directory.exists():
        return
    artifacts = sorted(
        directory.glob("*.cleanroomx.revision.json"),
        key=lambda item: item.name,
        reverse=True,
    )
    for artifact in artifacts[limit:]:
        artifact.unlink(missing_ok=True)
    if len(artifacts) > limit:
        _fsync_directory(directory)


def _remove_failed_revision(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
        _fsync_directory(path.parent)
    except OSError:
        pass


def _verify_project_write(
    destination: Path,
    expected_bytes: bytes,
    expected_project: ProjectDocument,
) -> None:
    actual_bytes = destination.read_bytes()
    if actual_bytes != expected_bytes:
        raise OSError("saved project verification failed: persisted bytes differ")
    actual_project = _project_from_bytes(actual_bytes)
    if actual_project != expected_project:
        raise OSError("saved project verification failed: project model differs after reload")


def _rollback_destination(destination: Path, previous_bytes: bytes | None) -> None:
    if previous_bytes is None:
        destination.unlink(missing_ok=True)
        _fsync_directory(destination.parent)
    else:
        atomic_write_bytes(destination, previous_bytes)


def save_project_document(
    path: str | Path,
    project: ProjectDocument,
    *,
    history_limit: int = DEFAULT_PROJECT_REVISION_HISTORY_LIMIT,
) -> Path:
    history_limit = _validate_history_limit(history_limit)
    destination = Path(path)
    data = project.to_dict()
    project_from_dict(data)
    text = json.dumps(
        data, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False
    ) + "\n"
    expected_bytes = text.encode("utf-8")

    previous_bytes = destination.read_bytes() if destination.exists() else None
    if previous_bytes == expected_bytes:
        _verify_project_write(destination, expected_bytes, project)
        return destination

    revision_path: Path | None = None
    if previous_bytes is not None and history_limit:
        try:
            revision_path = _write_project_revision(destination, previous_bytes)
        except (OSError, ProjectFormatError) as exc:
            raise ProjectRevisionError(
                "cannot preserve the previous project revision; save was not attempted: "
                f"{exc}"
            ) from exc

    try:
        atomic_write_bytes(destination, expected_bytes)
        _verify_project_write(destination, expected_bytes, project)
    except Exception as save_error:
        try:
            _rollback_destination(destination, previous_bytes)
        except Exception as rollback_error:
            raise OSError(
                "project save failed and rollback could not restore the previous file; "
                f"saved revision retained at {revision_path!s}: {rollback_error}"
            ) from save_error
        _remove_failed_revision(revision_path)
        raise

    if history_limit:
        _rotate_project_revisions(destination, history_limit)
    return destination


def restore_project_revision(
    revision_path: str | Path,
    destination: str | Path,
    *,
    expected_source_path: str | Path | None = None,
    history_limit: int = DEFAULT_PROJECT_REVISION_HISTORY_LIMIT,
) -> Path:
    """Restore a verified historical snapshot to a separate explicit project file."""
    history_limit = _validate_history_limit(history_limit)
    snapshot = load_project_revision(
        revision_path,
        expected_source_path=expected_source_path,
    )
    target = Path(destination)
    if os.path.normcase(str(_normalized_path(target))) == os.path.normcase(
        str(snapshot.source_path)
    ):
        raise ProjectRevisionError(
            "refusing to overwrite the source project; restore the revision to a separate file"
        )

    previous_bytes = target.read_bytes() if target.exists() else None
    target_revision: Path | None = None
    if previous_bytes is not None and previous_bytes != snapshot.source_bytes and history_limit:
        try:
            target_revision = _write_project_revision(target, previous_bytes)
        except (OSError, ProjectFormatError) as exc:
            raise ProjectRevisionError(
                "cannot preserve the destination before revision restore; "
                f"restore was not attempted: {exc}"
            ) from exc

    try:
        atomic_write_bytes(target, snapshot.source_bytes)
        actual = target.read_bytes()
        if actual != snapshot.source_bytes:
            raise OSError("restored project verification failed: persisted bytes differ")
        restored = _project_from_bytes(actual)
        if restored != snapshot.project:
            raise OSError("restored project verification failed after reload")
    except Exception as restore_error:
        try:
            _rollback_destination(target, previous_bytes)
        except Exception as rollback_error:
            raise OSError(
                "project revision restore failed and rollback could not restore the "
                f"destination; destination revision retained at {target_revision!s}: "
                f"{rollback_error}"
            ) from restore_error
        _remove_failed_revision(target_revision)
        raise

    if history_limit:
        _rotate_project_revisions(target, history_limit)
    return target
