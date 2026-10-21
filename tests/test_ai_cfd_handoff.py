"""Generated-case handoff contract tests. No OpenFOAM solver is run."""
from __future__ import annotations

from pathlib import Path

import pytest

from cleanroomx.ai_cfd_handoff import (
    prepare_cfd_run_handoff, render_cfd_run_handoff,
    revalidate_cfd_run_handoff, verify_cfd_run_handoff,
)
from cleanroomx.cfd_multizone import generate_multizone_open_door_case
from cleanroomx.gui import bundled_demo_project_path
from cleanroomx.project import (
    load_project_document, new_project, save_project_document,
)


@pytest.fixture
def generated(tmp_path):
    source = tmp_path / "project.json"
    source.write_bytes(bundled_demo_project_path().read_bytes())
    project = load_project_document(source)
    case = tmp_path / "generated-open-door"
    generate_multizone_open_door_case(
        source, case, door_mode="open", kinematic_viscosity_m2_s=1.5e-5,
        max_iterations=10, output_interval=5,
    )
    return source, project, case


def test_preview_is_strictly_read_only_and_requires_separate_run(generated):
    source, project, case = generated
    old_source = source.read_bytes()
    old_manifest = (case / "manifest.json").read_bytes()
    proposal = prepare_cfd_run_handoff(
        case, project=project, project_path=source,
    )
    assert proposal["schema"] == "cleanroomx.ai-cfd-run-handoff"
    assert proposal["state"] == "proposal_not_executed"
    assert proposal["solver_executed"] is False
    assert proposal["requires_explicit_user_confirmation"] is True
    assert proposal["engineering_release"] == "HOLD"
    assert proposal["closed_door_5pa_demonstrated"] is False
    assert verify_cfd_run_handoff(proposal)
    assert revalidate_cfd_run_handoff(
        proposal, project=project, project_path=source,
    ) == case.resolve()
    assert "NOT EXECUTED" in render_cfd_run_handoff(proposal)
    assert "separate Run action" in render_cfd_run_handoff(proposal)
    assert source.read_bytes() == old_source
    assert (case / "manifest.json").read_bytes() == old_manifest
    assert not (case / "run-receipt.json").exists()
    assert not (case / "simpleFoam.log").exists()


def test_handoff_rejects_unsaved_design_or_other_project(generated, tmp_path):
    source, project, case = generated
    project.description = "Unsaved modification"
    with pytest.raises(ValueError, match="Save current project edits"):
        prepare_cfd_run_handoff(case, project=project, project_path=source)

    other_path = tmp_path / "different.json"
    other = new_project("Not the recorded source")
    save_project_document(other_path, other)
    with pytest.raises(ValueError, match="different saved project revision"):
        prepare_cfd_run_handoff(case, project=other, project_path=other_path)


def test_handoff_rejects_solver_input_tampering(generated):
    source, project, case = generated
    solver_input = case / "0" / "U"
    solver_input.write_text(solver_input.read_text() + "\n// changed", encoding="utf-8")
    with pytest.raises(ValueError, match="Solver input changed"):
        prepare_cfd_run_handoff(case, project=project, project_path=source)


@pytest.mark.parametrize("prior_artifact", [
    "run-receipt.json", "blockMesh.log", "simpleFoam.log.gz",
])
def test_handoff_rejects_any_prior_solver_artifact(generated, prior_artifact):
    source, project, case = generated
    (case / prior_artifact).write_text("not a real solver run", encoding="utf-8")
    with pytest.raises(ValueError, match="execution receipt|prior solver logs"):
        prepare_cfd_run_handoff(case, project=project, project_path=source)


def test_handoff_rejects_prior_numeric_field_directory(generated):
    source, project, case = generated
    (case / "25").mkdir()
    with pytest.raises(ValueError, match="computed time directories"):
        prepare_cfd_run_handoff(case, project=project, project_path=source)


def test_saved_source_changed_after_preview_is_rejected(generated):
    source, project, case = generated
    proposal = prepare_cfd_run_handoff(case, project=project, project_path=source)
    source.write_bytes(source.read_bytes() + b" ")
    with pytest.raises(ValueError, match="project|source"):
        revalidate_cfd_run_handoff(proposal, project=project, project_path=source)


def test_case_changed_after_preview_is_rejected(generated):
    source, project, case = generated
    proposal = prepare_cfd_run_handoff(case, project=project, project_path=source)
    (case / "0" / "p").write_text("tampered input", encoding="utf-8")
    with pytest.raises(ValueError, match="Solver input changed"):
        revalidate_cfd_run_handoff(proposal, project=project, project_path=source)


def test_approval_preview_digest_is_not_a_solver_authorization(generated):
    source, project, case = generated
    proposal = prepare_cfd_run_handoff(case, project=project, project_path=source)
    proposal["solver_executed"] = True
    assert not verify_cfd_run_handoff(proposal)
    with pytest.raises(ValueError, match="invalid or has changed"):
        revalidate_cfd_run_handoff(proposal, project=project, project_path=source)


def test_symlinked_case_is_rejected(generated, tmp_path):
    source, project, case = generated
    alias = tmp_path / "case-alias"
    try:
        alias.symlink_to(case, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation not permitted")
    with pytest.raises(ValueError, match="not a symlink"):
        prepare_cfd_run_handoff(alias, project=project, project_path=source)


def test_duplicate_manifest_keys_fail_strict_json_validation(generated):
    source, project, case = generated
    manifest = case / "manifest.json"
    original = manifest.read_text(encoding="utf-8")
    manifest.write_text(
        original.replace('"input_mode":', '"input_mode": "hypothetical_all_doors_open", "input_mode":', 1),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate|Duplicate"):
        prepare_cfd_run_handoff(case, project=project, project_path=source)
