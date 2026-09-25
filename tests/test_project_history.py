from __future__ import annotations

import copy
import json

import pytest

from cleanroomx.gui import CleanroomXApp
from cleanroomx.project import AnalysisDocument, ProjectDocument
from cleanroomx.project_history import ProjectEditHistory
from cleanroomx.spatial import SPATIAL_METADATA_KEY, empty_layout


def _project_document(value: int) -> dict:
    return ProjectDocument(
        name="History",
        analyses=[
            AnalysisDocument(
                id="analysis-a",
                name="Analysis A",
                kind="room_verification",
                input={"value": value},
            )
        ],
        active_analysis_id="analysis-a",
    ).to_dict()


def test_project_history_round_trip_is_bounded_and_snapshot_isolated():
    history = ProjectEditHistory(limit=2)
    before = _project_document(1)
    after = _project_document(2)

    captured = history.capture(before, "analysis-a")
    assert history.record(
        before=captured,
        after_document=after,
        after_editor_analysis_id="analysis-a",
        description="Edit input",
    )

    before["analyses"][0]["input"]["value"] = 99
    after["analyses"][0]["input"]["value"] = 88

    restored, description = history.undo()
    assert description == "Edit input"
    assert restored.document["analyses"][0]["input"]["value"] == 1
    restored.document["analyses"][0]["input"]["value"] = 77

    replayed, description = history.redo()
    assert description == "Edit input"
    assert replayed.document["analyses"][0]["input"]["value"] == 2
    assert replayed.editor_analysis_id == "analysis-a"

    assert history.undo() is not None
    assert history.record(
        before=history.capture(_project_document(1), "analysis-a"),
        after_document=_project_document(3),
        after_editor_analysis_id="analysis-a",
        description="Edit again",
    )
    assert history.can_redo is False

    assert history.record(
        before=history.capture(_project_document(3), "analysis-a"),
        after_document=_project_document(4),
        after_editor_analysis_id="analysis-a",
        description="Edit third",
    )
    assert history.record(
        before=history.capture(_project_document(4), "analysis-a"),
        after_document=_project_document(5),
        after_editor_analysis_id="analysis-a",
        description="Edit fourth",
    )
    assert history.undo_description == "Edit fourth"
    assert history.undo() is not None
    oldest_retained, _ = history.undo()
    assert oldest_retained.document["analyses"][0]["input"]["value"] == 3
    assert history.undo() is None


def test_project_history_ignores_editor_focus_only_noop():
    history = ProjectEditHistory()
    document = _project_document(1)
    before = history.capture(document, "analysis-a")

    assert (
        history.record(
            before=before,
            after_document=copy.deepcopy(document),
            after_editor_analysis_id=None,
            description="Focus change",
        )
        is False
    )
    assert history.can_undo is False
    assert history.can_redo is False


def test_project_transaction_rolls_back_model_and_history_when_mutation_fails():
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.project = ProjectDocument(name="Before")
    app._editor_analysis_id = None
    app._project_history = ProjectEditHistory()
    original = copy.deepcopy(app.project)

    def failing_mutation() -> None:
        app.project.name = "Partially mutated"
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        app._perform_project_edit("Failing edit", failing_mutation)

    assert app.project == original
    assert app._project_history.can_undo is False
    assert app._project_history.can_redo is False


def test_project_transaction_rolls_back_invalid_post_edit_state():
    analysis = AnalysisDocument(
        id="analysis-a",
        name="Analysis A",
        kind="room_verification",
        input={},
    )
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.project = ProjectDocument(
        name="Before",
        analyses=[analysis],
        active_analysis_id=analysis.id,
    )
    app._editor_analysis_id = analysis.id
    app._project_history = ProjectEditHistory()
    original = copy.deepcopy(app.project)

    def invalid_mutation() -> None:
        app.project.analyses.append(
            AnalysisDocument(
                id="analysis-a",
                name="Duplicate",
                kind="room_verification",
                input={},
            )
        )

    with pytest.raises(ValueError, match="unique"):
        app._perform_project_edit("Invalid duplicate", invalid_mutation)

    assert app.project == original
    assert app._project_history.can_undo is False


class _Value:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def _history_restore_app(project: ProjectDocument) -> CleanroomXApp:
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.project = project
    app._project_history = ProjectEditHistory()
    app._editor_analysis_id = project.active_analysis_id
    app.name_var = _Value(project.name)
    app.description_var = _Value(project.description)
    app.status_var = _Value("")
    app._runs_by_analysis = {}
    app.last_run = None
    app.last_run_analysis_id = None
    app.result_text = object()
    app.report_text = object()
    app.diagnostics_text = object()
    app._set_text = lambda widget, value: None
    app._draw_plot = lambda: None
    app._update_title = lambda: None
    app._update_project_history_controls = lambda: None

    def refresh(select_id=None):
        app._editor_analysis_id = select_id or app.project.active_analysis_id

    app._refresh_analysis_list = refresh
    return app


