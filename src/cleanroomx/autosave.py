from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import uuid
from typing import Any

from . import __version__
from .persistence import (
    StableFileSizeError,
    atomic_write_text,
    stable_file_sha256,
)
from .project import PROJECT_FILE_MAX_BYTES, ProjectDocument, project_from_dict
from .strict_json import (
    StrictJSONError,
    StrictJSONSizeError,
    load_strict_json,
    strict_json_loads,
)


RECOVERY_SCHEMA = "cleanroomx.autosave"
RECOVERY_SCHEMA_VERSION = 2
RECOVERY_LEGACY_SCHEMA_VERSIONS = frozenset({1})
RECOVERY_INTEGRITY_ALGORITHM = "sha256"
RECOVERY_INTEGRITY_CANONICALIZATION = "json-sort-keys-compact-utf8-v1"
RECOVERY_QUARANTINE_SCHEMA = "cleanroomx.recovery-quarantine"
RECOVERY_QUARANTINE_SCHEMA_VERSION = 1
DEFAULT_AUTOSAVE_INTERVAL_SECONDS = 60.0
DEFAULT_RECOVERY_HISTORY_LIMIT = 5
DEFAULT_RECOVERY_QUARANTINE_LIMIT = 20
RECOVERY_FILE_MAX_BYTES = 2 * PROJECT_FILE_MAX_BYTES
RECOVERY_QUARANTINE_MANIFEST_MAX_BYTES = 1024 * 1024


class RecoveryFormatError(ValueError):
    """Raised when a recovery artifact is malformed or unsupported."""


@dataclass(frozen=True)
class AutosaveStatus:
    state: str
    message: str
    artifact_path: Path | None = None
    updated_at_utc: str | None = None
    sequence: int = 0


@dataclass(frozen=True)
class RecoveryCandidate:
    path: Path
    project_identity: str
    saved_at_utc: str
    project_name: str
    source_path: Path | None
    source_relation: str
    source_is_newer: bool
    integrity_status: str = "legacy_unverified"


@dataclass(frozen=True)
class RecoveryScanIssue:
    path: Path
    error: str


@dataclass(frozen=True)
class RecoveryScan:
    candidates: tuple[RecoveryCandidate, ...]
    issues: tuple[RecoveryScanIssue, ...]


@dataclass(frozen=True)
class QuarantinedRecoveryArtifact:
    path: Path
    manifest_path: Path
    original_name: str
    quarantined_at_utc: str
    reason: str
    sha256: str


@dataclass(frozen=True)
class RecoveredProjectState:
    project: ProjectDocument
    ui_state: dict[str, Any]
    source_path: Path | None
    saved_at_utc: str
    project_identity: str
    artifact_path: Path
    integrity_status: str = "legacy_unverified"


@dataclass(frozen=True)
class _AutosaveRequest:
    project_identity: str
    epoch: int
    source_path: Path | None
    snapshot_text: str
    digest: str


@dataclass(frozen=True)
class _VerifiedQuarantinePairRevision:
    manifest_sha256: str
    artifact_sha256: str
    artifact_size: int


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_utc(text: str) -> datetime:
    if not isinstance(text, str) or not text:
        raise RecoveryFormatError("saved_at_utc must be a non-empty string")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RecoveryFormatError("saved_at_utc is not a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise RecoveryFormatError("saved_at_utc must include a timezone")
    return parsed.astimezone(timezone.utc)


def default_recovery_dir() -> Path:
    override = os.environ.get("CLEANROOMX_RECOVERY_DIR")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "CleanroomX" / "Recovery"
        return Path.home() / "AppData" / "Local" / "CleanroomX" / "Recovery"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "CleanroomX" / "Recovery"
    state_home = os.environ.get("XDG_STATE_HOME")
    if state_home:
        return Path(state_home) / "cleanroomx" / "recovery"
    return Path.home() / ".local" / "state" / "cleanroomx" / "recovery"


def _ensure_recovery_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        try:
            path.chmod(0o700)
        except OSError:
            pass
    return path


def _reject_json_constant(value: str):
    raise RecoveryFormatError(f"non-finite JSON constant is not allowed: {value}")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )


def _recovery_integrity_sha256(data: dict[str, Any]) -> str:
    covered = {key: value for key, value in data.items() if key != "integrity"}
    canonical = _canonical_json(covered).encode("utf-8")
    return sha256(canonical).hexdigest()


def _recovery_integrity_block(data: dict[str, Any]) -> dict[str, str]:
    return {
        "algorithm": RECOVERY_INTEGRITY_ALGORITHM,
        "canonicalization": RECOVERY_INTEGRITY_CANONICALIZATION,
        "sha256": _recovery_integrity_sha256(data),
    }


