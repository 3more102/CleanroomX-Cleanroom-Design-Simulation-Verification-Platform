from __future__ import annotations

from dataclasses import dataclass, field
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


class ProjectFormatError(ValueError):
    pass


class ProjectSaveConflictError(RuntimeError):
    """Raised when an explicit save would overwrite a changed project file."""

    def __init__(self, path: str | Path, reason: str):
        self.path = Path(path)
        self.reason = reason
        super().__init__(f"refusing to overwrite {self.path}: {reason}")


@dataclass(frozen=True)
class FileRevision:
    """Content identity captured for optimistic project-save conflict checks."""

    path: Path
    size: int
    mtime_ns: int
    sha256: str

    def same_content(self, other: "FileRevision") -> bool:
        return (
            self.path == other.path
            and self.size == other.size
            and self.sha256 == other.sha256
        )


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


def _normalized_file_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _stat_identity(stat: os.stat_result) -> tuple[int, int, int | None, int | None]:
    return (
        stat.st_size,
        stat.st_mtime_ns,
        getattr(stat, "st_dev", None),
        getattr(stat, "st_ino", None),
    )


def _stable_read_bytes(path: str | Path) -> tuple[bytes, FileRevision]:
    source = _normalized_file_path(path)
    last_error: OSError | None = None
    for _attempt in range(2):
        try:
            before = source.stat()
            data = source.read_bytes()
            after = source.stat()
        except OSError as exc:
            last_error = exc
            continue
        if (
            _stat_identity(before) == _stat_identity(after)
            and len(data) == after.st_size
        ):
            return data, FileRevision(
                path=source,
                size=after.st_size,
                mtime_ns=after.st_mtime_ns,
                sha256=sha256(data).hexdigest(),
            )
        last_error = OSError(f"file changed while reading: {source}")
    assert last_error is not None
    raise last_error


def file_revision(path: str | Path) -> FileRevision | None:
    """Return a stable content revision, or None when the path does not exist."""
    try:
        _data, revision = _stable_read_bytes(path)
    except FileNotFoundError:
        return None
    return revision


def _project_from_bytes(data: bytes) -> ProjectDocument:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProjectFormatError("project file must be valid UTF-8") from exc
    try:
        payload = json.loads(text, parse_constant=_reject_json_constant)
    except json.JSONDecodeError as exc:
        raise ProjectFormatError(
            f"invalid JSON in project file at line {exc.lineno}, column {exc.colno}"
        ) from exc
    return project_from_dict(payload)


def load_project_document_with_revision(
    path: str | Path,
) -> tuple[ProjectDocument, FileRevision]:
    data, revision = _stable_read_bytes(path)
    return _project_from_bytes(data), revision


def load_project_document(path: str | Path) -> ProjectDocument:
    project, _revision = load_project_document_with_revision(path)
    return project


def _assert_expected_revision(
    destination: Path,
    expected_revision: FileRevision,
) -> None:
    normalized = _normalized_file_path(destination)
    if normalized != expected_revision.path:
        raise ValueError(
            "expected file revision path does not match the save destination"
        )
    actual = file_revision(normalized)
    if actual is None:
        raise ProjectSaveConflictError(
            destination,
            "the project file was deleted or moved after it was opened",
        )
    if not expected_revision.same_content(actual):
        raise ProjectSaveConflictError(
            destination,
            "the project file changed on disk after it was opened or last saved",
        )


def _atomic_write_text_with_revision(
    path: str | Path,
    text: str,
    *,
    expected_revision: FileRevision | None = None,
) -> tuple[Path, FileRevision]:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    encoded = text.encode("utf-8")
    expected_digest = sha256(encoded).hexdigest()

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
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())

        if expected_revision is not None:
            _assert_expected_revision(destination, expected_revision)

        temp_path.replace(destination)
        written_revision = file_revision(destination)
        if written_revision is None:
            raise OSError(f"save verification failed because {destination} is missing")
        if (
            written_revision.size != len(encoded)
            or written_revision.sha256 != expected_digest
        ):
            raise ProjectSaveConflictError(
                destination,
                "the project file changed during post-save verification",
            )
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise
    return destination, written_revision


def atomic_write_text(path: str | Path, text: str) -> Path:
    """Atomically replace UTF-8 text and verify the bytes written to disk."""
    destination, _revision = _atomic_write_text_with_revision(path, text)
    return destination


def _serialize_project_document(project: ProjectDocument) -> str:
    data = project.to_dict()
    project_from_dict(data)
    return json.dumps(
        data, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False
    ) + "\n"


def save_project_document_with_revision(
    path: str | Path,
    project: ProjectDocument,
    *,
    expected_revision: FileRevision | None = None,
) -> tuple[Path, FileRevision]:
    text = _serialize_project_document(project)
    return _atomic_write_text_with_revision(
        path,
        text,
        expected_revision=expected_revision,
    )


def save_project_document(path: str | Path, project: ProjectDocument) -> Path:
    destination, _revision = save_project_document_with_revision(path, project)
    return destination
