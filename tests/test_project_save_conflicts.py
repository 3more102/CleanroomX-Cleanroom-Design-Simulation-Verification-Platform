from __future__ import annotations

import os

import cleanroomx.gui as gui_module
from cleanroomx.gui import CleanroomXApp
from cleanroomx.project import (
    ProjectDocument,
    ProjectSaveConflictError,
    file_fingerprint,
    load_project_document,
    load_project_document_with_fingerprint,
    save_project_document,
)


class Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def test_guarded_project_save_rejects_external_content_change(tmp_path):
    path = save_project_document(tmp_path / "project.cleanroomx.json", ProjectDocument(name="Base"))
    _loaded, baseline = load_project_document_with_fingerprint(path)

    save_project_document(path, ProjectDocument(name="External"))
    external_bytes = path.read_bytes()

    try:
        save_project_document(
            path,
            ProjectDocument(name="Local"),
            expected_fingerprint=baseline,
        )
    except ProjectSaveConflictError as exc:
        assert exc.path == path
        assert exc.expected.same_content(baseline)
        assert not exc.expected.same_content(exc.current)
    else:
        raise AssertionError("stale project save should have been rejected")

    assert path.read_bytes() == external_bytes
    assert load_project_document(path).name == "External"


def test_guarded_project_save_accepts_metadata_only_timestamp_change(tmp_path):
    path = save_project_document(tmp_path / "project.cleanroomx.json", ProjectDocument(name="Base"))
    baseline = file_fingerprint(path)

    stat = path.stat()
    os.utime(
        path,
        ns=(stat.st_atime_ns + 1_000_000, stat.st_mtime_ns + 1_000_000),
    )
    touched = file_fingerprint(path)
    assert touched.mtime_ns != baseline.mtime_ns
    assert baseline.same_content(touched)

    save_project_document(
        path,
        ProjectDocument(name="Local"),
        expected_fingerprint=baseline,
    )
    assert load_project_document(path).name == "Local"


def test_guarded_project_save_rejects_deleted_baseline_file(tmp_path):
    path = save_project_document(tmp_path / "project.cleanroomx.json", ProjectDocument(name="Base"))
    baseline = file_fingerprint(path)
    path.unlink()

    try:
        save_project_document(
            path,
            ProjectDocument(name="Local"),
            expected_fingerprint=baseline,
        )
    except ProjectSaveConflictError as exc:
        assert exc.current.exists is False
    else:
        raise AssertionError("deleted project should be treated as a save conflict")

    assert not path.exists()


def test_load_returns_fingerprint_for_exact_loaded_bytes(tmp_path):
    path = save_project_document(tmp_path / "project.cleanroomx.json", ProjectDocument(name="Loaded"))

    project, fingerprint = load_project_document_with_fingerprint(path)

    assert project.name == "Loaded"
    assert fingerprint.same_content(file_fingerprint(path))
    assert fingerprint.sha256 is not None
    assert fingerprint.size == path.stat().st_size


def test_gui_save_blocks_stale_overwrite_and_preserves_dirty_state(tmp_path, monkeypatch):
    path = save_project_document(tmp_path / "project.cleanroomx.json", ProjectDocument(name="Base"))
    project, baseline = load_project_document_with_fingerprint(path)

    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = object()
    app.project = project
    app.project_path = path
    app._project_disk_fingerprint = baseline
    app._editor_analysis = lambda: None
    app.name_var = Value("Local")
    app.description_var = Value("")
    app.status_var = Value("")
    captured_saved_state = []
    explicit_saves = []
    app._capture_saved_state = lambda: captured_saved_state.append(True)
    app._notify_explicit_save = lambda saved_path: explicit_saves.append(saved_path)

    save_project_document(path, ProjectDocument(name="External"))
    external_bytes = path.read_bytes()

    errors = []
    monkeypatch.setattr(
        gui_module.messagebox,
        "showerror",
        lambda title, message, parent=None: errors.append((title, message, parent)),
    )

    app.save_project()

    assert path.read_bytes() == external_bytes
    assert load_project_document(path).name == "External"
    assert app.project.name == "Local"
    assert captured_saved_state == []
    assert explicit_saves == []
    assert app.status_var.value == "Save blocked — project changed on disk"
    assert errors and errors[0][0] == "Save conflict"
    assert "No project data was overwritten" in errors[0][1]


def test_gui_load_captures_disk_baseline_for_future_saves(tmp_path):
    path = save_project_document(tmp_path / "project.cleanroomx.json", ProjectDocument(name="Loaded"))

    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = object()
    app.project = ProjectDocument(name="Old")
    app.project_path = None
    app._project_disk_fingerprint = None
    app._recovery_source_path = None
    app._restored_recovery_artifact = None
    app._discard_current_autosave = lambda: None
    app._begin_autosave_project = lambda source: None
    app.name_var = Value("")
    app.description_var = Value("")
    app.status_var = Value("")
    app._clear_run_cache = lambda: None
    app._refresh_analysis_list = lambda: None
    app._capture_saved_state = lambda: None
    app._update_title = lambda: None

    app.load_project_path(path)

    assert app.project.name == "Loaded"
    assert app.project_path == path
    assert app._project_disk_fingerprint.same_content(file_fingerprint(path))
