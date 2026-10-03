from __future__ import annotations

from dataclasses import replace
import json
import multiprocessing

import pytest

import cleanroomx.gui as gui_module
import cleanroomx.project as project_module
import cleanroomx.strict_json as strict_json_module
from cleanroomx.gui import CleanroomXApp
from cleanroomx.persistence import AtomicWriteDurabilityError
from cleanroomx.project import (
    ProjectDocument,
    ProjectFileBusyError,
    ProjectFormatError,
    ProjectSaveDurabilityError,
    ProjectWriteConflictError,
    capture_project_file_revision,
    load_project_document,
    load_project_document_with_revision,
    load_project_document_with_revision_info,
    project_file_revision_matches,
    project_save_lock,
    project_save_lock_path,
    save_project_document,
    save_project_document_guarded,
)



def _hold_project_save_lock(path: str, ready, release) -> None:
    with project_save_lock(path):
        ready.set()
        if not release.wait(15):
            raise RuntimeError("test lock holder timed out waiting for release")


class Value:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def test_stable_load_retries_when_snapshot_reports_revision_change(
    tmp_path, monkeypatch
):
    path = tmp_path / "project.cleanroomx.json"
    save_project_document(path, ProjectDocument(name="First"))
    original_snapshot = project_module.load_strict_json_snapshot
    calls = {"count": 0}

    def changing_snapshot(source, *, max_bytes=None):
        if calls["count"] == 0:
            calls["count"] += 1
            save_project_document(path, ProjectDocument(name="Second"))
            raise project_module.StrictJSONFileChangedError(
                f"{source} changed while reading JSON input"
            )
        calls["count"] += 1
        return original_snapshot(source, max_bytes=max_bytes)

    monkeypatch.setattr(
        project_module,
        "load_strict_json_snapshot",
        changing_snapshot,
    )

    project, revision = load_project_document_with_revision(path)

    assert calls["count"] == 2
    assert project.name == "Second"
    assert revision == capture_project_file_revision(path)


def test_legacy_project_load_retries_changed_snapshot(tmp_path, monkeypatch):
    path = tmp_path / "project.cleanroomx.json"
    save_project_document(path, ProjectDocument(name="First"))
    original_snapshot = project_module.load_strict_json_snapshot
    calls = {"count": 0}

    def changing_snapshot(source, *, max_bytes=None):
        if calls["count"] == 0:
            calls["count"] += 1
            save_project_document(path, ProjectDocument(name="Second"))
            raise project_module.StrictJSONFileChangedError(
                f"{source} changed while reading JSON input"
            )
        calls["count"] += 1
        return original_snapshot(source, max_bytes=max_bytes)

    monkeypatch.setattr(
        project_module,
        "load_strict_json_snapshot",
        changing_snapshot,
    )

    project = load_project_document(path)

    assert calls["count"] == 2
    assert project.name == "Second"


def test_migration_aware_stable_load_retries_and_rebinds_provenance(
    tmp_path, monkeypatch
):
    path = tmp_path / "legacy.cleanroomx.json"
    path.write_text(
        json.dumps({
            "schema": "cleanroomx.project",
            "schema_version": 0,
            "name": "Legacy",
            "analysis": {
                "id": "a1",
                "name": "Room",
                "kind": "room_verification",
                "input": {},
            },
        }),
        encoding="utf-8",
    )
    original_snapshot = project_module.load_strict_json_snapshot
    calls = {"count": 0}

    def changing_snapshot(source, *, max_bytes=None):
        if calls["count"] == 0:
            calls["count"] += 1
            save_project_document(path, ProjectDocument(name="Current"))
            raise project_module.StrictJSONFileChangedError(
                f"{source} changed while reading JSON input"
            )
        calls["count"] += 1
        return original_snapshot(source, max_bytes=max_bytes)

    monkeypatch.setattr(
        project_module,
        "load_strict_json_snapshot",
        changing_snapshot,
    )

    project, revision, migration_info = load_project_document_with_revision_info(path)

    assert calls["count"] == 2
    assert project.name == "Current"
    assert migration_info.migrated is False
    assert migration_info.source_schema_version == 1
    assert revision == capture_project_file_revision(path)


