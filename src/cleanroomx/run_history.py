from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any

from .application import AnalysisRun, analysis_run_matches_input
from .project import ProjectFileRevision, atomic_write_text


RUN_HISTORY_SCHEMA = "cleanroomx.run-history"
RUN_HISTORY_SCHEMA_VERSION = 1
RUN_HISTORY_CANONICALIZATION = "json-sort-keys-compact-utf8-v1"
RUN_HISTORY_DIRECTORY_SUFFIX = ".runs"


class RunHistoryError(ValueError):
    """Raised when durable analysis-run history is malformed or inconsistent."""


class RunHistoryIntegrityError(RunHistoryError):
    """Raised when an immutable run-history record fails its integrity check."""


@dataclass(frozen=True)
class RunHistoryRecord:
    record_id: str
    completed_at_utc: str
    project_filename: str
    project_revision: ProjectFileRevision
    project_dirty: bool
    analysis_id: str
    analysis_name: str
    analysis_kind: str
    input_snapshot: dict[str, Any]
    run: AnalysisRun
    path: Path | None = None


@dataclass(frozen=True)
class RunHistoryScanItem:
    path: Path
    record: RunHistoryRecord | None
    error: str | None

    @property
    def valid(self) -> bool:
        return self.record is not None and self.error is None


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RunHistoryError("run history must contain only strict JSON values") from exc


def _sha256_hex(value: Any) -> str:
    return sha256(_canonical_bytes(value)).hexdigest()


