"""Live, read-only synchronization of OpenFOAM evidence into ProofGraph."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import stat
import sys
import time
from typing import Callable, Iterable

_MAX_WATCHED_ENTRIES = 100_000


def _record(path: Path) -> tuple[object, ...]:
    """Return a no-follow metadata record, including a stable missing marker."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return (str(path), "missing")
    return (
        str(path),
        stat.S_IFMT(info.st_mode),
        info.st_dev,
        info.st_ino,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _tree_records(root: Path, records: list[tuple[object, ...]]) -> None:
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"OpenFOAM sync root must be a real directory: {root}")
    pending = [root]
    while pending:
        directory = pending.pop()
        records.append(_record(directory))
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name)
            for entry in entries:
                path = Path(entry.path)
                info = entry.stat(follow_symlinks=False)
                records.append(_record(path))
                if stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode):
                    pending.append(path)
                if len(records) > _MAX_WATCHED_ENTRIES:
                    raise ValueError(
                        f"OpenFOAM sync tree exceeds {_MAX_WATCHED_ENTRIES} watched entries"
                    )
        except OSError as exc:
            raise ValueError(f"Could not inspect OpenFOAM sync path: {directory}: {exc}") from exc


def _study_references(study_path: Path) -> list[Path]:
    """Read referenced VTK/log paths for change detection; validation stays in ProofGraph."""
    paths = [study_path]
    try:
        document = json.loads(study_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return paths
    runs = document.get("runs") if type(document) is dict else None
    if type(runs) is not list:
        return paths
    for run in runs:
        if type(run) is not dict:
            continue
        for name in ("vtk_file", "solver_log"):
            value = run.get(name)
            if type(value) is str and value:
                paths.append(study_path.parent / value)
    return paths


def watch_signature(
    family: str | Path,
    grid_studies: Iterable[str | Path] = (),
) -> str:
    """Hash file metadata for OpenFOAM outputs and optional VTK study inputs.

    Directory traversal never follows symlinks. Content integrity is checked by
    the existing ProofGraph/grid verification pipeline when a change is read.
    """
    root = Path(family).expanduser()
    if root.is_symlink():
        raise ValueError("OpenFOAM sync root must not be a symlink")
    root = root.resolve(strict=True)
    records: list[tuple[object, ...]] = []
    _tree_records(root, records)
    exact_paths: set[Path] = set()
    for value in grid_studies:
        study_path = Path(value).expanduser().resolve(strict=False)
        for path in _study_references(study_path):
            exact_paths.add(path.resolve(strict=False))
    for path in sorted(exact_paths, key=lambda item: str(item)):
        records.append(_record(path))
    if len(records) > _MAX_WATCHED_ENTRIES:
        raise ValueError(
            f"OpenFOAM sync inputs exceed {_MAX_WATCHED_ENTRIES} watched entries"
        )
    encoded = json.dumps(records, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _payload(graph_factory: Callable[..., object] | None,
             family: Path,
             grid_studies: tuple[str, ...]) -> str:
    if graph_factory is None:
        from .proofgraph_cfd import proofgraph_from_cfd_grid_family

        graph_factory = proofgraph_from_cfd_grid_family
    graph = graph_factory(family, grid_study_specs=grid_studies)
    document = graph.to_dict()
    return json.dumps(
        document,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    )


def _payload_digest(path: Path) -> str | None:
    if path.is_symlink():
        return None
    try:
        info = path.stat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode):
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sync_grid_proofgraph_once(
    family: str | Path,
    output: str | Path,
    *,
    grid_studies: Iterable[str | Path] = (),
    graph_factory: Callable[..., object] | None = None,
    publisher: Callable[..., bool] | None = None,
) -> dict[str, str]:
    """Refresh one canonical ProofGraph, refusing a source tree that changed mid-read."""
    root = Path(family).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("OpenFOAM sync root must be a directory")
    supplied_destination = Path(output).expanduser()
    if supplied_destination.is_symlink():
        raise ValueError("ProofGraph sync output must not be a symlink")
    if supplied_destination.absolute().is_relative_to(root):
        raise ValueError("ProofGraph sync output must be outside the OpenFOAM family")
    destination = supplied_destination.resolve(strict=False)
    if destination == root or destination.is_relative_to(root):
        raise ValueError("ProofGraph sync output must be outside the OpenFOAM family")
    study_paths = tuple(str(Path(item).expanduser().resolve(strict=False)) for item in grid_studies)
    before = watch_signature(root, study_paths)
    payload = _payload(graph_factory, root, study_paths)
    after = watch_signature(root, study_paths)
    if before != after:
        return {"status": "source_changed_during_sync"}
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    if _payload_digest(destination) == digest:
        return {"status": "unchanged", "sha256": digest}
    if publisher is None:
        from .cli_output import publish_cli_output

        publisher = publish_cli_output
    protected_inputs: list[Path] = [root]
    for study in study_paths:
        protected_inputs.extend(_study_references(Path(study)))
    if not publisher(
        "cleanroomx-cfd-pipeline grid-sync",
        destination,
        payload,
        protected_inputs=protected_inputs,
    ):
        raise OSError("ProofGraph sync output could not be published")
    return {"status": "synced", "sha256": digest, "output": str(destination)}


def run_grid_sync(
    family: str | Path,
    output: str | Path,
    *,
    grid_studies: Iterable[str | Path] = (),
    interval_seconds: float = 2.0,
    once: bool = False,
    graph_factory: Callable[..., object] | None = None,
    publisher: Callable[..., bool] | None = None,
) -> int:
    """Continuously refresh ProofGraph after OpenFOAM evidence changes."""
    if (type(interval_seconds) not in (int, float)
            or not math.isfinite(float(interval_seconds))
            or not 0.25 <= float(interval_seconds) <= 3600):
        raise ValueError("interval_seconds must be a finite number in [0.25, 3600]")
    studies = tuple(grid_studies)
    last_signature: str | None = None
    last_payload_digest: str | None = None
    last_error_signature: str | None = None
    while True:
        try:
            signature = watch_signature(family, studies)
            output_matches = (
                last_payload_digest is not None
                and _payload_digest(Path(output).expanduser()) == last_payload_digest
            )
            if signature != last_signature or (
                last_payload_digest is not None and not output_matches
            ):
                try:
                    result = sync_grid_proofgraph_once(
                        family, output, grid_studies=studies,
                        graph_factory=graph_factory, publisher=publisher,
                    )
                    if result["status"] == "source_changed_during_sync":
                        print(
                            "cleanroomx-cfd-pipeline grid-sync: evidence changed during read; retrying",
                            file=sys.stderr,
                        )
                        last_signature = None
                        if once:
                            return 2
                    else:
                        print(json.dumps(result, sort_keys=True))
                        last_signature = signature
                        last_payload_digest = result.get("sha256")
                        last_error_signature = None
                except (OSError, ValueError) as exc:
                    if signature != last_error_signature:
                        print(
                            f"cleanroomx-cfd-pipeline grid-sync: waiting for valid evidence: {exc}",
                            file=sys.stderr,
                        )
                    last_signature = signature
                    last_error_signature = signature
                    if once:
                        return 1
            if once:
                return 0
            time.sleep(float(interval_seconds))
        except KeyboardInterrupt:
            return 130
        except (OSError, ValueError) as exc:
            print(f"cleanroomx-cfd-pipeline grid-sync: {exc}", file=sys.stderr)
            if once:
                return 1
            time.sleep(float(interval_seconds))

