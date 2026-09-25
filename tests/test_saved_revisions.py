from __future__ import annotations

import json

import pytest

import cleanroomx.saved_revisions as revision_module
from cleanroomx.project import (
    AnalysisDocument,
    ProjectDocument,
    ProjectWriteConflictError,
    capture_project_file_revision,
    load_project_document,
    save_project_document,
)
from cleanroomx.saved_revisions import (
    SavedRevisionFormatError,
    archive_project_revision,
    discard_saved_revision_artifact,
    load_saved_revision_artifact,
    restore_saved_revision_artifact,
    save_project_document_guarded_with_revision,
    scan_saved_revisions,
)


def _project(name: str) -> ProjectDocument:
    return ProjectDocument(
        name=name,
        description=f"description for {name}",
        analyses=[
            AnalysisDocument(
                id="room-1",
                name="Room",
                kind="room_verification",
                input={"value": name},
            )
        ],
        active_analysis_id="room-1",
        metadata={"marker": name},
    )


def _guarded_save(target, project, revisions, *, history_limit=10):
    expected = capture_project_file_revision(target)
    return save_project_document_guarded_with_revision(
        target,
        project,
        expected_revision=expected,
        revision_dir=revisions,
        history_limit=history_limit,
    )


def test_explicit_guarded_save_preserves_previous_valid_project(tmp_path):
    revisions = tmp_path / "revisions"
    target = tmp_path / "project.cleanroomx.json"

    _guarded_save(target, _project("Version 1"), revisions)
    assert scan_saved_revisions(target, revisions).candidates == ()

    saved_path, saved_revision = _guarded_save(
        target, _project("Version 2"), revisions
    )

    assert saved_path == target.resolve(strict=False)
    assert saved_revision == capture_project_file_revision(target)
    assert load_project_document(target).name == "Version 2"
    scan = scan_saved_revisions(target, revisions)
    assert len(scan.candidates) == 1
    restored = restore_saved_revision_artifact(scan.candidates[0].path)
    assert restored.project.name == "Version 1"
    assert restored.project.metadata["marker"] == "Version 1"
    assert restored.source_path == target.resolve()


def test_saved_revision_preserves_exact_legacy_utf8_bytes(tmp_path):
    revisions = tmp_path / "revisions"
    target = tmp_path / "legacy.cleanroomx.json"
    legacy_text = (
        '{\n'
        '  "name": "Legacy",\n'
        '  "analysis_type": "fan_operating_point",\n'
        '  "input": {"study": "legacy"}\n'
        '}\n'
    )
    target.write_text(legacy_text, encoding="utf-8")
    expected = capture_project_file_revision(target)

    artifact = archive_project_revision(
        target,
        expected_revision=expected,
        revision_dir=revisions,
    )
    assert artifact is not None

    payload = load_saved_revision_artifact(artifact)
    assert payload["source_text"] == legacy_text
    assert payload["source"]["size_bytes"] == len(legacy_text.encode("utf-8"))
    restored = restore_saved_revision_artifact(artifact)
    assert restored.project.name == "Legacy"
    assert restored.source_text == legacy_text


def test_saved_revision_history_is_bounded_and_keeps_newest_preimages(tmp_path):
    revisions = tmp_path / "revisions"
    target = tmp_path / "project.cleanroomx.json"

    for name in ("V1", "V2", "V3", "V4"):
        _guarded_save(target, _project(name), revisions, history_limit=2)

    scan = scan_saved_revisions(target, revisions)
    assert len(scan.candidates) == 2
    names = {
        restore_saved_revision_artifact(candidate.path).project.name
        for candidate in scan.candidates
    }
    assert names == {"V2", "V3"}
    assert load_project_document(target).name == "V4"


def test_identical_preimage_is_not_archived_twice(tmp_path):
    revisions = tmp_path / "revisions"
    target = save_project_document(
        tmp_path / "project.cleanroomx.json",
        _project("V1"),
    )
    expected = capture_project_file_revision(target)

    first = archive_project_revision(
        target,
        expected_revision=expected,
        revision_dir=revisions,
    )
    second = archive_project_revision(
        target,
        expected_revision=expected,
        revision_dir=revisions,
    )

    assert first == second
    assert len(scan_saved_revisions(target, revisions).candidates) == 1