def test_revision_aware_load_cannot_bind_separate_transient_parse(tmp_path, monkeypatch):
    path = tmp_path / "project.cleanroomx.json"
    save_project_document(path, ProjectDocument(name="First"))
    original_load = project_module.load_project_document
    calls = {"count": 0}

    def transient_separate_load(source):
        calls["count"] += 1
        save_project_document(path, ProjectDocument(name="Transient"))
        loaded = original_load(source)
        save_project_document(path, ProjectDocument(name="First"))
        return loaded

    monkeypatch.setattr(
        project_module,
        "load_project_document",
        transient_separate_load,
    )

    project, revision = load_project_document_with_revision(path)

    assert calls["count"] == 0
    assert project.name == "First"
    assert revision == capture_project_file_revision(path)


def test_revision_aware_load_binds_revision_to_bytes_supplied_to_parser(
    tmp_path, monkeypatch
):
    path = tmp_path / "project.cleanroomx.json"
    alternate = tmp_path / "alternate.cleanroomx.json"
    save_project_document(path, ProjectDocument(name="Parsed snapshot"))
    save_project_document(alternate, ProjectDocument(name="Later path contents"))
    parsed_bytes = path.read_bytes()
    later_bytes = alternate.read_bytes()
    original_parser = strict_json_module.strict_json_loads
    parser_inputs = []

    def mutate_path_after_verified_read(text):
        raw = text.encode("utf-8")
        parser_inputs.append(raw)
        path.write_bytes(later_bytes)
        return original_parser(text)

    monkeypatch.setattr(
        strict_json_module,
        "strict_json_loads",
        mutate_path_after_verified_read,
    )

    project, revision = load_project_document_with_revision(path, attempts=1)

    assert parser_inputs == [parsed_bytes]
    assert project.name == "Parsed snapshot"
    assert revision.size == len(parsed_bytes)
    assert revision.sha256 == project_module.sha256(parsed_bytes).hexdigest()
    assert path.read_bytes() == later_bytes
    assert revision.sha256 != project_module.sha256(later_bytes).hexdigest()


def test_revision_aware_load_preserves_project_invalid_utf8_diagnostic(tmp_path):
    path = tmp_path / "invalid-utf8.cleanroomx.json"
    path.write_bytes(b'{"schema":"cleanroomx.project","name":"\xff"}')

    with pytest.raises(
        ProjectFormatError,
        match="project file must contain valid UTF-8 text",
    ) as raised:
        load_project_document_with_revision(path)

    assert "invalid byte sequence at offset" in str(raised.value)
    assert isinstance(raised.value.__cause__, strict_json_module.StrictJSONError)
    assert isinstance(raised.value.__cause__.__cause__, UnicodeDecodeError)


def test_revision_aware_load_preserves_project_size_ceiling(tmp_path, monkeypatch):
    path = tmp_path / "oversized.cleanroomx.json"
    path.write_bytes(b"x" * 65)
    monkeypatch.setattr(project_module, "PROJECT_FILE_MAX_BYTES", 64)

    with pytest.raises(OSError, match="exceeds maximum supported size"):
        load_project_document_with_revision(path)


def test_revision_aware_load_rejects_live_path_replacement(tmp_path, monkeypatch):
    path = tmp_path / "project.cleanroomx.json"
    save_project_document(path, ProjectDocument(name="Stable"))
    replacement = tmp_path / "replacement.cleanroomx.json"
    save_project_document(replacement, ProjectDocument(name="Replacement"))
    real_stat = strict_json_module.Path.stat
    replacement_stat = real_stat(replacement)
    normalized = path.resolve(strict=False)

    def report_replacement(self, *args, **kwargs):
        if self == normalized:
            return replacement_stat
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(strict_json_module.Path, "stat", report_replacement)

    with pytest.raises(OSError, match="changed repeatedly while opening"):
        load_project_document_with_revision(path, attempts=1)


def test_revision_aware_load_rejects_live_path_disappearance(tmp_path, monkeypatch):
    path = tmp_path / "project.cleanroomx.json"
    save_project_document(path, ProjectDocument(name="Stable"))
    real_stat = strict_json_module.Path.stat
    normalized = path.resolve(strict=False)

    def disappear(self, *args, **kwargs):
        if self == normalized:
            raise FileNotFoundError(str(normalized))
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(strict_json_module.Path, "stat", disappear)

    with pytest.raises(OSError, match="changed repeatedly while opening"):
        load_project_document_with_revision(path, attempts=1)