def recovery_integrity_status(data: dict[str, Any]) -> str:
    """Validate embedded recovery integrity and report its verification status."""
    version = data.get("schema_version")
    if version in RECOVERY_LEGACY_SCHEMA_VERSIONS:
        return "legacy_unverified"

    integrity = data.get("integrity")
    if integrity is None:
        raise RecoveryFormatError(
            "recovery artifact is missing required integrity evidence"
        )
    if not isinstance(integrity, dict):
        raise RecoveryFormatError("recovery integrity must be an object")
    if integrity.get("algorithm") != RECOVERY_INTEGRITY_ALGORITHM:
        raise RecoveryFormatError(
            f"unsupported recovery integrity algorithm: {integrity.get('algorithm')!r}"
        )
    if integrity.get("canonicalization") != RECOVERY_INTEGRITY_CANONICALIZATION:
        raise RecoveryFormatError(
            "unsupported recovery integrity canonicalization: "
            f"{integrity.get('canonicalization')!r}"
        )
    expected = integrity.get("sha256")
    if (
        not isinstance(expected, str)
        or len(expected) != 64
        or any(ch not in "0123456789abcdef" for ch in expected.lower())
    ):
        raise RecoveryFormatError("recovery integrity SHA-256 is malformed")
    actual = _recovery_integrity_sha256(data)
    if actual != expected.lower():
        raise RecoveryFormatError(
            "recovery artifact integrity check failed; content does not match SHA-256 evidence"
        )
    return "verified"


def _normalized_source_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def project_identity(path: str | Path | None, *, unsaved_id: str) -> str:
    if path is None:
        return f"session-{unsaved_id}"
    normalized = os.path.normcase(str(_normalized_source_path(path)))
    return "file-" + sha256(normalized.encode("utf-8")).hexdigest()[:24]


