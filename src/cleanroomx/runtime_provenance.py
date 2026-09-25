from __future__ import annotations

import copy
from dataclasses import dataclass
import hashlib
import os
import platform
from pathlib import Path
import stat
import sys
from typing import Mapping


IMPLEMENTATION_REVISION_SCHEMA = "cleanroomx.implementation-revision"
EXECUTION_IMPLEMENTATION_SCHEMA = "cleanroomx.execution-implementation"
IMPLEMENTATION_SCHEMA_VERSION = 1
SOURCE_TREE_CANONICALIZATION = (
    "relative-posix-path+lf-normalized-python-source-sha256-v1"
)
_SOURCE_READ_ATTEMPTS = 3


class ImplementationProvenanceError(RuntimeError):
    """Raised when the installed CleanroomX source identity cannot be established."""


class ImplementationChangedError(RuntimeError):
    """Raised when CleanroomX source identity changes during one analysis run."""

    def __init__(self, evidence: dict) -> None:
        self.evidence = copy.deepcopy(evidence)
        changed = self.evidence.get("changed_source_files", [])
        detail = ", ".join(changed) if changed else "aggregate source-tree identity"
        super().__init__(
            "CleanroomX implementation changed during analysis execution; the result "
            "was discarded. Re-run after the installation/source tree is stable. "
            f"Changed evidence: {detail}"
        )


@dataclass(frozen=True)
class SourceFileRevision:
    path: str
    sha256: str
    canonical_size_bytes: int


@dataclass(frozen=True)
class RuntimeIdentity:
    python_implementation: str
    python_version: str
    python_cache_tag: str
    python_compiler: str
    platform_system: str
    platform_release: str
    platform_machine: str

    def to_dict(self) -> dict[str, str]:
        return {
            "python_implementation": self.python_implementation,
            "python_version": self.python_version,
            "python_cache_tag": self.python_cache_tag,
            "python_compiler": self.python_compiler,
            "platform_system": self.platform_system,
            "platform_release": self.platform_release,
            "platform_machine": self.platform_machine,
        }


@dataclass(frozen=True)
class ImplementationRevision:
    source_tree_sha256: str
    source_file_count: int
    source_files: tuple[SourceFileRevision, ...]
    runtime: RuntimeIdentity

    def to_dict(self) -> dict:
        return {
            "schema": IMPLEMENTATION_REVISION_SCHEMA,
            "schema_version": IMPLEMENTATION_SCHEMA_VERSION,
            "source_tree_canonicalization": SOURCE_TREE_CANONICALIZATION,
            "source_tree_sha256": self.source_tree_sha256,
            "source_file_count": self.source_file_count,
            "runtime": self.runtime.to_dict(),
        }


def _stat_signature(stat_result: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        int(stat_result.st_dev),
        int(stat_result.st_ino),
        int(stat_result.st_size),
        int(stat_result.st_mtime_ns),
        int(stat_result.st_ctime_ns),
    )


def _stable_read_source(path: Path) -> bytes:
    last_error: Exception | None = None
    for _attempt in range(_SOURCE_READ_ATTEMPTS):
        try:
            with path.open("rb") as handle:
                before = os.fstat(handle.fileno())
                payload = handle.read()
                after = os.fstat(handle.fileno())
            current = path.stat()
        except OSError as exc:
            last_error = exc
            continue

        signature = _stat_signature(after)
        if (
            _stat_signature(before) == signature
            and _stat_signature(current) == signature
            and len(payload) == after.st_size
        ):
            return payload
        last_error = ImplementationProvenanceError(
            f"source changed while fingerprinting: {path}"
        )

    if isinstance(last_error, OSError):
        raise ImplementationProvenanceError(
            f"cannot fingerprint CleanroomX source file: {path}: {last_error}"
        ) from last_error
    if last_error is not None:
        raise last_error
    raise ImplementationProvenanceError(
        f"cannot establish stable CleanroomX source identity: {path}"
    )


def _canonical_source_bytes(payload: bytes) -> bytes:
    return payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _runtime_identity() -> RuntimeIdentity:
    version = ".".join(str(value) for value in sys.version_info[:3])
    cache_tag = getattr(sys.implementation, "cache_tag", None) or ""
    return RuntimeIdentity(
        python_implementation=platform.python_implementation(),
        python_version=version,
        python_cache_tag=cache_tag,
        python_compiler=platform.python_compiler(),
        platform_system=platform.system(),
        platform_release=platform.release(),
        platform_machine=platform.machine(),
    )


