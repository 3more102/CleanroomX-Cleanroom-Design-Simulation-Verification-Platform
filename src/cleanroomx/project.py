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


class AtomicWriteVerificationError(OSError):
    """Raised when staged or committed bytes differ from the requested payload."""

    def __init__(
        self,
        path: str | Path,
        *,
        phase: str,
        expected_size: int,
        expected_sha256: str,
        actual_revision: "ProjectFileRevision | None" = None,
    ):
        self.path = Path(path)
        self.phase = phase
        self.expected_size = expected_size
        self.expected_sha256 = expected_sha256
        self.actual_revision = actual_revision
        actual = (
            "unavailable"
            if actual_revision is None
            else (
                f"exists={actual_revision.exists}, size={actual_revision.size}, "
                f"sha256={actual_revision.sha256}"
            )
        )
        super().__init__(
            f"{phase} verification failed for {self.path}: expected "
            f"size={expected_size}, sha256={expected_sha256}; actual {actual}. "
            "Keep the current CleanroomX session open and save to a different path "
            "if the destination may have been changed externally."
        )


class AtomicWriteDurabilityError(OSError):
    """Raised after replace when directory durability cannot be confirmed."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.committed = True
        super().__init__(
            f"file replacement completed for {self.path}, but durable directory "
            "synchronization failed. The new bytes may already be visible, but "
            "crash/power-loss durability could not be confirmed; keep the current "
            "session open and save again or use Save As."
        )


class ProjectWriteConflictError(RuntimeError):
    """Raised when an explicit save would overwrite a different on-disk revision."""

    def __init__(
        self,
        path: str | Path,
        expected: "ProjectFileRevision",
        current: "ProjectFileRevision",
    ):
        self.path = Path(path)
        self.expected = expected
        self.current = current
        super().__init__(
            f"project file changed on disk since it was opened or last saved: {self.path}"
        )


@dataclass(frozen=True)
class ProjectFileRevision:
    path: str
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


def load_project_document(path: str | Path) -> ProjectDocument:
    source = Path(path)
    try:
        data = json.loads(
            source.read_text(encoding="utf-8"),
            parse_constant=_reject_json_constant,
        )
    except json.JSONDecodeError as exc:
        raise ProjectFormatError(
            f"invalid JSON in project file at line {exc.lineno}, column {exc.colno}"
        ) from exc
    return project_from_dict(data)


def _normalized_project_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _sha256_path(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def capture_project_file_revision(path: str | Path) -> ProjectFileRevision:
    """Capture a stable content revision for optimistic project-save protection."""
    source = _normalized_project_path(path)
    normalized = os.path.normcase(str(source))
    if not source.exists():
        return ProjectFileRevision(
            path=normalized, exists=False, size=None, mtime_ns=None, sha256=None
        )
    if not source.is_file():
        raise OSError(f"project path is not a regular file: {source}")

    last_error: OSError | None = None
    for _attempt in range(3):
        before = source.stat()
        try:
            digest = _sha256_path(source)
        except OSError as exc:
            last_error = exc
            continue
        after = source.stat()
        if (
            before.st_dev == after.st_dev
            and before.st_ino == after.st_ino
            and before.st_size == after.st_size
            and before.st_mtime_ns == after.st_mtime_ns
        ):
            return ProjectFileRevision(
                path=normalized,
                exists=True,
                size=after.st_size,
                mtime_ns=after.st_mtime_ns,
                sha256=digest,
            )
        last_error = OSError(f"project file changed while fingerprinting: {source}")

    assert last_error is not None
    raise last_error


def project_file_revision_matches(
    expected: ProjectFileRevision,
    current: ProjectFileRevision,
) -> bool:
    """Compare content revisions while ignoring metadata-only timestamp changes."""
    if expected.path != current.path or expected.exists != current.exists:
        return False
    if not expected.exists:
        return True
    return expected.size == current.size and expected.sha256 == current.sha256


def load_project_document_with_revision(
    path: str | Path,
    *,
    attempts: int = 3,
) -> tuple[ProjectDocument, ProjectFileRevision]:
    """Load a project together with the exact stable content revision that was read."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    source = _normalized_project_path(path)
    for _attempt in range(attempts):
        before = capture_project_file_revision(source)
        project = load_project_document(source)
        after = capture_project_file_revision(source)
        if project_file_revision_matches(before, after):
            return project, after
    raise OSError(f"project file changed repeatedly while opening: {source}")


def _project_document_text(project: ProjectDocument) -> str:
    data = project.to_dict()
    project_from_dict(data)
    return json.dumps(
        data, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False
    ) + "\n"


def _text_identity(text: str) -> tuple[int, str]:
    payload = text.encode("utf-8")
    return len(payload), sha256(payload).hexdigest()


def _verify_text_revision(
    path: str | Path,
    text: str,
    *,
    phase: str,
) -> ProjectFileRevision:
    expected_size, expected_sha256 = _text_identity(text)
    try:
        current = capture_project_file_revision(path)
    except OSError as exc:
        raise AtomicWriteVerificationError(
            path,
            phase=phase,
            expected_size=expected_size,
            expected_sha256=expected_sha256,
            actual_revision=None,
        ) from exc
    if (
        not current.exists
        or current.size != expected_size
        or current.sha256 != expected_sha256
    ):
        raise AtomicWriteVerificationError(
            path,
            phase=phase,
            expected_size=expected_size,
            expected_sha256=expected_sha256,
            actual_revision=current,
        )
    return current


def _fsync_directory(path: Path) -> None:
    """Durably commit a directory-entry change where Python exposes POSIX semantics."""
    if os.name == "nt":
        return
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


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

        # Never replace an existing file with bytes that cannot be read back exactly
        # from the flushed staging file.
        _verify_text_revision(temp_path, text, phase="staged write")

        if before_replace is not None:
            before_replace()
        temp_path.replace(destination)

        try:
            _fsync_directory(destination.parent)
        except OSError as exc:
            raise AtomicWriteDurabilityError(destination) from exc

        # Detect an immediate external rewrite or an unexpected commit/readback
        # mismatch instead of reporting a successful save for different bytes.
        _verify_text_revision(destination, text, phase="committed write")
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise
    return destination


def atomic_write_text(path: str | Path, text: str) -> Path:
    """Atomically replace UTF-8 text with staged/readback verification and durability."""
    return _atomic_write_text(path, text)


def save_project_document(path: str | Path, project: ProjectDocument) -> Path:
    """Save and verify a project without an external-revision precondition."""
    text = _project_document_text(project)
    saved_path = atomic_write_text(path, text)
    _verify_text_revision(saved_path, text, phase="project save")
    return saved_path


def save_project_document_guarded(
    path: str | Path,
    project: ProjectDocument,
    *,
    expected_revision: ProjectFileRevision,
) -> tuple[Path, ProjectFileRevision]:
    """Save only while the destination still matches the expected content revision."""
    destination = _normalized_project_path(path)

    def assert_unchanged() -> None:
        current = capture_project_file_revision(destination)
        if not project_file_revision_matches(expected_revision, current):
            raise ProjectWriteConflictError(destination, expected_revision, current)

    assert_unchanged()
    text = _project_document_text(project)
    saved_path = _atomic_write_text(
        destination,
        text,
        before_replace=assert_unchanged,
    )
    saved_revision = _verify_text_revision(saved_path, text, phase="project save")
    return saved_path, saved_revision
