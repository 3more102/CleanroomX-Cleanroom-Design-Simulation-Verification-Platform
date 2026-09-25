from __future__ import annotations

import copy
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

_PROJECT_TOP_LEVEL_FIELDS = frozenset({
    "schema",
    "schema_version",
    "application_version",
    "project",
    "analyses",
    "active_analysis_id",
})
_PROJECT_BLOCK_FIELDS = frozenset({"name", "description", "metadata"})
_ANALYSIS_FIELDS = frozenset({"id", "name", "kind", "input"})


def _copy_extra_fields(extra_fields: Any) -> dict[str, Any]:
    """Validate and detach an opaque additive-field mapping."""
    if not isinstance(extra_fields, dict):
        raise ProjectFormatError("additive project fields must be an object")
    if any(not isinstance(key, str) for key in extra_fields):
        raise ProjectFormatError("additive project field names must be strings")
    return copy.deepcopy(extra_fields)


def _extra_fields(data: dict, known_fields: frozenset[str]) -> dict[str, Any]:
    """Return a detached copy of additive fields this build does not interpret."""
    return _copy_extra_fields({
        key: value
        for key, value in data.items()
        if key not in known_fields
    })


def _merge_extra_fields(extra_fields: dict[str, Any], known: dict[str, Any]) -> dict:
    """Serialize opaque extensions losslessly while keeping known fields authoritative."""
    merged = _copy_extra_fields(extra_fields)
    merged.update(known)
    return merged


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
    extra_fields: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # The model is mutable, but it owns its nested JSON state. Caller-owned
        # parser/build dictionaries must never remain aliases into project state.
        self.input = copy.deepcopy(self.input)
        self.extra_fields = _copy_extra_fields(self.extra_fields)

    def to_dict(self) -> dict:
        return _merge_extra_fields(
            self.extra_fields,
            {
                "id": self.id,
                "name": self.name,
                "kind": self.kind,
                "input": copy.deepcopy(self.input),
            },
        )


@dataclass
class ProjectDocument:
    name: str
    description: str = ""
    analyses: list[AnalysisDocument] = field(default_factory=list)
    active_analysis_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    project_extra_fields: dict[str, Any] = field(default_factory=dict)
    top_level_extra_fields: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Preserve AnalysisDocument object identity for in-model editing while
        # detaching every caller-owned container at the model boundary.
        self.analyses = list(self.analyses)
        self.metadata = copy.deepcopy(self.metadata)
        self.project_extra_fields = _copy_extra_fields(self.project_extra_fields)
        self.top_level_extra_fields = _copy_extra_fields(self.top_level_extra_fields)

    def to_dict(self) -> dict:
        project_block = _merge_extra_fields(
            self.project_extra_fields,
            {
                "name": self.name,
                "description": self.description,
                "metadata": copy.deepcopy(self.metadata),
            },
        )
        return _merge_extra_fields(
            self.top_level_extra_fields,
            {
                "schema": PROJECT_SCHEMA,
                "schema_version": PROJECT_SCHEMA_VERSION,
                "application_version": __version__,
                "project": project_block,
                "analyses": [item.to_dict() for item in self.analyses],
                "active_analysis_id": self.active_analysis_id,
            },
        )

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
    return AnalysisDocument(
        id=analysis_id,
        name=name,
        kind=kind,
        input=payload,
        extra_fields=_extra_fields(data, _ANALYSIS_FIELDS),
    )


def _migrate_legacy(data: dict) -> dict:
    if data.get("schema") == PROJECT_SCHEMA and data.get("schema_version") == 0:
        analysis = data.get("analysis", {})
        if not isinstance(analysis, dict):
            raise ProjectFormatError("legacy v0 analysis must be an object")
        analysis_id = analysis.get("id", "analysis-1")
        top_level_extra_fields = _extra_fields(
            data,
            frozenset({
                "schema",
                "schema_version",
                "application_version",
                "name",
                "description",
                "metadata",
                "analysis",
            }),
        )
        analysis_extra_fields = _extra_fields(analysis, _ANALYSIS_FIELDS)
        return _merge_extra_fields(
            top_level_extra_fields,
            {
                "schema": PROJECT_SCHEMA,
                "schema_version": PROJECT_SCHEMA_VERSION,
                "application_version": data.get("application_version", "legacy"),
                "project": {
                    "name": data.get("name", "Migrated CleanroomX Project"),
                    "description": data.get("description", ""),
                    "metadata": data.get("metadata", {}),
                },
                "analyses": [
                    _merge_extra_fields(
                        analysis_extra_fields,
                        {
                            "id": analysis_id,
                            "name": analysis.get("name", analysis.get("kind", "Analysis")),
                            "kind": analysis.get("kind"),
                            "input": analysis.get("input", {}),
                        },
                    )
                ],
                "active_analysis_id": analysis_id,
            },
        )

    if "schema" not in data and "analysis_type" in data and "input" in data:
        top_level_extra_fields = _extra_fields(
            data,
            frozenset({"name", "description", "analysis_name", "analysis_type", "input"}),
        )
        return _merge_extra_fields(
            top_level_extra_fields,
            {
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
            },
        )
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
        project_extra_fields=_extra_fields(project_data, _PROJECT_BLOCK_FIELDS),
        top_level_extra_fields=_extra_fields(data, _PROJECT_TOP_LEVEL_FIELDS),
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
        digest = sha256()
        try:
            with source.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as exc:
            last_error = exc
            continue
        after = source.stat()
        if before.st_size == after.st_size and before.st_mtime_ns == after.st_mtime_ns:
            return ProjectFileRevision(
                path=normalized,
                exists=True,
                size=after.st_size,
                mtime_ns=after.st_mtime_ns,
                sha256=digest.hexdigest(),
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
