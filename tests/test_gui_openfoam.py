from __future__ import annotations

import hashlib
import json

import pytest

from cleanroomx.gui_openfoam import (
    build_openfoam_generate_command,
    build_openfoam_run_command,
    build_openfoam_sync_vtk_command,
    read_openfoam_evidence_preview,
)


def test_case_generation_command_keeps_paths_as_single_arguments() -> None:
    command = build_openfoam_generate_command(
        "/tmp/spec with spaces.json",
        "/tmp/new case bundle",
        python_executable="/python",
    )

    assert command == [
        "/python",
        "-m",
        "cleanroomx.cfd_pipeline_cli",
        "generate",
        "/tmp/spec with spaces.json",
        "/tmp/new case bundle",
    ]


def test_run_command_only_enables_sync_with_a_safe_simulation_id() -> None:
    command = build_openfoam_run_command(
        "/tmp/case bundle",
        result_directory="/tmp/results",
        simulation_id="run-001",
        python_executable="/python",
    )

    assert command[-4:] == [
        "--sync-results",
        "/tmp/results",
        "--simulation-id",
        "run-001",
    ]
    with pytest.raises(ValueError, match="safe simulation ID"):
        build_openfoam_run_command(
            "/tmp/case bundle",
            result_directory="/tmp/results",
            simulation_id="../../outside",
        )
    with pytest.raises(ValueError, match="requires a result directory"):
        build_openfoam_run_command(
            "/tmp/case bundle",
            simulation_id="run-001",
        )


def test_sync_vtk_command_is_a_single_scan_and_preserves_source_paths() -> None:
    command = build_openfoam_sync_vtk_command(
        "/tmp/VTK output",
        "/tmp/imported results",
        "/tmp/case bundle/manifest.json",
        "vtk-run-01",
        python_executable="/python",
    )

    assert command[0] == "/python"
    assert command[4:6] == ["/tmp/VTK output", "/tmp/imported results"]
    assert command[-1] == "--once"


def test_evidence_preview_reports_digest_and_diagnostic_status(tmp_path) -> None:
    manifest = {
        "schema_version": "cleanroomx.openfoam.v1",
        "status": "executed_requires_convergence_review",
        "files": {"configuration_1/system/blockMeshDict": "0" * 64},
    }
    path = tmp_path / "manifest.json"
    raw = (json.dumps(manifest, sort_keys=True) + "\n").encode()
    path.write_bytes(raw)

    previews = read_openfoam_evidence_preview(tmp_path)

    assert len(previews) == 1
    assert previews[0]["path"] == "manifest.json"
    assert previews[0]["sha256"] == hashlib.sha256(raw).hexdigest()
    assert previews[0]["summary"]["status"] == "executed_requires_convergence_review"


def test_evidence_preview_rejects_a_symlink_directory(tmp_path) -> None:
    target = tmp_path / "real"
    target.mkdir()
    link = tmp_path / "linked"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks are unavailable: {exc}")

    with pytest.raises(ValueError, match="regular directory"):
        read_openfoam_evidence_preview(link)

