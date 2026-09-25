from __future__ import annotations

from dataclasses import replace
import hashlib
import os

import pytest

import cleanroomx.gui as gui_module
import cleanroomx.project as project_module
from cleanroomx.gui import CleanroomXApp
from cleanroomx.project import (
    ProjectDocument,
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



def test_revision_capture_retries_path_replacement_with_same_size_and_mtime(
    tmp_path, monkeypatch
):
    path = tmp_path / "project.cleanroomx.json"
    replacement = tmp_path / "replacement.cleanroomx.json"
    save_project_document(path, ProjectDocument(name="Alpha"))
    save_project_document(replacement, ProjectDocument(name="Bravo"))
    assert path.stat().st_size == replacement.stat().st_size

    original_revision = capture_project_file_revision(path)
    assert original_revision.mtime_ns is not None
    os.utime(
        replacement,
        ns=(original_revision.mtime_ns, original_revision.mtime_ns),
    )
    expected_replacement_sha = hashlib.sha256(replacement.read_bytes()).hexdigest()

    original_open = project_module.Path.open
    swapped = {"done": False}

    class SwapAfterRead:
        def __init__(self, handle):
            self._handle = handle

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return self._handle.__exit__(exc_type, exc, tb)

        def fileno(self):
            return self._handle.fileno()

        def read(self, size=-1):
            chunk = self._handle.read(size)
            if chunk and not swapped["done"]:
                swapped["done"] = True
                replacement.replace(path)
            return chunk

    def open_and_swap(self, *args, **kwargs):
        handle = original_open(self, *args, **kwargs)
        if (
            self.resolve(strict=False) == path.resolve(strict=False)
            and args
            and args[0] == "rb"
            and not swapped["done"]
        ):
            return SwapAfterRead(handle)
        return handle

    monkeypatch.setattr(project_module.Path, "open", open_and_swap)

    captured = capture_project_file_revision(path)

    assert swapped["done"] is True
    assert captured.sha256 == expected_replacement_sha
    assert captured.sha256 != original_revision.sha256