def test_revision_aware_load_rejects_opened_file_revision_change(
    tmp_path, monkeypatch
):
    path = tmp_path / "project.cleanroomx.json"
    save_project_document(path, ProjectDocument(name="Stable"))
    larger = tmp_path / "larger.cleanroomx.json"
    larger.write_bytes(path.read_bytes() + b" ")
    original_stat = path.stat()
    larger_stat = larger.stat()
    real_fstat = strict_json_module.os.fstat
    calls = {"count": 0}

    def changing_fstat(fd):
        calls["count"] += 1
        if calls["count"] == 1:
            return original_stat
        if calls["count"] == 2:
            return larger_stat
        return real_fstat(fd)

    monkeypatch.setattr(strict_json_module.os, "fstat", changing_fstat)

    with pytest.raises(OSError, match="changed repeatedly while opening"):
        load_project_document_with_revision(path, attempts=1)


def test_revision_capture_rejects_transient_path_descriptor_substitution(
    tmp_path, monkeypatch
):
    source = tmp_path / "project.cleanroomx.json"
    replacement = tmp_path / "replacement.cleanroomx.json"
    original_bytes = b'{"revision":1}\n'
    replacement_bytes = b'{"revision":2}\n'
    assert len(original_bytes) == len(replacement_bytes)
    source.write_bytes(original_bytes)
    replacement.write_bytes(replacement_bytes)

    original_open = project_module.Path.open
    substituted = False

    def transient_replacement_open(self, *args, **kwargs):
        nonlocal substituted
        mode = args[0] if args else kwargs.get("mode", "r")
        if self == source and mode == "rb" and not substituted:
            substituted = True
            return original_open(replacement, *args, **kwargs)
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(project_module.Path, "open", transient_replacement_open)

    revision = capture_project_file_revision(source)

    assert substituted is True
    assert revision.exists is True
    assert revision.size == len(original_bytes)
    assert revision.sha256 == project_module.sha256(original_bytes).hexdigest()
    assert revision.sha256 != project_module.sha256(replacement_bytes).hexdigest()


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



def test_project_save_lock_is_stable_adjacent_and_persistent(tmp_path):
    path = tmp_path / "project.cleanroomx.json"
    lock_path = project_save_lock_path(path)
    assert lock_path.parent == tmp_path.resolve()
    assert lock_path.name.startswith(".cleanroomx-save-")
    assert lock_path.name.endswith(".lock")

    with project_save_lock(path) as acquired:
        assert acquired == lock_path
        assert acquired.exists()

    assert lock_path.exists()


def test_guarded_save_refuses_concurrent_cleanroomx_writer_across_processes(tmp_path):
    path = tmp_path / "project.cleanroomx.json"
    save_project_document(path, ProjectDocument(name="Opened"))
    expected = capture_project_file_revision(path)

    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    release = context.Event()
    holder = context.Process(
        target=_hold_project_save_lock,
        args=(str(path), ready, release),
    )
    holder.start()
    try:
        assert ready.wait(10), "child process did not acquire project save lock"
        with pytest.raises(ProjectFileBusyError):
            save_project_document_guarded(
                path,
                ProjectDocument(name="Contending writer"),
                expected_revision=expected,
            )
        assert load_project_document(path).name == "Opened"
    finally:
        release.set()
        holder.join(10)
        if holder.is_alive():
            holder.terminate()
            holder.join(5)

    assert holder.exitcode == 0


def test_guarded_save_reports_committed_revision_when_directory_durability_fails(
    tmp_path, monkeypatch
):
    path = tmp_path / "project.cleanroomx.json"
    save_project_document(path, ProjectDocument(name="Opened"))
    expected = capture_project_file_revision(path)

    def committed_but_uncertain(target, text, *, before_replace=None):
        if before_replace is not None:
            before_replace()
        target = project_module.Path(target)
        target.write_text(text, encoding="utf-8")
        raise AtomicWriteDurabilityError(target, OSError("injected directory fsync failure"))

    monkeypatch.setattr(
        project_module,
        "_shared_atomic_write_text",
        committed_but_uncertain,
    )

    with pytest.raises(ProjectSaveDurabilityError) as exc_info:
        save_project_document_guarded(
            path,
            ProjectDocument(name="Committed"),
            expected_revision=expected,
        )

    assert load_project_document(path).name == "Committed"
    assert exc_info.value.committed_revision == capture_project_file_revision(path)


def test_gui_save_reports_busy_project_without_writing(tmp_path, monkeypatch):
    path = tmp_path / "project.cleanroomx.json"
    save_project_document(path, ProjectDocument(name="Opened"))
    app = _minimal_gui_app(path, ProjectDocument(name="Window edit"))

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

    with project_save_lock(path):
        app.save_project()

    assert load_project_document(path).name == "Opened"
    assert errors == []
    assert warnings
    assert warnings[-1][0] == "Project save in progress"
    assert "another CleanroomX process" in app.status_var.value
