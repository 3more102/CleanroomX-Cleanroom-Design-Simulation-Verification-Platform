from __future__ import annotations

from pathlib import Path

import pytest

from cleanroomx.application import verify_analysis_run_bundle
from cleanroomx.project import load_project_document, save_project_document
from cleanroomx.project_requirements_workflow import (
    run_project_requirements_workflow,
    verify_project_requirements_workflow_run,
)


ROOT = Path(__file__).resolve().parents[1]
GOLDEN_PROJECT = ROOT / "examples" / "golden_reference_room_ach.cleanroomx.json"


def _assert_golden_result(result) -> None:
    assert result.mapping_ids == ("MAP-ACH",)
    assert result.evidence[0]["evidence_locator"] == "/result/ach"
    assert result.verification["verified"] is True
    assert result.verification["status"] == "pass"
    assert len(result.verification["findings"]) == 1

    finding = result.verification["findings"][0]
    assert finding["requirement_id"] == "REQ-ACH"
    assert finding["actual"] == pytest.approx(25.0)
    assert finding["expected"] == pytest.approx(20.0)
    assert finding["status"] == "pass"

    assert len(result.proofgraphs) == 1
    graph = result.proofgraphs[0]
    assert graph["verdicts"][0]["status"] == "pass"

    verified_workflow = verify_project_requirements_workflow_run(result)
    assert verified_workflow["workflow_sha256"] == result.workflow_sha256
    verified_run = verify_analysis_run_bundle(result.run_bundle)
    assert verified_run["project_source_revision"] == result.source_revision


def test_golden_reference_project_has_known_ach_and_full_traceability() -> None:
    project = load_project_document(GOLDEN_PROJECT)
    analysis = project.analysis_by_id("room-a")

    volume_m3 = (
        analysis.input["length_m"]
        * analysis.input["width_m"]
        * analysis.input["height_m"]
    )
    expected_ach = analysis.input["supply_airflow_m3_h"] / volume_m3
    assert volume_m3 == pytest.approx(72.0)
    assert expected_ach == pytest.approx(25.0)

    result = run_project_requirements_workflow(GOLDEN_PROJECT, "room-a")
    _assert_golden_result(result)


def test_golden_reference_project_save_reopen_is_reproducible(tmp_path) -> None:
    project = load_project_document(GOLDEN_PROJECT)
    copied = save_project_document(tmp_path / "golden.cleanroomx.json", project)
    reopened = load_project_document(copied)

    assert reopened.name == project.name
    assert reopened.description == project.description
    assert reopened.metadata == project.metadata
    assert reopened.analysis_by_id("room-a").input == project.analysis_by_id("room-a").input

    first = run_project_requirements_workflow(copied, "room-a")
    second = run_project_requirements_workflow(copied, "room-a")
    _assert_golden_result(first)
    _assert_golden_result(second)

    assert first.source_revision == second.source_revision
    assert first.requirements_sha256 == second.requirements_sha256
    assert first.mappings_sha256 == second.mappings_sha256
    assert (
        first.verification["verification_sha256"]
        == second.verification["verification_sha256"]
    )
    assert first.proofgraphs[0]["graph_sha256"] == second.proofgraphs[0]["graph_sha256"]
    assert first.workflow_sha256 == second.workflow_sha256
