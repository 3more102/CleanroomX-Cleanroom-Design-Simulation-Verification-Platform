from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

import pytest

import cleanroomx.gui as gui_module
import cleanroomx.project as project_module
from cleanroomx.gui import CleanroomXApp
from cleanroomx.project import (
    ProjectDocument,
    ProjectFormatError,
    ProjectWriteConflictError,
    atomic_write_text,
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
    path_type = type(path)
    original_open = path_type.open
    mutated = {"done": False}

    class MutatingReader:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            self.handle.__enter__()
            return self

        def __exit__(self, exc_type, exc, tb):
            return self.handle.__exit__(exc_type, exc, tb)

        def read(self, *args, **kwargs):
            payload = self.handle.read(*args, **kwargs)
            if not mutated["done"]:
                mutated["done"] = True
                save_project_document(path, ProjectDocument(name="Second revision"))
            return payload

    def mutating_open(self, *args, **kwargs):
        handle = original_open(self, *args, **kwargs)
        mode = args[0] if args else kwargs.get("mode", "r")
        if (
            not mutated["done"]
            and self.resolve(strict=False) == path.resolve(strict=False)
            and "r" in mode
            and "b" in mode
        ):
            return MutatingReader(handle)
        return handle

    monkeypatch.setattr(path_type, "open", mutating_open)

    project, revision = load_project_document_with_revision(path)

    assert mutated["done"] is True
    assert project.name == "Second revision"
    assert revision == capture_project_file_revision(path)


def test_revision_bound_load_hashes_the_exact_parsed_bytes(tmp_path):
    path = tmp_path / "project.cleanroomx.json"
    save_project_document(path, ProjectDocument(name="Exact bytes"))
    expected_bytes = path.read_bytes()

    project, revision = load_project_document_with_revision(path)

    assert project.name == "Exact bytes"
    assert revision.size == len(expected_bytes)
    assert revision.sha256 == sha256(expected_bytes).hexdigest()


def test_load_rejects_invalid_utf8_as_project_format_error(tmp_path):
    path = tmp_path / "invalid.cleanroomx.json"
    path.write_bytes(b"\xff\xfe\x00")

    with pytest.raises(ProjectFormatError, match="valid UTF-8"):
        load_project_document_with_revision(path)


def test_atomic_write_text_emits_exact_utf8_bytes(tmp_path):
    path = tmp_path / "exact.txt"
    text = "alpha\nbeta β\n"

    atomic_write_text(path, text)

    assert path.read_bytes() == text.encode("utf-8")


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


def test_guarded_save_revision_stays_bound_to_committed_bytes_after_path_race(
    tmp_path, monkeypatch
):
    path = tmp_path / "project.cleanroomx.json"
    save_project_document(path, ProjectDocument(name="Opened"))
    expected = capture_project_file_revision(path)
    window_project = ProjectDocument(name="Window commit")
    external_project = ProjectDocument(name="External after commit")

    original_atomic_write_bytes = project_module._atomic_write_bytes
    evidence = {}

    def write_then_external_change(target, payload, *, before_replace=None):
        saved_path = original_atomic_write_bytes(
            target,
            payload,
            before_replace=before_replace,
        )
        evidence["committed_bytes"] = saved_path.read_bytes()
        original_atomic_write_bytes(
            saved_path,
            project_module._project_document_bytes(external_project),
        )
        return saved_path

    monkeypatch.setattr(
        project_module,
        "_atomic_write_bytes",
        write_then_external_change,
    )

    saved_path, saved_revision = save_project_document_guarded(
        path,
        window_project,
        expected_revision=expected,
    )

    assert saved_path == path.resolve(strict=False)
    assert load_project_document(path).name == "External after commit"
    assert saved_revision.sha256 == sha256(evidence["committed_bytes"]).hexdigest()
    assert saved_revision.sha256 != capture_project_file_revision(path).sha256


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
