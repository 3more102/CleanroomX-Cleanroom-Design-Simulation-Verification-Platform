from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import errno
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


class AtomicWriteDurabilityError(OSError):
    """Raised after replacement when directory durability cannot be confirmed."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        super().__init__(
            "atomic replacement completed but directory durability sync failed for "
            f"{self.path}; the file may contain the new data, but crash durability "
            "was not confirmed"
        )


class AtomicWriteVerificationError(OSError):
    """Raised when an atomic text write cannot be verified byte-for-byte."""

    def __init__(
        self,
        path: str | Path,
        *,
        stage: str,
        expected_size: int,
        expected_sha256: str,
        actual_size: int | None,
        actual_sha256: str | None,
    ) -> None:
        self.path = Path(path)
        self.stage = stage
        self.expected_size = expected_size
        self.expected_sha256 = expected_sha256
        self.actual_size = actual_size
        self.actual_sha256 = actual_sha256
        super().__init__(
            f"{stage} verification failed for {self.path}: "
            f"expected {expected_size} bytes / sha256 {expected_sha256}, "
            f"got {actual_size!r} bytes / sha256 {actual_sha256!r}"
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


def _stable_file_sha256(
    path: str | Path,
    *,
    attempts: int = 3,
    change_label: str = "file",
) -> tuple[os.stat_result, str]:
    """Hash one stable path revision, rejecting replacement or mutation during the read."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    source = Path(path)
    last_error: OSError | None = None
    for _attempt in range(attempts):
        try:
            before = source.stat()
            digest = sha256()
            with source.open("rb") as handle:
                opened_before = os.fstat(handle.fileno())
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
                opened_after = os.fstat(handle.fileno())
            after = source.stat()
        except OSError as exc:
            last_error = exc
            continue

        identities = {
            (before.st_dev, before.st_ino),
            (opened_before.st_dev, opened_before.st_ino),
            (opened_after.st_dev, opened_after.st_ino),
            (after.st_dev, after.st_ino),
        }
        if (
            len(identities) == 1
            and before.st_size == opened_before.st_size == opened_after.st_size == after.st_size
            and before.st_mtime_ns
            == opened_before.st_mtime_ns
            == opened_after.st_mtime_ns
            == after.st_mtime_ns
        ):
            return after, digest.hexdigest()
        last_error = OSError(f"{change_label} changed while fingerprinting: {source}")

    assert last_error is not None
    raise last_error


def _fsync_parent_directory(directory: Path) -> bool:
    """Durably commit a rename where directory fsync is supported."""
    if os.name == "nt":
        return False

    unsupported = {errno.EBADF, errno.EINVAL}
    for name in ("ENOTSUP", "EOPNOTSUPP"):
        value = getattr(errno, name, None)
        if value is not None:
            unsupported.add(value)

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(directory, flags)
    except OSError as exc:
        if exc.errno in unsupported:
            return False
        raise
    try:
        try:
            os.fsync(descriptor)
        except OSError as exc:
            if exc.errno in unsupported:
                return False
            raise
    finally:
        os.close(descriptor)
    return True


def _verify_file_payload(path: Path, payload: bytes, *, stage: str) -> None:
    """Re-read one stable path revision and require the exact requested bytes."""
    expected_size = len(payload)
    expected_sha256 = sha256(payload).hexdigest()
    try:
        stat, actual_sha256 = _stable_file_sha256(
            path,
            change_label=f"{stage} file",
        )
    except OSError as exc:
        raise AtomicWriteVerificationError(
            path,
            stage=stage,
            expected_size=expected_size,
            expected_sha256=expected_sha256,
            actual_size=None,
            actual_sha256=None,
        ) from exc
    if stat.st_size != expected_size or actual_sha256 != expected_sha256:
        raise AtomicWriteVerificationError(
            path,
            stage=stage,
            expected_size=expected_size,
            expected_sha256=expected_sha256,
            actual_size=stat.st_size,
            actual_sha256=actual_sha256,
        )


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

    stat, digest = _stable_file_sha256(
        source,
        attempts=3,
        change_label="project file",
    )
    return ProjectFileRevision(
        path=normalized,
        exists=True,
        size=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        sha256=digest,
    )


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


def _atomic_write_text(
    path: str | Path,
    text: str,
    *,
    before_replace: Callable[[], None] | None = None,
) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = text.encode("utf-8")

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{destination.name}.",
            suffix=".tmp", dir=destination.parent, delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

        # Do not replace an authoritative file until the exact staged bytes have
        # been re-read from a stable path revision and verified.
        _verify_file_payload(temp_path, payload, stage="staged write")

        if before_replace is not None:
            before_replace()
        temp_path.replace(destination)
        temp_path = None

        try:
            _fsync_parent_directory(destination.parent)
        except OSError as exc:
            raise AtomicWriteDurabilityError(destination) from exc

        # A successful replacement is not reported until the destination itself
        # matches the exact requested UTF-8 payload.
        _verify_file_payload(destination, payload, stage="committed write")
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise
    return destination


def atomic_write_text(path: str | Path, text: str) -> Path:
    """Commit exact UTF-8 bytes through a staged, durable, verified replacement."""
    return _atomic_write_text(path, text)


def save_project_document(path: str | Path, project: ProjectDocument) -> Path:
    """Save a project atomically without an external-revision precondition."""
    return atomic_write_text(path, _project_document_text(project))


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
    return saved_path, capture_project_file_revision(saved_path)