def test_saved_revision_checksum_corruption_is_rejected_and_reported(tmp_path):
    revisions = tmp_path / "revisions"
    target = save_project_document(
        tmp_path / "project.cleanroomx.json",
        _project("V1"),
    )
    artifact = archive_project_revision(
        target,
        expected_revision=capture_project_file_revision(target),
        revision_dir=revisions,
    )
    assert artifact is not None

    payload = json.loads(artifact.read_text(encoding="utf-8"))
    payload["source_text"] = payload["source_text"].replace("V1", "CORRUPTED", 1)
    artifact.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(SavedRevisionFormatError, match="checksum"):
        load_saved_revision_artifact(artifact)

    scan = scan_saved_revisions(target, revisions)
    assert scan.candidates == ()
    assert len(scan.issues) == 1
    assert scan.issues[0].path == artifact


def test_invalid_existing_destination_is_never_overwritten_without_archive(tmp_path):
    revisions = tmp_path / "revisions"
    target = tmp_path / "project.cleanroomx.json"
    original = b"{not a valid CleanroomX project"
    target.write_bytes(original)
    expected = capture_project_file_revision(target)

    with pytest.raises(SavedRevisionFormatError):
        save_project_document_guarded_with_revision(
            target,
            _project("Replacement"),
            expected_revision=expected,
            revision_dir=revisions,
        )

    assert target.read_bytes() == original
    assert not revisions.exists() or list(revisions.iterdir()) == []


def test_external_change_before_archive_uses_existing_write_conflict_contract(tmp_path):
    revisions = tmp_path / "revisions"
    target = save_project_document(
        tmp_path / "project.cleanroomx.json",
        _project("Opened"),
    )
    expected = capture_project_file_revision(target)
    save_project_document(target, _project("External edit"))

    with pytest.raises(ProjectWriteConflictError):
        save_project_document_guarded_with_revision(
            target,
            _project("Window edit"),
            expected_revision=expected,
            revision_dir=revisions,
        )

    assert load_project_document(target).name == "External edit"
    assert not revisions.exists() or list(revisions.iterdir()) == []


def test_external_change_after_archive_is_still_blocked(tmp_path, monkeypatch):
    revisions = tmp_path / "revisions"
    target = save_project_document(
        tmp_path / "project.cleanroomx.json",
        _project("Opened"),
    )
    expected = capture_project_file_revision(target)
    actual_guarded_save = revision_module.save_project_document_guarded

    def race_after_archive(path, project, *, expected_revision):
        save_project_document(path, _project("External edit"))
        return actual_guarded_save(
            path,
            project,
            expected_revision=expected_revision,
        )

    monkeypatch.setattr(
        revision_module,
        "save_project_document_guarded",
        race_after_archive,
    )

    with pytest.raises(ProjectWriteConflictError):
        save_project_document_guarded_with_revision(
            target,
            _project("Window edit"),
            expected_revision=expected,
            revision_dir=revisions,
        )

    assert load_project_document(target).name == "External edit"
    scan = scan_saved_revisions(target, revisions)
    assert len(scan.candidates) == 1
    assert (
        restore_saved_revision_artifact(scan.candidates[0].path).project.name
        == "Opened"
    )


def test_corrupt_revision_is_preserved_when_valid_history_rotates(tmp_path):
    revisions = tmp_path / "revisions"
    target = save_project_document(
        tmp_path / "project.cleanroomx.json",
        _project("V1"),
    )
    first = archive_project_revision(
        target,
        expected_revision=capture_project_file_revision(target),
        revision_dir=revisions,
        history_limit=1,
    )
    assert first is not None
    corrupt = revisions / (
        first.name.replace(".saved-revision.json", "-corrupt.saved-revision.json")
    )
    corrupt.write_text("{broken", encoding="utf-8")

    _guarded_save(target, _project("V2"), revisions, history_limit=1)
    _guarded_save(target, _project("V3"), revisions, history_limit=1)

    assert corrupt.exists()
    scan = scan_saved_revisions(target, revisions)
    assert len(scan.candidates) == 1
    assert len(scan.issues) == 1


def test_discard_saved_revision_is_restricted_to_revision_directory(tmp_path):
    revisions = tmp_path / "revisions"
    target = save_project_document(
        tmp_path / "project.cleanroomx.json",
        _project("V1"),
    )
    artifact = archive_project_revision(
        target,
        expected_revision=capture_project_file_revision(target),
        revision_dir=revisions,
    )
    assert artifact is not None

    outside = tmp_path / "outside.saved-revision.json"
    outside.write_text(artifact.read_text(encoding="utf-8"), encoding="utf-8")

    with pytest.raises(SavedRevisionFormatError, match="inside"):
        discard_saved_revision_artifact(outside, revision_dir=revisions)

    assert outside.exists()
    discard_saved_revision_artifact(artifact, revision_dir=revisions)
    assert not artifact.exists()
