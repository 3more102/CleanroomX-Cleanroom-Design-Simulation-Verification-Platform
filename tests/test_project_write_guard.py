from __future__ import annotations

from dataclasses import replace

import pytest

import cleanroomx.gui as gui_module
import cleanroomx.project as project_module
from cleanroomx.gui import CleanroomXApp
from cleanroomx.project import (
    ProjectDocument,
    ProjectSaveVerificationError,
    ProjectWriteConflictError,
    capture_project_file_revision,
    load_project_document,
    load_project_document_with_revision,
    project_file_revision_matches,
    save_project_document,
    save_project_document_guarded,
)


class Value:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def test_stable_load_retries_when_file_changes_during_open(tmp_path, monkeypatch):
    path = tmp_path / "project.cleanroomx.json"
    save_project_document(path, ProjectDocument(name="First"))
    original_load = project_module.load_project_document
    calls = {"count": 0}

    def changing_load(source):
        project = original_load(source)
        if calls["count"] == 0:
            save_project_document(path, ProjectDocument(name="Second"))
        calls["count"] += 1
        return project

    monkeypatch.setattr(project_module, "load_project_document", changing_load)

    project, revision = load_project_document_with_revision(path)

    assert calls["count"] == 2
    assert project.name == "Second"
    assert revision == capture_project_file_revision(path)


def test_guarded_save_rejects_external_content_change(tmp_path):
    path = tmp_path / "project.cleanroomx.json"
    save_project_document(path, ProjectDocument(name="Opened"))
    expected = capture_project_file_revision(path)

    save_project_document(path, ProjectDocument(name="External edit"))

    with pytest.raises(ProjectWriteConflictError) as exc_info:
        save_project_document_guarded(
            path,
            ProjectDocument(name="Window edit"),
            expected_revision=expected,
        )

    assert exc_info.value.expected == expected
    assert exc_info.value.current.sha256 != expected.sha256
    assert load_project_document(path).name == "External edit"


def test_guarded_save_rejects_external_delete(tmp_path):
    path = tmp_path / "project.cleanroomx.json"
    save_project_document(path, ProjectDocument(name="Opened"))
    expected = capture_project_file_revision(path)
    path.unlink()

    with pytest.raises(ProjectWriteConflictError):
        save_project_document_guarded(
            path,
            ProjectDocument(name="Window edit"),
            expected_revision=expected,
        )

    assert not path.exists()


def test_guarded_save_rejects_external_creation_for_new_destination(tmp_path):
    path = tmp_path / "new.cleanroomx.json"
    expected = capture_project_file_revision(path)
    path.write_text("foreign content", encoding="utf-8")

    with pytest.raises(ProjectWriteConflictError):
        save_project_document_guarded(
            path,
            ProjectDocument(name="Window edit"),
            expected_revision=expected,
        )

    assert path.read_text(encoding="utf-8") == "foreign content"


def test_revision_match_ignores_metadata_only_timestamp_change(tmp_path):
    path = tmp_path / "project.cleanroomx.json"
    save_project_document(path, ProjectDocument(name="Opened"))
    revision = capture_project_file_revision(path)

    metadata_only = replace(
        revision,
        mtime_ns=(revision.mtime_ns or 0) + 123456789,
    )

    assert project_file_revision_matches(revision, metadata_only) is True


def test_guarded_save_succeeds_and_returns_new_revision(tmp_path):
    path = tmp_path / "project.cleanroomx.json"
    save_project_document(path, ProjectDocument(name="Opened"))
    expected = capture_project_file_revision(path)

    saved_path, saved_revision = save_project_document_guarded(
        path,
        ProjectDocument(name="Window edit"),
        expected_revision=expected,
    )

    assert saved_path == path.resolve(strict=False)
    assert load_project_document(path).name == "Window edit"
    assert saved_revision == capture_project_file_revision(path)
    assert saved_revision.sha256 != expected.sha256


def _minimal_gui_app(path, project):
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = object()
    app.project = project
    app.project_path = path
    app._project_file_revision = capture_project_file_revision(path)
    app._editor_analysis_id = None
    app._recovery_source_path = None
    app._restored_recovery_artifact = None
    app.status_var = Value()
    app._editor_analysis = lambda: None
    app._sync_metadata = lambda: None
    app._capture_saved_state = lambda: None
    app._notify_explicit_save = lambda _path: None
    app._clear_run_cache = lambda: None
    app._discard_restored_recovery = lambda: None
    return app


