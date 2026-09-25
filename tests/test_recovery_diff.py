from __future__ import annotations

import json

from cleanroomx.autosave import AutosaveManager, scan_recovery_artifacts
from cleanroomx.project import AnalysisDocument, ProjectDocument, save_project_document
from cleanroomx.recovery_diff import (
    compare_recovery_to_source,
    format_recovery_comparison,
)


def _project(
    *,
    name: str = "Recovery Demo",
    description: str = "source",
    analyses: list[AnalysisDocument] | None = None,
    active: str | None = "a",
) -> ProjectDocument:
    if analyses is None:
        analyses = [
            AnalysisDocument(id="a", name="A", kind="room_verification", input={"value": 1}),
            AnalysisDocument(id="b", name="B", kind="room_verification", input={"value": 2}),
        ]
    return ProjectDocument(
        name=name,
        description=description,
        analyses=analyses,
        active_analysis_id=active,
        metadata={"owner": "qa"},
    )


def _recovery(tmp_path, project: ProjectDocument, *, editor_text='{"value": 1}', editor_valid=True):
    source = save_project_document(tmp_path / "source.cleanroomx.json", project)
    manager = AutosaveManager(tmp_path / "recovery", session_id="crashed")
    try:
        manager.begin_project(source)
        assert manager.request_autosave(
            {
                "project": project.to_dict(),
                "ui_state": {
                    "name_text": project.name,
                    "description_text": project.description,
                    "editor_analysis_id": "a",
                    "editor_text": editor_text,
                    "editor_json_valid": editor_valid,
                },
            },
            source_path=source,
        )
        manager.wait_for_idle()
        artifact = manager.status().artifact_path
        assert artifact is not None
    finally:
        manager.shutdown(wait=True)
    scan = scan_recovery_artifacts(tmp_path / "recovery")
    candidate = next(item for item in scan.candidates if item.path == artifact)
    return source, candidate


def test_semantic_comparison_reports_identical_project(tmp_path):
    _, candidate = _recovery(tmp_path, _project())

    comparison = compare_recovery_to_source(candidate)
    summary, details = format_recovery_comparison(comparison)

    assert comparison.source_state == "available"
    assert comparison.has_changes is False
    assert comparison.changed_project_fields == ()
    assert comparison.added_analysis_ids == ()
    assert comparison.removed_analysis_ids == ()
    assert comparison.modified_analysis_ids == ()
    assert comparison.active_analysis_changed is False
    assert comparison.editor_draft_state == "matches"
    assert "No semantic project differences" in summary
    assert details


def test_semantic_comparison_classifies_project_and_analysis_changes(tmp_path):
    source, candidate = _recovery(tmp_path, _project())

    changed = _project(
        name="Current Source",
        description="changed",
        analyses=[
            AnalysisDocument(id="a", name="A current", kind="room_verification", input={"value": 9}),
            AnalysisDocument(id="c", name="C", kind="room_verification", input={"value": 3}),
        ],
        active="c",
    )
    changed.metadata = {"owner": "source"}
    save_project_document(source, changed)

    comparison = compare_recovery_to_source(candidate)
    summary, details = format_recovery_comparison(comparison)

    assert comparison.changed_project_fields == ("name", "description", "metadata")
    assert comparison.added_analysis_ids == ("b",)
    assert comparison.removed_analysis_ids == ("c",)
    assert comparison.modified_analysis_ids == ("a",)
    assert comparison.active_analysis_changed is True
    assert comparison.has_changes is True
    assert "semantic area" in summary
    joined = "\n".join(details)
    assert "Recovery-only analyses: b" in joined
    assert "Source-only analyses: c" in joined
    assert "Modified analyses: a" in joined


def test_valid_raw_editor_draft_is_compared_even_when_project_model_matches(tmp_path):
    _, candidate = _recovery(tmp_path, _project(), editor_text='{"value": 99}')

    comparison = compare_recovery_to_source(candidate)
    _, details = format_recovery_comparison(comparison)

    assert comparison.editor_draft_state == "differs"
    assert comparison.has_changes is True
    assert any("editor draft" in line.lower() for line in details)


def test_invalid_raw_editor_draft_is_preserved_as_semantic_evidence(tmp_path):
    _, candidate = _recovery(tmp_path, _project(), editor_text="{broken", editor_valid=False)

    comparison = compare_recovery_to_source(candidate)
    _, details = format_recovery_comparison(comparison)

    assert comparison.editor_draft_state == "invalid"
    assert comparison.has_changes is True
    assert any("invalid/incomplete" in line for line in details)


def test_missing_source_is_reported_without_guessing_changes(tmp_path):
    source, candidate = _recovery(tmp_path, _project())
    source.unlink()

    comparison = compare_recovery_to_source(candidate)
    summary, details = format_recovery_comparison(comparison)

    assert comparison.source_state == "missing"
    assert comparison.comparable is False
    assert comparison.source_analysis_count is None
    assert "missing" in summary.lower()
    assert "no automatic reconstruction" in details[0].lower()


def test_unreadable_source_is_reported_without_mutating_recovery(tmp_path):
    source, candidate = _recovery(tmp_path, _project())
    artifact_before = candidate.path.read_bytes()
    source.write_text("{not-json", encoding="utf-8")

    comparison = compare_recovery_to_source(candidate)
    summary, details = format_recovery_comparison(comparison)

    assert comparison.source_state == "unreadable"
    assert comparison.source_error
    assert "cannot be parsed safely" in summary
    assert details[0].startswith("Source validation error:")
    assert candidate.path.read_bytes() == artifact_before


def test_analysis_id_lists_are_deterministically_sorted(tmp_path):
    recovered = _project(
        analyses=[
            AnalysisDocument(id="z", name="Z", kind="room_verification", input={}),
            AnalysisDocument(id="a", name="A", kind="room_verification", input={}),
        ],
        active="a",
    )
    source, candidate = _recovery(tmp_path, recovered, editor_text="{}", editor_valid=True)
    current = _project(
        analyses=[
            AnalysisDocument(id="y", name="Y", kind="room_verification", input={}),
            AnalysisDocument(id="b", name="B", kind="room_verification", input={}),
        ],
        active="b",
    )
    save_project_document(source, current)

    comparison = compare_recovery_to_source(candidate)

    assert comparison.added_analysis_ids == ("a", "z")
    assert comparison.removed_analysis_ids == ("b", "y")
