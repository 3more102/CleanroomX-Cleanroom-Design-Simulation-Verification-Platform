from __future__ import annotations

import json
from pathlib import Path

import pytest

from cleanroomx.project import AnalysisDocument, ProjectDocument, load_project_document
from cleanroomx.saved_revisions import (
    SavedRevisionFormatError,
    archive_project_revision,
    discard_saved_revision_artifact,
    load_saved_revision_artifact,
    restore_saved_revision_artifact,
    save_project_document_with_revision,
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


def test_explicit_save_preserves_previous_valid_project(tmp_path):
    revisions = tmp_path / "revisions"
    target = tmp_path / "project.cleanroomx.json"

    save_project_document_with_revision(
        target,
        _project("Version 1"),
        revision_dir=revisions,
    )
    assert scan_saved_revisions(target, revisions).candidates == ()

    save_project_document_with_revision(
        target,
        _project("Version 2"),
        revision_dir=revisions,
    )

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

    artifact = archive_project_revision(target, revision_dir=revisions)
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

    save_project_document_with_revision(
        target,
        _project("V1"),
        revision_dir=revisions,
        history_limit=2,
    )
    save_project_document_with_revision(
        target,
        _project("V2"),
        revision_dir=revisions,
        history_limit=2,
    )
    save_project_document_with_revision(
        target,
        _project("V3"),
        revision_dir=revisions,
        history_limit=2,
    )
    save_project_document_with_revision(
        target,
        _project("V4"),
        revision_dir=revisions,
        history_limit=2,
    )

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
    target = tmp_path / "project.cleanroomx.json"
    target.write_text(
        json.dumps(_project("V1").to_dict(), sort_keys=True) + "\n",
        encoding="utf-8",
    )

    first = archive_project_revision(target, revision_dir=revisions)
    second = archive_project_revision(target, revision_dir=revisions)

    assert first == second
    assert len(scan_saved_revisions(target, revisions).candidates) == 1


def test_saved_revision_checksum_corruption_is_rejected_and_reported(tmp_path):
    revisions = tmp_path / "revisions"
    target = tmp_path / "project.cleanroomx.json"
    target.write_text(
        json.dumps(_project("V1").to_dict(), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    artifact = archive_project_revision(target, revision_dir=revisions)
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

    with pytest.raises(SavedRevisionFormatError):
        save_project_document_with_revision(
            target,
            _project("Replacement"),
            revision_dir=revisions,
        )

    assert target.read_bytes() == original
    assert not revisions.exists() or list(revisions.iterdir()) == []


def test_discard_saved_revision_is_restricted_to_revision_directory(tmp_path):
    revisions = tmp_path / "revisions"
    target = tmp_path / "project.cleanroomx.json"
    target.write_text(
        json.dumps(_project("V1").to_dict(), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    artifact = archive_project_revision(target, revision_dir=revisions)
    assert artifact is not None

    outside = tmp_path / "outside.saved-revision.json"
    outside.write_text(artifact.read_text(encoding="utf-8"), encoding="utf-8")

    with pytest.raises(SavedRevisionFormatError, match="inside"):
        discard_saved_revision_artifact(outside, revision_dir=revisions)

    assert outside.exists()
    discard_saved_revision_artifact(artifact, revision_dir=revisions)
    assert not artifact.exists()
