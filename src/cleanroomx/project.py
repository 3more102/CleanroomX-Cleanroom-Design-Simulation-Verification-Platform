from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Iterator
import uuid

from . import __version__
from .application import ANALYSIS_SPECS

PROJECT_SCHEMA = "cleanroomx.project"
PROJECT_SCHEMA_VERSION = 1


class ProjectFormatError(ValueError):
    pass


class ProjectConflictError(RuntimeError):
    """Raised when a guarded save would overwrite a different on-disk revision."""


@dataclass(frozen=True)
class ProjectFileRevision:
    """Content identity for an explicit project file."""

    exists: bool
    size: int | None
    mtime_ns: int | None
    sha256: str | None


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


def _stable_file_bytes(path: Path) -> tuple[bytes, os.stat_result]:
    """Read one stable file revision, retrying if the path changes during the read."""
    last_error: OSError | None = None
    for _attempt in range(3):
        try:
            before = path.stat()
            payload = path.read_bytes()
            after = path.stat()
        except OSError as exc:
            last_error = exc
            continue
        before_identity = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        )
        after_identity = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        )
        if before_identity == after_identity and len(payload) == after.st_size:
            return payload, after
        last_error = OSError(f"project changed while reading: {path}")
    assert last_error is not None
    raise last_error


def project_file_revision(path: str | Path) -> ProjectFileRevision:
    """Return a stable content revision for a project path."""
    source = Path(path)
    try:
        payload, stat = _stable_file_bytes(source)
    except FileNotFoundError:
        return ProjectFileRevision(
            exists=False,
            size=None,
            mtime_ns=None,
            sha256=None,
        )
    return ProjectFileRevision(
        exists=True,
        size=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        sha256=sha256(payload).hexdigest(),
    )


def _same_project_revision(
    expected: ProjectFileRevision,
    current: ProjectFileRevision,
) -> bool:
    if expected.exists != current.exists:
        return False
    if not expected.exists:
        return True
    return expected.sha256 == current.sha256


def _parse_project_bytes(payload: bytes) -> ProjectDocument:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProjectFormatError(
            f"project file is not valid UTF-8 at byte {exc.start}"
        ) from exc
    try:
        data = json.loads(text, parse_constant=_reject_json_constant)
    except json.JSONDecodeError as exc:
        raise ProjectFormatError(
            f"invalid JSON in project file at line {exc.lineno}, column {exc.colno}"
        ) from exc
    return project_from_dict(data)


def load_project_document_with_revision(
    path: str | Path,
) -> tuple[ProjectDocument, ProjectFileRevision]:
    """Load and validate a project while capturing the exact on-disk revision."""
    source = Path(path)
    payload, stat = _stable_file_bytes(source)
    project = _parse_project_bytes(payload)
    revision = ProjectFileRevision(
        exists=True,
        size=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        sha256=sha256(payload).hexdigest(),
    )
    return project, revision


def load_project_document(path: str | Path) -> ProjectDocument:
    project, _revision = load_project_document_with_revision(path)
    return project


def _save_lock_path(destination: Path) -> Path:
    return destination.with_name(f".{destination.name}.cleanroomx-save.lock")


@contextmanager
def _exclusive_project_save_lock(
    destination: Path,
    *,
    stale_after_seconds: float = 300.0,
) -> Iterator[None]:
    """Serialize cooperating CleanroomX writers around compare-and-replace."""
    lock_path = _save_lock_path(destination)
    token = uuid.uuid4().hex
    descriptor: int | None = None

    for _attempt in range(2):
        try:
            descriptor = os.open(
                lock_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
            break
        except FileExistsError as exc:
            try:
                lock_stat = lock_path.stat()
            except FileNotFoundError:
                continue
            age_seconds = max(0.0, time.time() - lock_stat.st_mtime)
            if age_seconds >= stale_after_seconds:
                try:
                    lock_path.unlink()
                except FileNotFoundError:
                    continue
                continue
            raise ProjectConflictError(
                f"project is currently being saved by another CleanroomX process: "
                f"{destination}"
            ) from exc

    if descriptor is None:
        raise ProjectConflictError(
            f"could not acquire the project save lock: {destination}"
        )

    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = None
            handle.write(
                json.dumps(
                    {"pid": os.getpid(), "token": token, "created_unix": time.time()},
                    sort_keys=True,
                )
                + "\n"
            )
            handle.flush()
            os.fsync(handle.fileno())
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def atomic_write_text(path: str | Path, text: str) -> Path:
    """Atomically replace a UTF-8 text file using a same-directory temporary file."""
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

        temp_path.replace(destination)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise
    return destination


def _serialized_project_text(project: ProjectDocument) -> str:
    data = project.to_dict()
    project_from_dict(data)
    return json.dumps(
        data, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False
    ) + "\n"


def save_project_document_with_revision(
    path: str | Path,
    project: ProjectDocument,
    *,
    expected_revision: ProjectFileRevision,
) -> tuple[Path, ProjectFileRevision]:
    """Save only when the current file still matches the caller's revision."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    text = _serialized_project_text(project)
    payload = text.encode("utf-8")
    written_digest = sha256(payload).hexdigest()

    with _exclusive_project_save_lock(destination):
        current = project_file_revision(destination)
        if not _same_project_revision(expected_revision, current):
            raise ProjectConflictError(
                "project file changed on disk since it was opened or last saved: "
                f"{destination}. CleanroomX did not overwrite the newer file."
            )

        atomic_write_text(destination, text)
        saved_revision = project_file_revision(destination)
        if (
            not saved_revision.exists
            or saved_revision.sha256 != written_digest
        ):
            raise ProjectConflictError(
                "project file changed again while the save was completing: "
                f"{destination}. The current editor state remains unsaved."
            )

    return destination, saved_revision


def save_project_document(path: str | Path, project: ProjectDocument) -> Path:
    """Backward-compatible unconditional save using validated atomic replacement."""
    destination = Path(path)
    return atomic_write_text(destination, _serialized_project_text(project))