def _strict_json_loads(text: str) -> Any:
    def reject_constant(value: str) -> None:
        raise RunHistoryError(f"non-finite JSON constant is not allowed: {value}")

    try:
        return json.loads(text, parse_constant=reject_constant)
    except json.JSONDecodeError as exc:
        raise RunHistoryError(
            f"invalid run-history JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc


def _required_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RunHistoryError(f"{field_name} must be a non-empty string")
    return value.strip()


def _validate_sha256(value: Any, field_name: str) -> str:
    digest = _required_string(value, field_name).lower()
    if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise RunHistoryError(f"{field_name} must be a 64-character SHA-256 digest")
    return digest


def _format_utc_timestamp(value: datetime | None = None) -> str:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise RunHistoryError("completed_at must be timezone-aware")
    current = current.astimezone(timezone.utc)
    return current.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _validate_utc_timestamp(value: Any) -> str:
    text = _required_string(value, "completed_at_utc")
    if not text.endswith("Z"):
        raise RunHistoryError("completed_at_utc must use an explicit UTC Z suffix")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise RunHistoryError("completed_at_utc is not a valid ISO-8601 timestamp") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise RunHistoryError("completed_at_utc must be UTC")
    return text


def _normalized_path(path: str | Path) -> str:
    return os.path.normcase(str(Path(path).expanduser().resolve(strict=False)))


def run_history_directory(project_path: str | Path) -> Path:
    project = Path(project_path).expanduser().resolve(strict=False)
    return project.with_name(project.name + RUN_HISTORY_DIRECTORY_SUFFIX)


def _revision_payload(revision: ProjectFileRevision) -> dict[str, Any]:
    return {
        "exists": revision.exists,
        "size_bytes": revision.size,
        "mtime_ns": revision.mtime_ns,
        "sha256": revision.sha256,
    }


def _revision_from_payload(project_path: Path, value: Any) -> ProjectFileRevision:
    if not isinstance(value, dict):
        raise RunHistoryError("project_revision must be an object")
    exists = value.get("exists")
    if not isinstance(exists, bool):
        raise RunHistoryError("project_revision.exists must be a boolean")
    size = value.get("size_bytes")
    mtime_ns = value.get("mtime_ns")
    digest = value.get("sha256")
    if exists:
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise RunHistoryError(
                "project_revision.size_bytes must be a non-negative integer"
            )
        if isinstance(mtime_ns, bool) or not isinstance(mtime_ns, int) or mtime_ns < 0:
            raise RunHistoryError(
                "project_revision.mtime_ns must be a non-negative integer"
            )
        digest = _validate_sha256(digest, "project_revision.sha256")
    elif any(item is not None for item in (size, mtime_ns, digest)):
        raise RunHistoryError(
            "missing project revisions must not contain size, mtime, or digest"
        )
    return ProjectFileRevision(
        path=_normalized_path(project_path),
        exists=exists,
        size=size,
        mtime_ns=mtime_ns,
        sha256=digest,
    )


def _analysis_run_from_payload(value: Any) -> AnalysisRun:
    if not isinstance(value, dict):
        raise RunHistoryError("run must be an object")
    kind = _required_string(value.get("kind"), "run.kind")
    title = _required_string(value.get("title"), "run.title")
    status = _required_string(value.get("status"), "run.status")
    result = value.get("result")
    diagnostics = value.get("diagnostics")
    markdown = value.get("markdown")
    plot = value.get("plot")
    if not isinstance(result, dict):
        raise RunHistoryError("run.result must be an object")
    if not isinstance(diagnostics, dict):
        raise RunHistoryError("run.diagnostics must be an object")
    if not isinstance(markdown, str):
        raise RunHistoryError("run.markdown must be a string")
    if plot is not None and not isinstance(plot, dict):
        raise RunHistoryError("run.plot must be an object or null")
    return AnalysisRun(
        kind=kind,
        title=title,
        status=status,
        result=result,
        markdown=markdown,
        diagnostics=diagnostics,
        plot=plot,
    )


def _content_payload(
    *,
    completed_at_utc: str,
    project_path: Path,
    project_revision: ProjectFileRevision,
    project_dirty: bool,
    analysis_id: str,
    analysis_name: str,
    analysis_kind: str,
    input_snapshot: dict[str, Any],
    run: AnalysisRun,
) -> dict[str, Any]:
    return {
        "schema": RUN_HISTORY_SCHEMA,
        "schema_version": RUN_HISTORY_SCHEMA_VERSION,
        "completed_at_utc": completed_at_utc,
        "project": {
            "filename": project_path.name,
            "revision": _revision_payload(project_revision),
            "dirty_at_run": project_dirty,
        },
        "analysis": {
            "id": analysis_id,
            "name": analysis_name,
            "kind": analysis_kind,
        },
        "input_snapshot": input_snapshot,
        "run": run.to_dict(),
    }


def append_run_history_record(
    project_path: str | Path,
    *,
    project_revision: ProjectFileRevision,
    project_dirty: bool,
    analysis_id: str,
    analysis_name: str,
    input_snapshot: dict[str, Any],
    run: AnalysisRun,
    completed_at: datetime | None = None,
) -> Path:
    """Persist one immutable accepted analysis run next to a saved project.

    Each run is a separate atomic file so recording a new run never rewrites or
    truncates older engineering evidence.
    """
    project = Path(project_path).expanduser().resolve(strict=False)
    if project_revision.path != _normalized_path(project):
        raise RunHistoryError("project revision does not belong to the history project")
    if not project_revision.exists or project_revision.sha256 is None:
        raise RunHistoryError("run history requires an existing saved project revision")
    if not isinstance(project_dirty, bool):
        raise RunHistoryError("project_dirty must be a boolean")
    analysis_id = _required_string(analysis_id, "analysis_id")
    analysis_name = _required_string(analysis_name, "analysis_name")
    analysis_kind = _required_string(run.kind, "analysis_kind")
    if not isinstance(input_snapshot, dict):
        raise RunHistoryError("input_snapshot must be an object")
    _canonical_bytes(input_snapshot)
    _canonical_bytes(run.to_dict())
    if not analysis_run_matches_input(run, analysis_kind, input_snapshot):
        raise RunHistoryError(
            "completed run provenance does not match the submitted input snapshot"
        )

    completed_at_utc = _format_utc_timestamp(completed_at)
    content = _content_payload(
        completed_at_utc=completed_at_utc,
        project_path=project,
        project_revision=project_revision,
        project_dirty=project_dirty,
        analysis_id=analysis_id,
        analysis_name=analysis_name,
        analysis_kind=analysis_kind,
        input_snapshot=input_snapshot,
        run=run,
    )
    record_id = _sha256_hex(content)
    signed = {**content, "record_id": record_id}
    document = {
        **signed,
        "integrity": {
            "algorithm": "sha256",
            "canonicalization": RUN_HISTORY_CANONICALIZATION,
            "sha256": _sha256_hex(signed),
        },
    }

    directory = run_history_directory(project)
    if directory.exists():
        if directory.is_symlink() or not directory.is_dir():
            raise RunHistoryError(
                f"run-history destination is not a regular directory: {directory}"
            )
    else:
        directory.mkdir(mode=0o700)

    timestamp_slug = completed_at_utc.replace("-", "").replace(":", "").replace(".", "")
    timestamp_slug = timestamp_slug.replace("Z", "Z")
    analysis_slug = re.sub(r"[^A-Za-z0-9._-]+", "_", analysis_id).strip("._-")
    analysis_slug = (analysis_slug or "analysis")[:64]
    destination = directory / (
        f"{timestamp_slug}_{analysis_slug}_{record_id[:16]}.json"
    )
    if destination.exists():
        existing = load_run_history_record(destination)
        if existing.record_id == record_id:
            return destination
        raise RunHistoryError(f"run-history record path collision: {destination.name}")

    text = json.dumps(
        document,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"
    atomic_write_text(destination, text)
    return destination


def load_run_history_record(path: str | Path) -> RunHistoryRecord:
    source = Path(path)
    if source.is_symlink():
        raise RunHistoryError(f"run-history records may not be symbolic links: {source}")
    try:
        data = _strict_json_loads(source.read_text(encoding="utf-8"))
    except OSError:
        raise
    if not isinstance(data, dict):
        raise RunHistoryError("run-history record must contain a JSON object")
    if data.get("schema") != RUN_HISTORY_SCHEMA:
        raise RunHistoryError(f"run-history schema must be {RUN_HISTORY_SCHEMA!r}")
    version = data.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise RunHistoryError("run-history schema_version must be an integer")
    if version != RUN_HISTORY_SCHEMA_VERSION:
        raise RunHistoryError(
            f"unsupported run-history schema version {version}; "
            f"this build supports {RUN_HISTORY_SCHEMA_VERSION}"
        )

    integrity = data.get("integrity")
    if not isinstance(integrity, dict):
        raise RunHistoryIntegrityError("run-history integrity block is missing")
    if integrity.get("algorithm") != "sha256":
        raise RunHistoryIntegrityError("unsupported run-history integrity algorithm")
    if integrity.get("canonicalization") != RUN_HISTORY_CANONICALIZATION:
        raise RunHistoryIntegrityError(
            "unsupported run-history integrity canonicalization"
        )
    expected_integrity = _validate_sha256(
        integrity.get("sha256"), "integrity.sha256"
    )
    signed = {key: value for key, value in data.items() if key != "integrity"}
    if _sha256_hex(signed) != expected_integrity:
        raise RunHistoryIntegrityError("run-history content SHA-256 mismatch")

    record_id = _validate_sha256(data.get("record_id"), "record_id")
    content = {
        key: value
        for key, value in data.items()
        if key not in {"record_id", "integrity"}
    }
    if _sha256_hex(content) != record_id:
        raise RunHistoryIntegrityError("run-history record_id does not match content")

    completed_at_utc = _validate_utc_timestamp(data.get("completed_at_utc"))
    project_data = data.get("project")
    if not isinstance(project_data, dict):
        raise RunHistoryError("project must be an object")
    project_filename = _required_string(
        project_data.get("filename"), "project.filename"
    )
    if Path(project_filename).name != project_filename:
        raise RunHistoryError("project.filename must not contain path components")
    project_dirty = project_data.get("dirty_at_run")
    if not isinstance(project_dirty, bool):
        raise RunHistoryError("project.dirty_at_run must be a boolean")

    history_dir = source.parent
    suffix = RUN_HISTORY_DIRECTORY_SUFFIX
    if not history_dir.name.endswith(suffix):
        project_path = history_dir.parent / project_filename
    else:
        project_path = history_dir.parent / project_filename
    revision = _revision_from_payload(project_path, project_data.get("revision"))

    analysis_data = data.get("analysis")
    if not isinstance(analysis_data, dict):
        raise RunHistoryError("analysis must be an object")
    analysis_id = _required_string(analysis_data.get("id"), "analysis.id")
    analysis_name = _required_string(analysis_data.get("name"), "analysis.name")
    analysis_kind = _required_string(analysis_data.get("kind"), "analysis.kind")
    input_snapshot = data.get("input_snapshot")
    if not isinstance(input_snapshot, dict):
        raise RunHistoryError("input_snapshot must be an object")
    _canonical_bytes(input_snapshot)

    run = _analysis_run_from_payload(data.get("run"))
    if run.kind != analysis_kind:
        raise RunHistoryError("analysis kind does not match the stored run kind")
    if not analysis_run_matches_input(run, analysis_kind, input_snapshot):
        raise RunHistoryIntegrityError(
            "stored run provenance does not match its input snapshot"
        )

    return RunHistoryRecord(
        record_id=record_id,
        completed_at_utc=completed_at_utc,
        project_filename=project_filename,
        project_revision=revision,
        project_dirty=project_dirty,
        analysis_id=analysis_id,
        analysis_name=analysis_name,
        analysis_kind=analysis_kind,
        input_snapshot=input_snapshot,
        run=run,
        path=source,
    )


def scan_run_history(project_path: str | Path) -> list[RunHistoryScanItem]:
    """Return newest-first valid and corrupt history entries without deleting evidence."""
    directory = run_history_directory(project_path)
    if not directory.exists():
        return []
    if directory.is_symlink() or not directory.is_dir():
        raise RunHistoryError(
            f"run-history location is not a regular directory: {directory}"
        )

    items: list[RunHistoryScanItem] = []
    for path in sorted(directory.glob("*.json"), key=lambda item: item.name, reverse=True):
        try:
            record = load_run_history_record(path)
        except (OSError, RunHistoryError) as exc:
            items.append(RunHistoryScanItem(path=path, record=None, error=str(exc)))
        else:
            items.append(RunHistoryScanItem(path=path, record=record, error=None))
    return items
