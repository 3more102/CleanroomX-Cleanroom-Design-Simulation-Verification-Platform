from __future__ import annotations

import json

from cleanroomx.gui import CleanroomXApp
from cleanroomx.project import AnalysisDocument, ProjectDocument
from cleanroomx.project_history import ProjectEditHistory


class Value:
    def __init__(self, value=""):
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
        self.modified = bool(value)


def _app(project: ProjectDocument, editor_id: str, editor_text: str) -> CleanroomXApp:
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.project = project
    app.project_path = None
    app._running = False
    app._editor_analysis_id = editor_id
    app._project_history = ProjectEditHistory(limit=100)
    app._metadata_history_before = None
    app.name_var = Value(project.name)
    app.description_var = Value(project.description)
    app.input_text = Text(editor_text)
    app.status_var = Value()
    app.root = object()
    app._update_title = lambda: None
    app._clear_run_cache = lambda: None
    app.refresh_structure = lambda silent=False: None

    def refresh(select_id=None):
        target = select_id or app.project.active_analysis_id
        if target is None and app.project.analyses:
            target = app.project.analyses[0].id
        app._editor_analysis_id = target
        if target is None:
            app.input_text.value = ""
            return
        item = app.project.analysis_by_id(target)
        app.input_text.value = json.dumps(item.input, sort_keys=True)

    app._refresh_analysis_list = refresh
    app._load_analysis_into_editor = lambda item: (
        setattr(app, "_editor_analysis_id", item.id),
        setattr(app.input_text, "value", json.dumps(item.input, sort_keys=True)),
    )
    app._invalidate_last_run_for = lambda analysis_id: None
    app._base_dir = lambda: None
    return app


def test_import_input_is_project_undoable_and_restores_unsaved_raw_draft(tmp_path, monkeypatch):
    analysis = AnalysisDocument(
        id="room-1",
        name="Room",
        kind="room_verification",
        input={"stored": 1},
    )
    project = ProjectDocument(
        name="Import history",
        analyses=[analysis],
        active_analysis_id=analysis.id,
    )
    app = _app(project, analysis.id, '{"draft": 2}')

    source = tmp_path / "input.json"
    source.write_text('{"imported": 3}\n', encoding="utf-8")
    monkeypatch.setattr(
        "cleanroomx.gui.filedialog.askopenfilename",
        lambda **kwargs: str(source),
    )

    app.import_input_json()

    assert app.project.analysis_by_id("room-1").input == {"imported": 3}
    assert app._project_history.can_undo is True

    assert app.undo_project_edit() is True
    assert app.project.analysis_by_id("room-1").input == {"stored": 1}
    assert app.input_text.value == '{"draft": 2}'
    assert app.status_var.value == "Undo: Import input for Room"

    assert app.redo_project_edit() is True
    assert app.project.analysis_by_id("room-1").input == {"imported": 3}
    assert app.status_var.value == "Redo: Import input for Room"


def test_remove_analysis_is_undoable_with_identity_and_editor_state(monkeypatch):
    first = AnalysisDocument(
        id="room-1",
        name="Room 1",
        kind="room_verification",
        input={"value": 1},
    )
    second = AnalysisDocument(
        id="room-2",
        name="Room 2",
        kind="room_verification",
        input={"value": 2},
    )
    project = ProjectDocument(
        name="Delete history",
        analyses=[first, second],
        active_analysis_id=second.id,
    )
    app = _app(project, second.id, '{"unsaved": 22}')
    app._current_analysis = lambda: app.project.analysis_by_id("room-2")
    monkeypatch.setattr(
        "cleanroomx.gui.messagebox.askyesno",
        lambda *args, **kwargs: True,
    )

    app.remove_analysis()

    assert [item.id for item in app.project.analyses] == ["room-1"]
    assert app._project_history.can_undo is True

    assert app.undo_project_edit() is True
    assert [item.id for item in app.project.analyses] == ["room-1", "room-2"]
    assert app.project.active_analysis_id == "room-2"
    assert app._editor_analysis_id == "room-2"
    assert app.input_text.value == '{"unsaved": 22}'


def test_project_shortcuts_leave_json_and_spatial_local_histories_alone():
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.input_text = object()
    canvas_2d = object()
    canvas_3d = object()
    app.spatial_workspace = type(
        "Workspace",
        (),
        {"canvas_2d": canvas_2d, "canvas_3d": canvas_3d},
    )()
    focus = Value(app.input_text)
    app.root = type("Root", (), {"focus_get": lambda self: focus.value})()
    calls = []
    app.undo_project_edit = lambda: calls.append("undo") or True
    app.redo_project_edit = lambda: calls.append("redo") or True

    assert app._on_project_undo_shortcut() is None
    assert calls == []

    focus.value = canvas_2d
    assert app._on_project_redo_shortcut() is None
    assert calls == []

    focus.value = object()
    assert app._on_project_undo_shortcut() == "break"
    assert app._on_project_redo_shortcut() == "break"
    assert calls == ["undo", "redo"]


def test_project_undo_is_blocked_while_backend_run_is_active(monkeypatch):
    app = CleanroomXApp.__new__(CleanroomXApp)
    app._running = True
    app.root = object()
    app._project_history = ProjectEditHistory()
    warnings = []
    monkeypatch.setattr(
        "cleanroomx.gui.messagebox.showwarning",
        lambda *args, **kwargs: warnings.append((args, kwargs)),
    )

    assert app.undo_project_edit() is False
    assert warnings


def test_local_editor_or_spatial_edit_invalidates_stale_project_history():
    project = ProjectDocument(name="Boundary")
    app = _app(project, editor_id=None, editor_text="")
    before = app._capture_project_history_state()
    app.name_var.value = "Boundary 2"
    assert app._record_project_edit(before, "Rename project") is True
    assert app._project_history.can_undo is True

    app._invalidate_project_history_for_local_edit()
    assert app._project_history.can_undo is False
    assert app._project_history.can_redo is False
