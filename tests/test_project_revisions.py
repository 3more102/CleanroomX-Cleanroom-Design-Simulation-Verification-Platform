from __future__ import annotations

import json

import pytest

import cleanroomx.project as project_module
import cleanroomx.project_revisions as revision_module
from cleanroomx.project import (
    ProjectDocument,
    ProjectWriteConflictError,
    capture_project_file_revision,
    load_project_document,
    save_project_document,
    save_project_document_guarded,
)
from cleanroomx.project_revisions import (
    ProjectRevisionError,
    load_project_revision,
    project_revision_dir,
    restore_project_revision,
    scan_project_revisions,
)


def _project(description: str) -> ProjectDocument:
    return ProjectDocument(
        name="Revision Demo",
        description=description,
        metadata={"purpose": "revision-test"},
    )


def _guarded_save(path, project, *, history_limit=5):
    expected = capture_project_file_revision(path)
    return save_project_document_guarded(
        path,
        project,
        expected_revision=expected,
        revision_history_limit=history_limit,
    )


def test_guarded_overwrite_preserves_exact_previous_project_revision(tmp_path):
    path = tmp_path / "demo.cleanroomx.json"
    original = _project("original")
    updated = _project("updated")
    save_project_document(path, original)
    original_bytes = path.read_bytes()

    _guarded_save(path, updated)

    scan = scan_project_revisions(path)
    assert scan.issues == ()
    assert len(scan.revisions) == 1
    snapshot = load_project_revision(
        scan.revisions[0].path,
        expected_source_path=path,
    )
    assert snapshot.project == original
    assert snapshot.source_bytes == original_bytes
    assert snapshot.source_sha256 == scan.revisions[0].source_sha256
    assert load_project_document(path) == updated


def test_identical_guarded_save_does_not_create_redundant_revision(tmp_path):
    path = tmp_path / "demo.cleanroomx.json"
    project = _project("same")
    save_project_document(path, project)

    _guarded_save(path, project)

    assert scan_project_revisions(path).revisions == ()


def test_project_revision_history_is_bounded_newest_first(tmp_path):
    path = tmp_path / "demo.cleanroomx.json"
    save_project_document(path, _project("v0"))

    for index in range(1, 7):
        _guarded_save(path, _project(f"v{index}"), history_limit=3)

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