def source_fingerprint(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {
            "path": None,
            "exists": False,
            "size": None,
            "mtime_ns": None,
            "sha256": None,
        }
    source = _normalized_source_path(path)
    try:
        stat, digest = stable_file_sha256(
            source,
            max_bytes=PROJECT_FILE_MAX_BYTES,
        )
    except FileNotFoundError:
        return {
            "path": str(source),
            "exists": False,
            "size": None,
            "mtime_ns": None,
            "sha256": None,
        }
    return {
        "path": str(source),
        "exists": True,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": digest,
    }


def _session_filename_token(session_id: str) -> str:
    """Return a filesystem-safe stable token for one autosave session."""
    return sha256(session_id.encode("utf-8")).hexdigest()


def _artifact_filename(
    project_identity_value: str,
    session_id: str,
    recovery_id: str,
) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    session_token = _session_filename_token(session_id)
    return (
        f"{project_identity_value}-session-{session_token}-"
        f"{stamp}-{recovery_id[:8]}.recovery.json"
    )


def _validate_recovery_payload(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise RecoveryFormatError("recovery artifact must contain a JSON object")
    if data.get("schema") != RECOVERY_SCHEMA:
        raise RecoveryFormatError(f"recovery schema must be {RECOVERY_SCHEMA!r}")
    version = data.get("schema_version")
    supported_versions = RECOVERY_LEGACY_SCHEMA_VERSIONS | {RECOVERY_SCHEMA_VERSION}
    if not isinstance(version, int) or isinstance(version, bool) or version not in supported_versions:
        supported = ", ".join(str(item) for item in sorted(supported_versions))
        raise RecoveryFormatError(
            f"unsupported recovery schema version {version!r}; "
            f"supported versions are {supported}"
        )
    identity = data.get("project_identity")
    if not isinstance(identity, str) or not identity:
        raise RecoveryFormatError("project_identity must be a non-empty string")
    _parse_utc(data.get("saved_at_utc"))
    source = data.get("source")
    if not isinstance(source, dict):
        raise RecoveryFormatError("source must be an object")
    source_path = source.get("path")
    if source_path is not None and not isinstance(source_path, str):
        raise RecoveryFormatError("source.path must be a string or null")
    snapshot = data.get("snapshot")
    if not isinstance(snapshot, dict):
        raise RecoveryFormatError("snapshot must be an object")
    recovery_integrity_status(data)
    return data


def _recovery_file_size_message(size_bytes: int) -> str:
    return (
        f"recovery artifact size {size_bytes} bytes exceeds maximum supported size "
        f"of {RECOVERY_FILE_MAX_BYTES} bytes"
    )


def _validate_recovery_file_size(size_bytes: int) -> None:
    if size_bytes > RECOVERY_FILE_MAX_BYTES:
        raise RecoveryFormatError(_recovery_file_size_message(size_bytes))


def _read_recovery_json(path: str | Path) -> Any:
    """Read one bounded, revision-stable recovery artifact as strict JSON."""
    source = Path(path)
    try:
        return load_strict_json(
            source,
            max_bytes=RECOVERY_FILE_MAX_BYTES,
        )
    except json.JSONDecodeError as exc:
        raise RecoveryFormatError(
            f"invalid recovery JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc
    except StrictJSONSizeError as exc:
        raise RecoveryFormatError(
            _recovery_file_size_message(exc.observed_size)
        ) from exc
    except StrictJSONError as exc:
        raise RecoveryFormatError(f"invalid strict recovery JSON: {exc}") from exc
    except OSError as exc:
        raise RecoveryFormatError(
            f"recovery artifact could not be read: {source}: {exc}"
        ) from exc


def load_recovery_artifact(path: str | Path) -> dict[str, Any]:
    return _validate_recovery_payload(_read_recovery_json(path))


def restore_recovery_artifact(path: str | Path) -> RecoveredProjectState:
    artifact_path = Path(path)
    recovery = load_recovery_artifact(artifact_path)
    snapshot = recovery["snapshot"]
    project_data = snapshot.get("project")
    if not isinstance(project_data, dict):
        raise RecoveryFormatError("snapshot.project must be an object")
    try:
        project = project_from_dict(project_data)
    except (TypeError, ValueError) as exc:
        raise RecoveryFormatError(f"recovered project is invalid: {exc}") from exc

    ui_state = snapshot.get("ui_state", {})
    if not isinstance(ui_state, dict):
        raise RecoveryFormatError("snapshot.ui_state must be an object")

    source_path_text = recovery["source"].get("path")
    source_path = Path(source_path_text) if source_path_text is not None else None
    return RecoveredProjectState(
        project=project,
        ui_state=dict(ui_state),
        source_path=source_path,
        saved_at_utc=recovery["saved_at_utc"],
        project_identity=recovery["project_identity"],
        artifact_path=artifact_path,
        integrity_status=recovery_integrity_status(recovery),
    )


def discard_recovery_artifact(
    path: str | Path,
    *,
    recovery_dir: str | Path | None = None,
) -> None:
    resolved_artifact, _directory = _resolve_recovery_artifact_path(
        path, recovery_dir=recovery_dir
    )
    load_recovery_artifact(resolved_artifact)
    resolved_artifact.unlink()


def _resolve_recovery_artifact_path(
    path: str | Path,
    *,
    recovery_dir: str | Path | None = None,
) -> tuple[Path, Path]:
    artifact_path = Path(path)
    directory = Path(recovery_dir) if recovery_dir is not None else default_recovery_dir()
    try:
        resolved_artifact = artifact_path.resolve(strict=True)
        resolved_directory = directory.resolve(strict=True)
        resolved_artifact.relative_to(resolved_directory)
    except (FileNotFoundError, ValueError) as exc:
        raise RecoveryFormatError(
            "recovery artifact must be an existing file inside the recovery directory"
        ) from exc
    if not resolved_artifact.name.endswith(".recovery.json"):
        raise RecoveryFormatError("refusing to operate on a non-recovery file")
    return resolved_artifact, resolved_directory


def _quarantine_pair_revision(
    manifest_path: Path,
    artifact_path: Path,
    *,
    expected_quarantined_name: str | None = None,
) -> _VerifiedQuarantinePairRevision | None:
    """Return the exact verified revision of one rotatable quarantine pair."""
    try:
        manifest_stat_before, manifest_sha_before = stable_file_sha256(
            manifest_path,
            max_bytes=RECOVERY_QUARANTINE_MANIFEST_MAX_BYTES,
        )
        manifest = load_strict_json(
            manifest_path,
            max_bytes=RECOVERY_QUARANTINE_MANIFEST_MAX_BYTES,
        )
    except (OSError, ValueError):
        return None
    if not isinstance(manifest, dict):
        return None

    required_fields = {
        "schema",
        "schema_version",
        "quarantined_at_utc",
        "original_name",
        "quarantined_name",
        "reason",
        "size_bytes",
        "sha256",
    }
    if not required_fields.issubset(manifest):
        return None

    version = manifest["schema_version"]
    original_name = manifest["original_name"]
    quarantined_name = manifest["quarantined_name"]
    reason = manifest["reason"]
    quarantined_at_utc = manifest["quarantined_at_utc"]
    size_bytes = manifest["size_bytes"]
    digest = manifest["sha256"]
    expected_name = (
        artifact_path.name
        if expected_quarantined_name is None
        else expected_quarantined_name
    )
    if (
        manifest["schema"] != RECOVERY_QUARANTINE_SCHEMA
        or type(version) is not int
        or version != RECOVERY_QUARANTINE_SCHEMA_VERSION
        or not isinstance(original_name, str)
        or not original_name
        or Path(original_name).name != original_name
        or not isinstance(quarantined_name, str)
        or quarantined_name != expected_name
        or not isinstance(reason, str)
        or not reason.strip()
        or not isinstance(quarantined_at_utc, str)
        or not quarantined_at_utc
        or isinstance(size_bytes, bool)
        or not isinstance(size_bytes, int)
        or size_bytes < 0
        or not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        return None
    try:
        _parse_utc(quarantined_at_utc)
        artifact_stat, actual_sha256 = stable_file_sha256(
            artifact_path,
            max_bytes=RECOVERY_FILE_MAX_BYTES,
        )
        manifest_stat_after, manifest_sha_after = stable_file_sha256(
            manifest_path,
            max_bytes=RECOVERY_QUARANTINE_MANIFEST_MAX_BYTES,
        )
    except (OSError, ValueError):
        return None

    if (
        artifact_stat.st_size != size_bytes
        or actual_sha256 != digest
        or manifest_stat_before.st_size != manifest_stat_after.st_size
        or manifest_sha_before != manifest_sha_after
    ):
        return None
    return _VerifiedQuarantinePairRevision(
        manifest_sha256=manifest_sha_after,
        artifact_sha256=actual_sha256,
        artifact_size=artifact_stat.st_size,
    )


def _restore_staged_quarantine_path(staged: Path, original: Path) -> None:
    """Restore staged evidence without ever overwriting a repopulated pathname."""
    if not staged.exists():
        return
    try:
        os.link(staged, original)
    except FileExistsError:
        return
    except OSError:
        return
    try:
        staged.unlink()
    except OSError:
        # Both hard links preserve the same bytes; leaving the private staging
        # link behind is safer than risking evidence loss during cleanup.
        pass


def _prune_verified_quarantine_pair(
    directory: Path,
    manifest_path: Path,
    artifact_path: Path,
    expected_revision: _VerifiedQuarantinePairRevision,
) -> None:
    """Stage, re-verify, then delete exactly the revision selected for retention."""
    try:
        stage_dir = Path(
            tempfile.mkdtemp(prefix=".retention-prune-", dir=directory)
        )
    except OSError:
        return
    staged_artifact = stage_dir / "artifact.quarantined"
    staged_manifest = stage_dir / "manifest.json"
    artifact_moved = False
    manifest_moved = False
    try:
        os.replace(artifact_path, staged_artifact)
        artifact_moved = True
        os.replace(manifest_path, staged_manifest)
        manifest_moved = True
    except OSError:
        if manifest_moved:
            _restore_staged_quarantine_path(staged_manifest, manifest_path)
        if artifact_moved:
            _restore_staged_quarantine_path(staged_artifact, artifact_path)
        try:
            stage_dir.rmdir()
        except OSError:
            pass
        return

    staged_revision = _quarantine_pair_revision(
        staged_manifest,
        staged_artifact,
        expected_quarantined_name=artifact_path.name,
    )
    if staged_revision != expected_revision:
        # The pathnames changed after discovery. Restore without clobbering any
        # concurrent replacements; if restoration conflicts, the staged bytes
        # remain in the private directory as forensic evidence.
        _restore_staged_quarantine_path(staged_manifest, manifest_path)
        _restore_staged_quarantine_path(staged_artifact, artifact_path)
        try:
            stage_dir.rmdir()
        except OSError:
            pass
        return

    # The exact content revision selected and validated during discovery is now
    # isolated under private staging names. Deleting these names cannot remove a
    # later replacement published at either original quarantine pathname.
    try:
        staged_artifact.unlink()
        staged_manifest.unlink()
        stage_dir.rmdir()
    except OSError:
        # Retention cleanup is best-effort. Any undeleted staged path remains
        # isolated instead of falling back to pathname deletion of live evidence.
        return


def _rotate_quarantine(directory: Path, history_limit: int) -> None:
    manifests: list[
        tuple[
            int,
            str,
            Path,
            Path,
            _VerifiedQuarantinePairRevision,
        ]
    ] = []
    for manifest in directory.glob("*.quarantined.manifest.json"):
        artifact = manifest.with_name(
            manifest.name[: -len(".manifest.json")]
        )
        revision = _quarantine_pair_revision(manifest, artifact)
        if revision is None:
            # Retention must never destroy forensic evidence whose manifest or
            # suspect bytes are no longer trustworthy. Preserve the pair for
            # explicit operator review instead of counting it as rotatable history.
            continue
        try:
            modified_ns = manifest.stat().st_mtime_ns
        except OSError:
            continue
        manifests.append((modified_ns, manifest.name, manifest, artifact, revision))

    for _modified, _name, stale_manifest, stale_artifact, revision in sorted(
        manifests, reverse=True
    )[history_limit:]:
        _prune_verified_quarantine_pair(
            directory,
            stale_manifest,
            stale_artifact,
            revision,
        )


def quarantine_recovery_artifact(
    path: str | Path,
    *,
    recovery_dir: str | Path | None = None,
    reason: str,
    history_limit: int = DEFAULT_RECOVERY_QUARANTINE_LIMIT,
) -> QuarantinedRecoveryArtifact:
    """Move an invalid recovery aside without altering its suspect bytes."""
    if isinstance(history_limit, bool) or not isinstance(history_limit, int) or history_limit < 1:
        raise ValueError("history_limit must be at least 1")
    reason_text = str(reason).strip()
    if not reason_text:
        raise ValueError("quarantine reason must be non-empty")

    resolved_artifact, resolved_directory = _resolve_recovery_artifact_path(
        path, recovery_dir=recovery_dir
    )
    try:
        load_recovery_artifact(resolved_artifact)
    except (OSError, RecoveryFormatError, TypeError, ValueError):
        pass
    else:
        raise RecoveryFormatError(
            "refusing to quarantine a valid recovery artifact; use discard instead"
        )

    quarantined_at_utc = _utc_now_text()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    token = uuid.uuid4().hex[:8]
    quarantine_dir = _ensure_recovery_dir(resolved_directory / "quarantine")
    quarantined_name = f"{resolved_artifact.name}.{stamp}-{token}.quarantined"
    destination = quarantine_dir / quarantined_name
    manifest_path = quarantine_dir / f"{quarantined_name}.manifest.json"

    os.replace(resolved_artifact, destination)
    try:
        stat_result, artifact_sha256 = stable_file_sha256(
            destination,
            max_bytes=RECOVERY_FILE_MAX_BYTES,
        )
        if stat_result.st_size < 0:
            raise OSError("invalid recovery artifact byte size")
        manifest = {
            "schema": RECOVERY_QUARANTINE_SCHEMA,
            "schema_version": RECOVERY_QUARANTINE_SCHEMA_VERSION,
            "quarantined_at_utc": quarantined_at_utc,
            "original_name": resolved_artifact.name,
            "quarantined_name": quarantined_name,
            "reason": reason_text,
            "size_bytes": stat_result.st_size,
            "sha256": artifact_sha256,
        }
        manifest_text = json.dumps(
            manifest, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False
        ) + "\n"
        atomic_write_text(manifest_path, manifest_text)
    except BaseException as finalize_error:
        # Atomic persistence can report a failure after replacing the manifest.
        # In that committed state the manifest path already names this quarantine
        # artifact; rolling the artifact back would create a stale forensic record.
        if getattr(finalize_error, "committed", False):
            raise
        try:
            # Restore through a no-clobber hard link instead of check-then-replace.
            # link(2) fails atomically if any directory entry has repopulated the
            # recovery path, so rollback can never overwrite newer recovery data.
            os.link(destination, resolved_artifact)
        except FileExistsError:
            raise OSError(
                "quarantine finalization failed after the recovery path was "
                "repopulated; preserving the quarantined artifact instead of "
                "overwriting newer recovery data"
            ) from finalize_error
        except OSError as rollback_error:
            raise OSError(
                "quarantine finalization failed and safe rollback could not restore "
                f"{resolved_artifact}: {rollback_error}; preserving quarantined bytes"
            ) from rollback_error
        try:
            destination.unlink()
        except OSError as cleanup_error:
            raise OSError(
                "quarantine finalization failed after safe rollback restored the "
                f"original path, but quarantine cleanup failed: {cleanup_error}"
            ) from cleanup_error
        raise

    _rotate_quarantine(quarantine_dir, history_limit)
    return QuarantinedRecoveryArtifact(
        path=destination,
        manifest_path=manifest_path,
        original_name=resolved_artifact.name,
        quarantined_at_utc=quarantined_at_utc,
        reason=reason_text,
        sha256=artifact_sha256,
    )

def _compare_source(recovery: dict[str, Any]) -> tuple[str, bool, Path | None]:
    source = recovery["source"]
    source_path_text = source.get("path")
    if source_path_text is None:
        return "unsaved", False, None
    source_path = Path(source_path_text)

    try:
        current = source_fingerprint(source_path)
    except StableFileSizeError:
        return "source_oversized", False, source_path
    except OSError:
        return "source_unavailable", False, source_path

    if current.get("exists") is not True:
        return "source_missing", False, source_path

    if (
        source.get("exists") is True
        and source.get("sha256")
        and current.get("sha256") == source.get("sha256")
    ):
        return "source_unchanged", False, source_path

    saved_at = _parse_utc(recovery["saved_at_utc"])
    current_mtime_ns = current.get("mtime_ns")
    current_mtime = (
        datetime.fromtimestamp(current_mtime_ns / 1_000_000_000, tz=timezone.utc)
        if isinstance(current_mtime_ns, int)
        else None
    )
    is_newer = current_mtime is not None and current_mtime > saved_at
    return ("source_newer" if is_newer else "source_changed"), is_newer, source_path


def scan_recovery_artifacts(recovery_dir: str | Path | None = None) -> RecoveryScan:
    directory = Path(recovery_dir) if recovery_dir is not None else default_recovery_dir()
    if not directory.exists():
        return RecoveryScan(candidates=(), issues=())

    candidates: list[RecoveryCandidate] = []
    issues: list[RecoveryScanIssue] = []
    for path in sorted(directory.glob("*.recovery.json")):
        try:
            recovery = load_recovery_artifact(path)
            relation, is_newer, source_path = _compare_source(recovery)
            project = recovery["snapshot"].get("project", {})
            project_block = project.get("project", {}) if isinstance(project, dict) else {}
            project_name = (
                project_block.get("name", "Untitled Project")
                if isinstance(project_block, dict)
                else "Untitled Project"
            )
            if not isinstance(project_name, str) or not project_name:
                project_name = "Untitled Project"
            candidates.append(
                RecoveryCandidate(
                    path=path,
                    project_identity=recovery["project_identity"],
                    saved_at_utc=recovery["saved_at_utc"],
                    project_name=project_name,
                    source_path=source_path,
                    source_relation=relation,
                    source_is_newer=is_newer,
                    integrity_status=recovery_integrity_status(recovery),
                )
            )
        except (OSError, RecoveryFormatError, TypeError, ValueError) as exc:
            issues.append(RecoveryScanIssue(path=path, error=str(exc)))

    candidates.sort(key=lambda item: item.saved_at_utc, reverse=True)
    return RecoveryScan(candidates=tuple(candidates), issues=tuple(issues))


class AutosaveManager:
    """Serialize recovery snapshots away from the Tk/UI thread.

    Explicit project files are never written by this class. Recovery artifacts are
    separate JSON envelopes with bounded per-project, per-session history so one
    application session cannot prune another session's unsaved recovery evidence.
    A completed write may rotate history only after its project epoch is revalidated,
    so an invalidated in-flight request cannot evict an accepted recovery generation.
    """

    def __init__(
        self,
        recovery_dir: str | Path | None = None,
        *,
        history_limit: int = DEFAULT_RECOVERY_HISTORY_LIMIT,
        session_id: str | None = None,
    ) -> None:
        if history_limit < 1:
            raise ValueError("history_limit must be at least 1")
        self.recovery_dir = (
            Path(recovery_dir) if recovery_dir is not None else default_recovery_dir()
        )
        self.history_limit = history_limit
        self.session_id = session_id or uuid.uuid4().hex
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="cleanroomx-autosave",
        )
        self._lock = threading.RLock()
        self._current_identity = project_identity(None, unsaved_id=self.session_id)
        self._epochs: dict[str, int] = {self._current_identity: 0}
        self._last_saved_digest: dict[str, str] = {}
        self._artifacts_by_identity: dict[str, set[Path]] = {}
        self._active_request: _AutosaveRequest | None = None
        self._pending_request: _AutosaveRequest | None = None
        self._future: Future[Path] | None = None
        self._status = AutosaveStatus(
            state="idle",
            message="Autosave ready",
            updated_at_utc=_utc_now_text(),
        )
        self._sequence = 0
        self._closed = False

    @property
    def current_identity(self) -> str:
        with self._lock:
            return self._current_identity

    def begin_project(self, source_path: str | Path | None) -> str:
        with self._lock:
            if source_path is None:
                identity = project_identity(None, unsaved_id=uuid.uuid4().hex)
            else:
                identity = project_identity(source_path, unsaved_id=self.session_id)
            self._current_identity = identity
            self._epochs.setdefault(identity, 0)
            self._last_saved_digest.pop(identity, None)
            self._set_status_locked("idle", "Autosave ready")
            return identity

    def status(self) -> AutosaveStatus:
        with self._lock:
            return self._status

    def request_autosave(
        self,
        snapshot: dict[str, Any],
        *,
        source_path: str | Path | None,
    ) -> bool:
        snapshot_text = _canonical_json(snapshot)
        digest = sha256(snapshot_text.encode("utf-8")).hexdigest()
        normalized_source = (
            None if source_path is None else _normalized_source_path(source_path)
        )

        with self._lock:
            if self._closed:
                return False
            identity = self._current_identity
            epoch = self._epochs.setdefault(identity, 0)
            if self._last_saved_digest.get(identity) == digest:
                return False
            active_digest = (
                self._active_request.digest if self._active_request is not None else None
            )
            pending_digest = (
                self._pending_request.digest if self._pending_request is not None else None
            )
            if digest in {active_digest, pending_digest}:
                return False

            request = _AutosaveRequest(
                project_identity=identity,
                epoch=epoch,
                source_path=normalized_source,
                snapshot_text=snapshot_text,
                digest=digest,
            )
            # Future.done() becomes true before completion callbacks are guaranteed
            # to finish. Keep coordinator ownership until _on_write_done() releases it.
            if self._future is not None:
                self._pending_request = request
                self._set_status_locked("saving", "Autosave queued")
                return True

            self._submit_locked(request)
            return True

    def _submit_locked(self, request: _AutosaveRequest) -> None:
        self._active_request = request
        self._set_status_locked("saving", "Autosave saving")
        future = self._executor.submit(self._write_recovery, request)
        self._future = future
        future.add_done_callback(
            lambda completed, request=request: self._on_write_done(request, completed)
        )

    def _write_recovery(self, request: _AutosaveRequest) -> Path:
        snapshot = strict_json_loads(request.snapshot_text)
        recovery_id = uuid.uuid4().hex
        payload = {
            "schema": RECOVERY_SCHEMA,
            "schema_version": RECOVERY_SCHEMA_VERSION,
            "application_version": __version__,
            "session_id": self.session_id,
            "recovery_id": recovery_id,
            "project_identity": request.project_identity,
            "saved_at_utc": _utc_now_text(),
            "source": source_fingerprint(request.source_path),
            "snapshot": snapshot,
        }
        payload["integrity"] = _recovery_integrity_block(payload)
        _validate_recovery_payload(payload)
        directory = _ensure_recovery_dir(self.recovery_dir)
        destination = directory / _artifact_filename(
            request.project_identity,
            self.session_id,
            recovery_id,
        )
        text = json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        ) + "\n"
        _validate_recovery_file_size(len(text.encode("utf-8")))
        try:
            atomic_write_text(destination, text)
            persisted = load_recovery_artifact(destination)
            if (
                persisted.get("recovery_id") != recovery_id
                or persisted.get("project_identity") != request.project_identity
                or recovery_integrity_status(persisted) != "verified"
            ):
                raise RecoveryFormatError(
                    "persisted recovery artifact identity or integrity does not match the write request"
                )
        except (OSError, RecoveryFormatError):
            try:
                destination.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        return destination

    def _rotate_history(self, identity: str) -> None:
        """Prune only recovery generations owned by this manager's session.

        Project identity alone is not a safe ownership boundary because multiple
        CleanroomX processes can edit the same project concurrently. The filename
        token narrows discovery to this session, then the recovery envelope is
        validated before deletion so malformed or foreign evidence is preserved.
        """
        session_token = _session_filename_token(self.session_id)
        owned: list[tuple[str, Path]] = []
        pattern = f"{identity}-session-{session_token}-*.recovery.json"
        for path in self.recovery_dir.glob(pattern):
            try:
                recovery = load_recovery_artifact(path)
            except (OSError, RecoveryFormatError, TypeError, ValueError):
                continue
            if (
                recovery.get("project_identity") != identity
                or recovery.get("session_id") != self.session_id
            ):
                continue
            owned.append((recovery["saved_at_utc"], path))

        owned.sort(key=lambda item: (item[0], item[1].name), reverse=True)
        for _saved_at, stale in owned[self.history_limit :]:
            stale.unlink(missing_ok=True)

    def _on_write_done(
        self,
        request: _AutosaveRequest,
        future: Future[Path],
    ) -> None:
        try:
            artifact = future.result()
            failure: Exception | None = None
        except Exception as exc:  # background-worker error boundary
            artifact = None
            failure = exc

        with self._lock:
            # Only the coordinator-owned Future/request pair may finalize shared
            # state. This closes the Future.done()-before-callback race.
            if self._future is not future or self._active_request is not request:
                return

            current_epoch = self._epochs.get(request.project_identity, 0)
            stale = request.epoch != current_epoch
            stale_cleanup_failure: OSError | None = None
            if stale and artifact is not None:
                try:
                    artifact.unlink(missing_ok=True)
                except OSError as exc:
                    stale_cleanup_failure = exc
                    self._artifacts_by_identity.setdefault(
                        request.project_identity, set()
                    ).add(artifact)

            if stale_cleanup_failure is not None:
                self._set_status_locked(
                    "failed",
                    f"Autosave invalidated recovery cleanup failed: {stale_cleanup_failure}",
                    artifact_path=artifact,
                )
            elif not stale:
                if failure is None:
                    assert artifact is not None
                    self._last_saved_digest[request.project_identity] = request.digest
                    self._artifacts_by_identity.setdefault(
                        request.project_identity, set()
                    ).add(artifact)
                    try:
                        # Retention is part of accepting this autosave generation.
                        # Holding the lifecycle lock makes the epoch check and
                        # history mutation atomic with respect to explicit save,
                        # discard, and project-transition invalidation.
                        self._rotate_history(request.project_identity)
                    except OSError as exc:
                        self._set_status_locked(
                            "failed",
                            f"Autosave recovery saved but history cleanup failed: {exc}",
                            artifact_path=artifact,
                        )
                    else:
                        self._set_status_locked(
                            "saved",
                            "Autosave saved",
                            artifact_path=artifact,
                        )
                else:
                    self._set_status_locked(
                        "failed",
                        f"Autosave failed: {failure}",
                    )

            self._active_request = None
            self._future = None
            pending = self._pending_request
            self._pending_request = None
            if pending is not None:
                pending_epoch = self._epochs.get(pending.project_identity, 0)
                if pending.epoch == pending_epoch and not self._closed:
                    self._submit_locked(pending)

    def _set_status_locked(
        self,
        state: str,
        message: str,
        *,
        artifact_path: Path | None = None,
    ) -> None:
        self._sequence += 1
        self._status = AutosaveStatus(
            state=state,
            message=message,
            artifact_path=artifact_path,
            updated_at_utc=_utc_now_text(),
            sequence=self._sequence,
        )

    def _clear_identity_locked(
        self,
        identity: str,
    ) -> tuple[tuple[Path, OSError], ...]:
        self._epochs[identity] = self._epochs.get(identity, 0) + 1
        self._last_saved_digest.pop(identity, None)
        if (
            self._pending_request is not None
            and self._pending_request.project_identity == identity
        ):
            self._pending_request = None

        failures: list[tuple[Path, OSError]] = []
        remaining: set[Path] = set()
        for artifact in self._artifacts_by_identity.get(identity, set()):
            try:
                artifact.unlink(missing_ok=True)
            except OSError as exc:
                failures.append((artifact, exc))
                remaining.add(artifact)

        if remaining:
            # Retain failed paths so a later save/discard can retry cleanup
            # instead of silently orphaning a recovery artifact.
            self._artifacts_by_identity[identity] = remaining
        else:
            self._artifacts_by_identity.pop(identity, None)
        return tuple(failures)

    def _set_cleanup_failure_locked(
        self,
        context: str,
        failures: tuple[tuple[Path, OSError], ...] | list[tuple[Path, OSError]],
    ) -> None:
        artifact, exc = failures[0]
        count = len(failures)
        suffix = "" if count == 1 else f" ({count} artifacts could not be removed)"
        self._set_status_locked(
            "failed",
            f"{context}{suffix}: {artifact}: {exc}",
            artifact_path=artifact,
        )

    def discard_current_recoveries(self) -> AutosaveStatus:
        with self._lock:
            failures = self._clear_identity_locked(self._current_identity)
            if failures:
                self._set_cleanup_failure_locked(
                    "Autosave recovery discard incomplete",
                    failures,
                )
            else:
                self._set_status_locked("idle", "Autosave recovery discarded")
            return self._status

    def notify_explicit_save(self, source_path: str | Path) -> AutosaveStatus:
        with self._lock:
            previous = self._current_identity
            new_identity = project_identity(source_path, unsaved_id=self.session_id)
            failures = list(self._clear_identity_locked(previous))
            if new_identity != previous:
                failures.extend(self._clear_identity_locked(new_identity))
            self._current_identity = new_identity
            self._epochs.setdefault(new_identity, 0)
            if failures:
                self._set_cleanup_failure_locked(
                    "Project saved, but autosave recovery cleanup is incomplete",
                    failures,
                )
            else:
                self._set_status_locked("idle", "Autosave clean after explicit save")
            return self._status

    def wait_for_idle(self, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                idle = (
                    self._future is None
                    and self._active_request is None
                    and self._pending_request is None
                )
                failure = self._status if self._status.state == "failed" else None
            if idle:
                if failure is not None:
                    raise RuntimeError(failure.message)
                return
            if time.monotonic() >= deadline:
                raise TimeoutError("autosave worker did not become idle before timeout")
            time.sleep(0.01)

    def shutdown(self, *, wait: bool = False) -> None:
        with self._lock:
            self._closed = True
            self._pending_request = None
        self._executor.shutdown(wait=wait, cancel_futures=False)
