"""Synthetic checkMesh text fixtures, NOT evidence of real OpenFOAM execution."""
from __future__ import annotations

import os

import pytest

from cleanroomx.cfd_checkmesh_log import screen_checkmesh_log, screen_checkmesh_verdict


def _synthetic_checkmesh_log(path, *, points=12, faces=11, internal=1, cells=2):
    """Representative Foundation log fields; no OpenFOAM process is started."""
    path.write_text(
        "/* Synthetic fixture. NOT a real checkMesh invocation. */\n"
        "Create time\n"
        "Time = 0\n"
        "Mesh stats\n"
        f"    points: {points}\n"
        f"    faces: {faces}\n"
        f"    internal faces: {internal}\n"
        f"    cells: {cells}\n"
        "Checking topology...\n"
        "Checking geometry...\n"
        "    Cell volumes OK.\n"
        "    Non-orthogonality check OK.\n"
        "Mesh OK.\n"
        "End\n",
        encoding="utf-8",
    )


def _screen(path):
    return screen_checkmesh_log(
        path, expected_cells=2, expected_points=12,
        expected_faces=11, expected_internal_faces=1,
    )


def test_synthetic_complete_clean_checkmesh_log_matches_poly_mesh_counts(tmp_path):
    """A matching simulated log only earns the narrow local log-screen label."""
    path = tmp_path / "checkMesh.log"
    _synthetic_checkmesh_log(path)
    result = _screen(path)
    assert result["status"] == "checkmesh_log_screened"
    assert result["mesh_counts"] == {
        "points": 12, "faces": 11, "internal_faces": 1, "cells": 2,
    }
    assert result["engineering_review"] == "BLOCKED"


@pytest.mark.parametrize("tamper", [
    "failed_checks", "failed_zero", "fatal", "warning_stars",
    "missing_mesh_ok", "double_mesh_ok", "missing_end", "double_end",
    "log_after_end", "wrong_cells", "wrong_faces", "missing_internal",
    "duplicate_cell_stats", "bad_encoding", "truncated_log", "empty",
])
def test_synthetic_checkmesh_log_fail_closed_for_malformed_or_failed_output(
    tmp_path, tamper
):
    path = tmp_path / "checkMesh.log"
    _synthetic_checkmesh_log(path)
    content = path.read_text(encoding="utf-8")
    if tamper == "failed_checks":
        content = content.replace("Mesh OK.", "Failed 2 mesh checks.\nMesh OK.")
    elif tamper == "failed_zero":
        content = content.replace("Mesh OK.", "Failed 0 mesh checks.\nMesh OK.")
    elif tamper == "fatal":
        content += "\nFOAM FATAL ERROR: invalid mesh"
    elif tamper == "warning_stars":
        content = content.replace("Mesh OK.", "***Non-orthogonal faces\nMesh OK.")
    elif tamper == "missing_mesh_ok":
        content = content.replace("Mesh OK.", "")
    elif tamper == "double_mesh_ok":
        content = content.replace("Mesh OK.", "Mesh OK.\nMesh OK.")
    elif tamper == "missing_end":
        content = content.replace("End\n", "")
    elif tamper == "double_end":
        content = content.replace("End\n", "End\nEnd\n")
    elif tamper == "log_after_end":
        content += "\nFAKE OTHER STAGE"
    elif tamper == "wrong_cells":
        content = content.replace("cells: 2", "cells: 3")
    elif tamper == "wrong_faces":
        content = content.replace("faces: 11", "faces: 13")
    elif tamper == "missing_internal":
        content = content.replace("internal faces: 1", "")
    elif tamper == "duplicate_cell_stats":
        content = content.replace("cells: 2", "cells: 2\ncells: 2")
    elif tamper == "truncated_log":
        content = content[:len(content)//2]
    elif tamper == "empty":
        content = ""
    elif tamper == "bad_encoding":
        path.write_bytes(b"\xff\x00invalid")
    if tamper != "bad_encoding":
        path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        _screen(path)


@pytest.mark.parametrize("tamper", ["symlink", "hardlink", "missing"])
def test_checkmesh_log_requires_ordinary_unlinked_local_file(tmp_path, tamper):
    log = tmp_path / "checkMesh.log"
    if tamper == "missing":
        with pytest.raises(ValueError):
            _screen(log)
        return
    source = tmp_path / "other.log"
    _synthetic_checkmesh_log(source)
    if tamper == "symlink":
        try:
            log.symlink_to(source)
        except (NotImplementedError, OSError):
            pytest.skip("Symlinks unavailable in environment")
    else:
        try:
            os.link(source, log)
        except OSError:
            pytest.skip("Hard links unavailable in environment")
    with pytest.raises(ValueError):
        _screen(log)


def test_source_count_mismatch_blocks_even_explicit_mesh_ok(tmp_path):
    path = tmp_path / "checkMesh.log"
    _synthetic_checkmesh_log(path, cells=216, faces=900, points=400)
    with pytest.raises(ValueError, match="disagrees with polyMesh"):
        _screen(path)


@pytest.mark.parametrize("diagnostic", [
    "Mesh OK.\nEnd\n",
    "points: 12\nMesh OK.\nEnd\n",
])
def test_early_checkmesh_verdict_accepts_explicit_clean_log(tmp_path, diagnostic):
    path = tmp_path / "checkMesh.log"
    path.write_text("Synthetic log, not OpenFOAM evidence\n" + diagnostic)
    result = screen_checkmesh_verdict(path)
    assert result["status"] == "checkmesh_verdict_screened"
    assert result["engineering_review"] == "BLOCKED"


@pytest.mark.parametrize("diagnostic", [
    "Failed 2 mesh checks.\nEnd\n",
    "Mesh OK.\nFailed 2 mesh checks.\nEnd\n",
    "Mesh OK.\nEnd\nTrailing output",
    "Mesh OK.\nMesh OK.\nEnd\n",
])
def test_early_checkmesh_verdict_rejects_failed_or_ambiguous_log(
    tmp_path, diagnostic
):
    path = tmp_path / "checkMesh.log"
    path.write_text("Synthetic log, not OpenFOAM evidence\n" + diagnostic)
    with pytest.raises(ValueError):
        screen_checkmesh_verdict(path)