def test_revision_envelope_budget_preserves_valid_large_project_name(
    tmp_path, monkeypatch
):
    source = tmp_path / "source.cleanroomx.json"
    project = ProjectDocument(name="N" * 800, description="revision envelope")
    source_bytes = project_module._project_document_text(project).encode("utf-8")
    monkeypatch.setattr(
        revision_module,
        "PROJECT_FILE_MAX_BYTES",
        len(source_bytes),
    )
    monkeypatch.setattr(
        revision_module,
        "PROJECT_REVISION_METADATA_MAX_BYTES",
        512,
    )
    payload = revision_module._revision_payload(
        source,
        source_bytes,
        created_at_utc="2026-09-26T00:00:00Z",
    )
    artifact_bytes = (
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    encoded_only_budget = (
        ((len(source_bytes) + 2) // 3) * 4
        + revision_module.PROJECT_REVISION_METADATA_MAX_BYTES
    )
    assert len(artifact_bytes) > encoded_only_budget
    assert len(artifact_bytes) <= revision_module._project_revision_max_bytes()

    artifact = tmp_path / "large-name.cleanroomx.revision.json"
    artifact.write_bytes(artifact_bytes)
    snapshot = load_project_revision(artifact, expected_source_path=source)

    assert snapshot.project.name == project.name
    assert snapshot.source_bytes == source_bytes


def test_revision_loader_rejects_oversized_artifact_before_json_parsing(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(revision_module, "PROJECT_FILE_MAX_BYTES", 64)
    monkeypatch.setattr(
        revision_module,
        "PROJECT_REVISION_METADATA_MAX_BYTES",
        64,
    )
    artifact = tmp_path / "oversized.cleanroomx.revision.json"
    artifact.write_bytes(b"{" + (b"x" * 256))

    with pytest.raises(ProjectRevisionError, match="artifact size .* exceeds"):
        load_project_revision(artifact)


def test_revision_loader_rejects_declared_project_above_project_limit_before_decode(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(revision_module, "PROJECT_FILE_MAX_BYTES", 64)
    source = tmp_path / "source.cleanroomx.json"
    artifact = tmp_path / "declared-oversized.cleanroomx.revision.json"
    artifact.write_text(
        json.dumps(
            {
                "schema": "cleanroomx.project-revision",
                "schema_version": 1,
                "application_version": "test",
                "created_at_utc": "2026-09-26T00:00:00Z",
                "source": {
                    "path": str(source.resolve(strict=False)),
                    "size_bytes": 65,
                    "sha256": "0" * 64,
                    "project_name": "Oversized",
                    "application_version": "test",
                    "content_base64": "AAAA",
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ProjectRevisionError,
        match="exceeds maximum supported project size",
    ):
        load_project_revision(artifact)


def test_revision_embedded_project_bytes_are_defensively_bounded(monkeypatch):
    monkeypatch.setattr(revision_module, "PROJECT_FILE_MAX_BYTES", 64)

    with pytest.raises(
        ProjectRevisionError,
        match="exceeds maximum supported project size",
    ):
        revision_module._project_from_bytes(b"x" * 65)


def test_corrupted_revision_is_reported_and_preserved(tmp_path):
    path = tmp_path / "demo.cleanroomx.json"
    save_project_document(path, _project("v0"))
    _guarded_save(path, _project("v1"))
    revision = scan_project_revisions(path).revisions[0]

    payload = json.loads(revision.path.read_text(encoding="utf-8"))
    payload["source"]["sha256"] = "0" * 64
    revision.path.write_text(json.dumps(payload), encoding="utf-8")

    scan = scan_project_revisions(path)

    assert scan.revisions == ()
    assert len(scan.issues) == 1
    assert "SHA-256" in scan.issues[0].error
    assert revision.path.exists()


def test_external_change_blocks_save_before_revision_is_created(tmp_path):
    path = tmp_path / "demo.cleanroomx.json"
    save_project_document(path, _project("opened"))
    expected = capture_project_file_revision(path)
    save_project_document(path, _project("external"))

    with pytest.raises(ProjectWriteConflictError):
        save_project_document_guarded(
            path,
            _project("window"),
            expected_revision=expected,
        )

    assert load_project_document(path).description == "external"
    assert not project_revision_dir(path).exists()


def test_failed_uncommitted_save_removes_new_revision_artifact(tmp_path, monkeypatch):
    path = tmp_path / "demo.cleanroomx.json"
    save_project_document(path, _project("old"))
    expected = capture_project_file_revision(path)

    monkeypatch.setattr(
        project_module,
        "_atomic_write_text",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )

    with pytest.raises(OSError, match="disk full"):
        save_project_document_guarded(
            path,
            _project("new"),
            expected_revision=expected,
        )

    assert load_project_document(path).description == "old"
    assert scan_project_revisions(path).revisions == ()


def test_restore_revision_requires_separate_destination_and_round_trips_exact_bytes(tmp_path):
    source = tmp_path / "source.cleanroomx.json"
    old = _project("old")
    current = _project("current")
    save_project_document(source, old)
    old_bytes = source.read_bytes()
    _guarded_save(source, current)
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

    assert result == restored.resolve(strict=False)
    assert restored.read_bytes() == old_bytes
    assert load_project_document(restored) == old
    assert load_project_document(source) == current


def test_restore_preserves_existing_project_destination_as_revision(tmp_path):
    source = tmp_path / "source.cleanroomx.json"
    save_project_document(source, _project("source-old"))
    _guarded_save(source, _project("source-current"))
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


def test_guarded_save_over_non_project_target_does_not_mislabel_revision(tmp_path):
    path = tmp_path / "existing.json"
    path.write_text("not a CleanroomX project", encoding="utf-8")
    expected = capture_project_file_revision(path)

    save_project_document_guarded(
        path,
        _project("new"),
        expected_revision=expected,
    )

    assert load_project_document(path).description == "new"
    assert scan_project_revisions(path).revisions == ()
