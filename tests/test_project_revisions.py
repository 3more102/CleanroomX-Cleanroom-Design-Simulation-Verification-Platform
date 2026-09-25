from __future__ import annotations

import json

import pytest

import cleanroomx.project as project_module
from cleanroomx.project import (
    AnalysisDocument,
    ProjectDocument,
    ProjectRevisionError,
    load_project_document,
    load_project_revision,
    project_revision_dir,
    restore_project_revision,
    save_project_document,
    scan_project_revisions,
)


def _project(description: str) -> ProjectDocument:
    return ProjectDocument(
        name="Revision Demo",
        description=description,
        analyses=[
            AnalysisDocument(
                id="room-1",
                name="Room",
                kind="room_verification",
                input={"length_m": 5.0, "width_m": 4.0, "height_m": 3.0},
            )
        ],
        active_analysis_id="room-1",
        metadata={"purpose": "revision-test"},
    )


def test_overwrite_preserves_verified_previous_project_revision(tmp_path):
    path = tmp_path / "demo.cleanroomx.json"
    original = _project("original")
    updated = _project("updated")

    save_project_document(path, original)
    original_bytes = path.read_bytes()
    save_project_document(path, updated)

    scan = scan_project_revisions(path)
    assert scan.issues == ()
    assert len(scan.revisions) == 1

    revision = scan.revisions[0]
    snapshot = load_project_revision(
        revision.path,
        expected_source_path=path,
    )
    assert snapshot.project == original
    assert snapshot.source_bytes == original_bytes
    assert snapshot.source_sha256 == revision.source_sha256
    assert snapshot.source_size == len(original_bytes)
    assert load_project_document(path) == updated


def test_identical_save_does_not_create_redundant_revision(tmp_path):
    path = tmp_path / "demo.cleanroomx.json"
    project = _project("same")

    save_project_document(path, project)
    save_project_document(path, project)

    assert scan_project_revisions(path).revisions == ()


def test_revision_history_is_bounded_per_project(tmp_path):
    path = tmp_path / "demo.cleanroomx.json"
    save_project_document(path, _project("v0"), history_limit=3)

    for index in range(1, 7):
        save_project_document(path, _project(f"v{index}"), history_limit=3)

    scan = scan_project_revisions(path)
    assert scan.issues == ()
    assert len(scan.revisions) == 3
    descriptions = [
        load_project_revision(
            item.path,
            expected_source_path=path,
        ).project.description
        for item in scan.revisions
    ]
    assert descriptions == ["v5", "v4", "v3"]


def test_corrupted_revision_is_reported_without_hiding_other_revisions(tmp_path):
    path = tmp_path / "demo.cleanroomx.json"
    save_project_document(path, _project("v0"))
    save_project_document(path, _project("v1"))
    valid = scan_project_revisions(path).revisions[0]

    payload = json.loads(valid.path.read_text(encoding="utf-8"))
    payload["source"]["sha256"] = "0" * 64
    valid.path.write_text(json.dumps(payload), encoding="utf-8")

    scan = scan_project_revisions(path)
    assert scan.revisions == ()
    assert len(scan.issues) == 1
    assert "SHA-256" in scan.issues[0].error


def test_malformed_existing_destination_is_not_overwritten(tmp_path):
    path = tmp_path / "demo.cleanroomx.json"
    path.write_text("{broken", encoding="utf-8")

    with pytest.raises(
        ProjectRevisionError,
        match="save was not attempted",
    ):
        save_project_document(path, _project("new"))

    assert path.read_text(encoding="utf-8") == "{broken"


def test_failed_post_write_verification_rolls_back_previous_project(
    tmp_path, monkeypatch
):
    path = tmp_path / "demo.cleanroomx.json"
    original = _project("original")
    updated = _project("updated")
    save_project_document(path, original)
    original_bytes = path.read_bytes()

    def fail_verification(destination, expected_bytes, expected_project):
        raise OSError("injected verification failure")

    monkeypatch.setattr(
        project_module,
        "_verify_project_write",
        fail_verification,
    )

    with pytest.raises(OSError, match="injected verification failure"):
        save_project_document(path, updated)

    assert path.read_bytes() == original_bytes
    assert project_revision_dir(path).exists()
    assert list(
        project_revision_dir(path).glob("*.cleanroomx.revision.json")
    ) == []


def test_restore_revision_requires_separate_destination_and_round_trips(tmp_path):
    source = tmp_path / "source.cleanroomx.json"
    old = _project("old")
    current = _project("current")
    save_project_document(source, old)
    old_bytes = source.read_bytes()
    save_project_document(source, current)
    revision = scan_project_revisions(source).revisions[0]

    with pytest.raises(ProjectRevisionError, match="separate file"):
        restore_project_revision(
            revision.path,
            source,
            expected_source_path=source,
        )

    restored = tmp_path / "restored.cleanroomx.json"
    result = restore_project_revision(
        revision.path,
        restored,
        expected_source_path=source,
    )

    assert result == restored
    assert restored.read_bytes() == old_bytes
    assert load_project_document(restored) == old
    assert load_project_document(source) == current


def test_restore_preserves_existing_destination_as_its_own_revision(tmp_path):
    source = tmp_path / "source.cleanroomx.json"
    save_project_document(source, _project("source-old"))
    save_project_document(source, _project("source-current"))
    source_revision = scan_project_revisions(source).revisions[0]

    destination = tmp_path / "destination.cleanroomx.json"
    destination_before = _project("destination-before")
    save_project_document(destination, destination_before)

    restore_project_revision(
        source_revision.path,
        destination,
        expected_source_path=source,
    )

    destination_scan = scan_project_revisions(destination)
    assert destination_scan.issues == ()
    assert len(destination_scan.revisions) == 1
    preserved = load_project_revision(
        destination_scan.revisions[0].path,
        expected_source_path=destination,
    )
    assert preserved.project == destination_before
    assert load_project_document(destination).description == "source-old"
