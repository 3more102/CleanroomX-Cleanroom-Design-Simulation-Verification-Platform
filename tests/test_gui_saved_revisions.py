from __future__ import annotations

from pathlib import Path

import cleanroomx.gui as gui_module
from cleanroomx.gui import CleanroomXApp
from cleanroomx.project import (
    AnalysisDocument,
    ProjectDocument,
    save_project_document,
)
from cleanroomx.saved_revisions import (
    SavedRevisionScan,
    archive_project_revision,
    scan_saved_revisions,
)


class Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def _project(name="Saved Project") -> ProjectDocument:
    return ProjectDocument(
        name=name,
        description="historical",
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


def _make_saved_revision(tmp_path):
    source = save_project_document(tmp_path / "source.cleanroomx.json", _project())
    revisions = tmp_path / "revisions"
    artifact = archive_project_revision(source, revision_dir=revisions)
    assert artifact is not None
    return source, artifact, revisions


def test_restore_saved_revision_opens_unsaved_copy_with_source_context(tmp_path):
    source, artifact, _revisions = _make_saved_revision(tmp_path)
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.project = _project("Current")
    app.project_path = source
    app._recovery_source_path = None
    app._restored_recovery_artifact = None
    app._restored_saved_revision_artifact = None
    app.name_var = Value("Current")
    app.description_var = Value("")
    app.status_var = Value("")
    app.autosave_status_var = Value("")
    events = []
    app._discard_current_autosave = lambda: events.append("discard")
    app._begin_autosave_project = lambda path: events.append(("begin", Path(path)))
    app._clear_run_cache = lambda: events.append("clear")
    app._refresh_analysis_list = lambda: events.append("refresh")
    app._update_title = lambda: events.append("title")

    app.restore_saved_revision_path(artifact)

    assert app.project_path is None
    assert app._recovery_source_path == source.resolve()
    assert app._restored_recovery_artifact is None
    assert app._restored_saved_revision_artifact == artifact
    assert app.project.name == "Saved Project"
    assert app.name_var.value == "Saved Project"
    assert app.description_var.value == "historical"
    assert app._baseline_state == "__cleanroomx_saved_revision_requires_save_as__"
    assert "Save Project As" in app.status_var.value
    assert app.autosave_status_var.value == "Autosave: saved-version copy"
    assert events == [
        "discard",
        ("begin", source.resolve()),
        "clear",
        "refresh",
        "title",
    ]


def test_show_saved_versions_restores_selected_artifact(tmp_path, monkeypatch):
    source, artifact, revisions = _make_saved_revision(tmp_path)
    scan = scan_saved_revisions(source, revisions)

    class Root:
        def wait_window(self, dialog):
            self.dialog = dialog

    class Dialog:
        def __init__(self, parent, received_scan):
            assert received_scan == scan
            self.result = artifact

    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = Root()
    app.project_path = source
    app._recovery_source_path = None
    app._restored_saved_revision_artifact = None
    app.status_var = Value("")
    app._confirm_project_replacement = lambda: True
    restored = []
    app.restore_saved_revision_path = lambda path: restored.append(Path(path))

    monkeypatch.setattr(gui_module, "scan_saved_revisions", lambda path: scan)
    monkeypatch.setattr(gui_module, "SavedVersionsCenter", Dialog)

    assert app.show_saved_versions() is True
    assert restored == [artifact]


def test_show_saved_versions_reports_unsaved_project_without_scanning(monkeypatch):
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.project_path = None
    app._recovery_source_path = None
    app._restored_saved_revision_artifact = None
    app.status_var = Value("")

    monkeypatch.setattr(
        gui_module,
        "scan_saved_revisions",
        lambda path: (_ for _ in ()).throw(
            AssertionError("unsaved projects must not scan revision history")
        ),
    )

    assert app.show_saved_versions() is False
    assert "Save the project" in app.status_var.value


def test_restored_saved_revision_save_as_refuses_original_source(tmp_path, monkeypatch):
    source, artifact, _revisions = _make_saved_revision(tmp_path)
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = object()
    app.project = _project()
    app.project_path = None
    app._recovery_source_path = source.resolve()
    app._restored_recovery_artifact = None
    app._restored_saved_revision_artifact = artifact
    app._editor_analysis_id = None
    app.name_var = Value(app.project.name)
    app.description_var = Value(app.project.description)
    app._editor_analysis = lambda: None
    app._sync_metadata = lambda: None
    app._base_dir = lambda: source.parent
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
        "save_project_document_with_revision",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("restored first save must not overwrite source")
        ),
    )

    app.save_project_as()

    assert warnings
    assert "different" in warnings[0][0].lower()