def test_project_history_restore_preserves_separate_spatial_history_state():
    layout = empty_layout()
    layout["rooms"] = [
        {
            "id": "room-a",
            "name": "Room A",
            "x_m": 1.0,
            "y_m": 0.0,
            "length_m": 4.0,
            "width_m": 4.0,
            "height_m": 3.0,
        }
    ]
    analysis_a = AnalysisDocument(
        id="analysis-a", name="A", kind="room_verification", input={"value": 1}
    )
    analysis_b = AnalysisDocument(
        id="analysis-b", name="B", kind="room_verification", input={"value": 2}
    )
    app = _history_restore_app(
        ProjectDocument(
            name="History",
            analyses=[analysis_a, analysis_b],
            active_analysis_id=analysis_b.id,
            metadata={SPATIAL_METADATA_KEY: layout},
        )
    )

    app._perform_project_edit(
        "Remove B",
        lambda: (
            setattr(app.project, "analyses", [analysis_a]),
            setattr(app.project, "active_analysis_id", analysis_a.id),
        ),
    )
    app.project.metadata[SPATIAL_METADATA_KEY]["rooms"][0]["x_m"] = 9.0

    restored_state, description = app._project_history.undo()
    assert description == "Remove B"
    app._restore_project_history_state(restored_state)

    assert [item.id for item in app.project.analyses] == ["analysis-a", "analysis-b"]
    assert app.project.active_analysis_id == "analysis-b"
    assert app.project.metadata[SPATIAL_METADATA_KEY]["rooms"][0]["x_m"] == 9.0

    replay_state, description = app._project_history.redo()
    assert description == "Remove B"
    app._restore_project_history_state(replay_state)

    assert [item.id for item in app.project.analyses] == ["analysis-a"]
    assert app.project.active_analysis_id == "analysis-a"
    assert app.project.metadata[SPATIAL_METADATA_KEY]["rooms"][0]["x_m"] == 9.0


def test_project_history_restore_invalidates_cached_engineering_results():
    analysis = AnalysisDocument(
        id="analysis-a",
        name="A",
        kind="room_verification",
        input={"value": 1},
    )
    app = _history_restore_app(
        ProjectDocument(
            name="History",
            analyses=[analysis],
            active_analysis_id=analysis.id,
        )
    )
    app._runs_by_analysis = {"analysis-a": object()}
    app.last_run = app._runs_by_analysis["analysis-a"]
    app.last_run_analysis_id = "analysis-a"

    app._perform_project_edit(
        "Edit input",
        lambda: setattr(analysis, "input", {"value": 2}),
    )
    state, _ = app._project_history.undo()
    app._restore_project_history_state(state)

    assert app.project.analysis_by_id("analysis-a").input == {"value": 1}
    assert app._runs_by_analysis == {}
    assert app.last_run is None
    assert app.last_run_analysis_id is None


class _Text:
    def __init__(self, value: str):
        self.value = value

    def get(self, *args):
        return self.value

    def delete(self, *args):
        self.value = ""

    def insert(self, index, value):
        self.value = value

    def edit_modified(self, *args):
        return False


def test_desktop_undo_redo_commits_pending_editor_change_and_replays_it():
    analysis = AnalysisDocument(
        id="analysis-a",
        name="A",
        kind="room_verification",
        input={"value": 1},
    )
    app = _history_restore_app(
        ProjectDocument(
            name="History",
            analyses=[analysis],
            active_analysis_id=analysis.id,
        )
    )
    app.root = object()
    app._running = False
    app.input_text = _Text(json.dumps({"value": 1}))

    def refresh(select_id=None):
        target = select_id or app.project.active_analysis_id
        app._editor_analysis_id = target
        if target is not None:
            app.input_text.value = json.dumps(app.project.analysis_by_id(target).input)

    app._refresh_analysis_list = refresh

    app.input_text.value = json.dumps({"value": 2})
    assert app.undo_project_edit() is True
    assert app.project.analysis_by_id("analysis-a").input == {"value": 1}
    assert json.loads(app.input_text.value) == {"value": 1}
    assert app._project_history.can_redo is True
    assert app.status_var.value == "Undo: Edit A input"

    assert app.redo_project_edit() is True
    assert app.project.analysis_by_id("analysis-a").input == {"value": 2}
    assert json.loads(app.input_text.value) == {"value": 2}
    assert app.status_var.value == "Redo: Edit A input"


def test_desktop_undo_refuses_to_discard_malformed_pending_editor_text(monkeypatch):
    analysis = AnalysisDocument(
        id="analysis-a",
        name="A",
        kind="room_verification",
        input={"value": 1},
    )
    app = _history_restore_app(
        ProjectDocument(
            name="History",
            analyses=[analysis],
            active_analysis_id=analysis.id,
        )
    )
    app.root = object()
    app._running = False
    app.input_text = _Text(json.dumps({"value": 1}))
    app._perform_project_edit(
        "Edit input",
        lambda: setattr(analysis, "input", {"value": 2}),
    )
    assert app._project_history.can_undo is True

    app.input_text.value = "{broken"
    errors = []
    monkeypatch.setattr(
        "cleanroomx.gui.messagebox.showerror",
        lambda title, message, **kwargs: errors.append((title, message)),
    )

    assert app.undo_project_edit() is False
    assert app.project.analysis_by_id("analysis-a").input == {"value": 2}
    assert app._project_history.can_undo is True
    assert errors
    assert errors[0][0] == "Cannot undo"


def test_project_history_rejects_invalid_configuration():
    for invalid in (0, -1, True, 1.5):
        with pytest.raises(ValueError, match="positive integer"):
            ProjectEditHistory(limit=invalid)
