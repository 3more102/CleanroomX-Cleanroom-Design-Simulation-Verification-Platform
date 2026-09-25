from __future__ import annotations

from pathlib import Path

import cleanroomx.gui as gui_module
from cleanroomx.autosave import (
    AutosaveManager,
    RecoveryCandidate,
    RecoveryScan,
)
from cleanroomx.gui import CleanroomXApp
from cleanroomx.project import AnalysisDocument, ProjectDocument, save_project_document


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
        self.modified = False

    def get(self, *args):
        return self.value

    def delete(self, *args):
        self.value = ""

    def insert(self, index, value):
        self.value = value

    def edit_modified(self, value=None):
        if value is None:
            return self.modified
        self.modified = value


class Root:
    def __init__(self):
        self.waited = None
        self.title_value = None

    def wait_window(self, dialog):
        self.waited = dialog

    def title(self, value):
        self.title_value = value


def _project() -> ProjectDocument:
    return ProjectDocument(
        name="Recovery Project",
        analyses=[
            AnalysisDocument(
                id="a",
                name="Room",
                kind="room_verification",
                input={"value": 1},
            )
        ],
        active_analysis_id="a",
    )


def _write_prior_session_recovery(tmp_path, *, editor_text="{broken"):
    source = save_project_document(tmp_path / "source.cleanroomx.json", _project())
    recovery_dir = tmp_path / "recovery"
    manager = AutosaveManager(recovery_dir, session_id="prior-session")
    try:
        manager.begin_project(source)
        snapshot = {
            "project": _project().to_dict(),
            "ui_state": {
                "name_text": "Recovered Draft",
                "description_text": "Recovered unsaved work",
                "editor_analysis_id": "a",
                "editor_text": editor_text,
                "editor_json_valid": False,
            },
        }
        manager.request_autosave(snapshot, source_path=source)
        manager.wait_for_idle()
        artifact = manager.status().artifact_path
        assert artifact is not None
    finally:
        manager.shutdown(wait=True)
    return source, recovery_dir, artifact


def test_restore_recovery_opens_protected_working_copy_and_preserves_raw_draft(tmp_path):
    source, recovery_dir, artifact = _write_prior_session_recovery(tmp_path)
    source_before = source.read_bytes()
    current_manager = AutosaveManager(recovery_dir, session_id="current-session")
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = Root()
    app.project = ProjectDocument(name="Current")
    app.project_path = None
    app._baseline_state = None
    app._recovery_requires_save_as = False
    app._restored_recovery_path = None
    app._recovery_source_path = None
    app._recovery_source_relation = None
    app._autosave_manager = current_manager
    app._editor_analysis_id = None
    app.name_var = Value("Current")
    app.description_var = Value("")
    app.status_var = Value("")
    app.autosave_status_var = Value("")
    app.input_text = Text("")
    app._clear_run_cache = lambda: None
    app.refresh_structure = lambda silent=False: None
    app._update_title = lambda: None

    def refresh(select_id=None):
        app._editor_analysis_id = select_id

    app._refresh_analysis_list = refresh

    try:
        app.restore_recovery_path(artifact)

        assert app.project.name == "Recovery Project"
        assert app.project.analysis_by_id("a").input == {"value": 1}
        assert app.project_path == source.resolve()
        assert app._recovery_requires_save_as is True
        assert app._restored_recovery_path == artifact
        assert app._recovery_source_path == source.resolve()
        assert app.name_var.value == "Recovered Draft"
        assert app.description_var.value == "Recovered unsaved work"
        assert app.input_text.value == "{broken"
        assert "original preserved" in app.status_var.value
        assert source.read_bytes() == source_before
    finally:
        current_manager.shutdown(wait=True)


def test_save_project_routes_recovered_working_copy_to_save_as():
    app = CleanroomXApp.__new__(CleanroomXApp)
    app._recovery_requires_save_as = True
    calls = []
    app.save_project_as = lambda: calls.append("save-as")

    app.save_project()

    assert calls == ["save-as"]


def test_recovered_first_save_cannot_target_original_source(tmp_path, monkeypatch):
    source = save_project_document(tmp_path / "source.cleanroomx.json", _project())
    before = source.read_bytes()
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = object()
    app.project = _project()
    app.project_path = source
    app._editor_analysis_id = None
    app._recovery_requires_save_as = True
    app._recovery_source_path = source.resolve()
    app._recovery_source_relation = "source_newer"
    app.name_var = Value(app.project.name)
    app.description_var = Value("")
    app._sync_metadata = lambda: None
    app._editor_analysis = lambda: None

    warnings = []
    monkeypatch.setattr(
        gui_module.filedialog,
        "asksaveasfilename",
        lambda **kwargs: str(source),
    )
    monkeypatch.setattr(
        gui_module.messagebox,
        "showwarning",
        lambda title, message, parent=None: warnings.append((title, message)),
    )
    monkeypatch.setattr(
        gui_module,
        "save_project_document",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("recovery source must not be overwritten")
        ),
    )

    app.save_project_as()

    assert source.read_bytes() == before
    assert warnings
    assert "different file name" in warnings[0][1]


def test_startup_recovery_dialog_can_select_candidate_for_restore(tmp_path, monkeypatch):
    artifact = tmp_path / "recovery" / "candidate.recovery.json"
    candidate = RecoveryCandidate(
        path=artifact,
        project_identity="file-123",
        saved_at_utc="2026-09-25T09:00:00Z",
        project_name="Recovered",
        source_path=tmp_path / "project.cleanroomx.json",
        source_relation="source_changed",
        source_is_newer=False,
    )
    scan = RecoveryScan(candidates=(candidate,), issues=())

    class Manager:
        recovery_dir = tmp_path / "recovery"

    class Dialog:
        def __init__(self, parent, supplied_scan, *, recovery_dir):
            assert supplied_scan == scan
            assert recovery_dir == Manager.recovery_dir
            self.result_path = artifact

    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = Root()
    app._autosave_manager = Manager()
    restored = []
    app.restore_recovery_path = lambda path: restored.append(path)

    monkeypatch.setattr(gui_module, "scan_recovery_artifacts", lambda path: scan)
    monkeypatch.setattr(gui_module, "RecoveryDialog", Dialog)

    app.offer_startup_recovery()

    assert restored == [artifact]
    assert app.root.waited is not None


def test_recovery_window_title_is_visibly_marked():
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = Root()
    app.project_path = Path("/tmp/source.cleanroomx.json")
    app._recovery_requires_save_as = True
    app._has_unsaved_changes = lambda: True

    app._update_title()

    assert "[Recovered]" in app.root.title_value
    assert app.root.title_value.endswith("*")