def _python_source_paths(root: Path) -> tuple[Path, ...]:
    try:
        candidates = sorted(
            root.rglob("*.py"),
            key=lambda path: path.relative_to(root).as_posix(),
        )
    except OSError as exc:
        raise ImplementationProvenanceError(
            f"cannot enumerate CleanroomX Python sources under {root}: {exc}"
        ) from exc

    paths: list[Path] = []
    for path in candidates:
        try:
            mode = path.stat().st_mode
        except OSError as exc:
            raise ImplementationProvenanceError(
                f"cannot inspect CleanroomX source path: {path}: {exc}"
            ) from exc
        if not stat.S_ISREG(mode):
            raise ImplementationProvenanceError(
                f"CleanroomX Python source path is not a regular file: {path}"
            )
        paths.append(path)
    if not paths:
        raise ImplementationProvenanceError(
            f"CleanroomX source root contains no Python source files: {root}"
        )
    return tuple(paths)


def capture_implementation_revision(
    package_root: str | Path | None = None,
) -> ImplementationRevision:
    """Fingerprint CleanroomX Python source without installation-path dependence."""
    root = (
        Path(package_root).expanduser()
        if package_root is not None
        else Path(__file__).resolve().parent
    )
    try:
        root = root.resolve(strict=True)
    except OSError as exc:
        raise ImplementationProvenanceError(
            f"CleanroomX source root is unavailable: {root}: {exc}"
        ) from exc
    if not root.is_dir():
        raise ImplementationProvenanceError(
            f"CleanroomX source root is not a directory: {root}"
        )

    paths = _python_source_paths(root)
    records: list[SourceFileRevision] = []
    tree_digest = hashlib.sha256()
    for path in paths:
        relative = path.relative_to(root).as_posix()
        canonical = _canonical_source_bytes(_stable_read_source(path))
        digest = hashlib.sha256(canonical).hexdigest()
        record = SourceFileRevision(
            path=relative,
            sha256=digest,
            canonical_size_bytes=len(canonical),
        )
        records.append(record)
        tree_digest.update(relative.encode("utf-8"))
        tree_digest.update(b"\0")
        tree_digest.update(str(record.canonical_size_bytes).encode("ascii"))
        tree_digest.update(b"\0")
        tree_digest.update(digest.encode("ascii"))
        tree_digest.update(b"\n")

    final_paths = tuple(
        path.relative_to(root).as_posix() for path in _python_source_paths(root)
    )
    captured_paths = tuple(record.path for record in records)
    if final_paths != captured_paths:
        raise ImplementationProvenanceError(
            "CleanroomX Python source file set changed while fingerprinting"
        )

    return ImplementationRevision(
        source_tree_sha256=tree_digest.hexdigest(),
        source_file_count=len(records),
        source_files=tuple(records),
        runtime=_runtime_identity(),
    )


def _changed_source_files(
    before: ImplementationRevision,
    after: ImplementationRevision,
) -> list[str]:
    before_files = {
        item.path: (item.sha256, item.canonical_size_bytes)
        for item in before.source_files
    }
    after_files = {
        item.path: (item.sha256, item.canonical_size_bytes)
        for item in after.source_files
    }
    return sorted(
        path
        for path in set(before_files) | set(after_files)
        if before_files.get(path) != after_files.get(path)
    )


def compare_implementation_revisions(
    before: ImplementationRevision,
    after: ImplementationRevision,
    *,
    entrypoints: Mapping[str, str],
) -> dict:
    """Build deterministic before/after implementation evidence for one run."""
    normalized_entrypoints: dict[str, str] = {}
    for role, target in sorted(entrypoints.items()):
        if not isinstance(role, str) or not role:
            raise ValueError("implementation entrypoint roles must be non-empty strings")
        if not isinstance(target, str) or not target:
            raise ValueError("implementation entrypoints must be non-empty strings")
        normalized_entrypoints[role] = target

    changed_files = _changed_source_files(before, after)
    runtime_stable = before.runtime == after.runtime
    stable = (
        not changed_files
        and before.source_file_count == after.source_file_count
        and before.source_tree_sha256 == after.source_tree_sha256
        and runtime_stable
    )
    return {
        "schema": EXECUTION_IMPLEMENTATION_SCHEMA,
        "schema_version": IMPLEMENTATION_SCHEMA_VERSION,
        "source_tree_canonicalization": SOURCE_TREE_CANONICALIZATION,
        "source_tree_sha256_before": before.source_tree_sha256,
        "source_tree_sha256_after": after.source_tree_sha256,
        "source_file_count_before": before.source_file_count,
        "source_file_count_after": after.source_file_count,
        "runtime_stable": runtime_stable,
        "stable_during_run": stable,
        "changed_source_files": changed_files,
        "runtime": before.runtime.to_dict(),
        "entrypoints": normalized_entrypoints,
    }
