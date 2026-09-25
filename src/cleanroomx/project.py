from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable

from . import __version__
from .application import ANALYSIS_SPECS

PROJECT_SCHEMA = "cleanroomx.project"
PROJECT_SCHEMA_VERSION = 1


class ProjectFormatError(ValueError):
    pass


@dataclass(frozen=True)
class FileFingerprint:
    """Content identity for an on-disk project used by optimistic save guards."""

    path: Path
    exists: bool
    size: int | None
    mtime_ns: int | None
    sha256: str | None

    def same_content(self, other: "FileFingerprint") -> bool:
        if os.path.normcase(str(self.path)) != os.path.normcase(str(other.path)):
            return False
        if self.exists != other.exists:
            return False
        if not self.exists:
            return True
        return self.size == other.size and self.sha256 == other.sha256

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "exists": self.exists,
            "size": self.size,
            "mtime_ns": self.mtime_ns,
            "sha256": self.sha256,
        }


class ProjectSaveConflictError(RuntimeError):
    """Raised when the project changed on disk since the caller's baseline."""

    def __init__(
        self,
        path: str | Path,
        expected: FileFingerprint,
        current: FileFingerprint,
    ) -> None:
        self.path = Path(path)
        self.expected = expected
        self.current = current
        super().__init__(
            f"project changed on disk since it was opened or last saved: {self.path}. "
            "Reload it or use Save Project As to preserve both versions."
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


def _stat_identity(stat: os.stat_result) -> tuple[int, int, int, int]:
    return (
        int(getattr(stat, "st_dev", 0)),
        int(getattr(stat, "st_ino", 0)),
        stat.st_size,
        stat.st_mtime_ns,
    )


def _stable_file_bytes(path: str | Path) -> tuple[bytes, FileFingerprint]:
    source = _normalized_file_path(path)
    last_error: OSError | None = None
    for _attempt in range(3):
        before = source.stat()
        try:
            raw = source.read_bytes()
        except OSError as exc:
            last_error = exc
            continue
        after = source.stat()
        if _stat_identity(before) == _stat_identity(after) and len(raw) == after.st_size:
            return raw, FileFingerprint(
                path=source,
                exists=True,
                size=after.st_size,
                mtime_ns=after.st_mtime_ns,
                sha256=sha256(raw).hexdigest(),
            )
        last_error = OSError(f"file changed while reading: {source}")
    assert last_error is not None
    raise last_error


def file_fingerprint(path: str | Path) -> FileFingerprint:
    source = _normalized_file_path(path)
    if not source.exists():
        return FileFingerprint(
            path=source,
            exists=False,
            size=None,
            mtime_ns=None,
            sha256=None,
        )
    _raw, fingerprint = _stable_file_bytes(source)
    return fingerprint


def load_project_document_with_fingerprint(
    path: str | Path,
) -> tuple[ProjectDocument, FileFingerprint]:
    raw, fingerprint = _stable_file_bytes(path)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProjectFormatError("project file must be valid UTF-8") from exc
    try:
        data = json.loads(text, parse_constant=_reject_json_constant)
    except json.JSONDecodeError as exc:
        raise ProjectFormatError(
            f"invalid JSON in project file at line {exc.lineno}, column {exc.colno}"
        ) from exc
    return project_from_dict(data), fingerprint


def load_project_document(path: str | Path) -> ProjectDocument:
    project, _fingerprint = load_project_document_with_fingerprint(path)
    return project


def _atomic_write_text(
    path: str | Path,
    text: str,
    *,
    before_replace: Callable[[], None] | None = None,
) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix=f".{destination.name}.",
            suffix=".tmp", dir=destination.parent, delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())

        if before_replace is not None:
            before_replace()
        temp_path.replace(destination)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise
    return destination


def atomic_write_text(path: str | Path, text: str) -> Path:
    """Atomically replace a UTF-8 text file using a same-directory temporary file."""
    return _atomic_write_text(path, text)


def save_project_document(
    path: str | Path,
    project: ProjectDocument,
    *,
    expected_fingerprint: FileFingerprint | None = None,
) -> Path:
    destination = Path(path)
    data = project.to_dict()
    project_from_dict(data)
    text = json.dumps(
        data, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False
    ) + "\n"

    def ensure_destination_unchanged() -> None:
        if expected_fingerprint is None:
            return
        current = file_fingerprint(destination)
        if not expected_fingerprint.same_content(current):
            raise ProjectSaveConflictError(destination, expected_fingerprint, current)

    return _atomic_write_text(
        destination,
        text,
        before_replace=ensure_destination_unchanged,
    )