def test_gui_save_blocks_external_change_without_overwrite(tmp_path, monkeypatch):
    path = tmp_path / "project.cleanroomx.json"
    save_project_document(path, ProjectDocument(name="Opened"))
    app = _minimal_gui_app(path, ProjectDocument(name="Window edit"))

    save_project_document(path, ProjectDocument(name="External edit"))
    warnings = []
    errors = []
    monkeypatch.setattr(
        gui_module.messagebox,
        "showwarning",
        lambda title, message, parent=None: warnings.append((title, message)),
    )
    monkeypatch.setattr(
        gui_module.messagebox,
        "showerror",
        lambda title, message, parent=None: errors.append((title, message)),
    )

    app.save_project()

    assert load_project_document(path).name == "External edit"
    assert warnings
    assert "changed on disk" in app.status_var.value
    assert errors == []


def test_gui_save_as_same_path_cannot_bypass_external_change(tmp_path, monkeypatch):
    path = tmp_path / "project.cleanroomx.json"
    save_project_document(path, ProjectDocument(name="Opened"))
    app = _minimal_gui_app(path, ProjectDocument(name="Window edit"))

    save_project_document(path, ProjectDocument(name="External edit"))
    warnings = []
    monkeypatch.setattr(
        gui_module.filedialog,
        "asksaveasfilename",
        lambda **kwargs: str(path),
    )
    monkeypatch.setattr(
        gui_module.messagebox,
        "showwarning",
        lambda title, message, parent=None: warnings.append((title, message)),
    )
    monkeypatch.setattr(
        gui_module.messagebox,
        "showerror",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("write conflict must not be reported as a generic save error")
        ),
    )

    app.save_project_as()

    assert load_project_document(path).name == "External edit"
    assert warnings
    assert app.project_path == path



def test_atomic_write_fsyncs_directory_after_replacement(tmp_path, monkeypatch):
    target = tmp_path / "durable.txt"
    observed = []

    def record_directory_fsync(directory):
        observed.append((directory, target.read_text(encoding="utf-8")))

    monkeypatch.setattr(project_module, "_fsync_directory", record_directory_fsync)

    project_module.atomic_write_text(target, "committed\n")

    assert observed == [(tmp_path, "committed\n")]


def test_atomic_write_surfaces_directory_fsync_failure(tmp_path, monkeypatch):
    target = tmp_path / "durability-unknown.txt"

    def fail_directory_fsync(directory):
        raise OSError("directory fsync failed")

    monkeypatch.setattr(project_module, "_fsync_directory", fail_directory_fsync)

    with pytest.raises(OSError, match="directory fsync failed"):
        project_module.atomic_write_text(target, "new content\n")

    assert target.read_text(encoding="utf-8") == "new content\n"
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_project_save_detects_post_replace_byte_corruption(tmp_path, monkeypatch):
    path = tmp_path / "corrupted-after-replace.cleanroomx.json"
    path_type = type(path)
    original_replace = path_type.replace

    def corrupt_after_replace(self, destination):
        replaced = original_replace(self, destination)
        destination_path = type(self)(destination)
        destination_path.write_text('{"corrupted": true}\n', encoding="utf-8")
        return replaced

    monkeypatch.setattr(path_type, "replace", corrupt_after_replace)

    with pytest.raises(ProjectSaveVerificationError) as exc_info:
        save_project_document(path, ProjectDocument(name="Verified"))

    assert exc_info.value.path == path
    assert exc_info.value.expected_size > 0
    assert len(exc_info.value.expected_sha256) == 64
    assert exc_info.value.current.sha256 != exc_info.value.expected_sha256
    assert list(tmp_path.glob(f".{path.name}.*.tmp")) == []


def test_guarded_save_returns_revision_of_verified_persisted_bytes(tmp_path):
    path = tmp_path / "verified-guard.cleanroomx.json"
    save_project_document(path, ProjectDocument(name="Opened"))
    expected = capture_project_file_revision(path)

    saved_path, verified_revision = save_project_document_guarded(
        path,
        ProjectDocument(name="Verified update"),
        expected_revision=expected,
    )

    assert saved_path == path.resolve(strict=False)
    assert verified_revision == capture_project_file_revision(path)
    assert load_project_document(path).name == "Verified update"
