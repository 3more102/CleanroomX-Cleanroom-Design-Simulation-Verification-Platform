from __future__ import annotations

from pathlib import Path

import cleanroomx.gui as gui_module
from cleanroomx.autosave import AutosaveManager, RecoveryScan
from cleanroomx.gui import CleanroomXApp
from cleanroomx.project import (
    AnalysisDocument,
    ProjectDocument,
    load_project_document,
    new_project,
    save_project_document,
)


class Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Text:
    def __init__(self, value=""):
        self.value = value

    def get(self, *args):
        return self.value

    def delete(self, *args):
        self.value = ""

    def insert(self, index, value):
        self.value = value

    def edit_modified(self, value):
        self.modified = value


class Tree:
    def __init__(self):
        self.selected = ()

    def exists(self, analysis_id):
        return analysis_id == "room-1"

    def selection_set(self, analysis_id):
        self.selected = (analysis_id,)

    def focus(self, analysis_id):
        self.focused = analysis_id

    def see(self, analysis_id):
        self.seen = analysis_id


class Manager:
    def __init__(self, recovery_dir):
        self.recovery_dir = recovery_dir
        self.begun = []
        self.discards = 0
        self.saved = []

    def begin_project(self, path):
        self.begun.append(path)

    def discard_current_recoveries(self):
        self.discards += 1

    def notify_explicit_save(self, path):
        self.saved.append(Path(path))


def _project() -> ProjectDocument:
    return ProjectDocument(
        name="Source Project",
        description="saved",
        analyses=[
            AnalysisDocument(
                id="room-1",
                name="Room",
                kind="room_verification",
                input={"value": 1},
            )
        ],
        active_analysis_id="room-1",
    )


def _make_recovery(tmp_path, editor_text):
    source = save_project_document(tmp_path / "source.cleanroomx.json", _project())
    recovery_dir = tmp_path / "recovery"
    writer = AutosaveManager(recovery_dir, session_id="crashed")
    try:
        writer.begin_project(source)
        writer.request_autosave(
            {
                "project": _project().to_dict(),
                "ui_state": {
                    "name_text": "Recovered Project",
                    "description_text": "unsaved description",
                    "editor_analysis_id": "room-1",
                    "editor_text": editor_text,
                    "editor_json_valid": editor_text == '{"value": 2}',
                },
            },
            source_path=source,
        )
        writer.wait_for_idle()
        artifact = writer.status().artifact_path
        assert artifact is not None
    finally:
        writer.shutdown(wait=True)
    return source, artifact, recovery_dir


def _app_for_restore(recovery_dir):
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.project = new_project()
    app.project_path = None
    app._recovery_source_path = None
    app._restored_recovery_artifact = None
    app._baseline_state = ""
    app._editor_analysis_id = None
    app._autosave_manager = Manager(recovery_dir)
    app.name_var = Value("Untitled Project")
    app.description_var = Value("")
    app.status_var = Value("")
    app.autosave_status_var = Value("")
    app.input_text = Text()
    app.analysis_tree = Tree()
    app._clear_run_cache = lambda: None
    app._refresh_analysis_list = lambda: None
    app.refresh_structure = lambda silent=False: None
    app._update_title = lambda: None
    return app


def test_restore_recovery_opens_protected_unsaved_copy_with_source_context(tmp_path):
    source, artifact, recovery_dir = _make_recovery(tmp_path, "{broken")
    source_before = source.read_bytes()
    app = _app_for_restore(recovery_dir)

    app.restore_recovery_path(artifact)

    assert app.project_path is None
    assert app._recovery_source_path == source.resolve()
    assert app._restored_recovery_artifact == artifact
    assert app._base_dir() == source.parent
    assert app.name_var.value == "Recovered Project"
    assert app.description_var.value == "unsaved description"
    assert app.input_text.value == "{broken"
    assert app.project.analysis_by_id("room-1").input == {"value": 1}
    assert app.project.active_analysis_id == "room-1"
    assert app._has_unsaved_changes() is True
    assert app._autosave_manager.discards == 1
    assert app._autosave_manager.begun == [source.resolve()]
    assert "Save Project As" in app.status_var.value
    assert source.read_bytes() == source_before
    assert artifact.exists()


def test_recovered_save_as_preserves_original_and_cleans_recovery(
    tmp_path, monkeypatch
):
    source, artifact, recovery_dir = _make_recovery(tmp_path, '{"value": 2}')
    source_before = source.read_bytes()
    app = _app_for_restore(recovery_dir)
    app.restore_recovery_path(artifact)
    app._load_analysis_into_editor = lambda analysis: None
    app._capture_saved_state = lambda: None
    app._update_title = lambda: None

    destination_dir = tmp_path / "restored"
    destination_dir.mkdir()
    destination = destination_dir / "restored.cleanroomx.json"
    monkeypatch.setattr(
        gui_module.filedialog,
        "asksaveasfilename",
        lambda **kwargs: str(destination),
    )

    app.save_project_as()

    assert source.read_bytes() == source_before
    assert destination.exists()
    saved = load_project_document(destination)
    assert saved.analysis_by_id("room-1").input == {"value": 2}
    assert app.project_path == destination
    assert app._recovery_source_path is None
    assert app._restored_recovery_artifact is None
    assert not artifact.exists()
    assert app._autosave_manager.saved == [destination]


def test_show_recovery_center_restores_selected_artifact(tmp_path, monkeypatch):
    source, artifact, recovery_dir = _make_recovery(tmp_path, '{"value": 2}')
    scan = gui_module.scan_recovery_artifacts(recovery_dir)

    class Root:
        def wait_window(self, dialog):
            self.dialog = dialog

    class Dialog:
        def __init__(self, parent, received_scan):
            assert received_scan == scan
            self.result = artifact

    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = Root()
    app.status_var = Value("")
    app._autosave_manager = Manager(recovery_dir)
    app._confirm_project_replacement = lambda: True
    restored = []
    app.restore_recovery_path = lambda path: restored.append(Path(path))
    monkeypatch.setattr(gui_module, "scan_recovery_artifacts", lambda directory: scan)
    monkeypatch.setattr(gui_module, "RecoveryCenter", Dialog)

    assert app.show_recovery_center() is True
    assert restored == [artifact]


def test_show_recovery_center_reports_empty_scan_without_dialog(tmp_path, monkeypatch):
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = object()
    app.status_var = Value("")
    app._autosave_manager = Manager(tmp_path / "recovery")
    monkeypatch.setattr(
        gui_module,
        "scan_recovery_artifacts",
        lambda directory: RecoveryScan(candidates=(), issues=()),
    )

    assert app.show_recovery_center() is False
    assert app.status_var.value == "No recoverable sessions found."


def test_startup_recovery_takes_precedence_over_requested_project(monkeypatch):
    events = []

    class Root:
        def mainloop(self):
            events.append("mainloop")

    class App:
        def __init__(self, root, *, autosave_interval_seconds):
            self.project = new_project()

        def offer_startup_recovery(self):
            events.append("recovery")
            return True

        def load_project_path(self, path):
            events.append(("load", path))

    monkeypatch.setattr(gui_module.tk, "Tk", Root)
    monkeypatch.setattr(gui_module, "CleanroomXApp", App)
    monkeypatch.setattr(gui_module, "validate_application_registry", lambda: None)

    assert gui_module.main(["requested.cleanroomx.json"]) == 0
    assert events == ["recovery", "mainloop"]
