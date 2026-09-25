from __future__ import annotations

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
    def __init__(self, value):
        self.value = value

    def get(self, *args):
        return self.value


def _app() -> CleanroomXApp:
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.project = ProjectDocument(
        name="Demo",
        analyses=[
            AnalysisDocument(
                id="a",
                name="Analysis A",
                kind="room_verification",
                input={"value": 1},
            )
        ],
        active_analysis_id="a",
        metadata={"spatial_layout": {"version": 1, "rooms": []}},
    )
    app._editor_analysis_id = "a"
    app.input_text = Text('{"value": 2}')
    app.name_var = Value("Demo")
    app.description_var = Value("")
    app._project_history = ProjectEditHistory(
        preserved_metadata_keys={"spatial_layout"}
    )
    app._update_project_history_controls = lambda: None
    app._runs_by_analysis = {}
    app.last_run = None
    app.last_run_analysis_id = None
    return app


def test_commit_editor_records_reversible_project_edit():
    app = _app()

    app._commit_editor()

    assert app.project.analysis_by_id("a").input == {"value": 2}
    assert app._project_history.undo_description == "Edit Analysis A input"

    restored, description = app._project_history.undo(app.project)
    assert description == "Edit Analysis A input"
    assert restored.analysis_by_id("a").input == {"value": 1}


def test_project_undo_restores_document_and_invalidates_cached_results():
    app = _app()
    before = app._project_history_snapshot()
    app.project.analysis_by_id("a").input = {"value": 3}
    app._record_project_history(before, "Edit Analysis A input")

    app.input_text = Text('{"value": 3}')
    app._commit_editor = lambda *args, **kwargs: app.project.analysis_by_id("a")
    app._running = False
    app.root = object()
    app.status_var = Value()
    app.project_path = None
    app._baseline_state = None
    app._runs_by_analysis = {"a": object()}
    app.last_run = app._runs_by_analysis["a"]
    app.last_run_analysis_id = "a"
    cleared = []
    app._clear_run_cache = lambda: (cleared.append(True), app._runs_by_analysis.clear())
    app._refresh_analysis_list = lambda select_id=None: None
    app._update_title = lambda: None

    app.undo_project_edit()

    assert app.project.analysis_by_id("a").input == {"value": 1}
    assert cleared == [True]
    assert app._runs_by_analysis == {}
    assert app.status_var.value == "Undo: Edit Analysis A input"


def test_project_history_clear_is_used_for_new_document_boundaries():
    app = _app()
    before = app._project_history_snapshot()
    app.project.analysis_by_id("a").input = {"value": 2}
    app._record_project_history(before, "Edit Analysis A input")
    assert app._project_history.can_undo

    app._clear_project_history()

    assert app._project_history.can_undo is False
    assert app._project_history.can_redo is False
