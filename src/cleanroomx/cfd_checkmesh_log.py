"""Conservative, read-only OpenFOAM Foundation checkMesh log screening.

A successful subprocess exit alone is not a passed mesh check: checkMesh
reports "Failed N mesh checks." in stdout. This is a bounded text and
cross-source-consistency check, not a replacement for OpenFOAM, formal
provenance, mesh-quality analysis or scientific qualification.
"""
from __future__ import annotations

from pathlib import Path
import re

from .cfd_grid_runner import _hash


MAX_LOG_BYTES = 16 * 1024 * 1024
_VERDICT = re.compile(r"(?m)^[ \t]*Mesh OK\.[ \t]*\r?$")
_FAILED = re.compile(r"(?im)^[ \t]*Failed[ \t]+([0-9]+)[ \t]+mesh checks?\.[ \t]*\r?$")
_END = re.compile(r"(?m)^[ \t]*End[ \t]*\r?$")
_ERROR = re.compile(r"(?im)(?:FOAM[ \t]+FATAL[ \t]+ERROR|^\s*\*{3}|^\s*error\s*:)")
_STATS = {
    "points": re.compile(r"(?m)^[ \t]*points[ \t]*:[ \t]*([0-9]+)[ \t]*\r?$"),
    "faces": re.compile(r"(?m)^[ \t]*faces[ \t]*:[ \t]*([0-9]+)[ \t]*\r?$"),
    "internal_faces": re.compile(r"(?m)^[ \t]*internal[ \t]+faces[ \t]*:[ \t]*([0-9]+)[ \t]*\r?$"),
    "cells": re.compile(r"(?m)^[ \t]*cells[ \t]*:[ \t]*([0-9]+)[ \t]*\r?$"),
}


def screen_checkmesh_log(
    log: str | Path, *,
    expected_cells: int,
    expected_points: int,
    expected_faces: int,
    expected_internal_faces: int,
) -> dict[str, object]:
    """Require explicit clean checkMesh verdict and matching printed counts.

    A passed screen only reports agreement of a local log with its matching
    local polyMesh. A self-forged log and source can still agree, and an
    ordinary checkMesh run does not enforce project-specific quality limits.
    """
    expected = {
        "cells": expected_cells, "points": expected_points,
        "faces": expected_faces, "internal_faces": expected_internal_faces,
    }
    if any(type(value) is not int or value < 0 for value in expected.values()):
        raise ValueError("Invalid expected checkMesh statistics")
    if not expected_cells or not expected_points or not expected_faces:
        raise ValueError("Empty mesh cannot have a passed checkMesh screen")
    path = Path(log)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Missing or unsafe checkMesh log")
    if path.stat().st_nlink != 1:
        raise ValueError("Hardlinked checkMesh log is not independent evidence")
    if path.stat().st_size > MAX_LOG_BYTES:
        raise ValueError("checkMesh log exceeds bounded 16 MiB limit")
    before_sha = _hash(path)
    with path.open("rb") as handle:
        raw = handle.read(MAX_LOG_BYTES + 1)
    if not raw or len(raw) > MAX_LOG_BYTES or b"\x00" in raw:
        raise ValueError("Empty, oversized or binary checkMesh log")
    try:
        source = raw.decode("utf-8")
    except UnicodeError as exc:
        raise ValueError("checkMesh log is not valid UTF-8") from exc
    verdict = list(_VERDICT.finditer(source))
    endings = list(_END.finditer(source))
    if len(verdict) != 1 or len(endings) != 1:
        raise ValueError("checkMesh log lacks one explicit Mesh OK and End")
    if verdict[0].start() >= endings[0].start() or source[endings[0].end():].strip():
        raise ValueError("checkMesh log is not a single completed mesh check")
    if _FAILED.search(source) or _ERROR.search(source):
        raise ValueError("checkMesh reports failed checks or fatal errors")
    stats = {}
    for key, pattern in _STATS.items():
        matches = pattern.findall(source)
        if len(matches) != 1:
            raise ValueError("Missing or ambiguous checkMesh mesh statistic: " + key)
        stats[key] = int(matches[0])
        if stats[key] != expected[key]:
            raise ValueError("checkMesh mesh statistic disagrees with polyMesh: " + key)
    if _hash(path) != before_sha:
        raise ValueError("checkMesh log changed during evidence screening")
    return {
        "status": "checkmesh_log_screened",
        "mesh_counts": stats,
        "engineering_review": "BLOCKED",
    }
